"""Audit & cleanup state MikroTik vs DB.

Tujuan utama script ini:
- Menginventarisasi entry /ip/firewall/address-list dan /ip/hotspot/ip-binding yang mengandung token user (uid/user=08...).
- Mengidentifikasi "stale blocked" address-list (IP masih ada di list blocked) padahal user sudah tidak semestinya diblokir.
- Opsional: menghapus entry stale blocked tersebut (cleanup) agar tidak perlu bypass manual.

Catatan penting:
- Comment pada ip-binding sering dipakai sistem untuk mapping MAC -> user (auto-enroll device). Jangan dibersihkan sembarangan.
- Cleanup default hanya menyasar address-list blocked (berbasis IP) karena itu sumber paling umum stale block.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
import re
import os
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone as dt_timezone
from typing import Any, Optional

import sqlalchemy as sa

# Saat script dijalankan via path (contoh: `python scripts/audit_mikrotik_total.py`),
# Python akan menambahkan direktori script (`/app/scripts`) ke sys.path, bukan root project.
# Agar `import app` tetap berfungsi, pastikan root project (parent dari folder scripts) ada di sys.path.
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from app import create_app
from app.extensions import db
from app.infrastructure.db.models import ApprovalStatus, User, UserRole
from app.infrastructure.gateways.mikrotik_client import get_mikrotik_connection
from app.services import settings_service
from app.utils.formatters import format_to_local_phone, round_mb
from app.utils.quota_debt import compute_debt_mb


UID_RE = re.compile(r"(?:^|[|\s])uid=([^|\s]+)")
USER08_RE = re.compile(r"(?:^|[|\s])user=(0\d{6,})")


@dataclass
class _UserExpectation:
    user_id: uuid.UUID
    username_08: str
    role: str
    is_unlimited: bool
    is_blocked_db: bool
    debt_mb: float
    debt_limit_mb: int
    expected_blocked: bool


def _extract_uid(comment: Any) -> Optional[str]:
    if not comment:
        return None
    text = str(comment)
    match = UID_RE.search(text)
    if not match:
        return None
    value = (match.group(1) or "").strip()
    return value or None


def _extract_user08(comment: Any) -> Optional[str]:
    if not comment:
        return None
    text = str(comment)
    match = USER08_RE.search(text)
    if not match:
        return None
    value = (match.group(1) or "").strip()
    return value or None


def _safe_uuid(value: Optional[str]) -> Optional[uuid.UUID]:
    if not value:
        return None
    try:
        return uuid.UUID(str(value))
    except Exception:
        return None


def _resolve_blocked_list_name() -> str:
    value = settings_service.get_setting("MIKROTIK_ADDRESS_LIST_BLOCKED", "blocked")
    return str(value or "blocked").strip() or "blocked"


def _compute_expected_for_user(user: User, *, debt_limit_mb: int) -> _UserExpectation:
    username_08 = format_to_local_phone(user.phone_number) or ""
    debt_mb = compute_debt_mb(float(user.total_quota_purchased_mb or 0.0), float(user.total_quota_used_mb or 0.0))

    # Mirror hotspot_sync_service logic:
    # - debt hard block NOT applied to unlimited or role KOMANDAN
    # - otherwise apply when debt >= limit (if limit > 0)
    debt_block_applies = (
        (not bool(getattr(user, "is_unlimited_user", False)))
        and getattr(user, "role", None) != UserRole.KOMANDAN
        and debt_limit_mb > 0
        and debt_mb >= float(debt_limit_mb)
    )

    expected_blocked = bool(getattr(user, "is_blocked", False)) or debt_block_applies

    return _UserExpectation(
        user_id=user.id,
        username_08=username_08,
        role=getattr(user.role, "value", str(user.role)),
        is_unlimited=bool(getattr(user, "is_unlimited_user", False)),
        is_blocked_db=bool(getattr(user, "is_blocked", False)),
        debt_mb=float(debt_mb),
        debt_limit_mb=int(debt_limit_mb),
        expected_blocked=bool(expected_blocked),
    )


def _load_users() -> tuple[dict[str, _UserExpectation], dict[str, _UserExpectation]]:
    debt_limit_mb = settings_service.get_setting_as_int("QUOTA_DEBT_LIMIT_MB", 0)

    users = db.session.scalars(
        sa.select(User).where(
            User.is_active.is_(True),
            User.approval_status == ApprovalStatus.APPROVED,
            User.role.in_([UserRole.USER, UserRole.KOMANDAN]),
        )
    ).all()

    by_uid: dict[str, _UserExpectation] = {}
    by_user08: dict[str, _UserExpectation] = {}

    for user in users:
        expected = _compute_expected_for_user(user, debt_limit_mb=debt_limit_mb)
        by_uid[str(user.id)] = expected
        if expected.username_08:
            by_user08[expected.username_08] = expected

    return by_uid, by_user08


def _is_managed_comment(comment: Any) -> bool:
    if not comment:
        return False
    text = str(comment)
    return ("lpsaring" in text) or ("uid=" in text) or ("user=" in text)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Audit total MikroTik vs DB (blocked/ip-binding/address-list).")
    parser.add_argument("--apply", action="store_true", help="Jika diset, lakukan cleanup (default: dry-run saja).")
    parser.add_argument(
        "--cleanup-stale-blocked",
        action="store_true",
        help="Hapus address-list entry pada list blocked yang terdeteksi stale (user tidak expected_blocked).",
    )
    parser.add_argument(
        "--print-json",
        action="store_true",
        help="Cetak ringkasan audit dalam format JSON (lebih mudah disimpan/log).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Batas maksimum detail anomaly yang dicetak (default 50).",
    )
    args = parser.parse_args(argv)

    app = create_app()
    with app.app_context():
        by_uid, by_user08 = _load_users()
        blocked_list_name = _resolve_blocked_list_name()

        report: dict[str, Any] = {
            "time_utc": datetime.now(dt_timezone.utc).isoformat(),
            "blocked_list": blocked_list_name,
            "users_loaded": len(by_uid),
            "mikrotik": {"available": False},
            "counts": {},
            "anomalies": {"stale_blocked": []},
            "cleanup": {"removed_blocked_rows": 0, "dry_run": (not args.apply)},
        }

        with get_mikrotik_connection() as api:
            if not api:
                if args.print_json:
                    print(json.dumps(report, indent=2, ensure_ascii=False))
                else:
                    print("MikroTik tidak tersedia (koneksi gagal).")
                return 2

            report["mikrotik"]["available"] = True

            fw_resource = api.get_resource("/ip/firewall/address-list")
            ipb_resource = api.get_resource("/ip/hotspot/ip-binding")

            # Pull subsets for audit; RouterOS API filtering on comment isn't reliable across versions.
            all_blocked_rows = fw_resource.get(list=blocked_list_name) or []
            all_ipb_rows = ipb_resource.get() or []

            report["counts"]["address_list_blocked_total"] = len(all_blocked_rows)
            report["counts"]["ip_binding_total"] = len(all_ipb_rows)
            ipb_type_counts = Counter(
                (str(row.get("type") or "").strip().lower() or "(empty)") for row in all_ipb_rows
            )
            report["counts"]["ip_binding_type_counts"] = dict(ipb_type_counts)
            report["counts"]["ip_binding_regular_total"] = int(ipb_type_counts.get("regular", 0))
            report["counts"]["ip_binding_bypassed_total"] = int(ipb_type_counts.get("bypassed", 0))
            report["counts"]["ip_binding_blocked_total"] = int(ipb_type_counts.get("blocked", 0))

            stale_candidates: list[dict[str, Any]] = []
            for row in all_blocked_rows:
                comment = row.get("comment")
                if not _is_managed_comment(comment):
                    continue

                uid_raw = _extract_uid(comment)
                user08 = _extract_user08(comment)

                expected: Optional[_UserExpectation] = None
                uid_obj = _safe_uuid(uid_raw)
                if uid_obj and str(uid_obj) in by_uid:
                    expected = by_uid[str(uid_obj)]
                elif user08 and user08 in by_user08:
                    expected = by_user08[user08]

                if not expected:
                    continue
                if expected.expected_blocked:
                    continue

                stale_candidates.append(
                    {
                        "id": row.get("id") or row.get(".id"),
                        "address": row.get("address"),
                        "list": row.get("list"),
                        "comment": comment,
                        "user_id": str(expected.user_id),
                        "user": expected.username_08,
                        "role": expected.role,
                        "is_blocked_db": expected.is_blocked_db,
                        "debt_mb": float(round_mb(expected.debt_mb)),
                        "debt_limit_mb": expected.debt_limit_mb,
                    }
                )

            report["counts"]["stale_blocked_detected"] = len(stale_candidates)
            report["anomalies"]["stale_blocked"] = stale_candidates[: max(0, int(args.limit))]

            if args.cleanup_stale_blocked and args.apply:
                removed = 0
                for item in stale_candidates:
                    row_id = item.get("id")
                    if not row_id:
                        continue
                    try:
                        fw_resource.remove(id=row_id)
                        removed += 1
                    except Exception:
                        continue
                report["cleanup"]["removed_blocked_rows"] = removed

        if args.print_json:
            print(json.dumps(report, indent=2, ensure_ascii=False))
            return 0

        print("=== MikroTik Audit Summary ===")
        print(f"blocked_list={report['blocked_list']} mikrotik_available={report['mikrotik']['available']}")
        print(f"users_loaded={report['users_loaded']}")
        for key, value in report["counts"].items():
            print(f"{key}={value}")

        if stale_candidates:
            print("\n--- Stale blocked (needs cleanup) ---")
            for item in report["anomalies"]["stale_blocked"]:
                print(
                    "- ip={address} user={user} uid={user_id} role={role} debt={debt_mb}MB/{debt_limit_mb} comment={comment}".format(
                        **item
                    )
                )
            if len(stale_candidates) > len(report["anomalies"]["stale_blocked"]):
                print(f"... truncated, total={len(stale_candidates)}")
        else:
            print("\nTidak ada stale blocked terdeteksi.")

        if args.cleanup_stale_blocked and not args.apply:
            print("\nNOTE: cleanup diminta tapi masih dry-run. Tambahkan --apply untuk eksekusi remove.")

        return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))