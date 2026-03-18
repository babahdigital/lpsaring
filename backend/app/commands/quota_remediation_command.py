from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone as dt_timezone
from decimal import Decimal
from typing import Any, Optional

import click
from flask.cli import with_appcontext
from sqlalchemy import or_, select
from sqlalchemy.orm import selectinload

from app.extensions import db
from app.infrastructure.db.models import AdminActionLog, AdminActionType, Package, QuotaMutationLedger, Transaction, TransactionStatus, User
from app.services.quota_expiry_policy import calculate_quota_expiry_date
from app.services.quota_mutation_ledger_service import append_quota_mutation_event, lock_user_quota_row, snapshot_user_quota_state
from app.services.user_management.helpers import _send_whatsapp_notification
from app.utils.block_reasons import is_auto_debt_limit_reason
from app.utils.formatters import get_app_local_datetime, get_phone_number_variations


IMPORT_SOURCE = "quota.purchase_package.imported"
SPIKE_REFUND_SOURCE = "quota.hotspot_spike_refund"
NORMALIZE_EXPIRY_SOURCE = "quota.normalize_expiry"
NORMALIZE_UNLIMITED_EXPIRY_SOURCE = "quota.normalize_unlimited_expiry"
DEFAULT_MANUAL_DEBT_ADVANCE_DAYS = 30

EXPIRY_CANDIDATE_PRIORITY = {
    "quota.inject": 40,
    "quota.debt_advance": 30,
    "admin.debt_action": 20,
    "quota.purchase_package": 10,
}


@click.group(
    "quota-remediation",
    help=(
        "Tool remediation kuota: backfill riwayat pembelian lama, normalisasi expiry unlimited, "
        "dan audit/refund lonjakan sinkronisasi hotspot."
    ),
)
def quota_remediation_command() -> None:
    pass


def _safe_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None


def _safe_int(value: Any, default: int = 0) -> int:
    if value is None:
        return int(default)
    try:
        return int(value)
    except Exception:
        try:
            return int(float(value))
        except Exception:
            return int(default)


def _coerce_datetime(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value
    if value is None:
        return None

    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"

    try:
        parsed = datetime.fromisoformat(text)
    except Exception:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt_timezone.utc)
    return parsed


def _parse_optional_user_uuid(raw_user_id: Optional[str]) -> Optional[uuid.UUID]:
    if raw_user_id is None:
        return None

    text = str(raw_user_id).strip()
    if not text:
        return None

    try:
        return uuid.UUID(text)
    except (ValueError, TypeError) as exc:
        raise click.BadParameter(f"user-id tidak valid: {text}") from exc


def _parse_optional_ledger_ids(raw_values: tuple[str, ...]) -> list[uuid.UUID]:
    parsed: list[uuid.UUID] = []
    for raw in raw_values:
        text = str(raw or "").strip()
        if not text:
            continue
        try:
            parsed.append(uuid.UUID(text))
        except (ValueError, TypeError) as exc:
            raise click.BadParameter(f"ledger-id tidak valid: {text}") from exc
    return parsed


def _parse_optional_datetime(raw_value: Optional[str], option_name: str) -> Optional[datetime]:
    if raw_value is None:
        return None

    parsed = _coerce_datetime(raw_value)
    if parsed is None:
        raise click.BadParameter(
            f"{option_name} harus format ISO-8601, contoh 2026-03-15 atau 2026-03-15T09:30:00+00:00"
        )
    return parsed


def _resolve_transaction_event_time(transaction: Transaction) -> datetime:
    payment_time = _coerce_datetime(getattr(transaction, "payment_time", None))
    if payment_time is not None:
        return payment_time

    created_at = _coerce_datetime(getattr(transaction, "created_at", None))
    if created_at is not None:
        return created_at

    updated_at = _coerce_datetime(getattr(transaction, "updated_at", None))
    if updated_at is not None:
        return updated_at

    return datetime.now(dt_timezone.utc)


def _package_quota_mb(package: Optional[Package]) -> int:
    if package is None:
        return 0
    try:
        quota_gb = Decimal(str(getattr(package, "data_quota_gb", 0) or 0))
    except Exception:
        quota_gb = Decimal("0")
    return int(quota_gb * Decimal("1024"))


def _is_unlimited_package(package: Optional[Package]) -> bool:
    return _package_quota_mb(package) <= 0


def _format_datetime(value: Any) -> str:
    parsed = _coerce_datetime(value)
    if parsed is None:
        return "-"
    return parsed.astimezone(dt_timezone.utc).isoformat()


def _format_local_datetime(value: Any) -> str:
    parsed = _coerce_datetime(value)
    if parsed is None:
        return "-"
    return get_app_local_datetime(parsed).strftime("%d-%m-%Y %H:%M")


def _format_quota_display(value_mb: Any) -> str:
    parsed = _safe_float(value_mb)
    if parsed is None:
        return str(value_mb or "-")
    if parsed >= 1024:
        value_gb = parsed / 1024.0
        return f"{value_gb:.2f} GB"
    if float(parsed).is_integer():
        return f"{int(parsed)} MB"
    return f"{parsed:.2f} MB"


