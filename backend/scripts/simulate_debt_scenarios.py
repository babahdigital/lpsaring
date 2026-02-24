from __future__ import annotations

import os
import sys
import uuid
from dataclasses import dataclass


# Ensure backend root (../) is on sys.path so `import app` works in local and container runs.
_HERE = os.path.abspath(os.path.dirname(__file__))
_BACKEND_ROOT = os.path.abspath(os.path.join(_HERE, ".."))
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)


def _mb_to_gb(mb: float) -> float:
    try:
        return float(mb) / 1024.0
    except Exception:
        return 0.0


def _print_kv(title: str, **items: object) -> None:
    print(f"\n=== {title} ===")
    for key, value in items.items():
        print(f"- {key}: {value}")


@dataclass
class ScenarioResult:
    purchased_mb: float
    used_mb: float
    auto_offset_mb: float
    auto_debt_mb: float
    manual_debt_mb: int
    total_debt_mb: float
    remaining_mb: float


def _snapshot_user(user) -> ScenarioResult:
    purchased = float(getattr(user, "total_quota_purchased_mb", 0) or 0)
    used = float(getattr(user, "total_quota_used_mb", 0) or 0)
    offset = float(getattr(user, "auto_debt_offset_mb", 0) or 0)
    auto_debt = float(getattr(user, "quota_debt_auto_mb", 0) or 0)
    manual_debt = int(getattr(user, "manual_debt_mb", 0) or 0)
    total_debt = float(getattr(user, "quota_debt_total_mb", 0) or 0)
    remaining = max(0.0, purchased - used)
    return ScenarioResult(
        purchased_mb=purchased,
        used_mb=used,
        auto_offset_mb=offset,
        auto_debt_mb=auto_debt,
        manual_debt_mb=manual_debt,
        total_debt_mb=total_debt,
        remaining_mb=remaining,
    )


def main() -> int:
    os.environ.setdefault("FLASK_APP", "run.py")

    from app import create_app
    from app.extensions import db
    from app.infrastructure.db.models import (
        ApprovalStatus,
        Package,
        PackageProfile,
        Transaction,
        TransactionStatus,
        User,
        UserRole,
    )
    from app.services.transaction_service import apply_package_and_sync_to_mikrotik
    from app.services.user_management import user_debt as debt_service

    app = create_app()
    with app.app_context():
        print("[simulate] creating test data (will COMMIT to current DB)")

        # Create a dedicated profile+packages for simulation.
        profile_name = "sim-profile"
        profile = db.session.query(PackageProfile).filter(PackageProfile.profile_name == profile_name).first()
        if profile is None:
            profile = PackageProfile()
            profile.id = uuid.uuid4()
            profile.profile_name = profile_name
            profile.description = "simulation profile"
            db.session.add(profile)
            db.session.commit()

        def upsert_package(*, name: str, gb: float) -> Package:
            pkg = db.session.query(Package).filter(Package.name == name).first()
            if pkg is None:
                pkg = Package()
                pkg.id = uuid.uuid4()
                pkg.name = name
            pkg.price = 1000
            pkg.description = "simulation"
            pkg.is_active = True
            pkg.data_quota_gb = gb
            pkg.duration_days = 30
            pkg.profile_id = profile.id
            db.session.add(pkg)
            db.session.commit()
            return pkg

        pkg_10 = upsert_package(name="SIM-10GB", gb=10)
        pkg_25 = upsert_package(name="SIM-25GB", gb=25)

        # Create simulation user.
        phone = "+620000000000"
        user = db.session.query(User).filter(User.phone_number == phone).first()
        if user is None:
            user = User()
            user.id = uuid.uuid4()
            user.phone_number = phone
            user.full_name = "SIM USER"
            user.role = UserRole.USER
            user.approval_status = ApprovalStatus.APPROVED
            user.is_active = True
            user.is_unlimited_user = False
            user.total_quota_purchased_mb = 0
            user.total_quota_used_mb = 0
            user.manual_debt_mb = 0
            user.auto_debt_offset_mb = 0
            db.session.add(user)
            db.session.commit()

        # --- Scenario A: auto-debt 500MB + advance 10GB -> net 9.5GB ---
        user.total_quota_purchased_mb = 0
        user.total_quota_used_mb = 500
        user.manual_debt_mb = 0
        user.auto_debt_offset_mb = 0
        db.session.commit()

        before = _snapshot_user(user)
        _print_kv(
            "Scenario A - BEFORE (auto debt 500MB)",
            purchased_mb=before.purchased_mb,
            used_mb=before.used_mb,
            auto_debt_mb=before.auto_debt_mb,
            manual_debt_mb=before.manual_debt_mb,
            total_debt_mb=before.total_debt_mb,
            remaining_mb=before.remaining_mb,
        )

        ok, msg, _entry = debt_service.add_manual_debt(
            user=user,
            admin_actor=None,
            amount_mb=10 * 1024,
            note="SIM advance 10GB",
        )
        if not ok:
            raise RuntimeError(msg)

        paid_auto_mb, remaining_credit_mb = debt_service.consume_injected_mb_for_auto_debt_only(
            user=user,
            admin_actor=None,
            injected_mb=10 * 1024,
            source="sim_advance",
        )
        # Credit full remaining (NOTE: remaining_credit_mb is not reduced by auto-debt).
        user.total_quota_purchased_mb = int(user.total_quota_purchased_mb or 0) + int(remaining_credit_mb)
        db.session.commit()

        after = _snapshot_user(user)
        _print_kv(
            "Scenario A - AFTER (advance 10GB, auto settled)",
            paid_auto_mb=paid_auto_mb,
            credited_mb=remaining_credit_mb,
            purchased_mb=after.purchased_mb,
            used_mb=after.used_mb,
            auto_offset_mb=after.auto_offset_mb,
            auto_debt_mb=after.auto_debt_mb,
            manual_debt_mb=after.manual_debt_mb,
            total_debt_mb=after.total_debt_mb,
            remaining_mb=after.remaining_mb,
            remaining_gb=round(_mb_to_gb(after.remaining_mb), 3),
        )
        print("[expect] remaining should be ~9.5 GB")

        # --- Scenario B: auto debt 500MB + manual debt 10GB, remaining 0. Buy 10GB rejected, buy 25GB succeeds -> net 14.5GB ---
        # Make remaining 0 but keep auto debt 500MB.
        user.total_quota_purchased_mb = 10 * 1024
        user.total_quota_used_mb = (10 * 1024) + 500
        user.auto_debt_offset_mb = 0
        user.manual_debt_mb = 10 * 1024
        db.session.commit()

        b_before = _snapshot_user(user)
        _print_kv(
            "Scenario B - BEFORE (auto 500MB + manual 10GB, remaining 0)",
            purchased_mb=b_before.purchased_mb,
            used_mb=b_before.used_mb,
            auto_debt_mb=b_before.auto_debt_mb,
            manual_debt_mb=b_before.manual_debt_mb,
            total_debt_mb=b_before.total_debt_mb,
            remaining_mb=b_before.remaining_mb,
        )

        debt_total_mb = float(getattr(user, "quota_debt_total_mb", 0) or 0)
        required_mb = int(debt_total_mb + (0 if float(int(debt_total_mb)) == debt_total_mb else 1))
        pkg_10_mb = int(float(pkg_10.data_quota_gb) * 1024)
        pkg_25_mb = int(float(pkg_25.data_quota_gb) * 1024)

        print(f"[check] debt_total_mb={debt_total_mb} => required_mb={required_mb}")
        print(f"[check] pkg_10_mb={pkg_10_mb} => should_reject={pkg_10_mb <= required_mb}")
        print(f"[check] pkg_25_mb={pkg_25_mb} => should_accept={pkg_25_mb > required_mb}")

        tx = Transaction()
        tx.id = uuid.uuid4()
        tx.user_id = user.id
        tx.package_id = pkg_25.id
        tx.midtrans_order_id = f"SIM-{uuid.uuid4().hex[:10].upper()}"
        tx.amount = 1000
        tx.status = TransactionStatus.SUCCESS
        db.session.add(tx)
        db.session.commit()
        db.session.refresh(tx)

        ok_apply, msg_apply = apply_package_and_sync_to_mikrotik(tx, mikrotik_api=None)
        if not ok_apply:
            raise RuntimeError(msg_apply)

        db.session.commit()
        b_after = _snapshot_user(user)
        _print_kv(
            "Scenario B - AFTER (buy 25GB; debts deducted)",
            purchased_mb=b_after.purchased_mb,
            used_mb=b_after.used_mb,
            auto_offset_mb=b_after.auto_offset_mb,
            auto_debt_mb=b_after.auto_debt_mb,
            manual_debt_mb=b_after.manual_debt_mb,
            total_debt_mb=b_after.total_debt_mb,
            remaining_mb=b_after.remaining_mb,
            remaining_gb=round(_mb_to_gb(b_after.remaining_mb), 3),
        )
        print("[expect] remaining should be ~14.5 GB")

        print("\n[simulate] done")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