def _normalize_event_details(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _normalize_json_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if value is None:
        return {}

    text = str(value or "").strip()
    if not text:
        return {}

    try:
        parsed = json.loads(text)
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _extract_order_id_from_event_details(value: Any) -> str:
    details = _normalize_event_details(value)
    return str(details.get("order_id") or "").strip()


def _resolve_target_user_ids(*, phone: Optional[str], user_id: Optional[str], unlimited_only: bool = False) -> Optional[set[uuid.UUID]]:
    resolved_user_id = _parse_optional_user_uuid(user_id)

    stmt = select(User.id)
    if resolved_user_id is not None:
        stmt = stmt.where(User.id == resolved_user_id)

    if phone:
        variations = [value for value in get_phone_number_variations(phone) if value]
        if variations:
            stmt = stmt.where(User.phone_number.in_(variations))
        else:
            stmt = stmt.where(User.phone_number == str(phone).strip())

    if unlimited_only:
        stmt = stmt.where(User.is_unlimited_user.is_(True))

    if resolved_user_id is None and not phone and not unlimited_only:
        return None

    user_ids = {user_id for user_id in db.session.scalars(stmt).all() if user_id}
    return user_ids


def _load_existing_purchase_order_ids(user_ids: Optional[set[uuid.UUID]] = None) -> set[str]:
    stmt = select(QuotaMutationLedger.event_details).where(QuotaMutationLedger.source.startswith("quota.purchase_package"))
    if user_ids:
        stmt = stmt.where(QuotaMutationLedger.user_id.in_(list(user_ids)))

    order_ids: set[str] = set()
    for details in db.session.execute(stmt).scalars().all():
        order_id = _extract_order_id_from_event_details(details)
        if order_id:
            order_ids.add(order_id)
    return order_ids


def _load_existing_spike_refund_ids(user_ids: Optional[set[uuid.UUID]] = None) -> set[str]:
    stmt = select(QuotaMutationLedger.event_details).where(QuotaMutationLedger.source == SPIKE_REFUND_SOURCE)
    if user_ids:
        stmt = stmt.where(QuotaMutationLedger.user_id.in_(list(user_ids)))

    refunded_ids: set[str] = set()
    for details in db.session.execute(stmt).scalars().all():
        event_details = _normalize_event_details(details)
        refunded_ledger_id = str(event_details.get("refunded_ledger_id") or "").strip()
        if refunded_ledger_id:
            refunded_ids.add(refunded_ledger_id)
    return refunded_ids


def _build_purchase_import_details(transaction: Transaction) -> dict[str, Any]:
    package = transaction.package
    event_time = _resolve_transaction_event_time(transaction)
    return {
        "order_id": str(getattr(transaction, "midtrans_order_id", "") or "").strip(),
        "package_name": str(getattr(package, "name", "") or "").strip(),
        "package_quota_gb": float(getattr(package, "data_quota_gb", 0) or 0),
        "package_duration_days": int(getattr(package, "duration_days", 0) or 0),
        "is_unlimited_package": bool(_is_unlimited_package(package)),
        "imported_from_transaction": True,
        "imported_transaction_id": str(getattr(transaction, "id", "") or "").strip() or None,
        "payment_time": event_time.isoformat(),
    }


def _build_expiry_candidate(
    *,
    user_id: Optional[uuid.UUID],
    grant_at: Any,
    duration_days: Any,
    source_kind: str,
    grant_kind: str,
    is_unlimited: bool,
    grant_reference: Optional[str] = None,
    grant_label: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    normalized_grant_at = _coerce_datetime(grant_at)
    safe_duration_days = max(0, _safe_int(duration_days, 0))
    if user_id is None or normalized_grant_at is None or safe_duration_days <= 0:
        return None

    return {
        "user_id": user_id,
        "grant_at": normalized_grant_at,
        "duration_days": safe_duration_days,
        "source_kind": str(source_kind or "").strip(),
        "grant_kind": str(grant_kind or "").strip(),
        "is_unlimited": bool(is_unlimited),
        "grant_reference": str(grant_reference or "").strip() or None,
        "grant_label": str(grant_label or "").strip() or None,
        "priority": int(EXPIRY_CANDIDATE_PRIORITY.get(str(source_kind or "").strip(), 0)),
    }


def _register_latest_expiry_candidate(
    candidate_map: dict[tuple[uuid.UUID, bool], dict[str, Any]],
    candidate: Optional[dict[str, Any]],
) -> None:
    if not candidate:
        return

    key = (candidate["user_id"], bool(candidate["is_unlimited"]))
    existing = candidate_map.get(key)
    if existing is None:
        candidate_map[key] = candidate
        return

    candidate_at = candidate["grant_at"]
    existing_at = existing["grant_at"]
    if candidate_at > existing_at:
        candidate_map[key] = candidate
        return
    if candidate_at == existing_at and int(candidate.get("priority", 0) or 0) >= int(existing.get("priority", 0) or 0):
        candidate_map[key] = candidate


def _build_transaction_expiry_candidate(transaction: Transaction) -> Optional[dict[str, Any]]:
    package = getattr(transaction, "package", None)
    return _build_expiry_candidate(
        user_id=getattr(transaction, "user_id", None),
        grant_at=_resolve_transaction_event_time(transaction),
        duration_days=getattr(package, "duration_days", 0) if package is not None else 0,
        source_kind="quota.purchase_package",
        grant_kind="purchase",
        is_unlimited=_is_unlimited_package(package),
        grant_reference=str(getattr(transaction, "midtrans_order_id", "") or "").strip() or str(getattr(transaction, "id", "") or "").strip(),
        grant_label=str(getattr(package, "name", "") or "").strip() or "Paket pembelian",
    )


def _build_inject_expiry_candidate(entry: QuotaMutationLedger) -> Optional[dict[str, Any]]:
    event_details = _normalize_event_details(getattr(entry, "event_details", None))
    after_state = _normalize_event_details(getattr(entry, "after_state", None))
    requested_days = _safe_int(event_details.get("requested_inject_days"), 0)
    if requested_days <= 0:
        requested_days = _safe_int(event_details.get("added_days_for_unlimited"), 0)

    is_unlimited = bool(after_state.get("is_unlimited_user"))
    return _build_expiry_candidate(
        user_id=getattr(entry, "user_id", None),
        grant_at=getattr(entry, "created_at", None),
        duration_days=requested_days,
        source_kind="quota.inject",
        grant_kind="admin_inject",
        is_unlimited=is_unlimited,
        grant_reference=str(getattr(entry, "id", "") or "").strip(),
        grant_label="Inject masa aktif unlimited" if is_unlimited else "Inject kuota admin",
    )


def _build_debt_advance_ledger_candidate(entry: QuotaMutationLedger) -> Optional[dict[str, Any]]:
    event_details = _normalize_event_details(getattr(entry, "event_details", None))
    return _build_expiry_candidate(
        user_id=getattr(entry, "user_id", None),
        grant_at=getattr(entry, "created_at", None),
        duration_days=event_details.get("added_days"),
        source_kind="quota.debt_advance",
        grant_kind="manual_debt_advance",
        is_unlimited=False,
        grant_reference=str(event_details.get("grant_reference") or "").strip() or str(getattr(entry, "id", "") or "").strip(),
        grant_label=str(event_details.get("grant_label") or "").strip() or "Manual debt advance",
    )


def _build_admin_debt_action_candidate(
    action_log: AdminActionLog,
    packages_by_id: dict[uuid.UUID, Package],
) -> Optional[dict[str, Any]]:
    details = _normalize_json_dict(getattr(action_log, "details", None))
    if not details:
        return None

    package_id_text = str(details.get("debt_package_id") or "").strip()
    debt_add_mb = _safe_int(details.get("debt_add_mb"), 0)
    if not package_id_text and debt_add_mb <= 0:
        return None

    package: Optional[Package] = None
    if package_id_text:
        try:
            package = packages_by_id.get(uuid.UUID(package_id_text))
        except (ValueError, TypeError):
            package = None

    duration_days = _safe_int(getattr(package, "duration_days", 0) if package is not None else 0, 0)
    if duration_days <= 0:
        duration_days = DEFAULT_MANUAL_DEBT_ADVANCE_DAYS

    grant_label = str(getattr(package, "name", "") or "").strip() if package is not None else ""
    if not grant_label:
        if debt_add_mb > 0:
            grant_label = f"Manual debt advance {_format_quota_display(debt_add_mb)}"
        else:
            grant_label = "Manual debt advance"

    grant_reference = package_id_text or str(getattr(action_log, "id", "") or "").strip()
    return _build_expiry_candidate(
        user_id=getattr(action_log, "target_user_id", None),
        grant_at=getattr(action_log, "created_at", None),
        duration_days=duration_days,
        source_kind="admin.debt_action",
        grant_kind="manual_debt_advance",
        is_unlimited=False,
        grant_reference=grant_reference,
        grant_label=grant_label,
    )


def _load_latest_expiry_candidates(
    target_user_ids: Optional[set[uuid.UUID]] = None,
) -> dict[tuple[uuid.UUID, bool], dict[str, Any]]:
    candidate_map: dict[tuple[uuid.UUID, bool], dict[str, Any]] = {}

    tx_stmt = (
        select(Transaction)
        .join(Transaction.package)
        .options(selectinload(Transaction.package))
        .where(
            Transaction.status == TransactionStatus.SUCCESS,
            Transaction.user_id.is_not(None),
            Transaction.package_id.is_not(None),
        )
    )
    if target_user_ids:
        tx_stmt = tx_stmt.where(Transaction.user_id.in_(list(target_user_ids)))
    for transaction in db.session.scalars(tx_stmt).all():
        _register_latest_expiry_candidate(candidate_map, _build_transaction_expiry_candidate(transaction))

    inject_stmt = select(QuotaMutationLedger).where(QuotaMutationLedger.source == "quota.inject")
    if target_user_ids:
        inject_stmt = inject_stmt.where(QuotaMutationLedger.user_id.in_(list(target_user_ids)))
    for entry in db.session.scalars(inject_stmt).all():
        _register_latest_expiry_candidate(candidate_map, _build_inject_expiry_candidate(entry))

    debt_advance_stmt = select(QuotaMutationLedger).where(QuotaMutationLedger.source.startswith("quota.debt_advance:"))
    if target_user_ids:
        debt_advance_stmt = debt_advance_stmt.where(QuotaMutationLedger.user_id.in_(list(target_user_ids)))
    for entry in db.session.scalars(debt_advance_stmt).all():
        _register_latest_expiry_candidate(candidate_map, _build_debt_advance_ledger_candidate(entry))

    action_stmt = select(AdminActionLog).where(
        AdminActionLog.action_type == AdminActionType.UPDATE_USER_PROFILE,
        AdminActionLog.target_user_id.is_not(None),
        AdminActionLog.details.is_not(None),
        or_(
            AdminActionLog.details.like("%debt_package_id%"),
            AdminActionLog.details.like("%debt_add_mb%"),
        ),
    )
    if target_user_ids:
        action_stmt = action_stmt.where(AdminActionLog.target_user_id.in_(list(target_user_ids)))
    action_logs = db.session.scalars(action_stmt).all()

    package_ids: set[uuid.UUID] = set()
    for action_log in action_logs:
        details = _normalize_json_dict(getattr(action_log, "details", None))
        package_id_text = str(details.get("debt_package_id") or "").strip()
        if not package_id_text:
            continue
        try:
            package_ids.add(uuid.UUID(package_id_text))
        except (ValueError, TypeError):
            continue

    packages_by_id: dict[uuid.UUID, Package] = {}
    if package_ids:
        package_stmt = select(Package).where(Package.id.in_(list(package_ids)))
        packages_by_id = {package.id: package for package in db.session.scalars(package_stmt).all()}

    for action_log in action_logs:
        _register_latest_expiry_candidate(candidate_map, _build_admin_debt_action_candidate(action_log, packages_by_id))

    return candidate_map


def _dispatch_whatsapp_notifications(notifications: list[dict[str, Any]]) -> int:
    sent_count = 0
    for item in notifications:
        template_key = str(item.get("template_key") or "").strip()
        phone_number = str(item.get("phone_number") or "").strip()
        raw_context = item.get("context")
        context: dict[str, Any] = raw_context if isinstance(raw_context, dict) else {}
        if not template_key or not phone_number:
            continue
        if _send_whatsapp_notification(phone_number, template_key, context):
            sent_count += 1
    return sent_count


def _build_spike_candidate(
    entry: QuotaMutationLedger,
    *,
    min_delta_mb: float,
    min_device_delta_mb: float,
    max_device_count: int,
) -> Optional[dict[str, Any]]:
    event_details = _normalize_event_details(getattr(entry, "event_details", None))
    before_state = _normalize_event_details(getattr(entry, "before_state", None))
    after_state = _normalize_event_details(getattr(entry, "after_state", None))

    delta_mb = _safe_float(event_details.get("delta_mb"))
    if delta_mb is None:
        before_used = _safe_float(before_state.get("total_quota_used_mb"))
        after_used = _safe_float(after_state.get("total_quota_used_mb"))
        if before_used is not None and after_used is not None:
            delta_mb = max(0.0, after_used - before_used)

    if delta_mb is None or delta_mb < min_delta_mb:
        return None

    raw_device_deltas = event_details.get("device_deltas")
    device_deltas: list[dict[str, Any]] = []
    if isinstance(raw_device_deltas, list):
        for raw_item in raw_device_deltas:
            if not isinstance(raw_item, dict):
                continue
            item_delta_mb = max(0.0, float(_safe_float(raw_item.get("delta_mb")) or 0.0))
            device_deltas.append(
                {
                    "delta_mb": round(item_delta_mb, 2),
                    "label": str(raw_item.get("label") or "").strip() or None,
                    "mac_address": str(raw_item.get("mac_address") or "").strip().upper() or None,
                }
            )

    large_device_deltas = [item for item in device_deltas if float(item["delta_mb"]) >= min_device_delta_mb]
    dominant_device_mb = max((float(item["delta_mb"]) for item in device_deltas), default=0.0)

    if device_deltas and len(device_deltas) > max_device_count and not large_device_deltas:
        return None

    if large_device_deltas:
        refundable_mb = round(sum(float(item["delta_mb"]) for item in large_device_deltas), 2)
    else:
        refundable_mb = round(float(delta_mb), 2)

    if refundable_mb < min_delta_mb:
        if dominant_device_mb >= min_delta_mb:
            refundable_mb = round(dominant_device_mb, 2)
        elif not device_deltas:
            refundable_mb = round(float(delta_mb), 2)
        else:
            return None

    confidence = "low"
    if device_deltas:
        dominance_ratio = refundable_mb / float(delta_mb or 1.0)
        if len(device_deltas) <= max_device_count and dominance_ratio >= 0.8:
            confidence = "high"
        else:
            confidence = "medium"

    reason_parts: list[str] = []
    if device_deltas:
        reason_parts.append(f"device_detail={len(device_deltas)}")
        if large_device_deltas:
            reason_parts.append(f"device_ge_{int(min_device_delta_mb)}MB={len(large_device_deltas)}")
        if dominant_device_mb > 0:
            reason_parts.append(f"dominant_device_mb={round(dominant_device_mb, 2)}")
    else:
        reason_parts.append("tanpa_rincian_device")

    return {
        "entry": entry,
        "delta_mb": round(float(delta_mb), 2),
        "refundable_mb": round(refundable_mb, 2),
        "device_count": len(device_deltas),
        "large_device_count": len(large_device_deltas),
        "dominant_device_mb": round(dominant_device_mb, 2),
        "device_deltas": device_deltas,
        "confidence": confidence,
        "reason": "; ".join(reason_parts),
    }


@quota_remediation_command.command(
    "backfill-purchase-history",
    help="Impor transaksi sukses lama ke quota mutation ledger agar pembelian lama muncul di histori kuota.",
)
@click.option("--apply", is_flag=True, help="Simpan perubahan ke database. Default hanya preview.")
@click.option("--phone", default=None, help="Filter nomor telepon user tertentu.")
@click.option("--user-id", default=None, help="Filter UUID user tertentu.")
@click.option("--order-id", default=None, help="Filter satu order tertentu.")
@click.option("--limit", type=int, default=500, show_default=True, help="Batas maksimum transaksi yang diproses.")
@with_appcontext
def backfill_purchase_history(apply: bool, phone: Optional[str], user_id: Optional[str], order_id: Optional[str], limit: int):
    safe_limit = max(1, int(limit or 500))
    target_user_ids = _resolve_target_user_ids(phone=phone, user_id=user_id)
    if target_user_ids == set():
        click.echo(click.style("Tidak ada user yang cocok dengan filter.", fg="yellow"))
        return

    stmt = (
        select(Transaction)
        .options(selectinload(Transaction.user), selectinload(Transaction.package))
        .where(
            Transaction.status == TransactionStatus.SUCCESS,
            Transaction.user_id.is_not(None),
            Transaction.package_id.is_not(None),
        )
        .order_by(Transaction.created_at.asc())
        .limit(safe_limit)
    )
    if target_user_ids:
        stmt = stmt.where(Transaction.user_id.in_(list(target_user_ids)))
    if order_id:
        stmt = stmt.where(Transaction.midtrans_order_id == str(order_id).strip())

    transactions = db.session.scalars(stmt).all()
    if not transactions:
        click.echo(click.style("Tidak ada transaksi sukses yang cocok untuk dibackfill.", fg="yellow"))
        return

    relevant_user_ids = {
        transaction_user_id
        for transaction in transactions
        for transaction_user_id in [getattr(transaction, "user_id", None)]
        if transaction_user_id is not None
    }
    existing_order_ids = _load_existing_purchase_order_ids(relevant_user_ids)

    imported_count = 0
    skipped_existing = 0
    skipped_invalid = 0

    click.echo(click.style("=== Backfill Riwayat Pembelian Lama ===", bold=True))
    click.echo(f"Mode: {'APPLY' if apply else 'DRY-RUN'}")

    for transaction in transactions:
        user = transaction.user
        package = transaction.package
        normalized_order_id = str(getattr(transaction, "midtrans_order_id", "") or "").strip()
        if not user or not package or not normalized_order_id:
            skipped_invalid += 1
            continue

        if normalized_order_id in existing_order_ids:
            skipped_existing += 1
            continue

        event_time = _resolve_transaction_event_time(transaction)
        event_details = _build_purchase_import_details(transaction)
        click.echo(
            f"[{'IMPOR' if apply else 'PREVIEW'}] {user.full_name} ({user.phone_number}) "
            f"order={normalized_order_id} package={package.name} waktu={event_time.isoformat()}"
        )

        if apply:
            item = QuotaMutationLedger()
            item.user_id = user.id
            item.source = IMPORT_SOURCE
            item.idempotency_key = f"purchase_history_import:{normalized_order_id}"[:128]
            item.before_state = None
            item.after_state = None
            item.event_details = event_details
            item.created_at = event_time
            db.session.add(item)

        existing_order_ids.add(normalized_order_id)
        imported_count += 1

    click.echo(f"\nDiimpor : {imported_count}")
    click.echo(f"Sudah ada: {skipped_existing}")
    click.echo(f"Tidak valid: {skipped_invalid}")

    if apply and imported_count > 0:
        try:
            db.session.commit()
            click.echo(click.style("Commit berhasil.", fg="green", bold=True))
        except Exception as exc:
            db.session.rollback()
            raise click.ClickException(f"Commit backfill purchase history gagal: {exc}") from exc


def _run_normalize_expiry(
    *,
    apply: bool,
    phone: Optional[str],
    user_id: Optional[str],
    limit: int,
    unlimited_only: bool,
    notify_unlimited_whatsapp: bool,
) -> None:
    safe_limit = max(1, int(limit or 300))
    target_user_ids = _resolve_target_user_ids(phone=phone, user_id=user_id, unlimited_only=unlimited_only)
    if target_user_ids == set():
        click.echo(
            click.style(
                "Tidak ada user unlimited yang cocok dengan filter." if unlimited_only else "Tidak ada user yang cocok dengan filter.",
                fg="yellow",
            )
        )
        return

    candidate_map = _load_latest_expiry_candidates(target_user_ids)
    if not candidate_map:
        click.echo(click.style("Tidak ada grant kuota yang bisa dijadikan acuan normalisasi.", fg="yellow"))
        return

    candidate_user_ids = {candidate_key[0] for candidate_key in candidate_map.keys()}
    user_stmt = select(User).where(User.id.in_(list(candidate_user_ids))).order_by(User.created_at.asc()).limit(safe_limit)
    if target_user_ids:
        user_stmt = user_stmt.where(User.id.in_(list(target_user_ids)))
    if unlimited_only:
        user_stmt = user_stmt.where(User.is_unlimited_user.is_(True))

    users = db.session.scalars(user_stmt).all()
    if not users:
        click.echo(
            click.style(
                "Tidak ada user unlimited untuk dinormalisasi." if unlimited_only else "Tidak ada user untuk dinormalisasi.",
                fg="yellow",
            )
        )
        return

    normalized_count = 0
    skipped_missing_grant = 0
    skipped_already_normalized = 0
    pending_notifications: list[dict[str, Any]] = []

    click.echo(
        click.style(
            "=== Normalisasi Expiry User Unlimited ===" if unlimited_only else "=== Normalisasi Expiry User ===",
            bold=True,
        )
    )
    click.echo(f"Mode: {'APPLY' if apply else 'DRY-RUN'}")

    for user in users:
        candidate = candidate_map.get((user.id, bool(getattr(user, "is_unlimited_user", False))))
        if candidate is None:
            skipped_missing_grant += 1
            continue

        normalized_expiry = calculate_quota_expiry_date(
            current_expiry=None,
            now=candidate["grant_at"],
            days_to_add=int(candidate["duration_days"]),
            strategy="reset_from_now",
        )

        current_expiry = _coerce_datetime(getattr(user, "quota_expiry_date", None))
        if current_expiry is not None and abs((current_expiry - normalized_expiry).total_seconds()) < 60:
            skipped_already_normalized += 1
            continue

        grant_label = str(candidate.get("grant_label") or candidate.get("grant_kind") or "grant").strip()
        grant_reference = str(candidate.get("grant_reference") or "-").strip()
        click.echo(
            f"[{'NORMALIZE' if apply else 'PREVIEW'}] {user.full_name} ({user.phone_number}) "
            f"grant={grant_label} ref={grant_reference} "
            f"waktu={candidate['grant_at'].isoformat()} expiry_lama={_format_datetime(current_expiry)} "
            f"expiry_baru={normalized_expiry.isoformat()}"
        )

        if apply:
            lock_user_quota_row(user)
            before_state = snapshot_user_quota_state(user)
            previous_expiry = _coerce_datetime(getattr(user, "quota_expiry_date", None))
            user.quota_expiry_date = normalized_expiry
            source = NORMALIZE_UNLIMITED_EXPIRY_SOURCE if bool(getattr(user, "is_unlimited_user", False)) else NORMALIZE_EXPIRY_SOURCE
            append_quota_mutation_event(
                user=user,
                source=source,
                before_state=before_state,
                after_state=snapshot_user_quota_state(user),
                idempotency_key=(
                    f"normalize_expiry:{candidate['source_kind']}:{grant_reference}:{normalized_expiry.isoformat()}"
                )[:128],
                event_details={
                    "order_id": grant_reference if candidate["source_kind"] == "quota.purchase_package" else None,
                    "package_name": grant_label if candidate["source_kind"] == "quota.purchase_package" else None,
                    "grant_kind": str(candidate.get("grant_kind") or "").strip() or None,
                    "grant_source": str(candidate.get("source_kind") or "").strip() or None,
                    "grant_label": grant_label,
                    "grant_reference": grant_reference,
                    "duration_days": int(candidate["duration_days"]),
                    "purchase_at": candidate["grant_at"].isoformat() if candidate["source_kind"] == "quota.purchase_package" else None,
                    "grant_at": candidate["grant_at"].isoformat(),
                    "previous_expiry_at": previous_expiry.isoformat() if previous_expiry else None,
                    "normalized_expiry_at": normalized_expiry.isoformat(),
                },
            )
            db.session.add(user)
            db.session.flush()

            if notify_unlimited_whatsapp and bool(getattr(user, "is_unlimited_user", False)):
                pending_notifications.append(
                    {
                        "phone_number": str(getattr(user, "phone_number", "") or "").strip(),
                        "template_key": "user_unlimited_expiry_corrected",
                        "context": {
                            "full_name": str(getattr(user, "full_name", "") or "").strip() or "Pelanggan",
                            "grant_label": grant_label,
                            "grant_at": _format_local_datetime(candidate["grant_at"]),
                            "previous_expiry": _format_local_datetime(previous_expiry) if previous_expiry else "-",
                            "normalized_expiry": _format_local_datetime(normalized_expiry),
                        },
                    }
                )

        normalized_count += 1

    click.echo(f"\nDinormalisasi: {normalized_count}")
    click.echo(f"Tanpa grant acuan: {skipped_missing_grant}")
    click.echo(f"Sudah sesuai: {skipped_already_normalized}")

    if apply and normalized_count > 0:
        try:
            db.session.commit()
            sent_count = _dispatch_whatsapp_notifications(pending_notifications)
            click.echo(click.style("Commit berhasil.", fg="green", bold=True))
            if pending_notifications:
                click.echo(f"WhatsApp unlimited terkirim: {sent_count}/{len(pending_notifications)}")
        except Exception as exc:
            db.session.rollback()
            raise click.ClickException(
                f"Commit normalisasi expiry {'unlimited' if unlimited_only else 'user'} gagal: {exc}"
            ) from exc


@quota_remediation_command.command(
    "normalize-user-expiry",
    help=(
        "Selaraskan expiry semua user ke grant kuota terakhir agar pembelian, inject, dan debt advance "
        "tidak lagi mengakumulasi sisa masa aktif lama."
    ),
)
@click.option("--apply", is_flag=True, help="Simpan perubahan ke database. Default hanya preview.")
@click.option("--phone", default=None, help="Filter nomor telepon user tertentu.")
@click.option("--user-id", default=None, help="Filter UUID user tertentu.")
@click.option("--limit", type=int, default=1000, show_default=True, help="Batas maksimum user yang diproses.")
@click.option(
    "--notify-unlimited-whatsapp/--no-notify-unlimited-whatsapp",
    default=True,
    show_default=True,
    help="Kirim WhatsApp hanya untuk user unlimited yang expiry-nya dikoreksi.",
)
@with_appcontext
def normalize_user_expiry(
    apply: bool,
    phone: Optional[str],
    user_id: Optional[str],
    limit: int,
    notify_unlimited_whatsapp: bool,
):
    _run_normalize_expiry(
        apply=apply,
        phone=phone,
        user_id=user_id,
        limit=limit,
        unlimited_only=False,
        notify_unlimited_whatsapp=notify_unlimited_whatsapp,
    )


@quota_remediation_command.command(
    "normalize-unlimited-expiry",
    help=(
        "Selaraskan expiry user unlimited ke grant unlimited terakhir, "
        "bukan menumpuk sisa masa aktif lama."
    ),
)
@click.option("--apply", is_flag=True, help="Simpan perubahan ke database. Default hanya preview.")
@click.option("--phone", default=None, help="Filter nomor telepon user tertentu.")
@click.option("--user-id", default=None, help="Filter UUID user tertentu.")
@click.option("--limit", type=int, default=300, show_default=True, help="Batas maksimum user unlimited yang diproses.")
@click.option(
    "--notify-unlimited-whatsapp/--no-notify-unlimited-whatsapp",
    default=True,
    show_default=True,
    help="Kirim WhatsApp koreksi expiry unlimited setelah commit berhasil.",
)
@with_appcontext
def normalize_unlimited_expiry(
    apply: bool,
    phone: Optional[str],
    user_id: Optional[str],
    limit: int,
    notify_unlimited_whatsapp: bool,
):
    _run_normalize_expiry(
        apply=apply,
        phone=phone,
        user_id=user_id,
        limit=limit,
        unlimited_only=True,
        notify_unlimited_whatsapp=notify_unlimited_whatsapp,
    )


@quota_remediation_command.command(
    "audit-hotspot-spikes",
    help=(
        "Cari lonjakan hotspot.sync_usage yang mencurigakan dan, bila diminta, refund kembali kuota yang hilang. "
        "Default hanya preview."
    ),
)
@click.option("--apply", is_flag=True, help="Terapkan refund ke kandidat yang lolos filter.")
@click.option("--phone", default=None, help="Filter nomor telepon user tertentu.")
@click.option("--user-id", default=None, help="Filter UUID user tertentu.")
@click.option("--ledger-id", "ledger_ids", multiple=True, help="Filter satu atau lebih UUID ledger hotspot.sync_usage.")
@click.option(
    "--created-after",
    default=None,
    help="Filter event hotspot.sync_usage sesudah timestamp ini (ISO-8601).",
)
@click.option(
    "--created-before",
    default=None,
    help="Filter event hotspot.sync_usage sebelum timestamp ini (ISO-8601).",
)
@click.option("--min-delta-mb", type=float, default=4096.0, show_default=True, help="Batas minimal delta event.")
@click.option(
    "--min-device-delta-mb",
    type=float,
    default=2048.0,
    show_default=True,
    help="Batas minimal delta device agar dihitung sebagai kandidat refund.",
)
@click.option(
    "--max-device-count",
    type=int,
    default=2,
    show_default=True,
    help="Jumlah maksimal device detail agar kandidat dianggap cukup fokus.",
)
@click.option("--allow-low-confidence-apply", is_flag=True, help="Izinkan apply untuk kandidat confidence rendah.")
@click.option(
    "--notify-whatsapp/--no-notify-whatsapp",
    default=True,
    show_default=True,
    help="Kirim WhatsApp ke user yang kuotanya dikembalikan setelah commit berhasil.",
)
@click.option("--limit", type=int, default=200, show_default=True, help="Batas maksimum event yang diperiksa.")
@with_appcontext
def audit_hotspot_spikes(
    apply: bool,
    phone: Optional[str],
    user_id: Optional[str],
    ledger_ids: tuple[str, ...],
    created_after: Optional[str],
    created_before: Optional[str],
    min_delta_mb: float,
    min_device_delta_mb: float,
    max_device_count: int,
    allow_low_confidence_apply: bool,
    notify_whatsapp: bool,
    limit: int,
):
    safe_limit = max(1, int(limit or 200))
    safe_max_device_count = max(1, int(max_device_count or 2))
    parsed_ledger_ids = _parse_optional_ledger_ids(ledger_ids)
    parsed_created_after = _parse_optional_datetime(created_after, "created-after")
    parsed_created_before = _parse_optional_datetime(created_before, "created-before")
    target_user_ids = _resolve_target_user_ids(phone=phone, user_id=user_id)
    if target_user_ids == set():
        click.echo(click.style("Tidak ada user yang cocok dengan filter.", fg="yellow"))
        return

    stmt = (
        select(QuotaMutationLedger)
        .options(selectinload(QuotaMutationLedger.user))
        .where(QuotaMutationLedger.source == "hotspot.sync_usage")
        .order_by(QuotaMutationLedger.created_at.desc())
        .limit(safe_limit)
    )
    if target_user_ids:
        stmt = stmt.where(QuotaMutationLedger.user_id.in_(list(target_user_ids)))
    if parsed_ledger_ids:
        stmt = stmt.where(QuotaMutationLedger.id.in_(parsed_ledger_ids))
    if parsed_created_after is not None:
        stmt = stmt.where(QuotaMutationLedger.created_at >= parsed_created_after)
    if parsed_created_before is not None:
        stmt = stmt.where(QuotaMutationLedger.created_at <= parsed_created_before)

    rows = db.session.scalars(stmt).all()
    if not rows:
        click.echo(click.style("Tidak ada event hotspot.sync_usage yang cocok dengan filter.", fg="yellow"))
        return

    relevant_user_ids = {row.user_id for row in rows if getattr(row, "user_id", None)}
    refunded_ledger_ids = _load_existing_spike_refund_ids(relevant_user_ids)

    candidates: list[dict[str, Any]] = []
    for row in rows:
        if str(getattr(row, "id", "") or "") in refunded_ledger_ids:
            continue

        candidate = _build_spike_candidate(
            row,
            min_delta_mb=float(min_delta_mb or 0),
            min_device_delta_mb=float(min_device_delta_mb or 0),
            max_device_count=safe_max_device_count,
        )
        if candidate is not None:
            candidates.append(candidate)

    if not candidates:
        click.echo(click.style("Tidak ada kandidat lonjakan hotspot yang lolos heuristik saat ini.", fg="yellow"))
        return

    refunded_count = 0
    skipped_low_confidence = 0
    total_refunded_mb = 0.0
    pending_notifications: list[dict[str, Any]] = []

    click.echo(click.style("=== Audit Lonjakan Hotspot Sync Usage ===", bold=True))
    click.echo(f"Mode: {'APPLY' if apply else 'DRY-RUN'}")

    for candidate in candidates:
        entry = candidate["entry"]
        user = getattr(entry, "user", None)
        user_name = str(getattr(user, "full_name", "-") or "-")
        user_phone = str(getattr(user, "phone_number", "-") or "-")
        created_at = _format_datetime(getattr(entry, "created_at", None))
        ledger_id_text = str(getattr(entry, "id", "") or "")

        click.echo(
            f"[{'REFUND' if apply else 'KANDIDAT'}] ledger={ledger_id_text} "
            f"user={user_name} phone={user_phone} at={created_at} delta={candidate['delta_mb']} MB "
            f"refund_est={candidate['refundable_mb']} MB confidence={candidate['confidence']} reason={candidate['reason']}"
        )

        if not apply:
            continue

        if candidate["confidence"] == "low" and not allow_low_confidence_apply:
            skipped_low_confidence += 1
            click.echo(click.style("  -> SKIP apply karena confidence rendah. Gunakan --allow-low-confidence-apply bila yakin.", fg="yellow"))
            continue

        if user is None:
            click.echo(click.style("  -> SKIP apply karena user ledger tidak tersedia.", fg="yellow"))
            continue

        lock_user_quota_row(user)
        before_state = snapshot_user_quota_state(user)
        was_blocked = bool(getattr(user, "is_blocked", False))
        current_used_mb = float(getattr(user, "total_quota_used_mb", 0) or 0.0)
        requested_refund_mb = float(candidate["refundable_mb"] or 0.0)
        applied_refund_mb = round(min(current_used_mb, requested_refund_mb), 2)
        if applied_refund_mb <= 0:
            click.echo(click.style("  -> SKIP apply karena total_quota_used_mb user sudah 0.", fg="yellow"))
            continue

        user.total_quota_used_mb = round(max(0.0, current_used_mb - applied_refund_mb), 2)

        blocked_reason = str(getattr(user, "blocked_reason", "") or "")
        if bool(getattr(user, "is_blocked", False)) and is_auto_debt_limit_reason(blocked_reason):
            remaining_debt_mb = float(getattr(user, "quota_debt_total_mb", 0) or 0.0)
            if remaining_debt_mb <= 0.01:
                user.is_blocked = False
                user.blocked_reason = None
                user.blocked_at = None
                user.blocked_by_id = None

        original_event_created_at = _coerce_datetime(getattr(entry, "created_at", None))

        append_quota_mutation_event(
            user=user,
            source=SPIKE_REFUND_SOURCE,
            before_state=before_state,
            after_state=snapshot_user_quota_state(user),
            idempotency_key=f"hotspot_spike_refund:{ledger_id_text}"[:128],
            event_details={
                "refunded_ledger_id": ledger_id_text,
                "refunded_mb_requested": round(requested_refund_mb, 2),
                "refunded_mb_applied": round(applied_refund_mb, 2),
                "original_delta_mb": round(float(candidate["delta_mb"] or 0.0), 2),
                "original_event_created_at": original_event_created_at.isoformat()
                if original_event_created_at is not None
                else None,
                "confidence": candidate["confidence"],
                "detection_reason": candidate["reason"],
                "device_count": int(candidate["device_count"] or 0),
            },
        )
        db.session.add(user)
        db.session.flush()

        if notify_whatsapp:
            remaining_quota_mb = max(
                0.0,
                float(getattr(user, "total_quota_purchased_mb", 0) or 0.0)
                - float(getattr(user, "total_quota_used_mb", 0) or 0.0),
            )
            access_status_note = "Akses aktif kembali" if was_blocked and not bool(getattr(user, "is_blocked", False)) else "Status akses tidak berubah"
            pending_notifications.append(
                {
                    "phone_number": str(getattr(user, "phone_number", "") or "").strip(),
                    "template_key": "user_quota_refund_corrected",
                    "context": {
                        "full_name": str(getattr(user, "full_name", "") or "").strip() or "Pelanggan",
                        "refunded_quota": _format_quota_display(applied_refund_mb),
                        "remaining_quota": _format_quota_display(remaining_quota_mb),
                        "access_status_note": access_status_note,
                    },
                }
            )

        refunded_count += 1
        total_refunded_mb += applied_refund_mb

    click.echo(f"\nKandidat: {len(candidates)}")
    click.echo(f"Direfund: {refunded_count}")
    click.echo(f"Skip confidence rendah: {skipped_low_confidence}")
    click.echo(f"Total refund: {round(total_refunded_mb, 2)} MB")

    if apply and refunded_count > 0:
        try:
            db.session.commit()
            sent_count = _dispatch_whatsapp_notifications(pending_notifications)
            click.echo(click.style("Commit berhasil.", fg="green", bold=True))
            if pending_notifications:
                click.echo(f"WhatsApp refund terkirim: {sent_count}/{len(pending_notifications)}")
        except Exception as exc:
            db.session.rollback()
            raise click.ClickException(f"Commit refund lonjakan hotspot gagal: {exc}") from exc