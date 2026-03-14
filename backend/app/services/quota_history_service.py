from __future__ import annotations

from collections import Counter
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.extensions import db
from app.infrastructure.db.models import QuotaMutationLedger, User
from app.utils.formatters import get_app_local_datetime, round_mb


def _as_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None


def _normalize_state(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _state_float(state: dict[str, Any], key: str) -> Optional[float]:
    if key not in state:
        return None
    return _as_float(state.get(key))


def _round_optional(value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    return round_mb(float(value))


def _format_quota_text(value_mb: Optional[float], *, signed: bool = False) -> Optional[str]:
    if value_mb is None:
        return None

    try:
        value = float(value_mb)
    except Exception:
        return None

    sign = ""
    if value < 0:
        sign = "-"
        value = abs(value)
    elif signed and value > 0:
        sign = "+"

    if value < (1 / 1024):
        return f"{sign}0 KB"
    if value < 1:
        return f"{sign}{int(round(value * 1024))} KB"
    if value >= 1024:
        gb_value = round(value / 1024, 2)
        text = f"{gb_value:.2f}".rstrip("0").rstrip(".")
        return f"{sign}{text} GB"
    return f"{sign}{int(round(value))} MB"


def _format_event_datetime(value: Any) -> Optional[str]:
    if value is None:
        return None
    try:
        return get_app_local_datetime(value).strftime("%d-%m-%Y %H:%M")
    except Exception:
        return None


def _format_source_label(source: str) -> str:
    normalized = str(source or "").strip()
    if normalized == "hotspot.sync_usage":
        return "Pemakaian hotspot tersinkron"
    if normalized == "hotspot.sync_rebaseline":
        return "Baseline hotspot direfresh"
    if normalized == "quota.purchase_package":
        return "Paket berhasil diaktifkan"
    if normalized == "quota.inject":
        return "Inject kuota oleh admin"
    if normalized == "quota.set_unlimited":
        return "Status unlimited diperbarui"
    if normalized == "debt.add_manual":
        return "Tunggakan manual ditambahkan"
    if normalized.startswith("debt.apply_manual_payment:"):
        return "Pembayaran tunggakan manual"
    if normalized == "debt.settle_auto_to_zero":
        return "Tunggakan otomatis dibersihkan"
    if normalized == "transactions.debt_settlement_success":
        return "Pelunasan tunggakan berhasil"
    if normalized.startswith("policy.block_transition:"):
        return "Status blokir diperbarui"
    if normalized == "quota.adjust_direct":
        return "Koreksi kuota langsung"
    if normalized == "quota.reset_unlimited_counters":
        return "Counter unlimited direset"

    pretty = normalized.replace(".", " ").replace(":", " ").replace("_", " ").strip()
    return pretty[:1].upper() + pretty[1:] if pretty else "Mutasi kuota"


def _format_category(source: str) -> str:
    normalized = str(source or "").strip()
    if normalized == "hotspot.sync_usage":
        return "usage"
    if normalized == "hotspot.sync_rebaseline":
        return "sync"
    if normalized.startswith("quota.purchase_package"):
        return "purchase"
    if normalized.startswith("quota.inject") or normalized == "quota.adjust_direct":
        return "adjustment"
    if normalized.startswith("quota.set_unlimited") or normalized.startswith("policy.block_transition:"):
        return "policy"
    if normalized.startswith("debt.") or "debt_settlement" in normalized or normalized.startswith("admin_settle"):
        return "debt"
    return "system"


def _humanize_rebaseline_reason(reason: str) -> str:
    mapping = {
        "host_row_changed": "baris host berganti",
        "uptime_regressed": "uptime mundur",
        "counter_regressed": "counter mundur",
    }
    parts = [mapping.get(part.strip(), part.strip()) for part in str(reason or "").split("+") if part.strip()]
    return ", ".join(parts) or "baseline direset"


def _normalize_device_deltas(event_details: dict[str, Any]) -> list[dict[str, Any]]:
    raw_items = event_details.get("device_deltas")
    if not isinstance(raw_items, list):
        return []

    items: list[dict[str, Any]] = []
    for raw in raw_items:
        if not isinstance(raw, dict):
            continue

        delta_mb = _round_optional(_as_float(raw.get("delta_mb"))) or 0.0
        items.append(
            {
                "mac_address": str(raw.get("mac_address") or "").strip() or None,
                "ip_address": str(raw.get("ip_address") or "").strip() or None,
                "label": str(raw.get("label") or "").strip() or None,
                "delta_mb": delta_mb,
                "delta_display": _format_quota_text(delta_mb, signed=True),
                "host_id": str(raw.get("host_id") or "").strip() or None,
                "uptime_seconds": raw.get("uptime_seconds"),
                "source_address": str(raw.get("source_address") or "").strip() or None,
                "to_address": str(raw.get("to_address") or "").strip() or None,
            }
        )

    return items


def _normalize_rebaseline_events(event_details: dict[str, Any]) -> list[dict[str, Any]]:
    raw_items = event_details.get("rebaseline_events")
    if not isinstance(raw_items, list):
        return []

    items: list[dict[str, Any]] = []
    for raw in raw_items:
        if not isinstance(raw, dict):
            continue

        reason = str(raw.get("reason") or "").strip()
        items.append(
            {
                "mac_address": str(raw.get("mac_address") or "").strip() or None,
                "ip_address": str(raw.get("ip_address") or "").strip() or None,
                "label": str(raw.get("label") or "").strip() or None,
                "reason": reason or None,
                "reason_label": _humanize_rebaseline_reason(reason),
                "host_id": str(raw.get("host_id") or "").strip() or None,
                "previous_host_id": str(raw.get("previous_host_id") or "").strip() or None,
            }
        )

    return items


def _build_highlights(
    *,
    source: str,
    event_details: dict[str, Any],
    purchased_delta_mb: Optional[float],
    used_delta_mb: Optional[float],
    total_debt_delta_mb: Optional[float],
    remaining_after_mb: Optional[float],
    device_deltas: list[dict[str, Any]],
    rebaseline_events: list[dict[str, Any]],
) -> list[str]:
    highlights: list[str] = []
    normalized = str(source or "").strip()

    if normalized == "quota.purchase_package":
        package_name = str(event_details.get("package_name") or "").strip()
        package_quota_gb = event_details.get("package_quota_gb")
        package_duration_days = event_details.get("package_duration_days")
        order_id = str(event_details.get("order_id") or "").strip()
        if package_name:
            highlights.append(f"Paket: {package_name}")
        if package_quota_gb not in (None, "") or package_duration_days not in (None, ""):
            parts = []
            if package_quota_gb not in (None, ""):
                parts.append(f"Kuota {package_quota_gb} GB")
            if package_duration_days not in (None, ""):
                parts.append(f"Masa aktif {package_duration_days} hari")
            if parts:
                highlights.append(" • ".join(parts))
        if order_id:
            highlights.append(f"Order ID: {order_id}")

    if normalized == "quota.inject":
        requested_inject_mb = _as_float(event_details.get("requested_inject_mb"))
        requested_inject_days = event_details.get("requested_inject_days")
        net_added_mb = _as_float(event_details.get("net_added_mb"))
        if requested_inject_mb and requested_inject_mb > 0:
            highlights.append(f"Inject diminta: {_format_quota_text(requested_inject_mb)}")
        if net_added_mb and net_added_mb > 0:
            highlights.append(f"Kuota efektif: {_format_quota_text(net_added_mb, signed=True)}")
        if requested_inject_days not in (None, "", 0):
            highlights.append(f"Tambah masa aktif: {requested_inject_days} hari")

    if normalized == "debt.add_manual":
        amount_mb = _as_float(event_details.get("amount_mb"))
        note = str(event_details.get("note") or "").strip()
        if amount_mb and amount_mb > 0:
            highlights.append(f"Tunggakan baru: {_format_quota_text(amount_mb, signed=True)}")
        if note:
            highlights.append(f"Catatan: {note}")

    if normalized.startswith("debt.apply_manual_payment:") or normalized == "transactions.debt_settlement_success":
        paid_auto_mb = _as_float(event_details.get("paid_auto_mb"))
        paid_manual_mb = _as_float(event_details.get("paid_manual_mb"))
        order_id = str(event_details.get("order_id") or "").strip()
        if paid_auto_mb and paid_auto_mb > 0:
            highlights.append(f"Auto debt dibayar: {_format_quota_text(paid_auto_mb)}")
        if paid_manual_mb and paid_manual_mb > 0:
            highlights.append(f"Manual debt dibayar: {_format_quota_text(paid_manual_mb)}")
        if order_id:
            highlights.append(f"Order ID: {order_id}")
        if event_details.get("unblocked") is True:
            highlights.append("Akun dibuka kembali otomatis")

    if normalized == "debt.settle_auto_to_zero":
        paid_auto_mb = _as_float(event_details.get("paid_auto_mb"))
        reason = str(event_details.get("reason") or "").strip()
        if paid_auto_mb and paid_auto_mb > 0:
            highlights.append(f"Auto debt dibersihkan: {_format_quota_text(paid_auto_mb)}")
        if reason:
            highlights.append(f"Alasan: {reason}")

    if normalized == "quota.adjust_direct":
        reason = str(event_details.get("reason") or "").strip()
        if reason:
            highlights.append(f"Alasan: {reason}")
        if event_details.get("set_purchased_mb") not in (None, ""):
            highlights.append(f"Purchased diset: {_format_quota_text(_as_float(event_details.get('set_purchased_mb')))}")
        if event_details.get("set_used_mb") not in (None, ""):
            highlights.append(f"Used diset: {_format_quota_text(_as_float(event_details.get('set_used_mb')))}")

    if normalized == "hotspot.sync_usage":
        if device_deltas:
            highlights.append(f"Perangkat tersinkron: {len(device_deltas)}")
            for item in device_deltas[:3]:
                label = item.get("label") or item.get("ip_address") or item.get("mac_address") or "Perangkat"
                delta_display = item.get("delta_display") or _format_quota_text(item.get("delta_mb"), signed=True)
                highlights.append(f"{label}: {delta_display}")

    if normalized == "hotspot.sync_rebaseline" and rebaseline_events:
        highlights.append(f"Perangkat direfresh: {len(rebaseline_events)}")
        for item in rebaseline_events[:3]:
            label = item.get("label") or item.get("ip_address") or item.get("mac_address") or "Perangkat"
            highlights.append(f"{label}: {item.get('reason_label')}")

    if purchased_delta_mb and abs(purchased_delta_mb) >= 0.01:
        highlights.append(f"Perubahan kuota beli: {_format_quota_text(purchased_delta_mb, signed=True)}")
    if used_delta_mb and abs(used_delta_mb) >= 0.01:
        highlights.append(f"Perubahan kuota pakai: {_format_quota_text(used_delta_mb, signed=True)}")
    if total_debt_delta_mb and abs(total_debt_delta_mb) >= 0.01:
        highlights.append(f"Perubahan total tunggakan: {_format_quota_text(total_debt_delta_mb, signed=True)}")
    if remaining_after_mb is not None:
        highlights.append(f"Sisa kuota sesudah event: {_format_quota_text(remaining_after_mb)}")

    deduped: list[str] = []
    for item in highlights:
        text = str(item or "").strip()
        if not text or text in deduped:
            continue
        deduped.append(text)
    return deduped


def _build_description(
    *,
    source: str,
    event_details: dict[str, Any],
    purchased_delta_mb: Optional[float],
    used_delta_mb: Optional[float],
    device_deltas: list[dict[str, Any]],
    rebaseline_events: list[dict[str, Any]],
) -> str:
    normalized = str(source or "").strip()

    if normalized == "hotspot.sync_usage":
        usage_text = _format_quota_text(_as_float(event_details.get("delta_mb")) or used_delta_mb)
        if device_deltas:
            return f"Pemakaian baru {usage_text or '-'} tersinkron dari {len(device_deltas)} perangkat."
        return f"Pemakaian baru {usage_text or '-'} tersinkron dari hotspot."

    if normalized == "hotspot.sync_rebaseline":
        return (
            f"Counter hotspot direfresh pada {len(rebaseline_events)} perangkat agar perubahan sesi/counter ambigu tidak ikut ditagih."
            if rebaseline_events
            else "Counter hotspot direfresh agar baseline kembali akurat."
        )

    if normalized == "quota.purchase_package":
        package_name = str(event_details.get("package_name") or "paket").strip()
        return f"Pembelian {package_name} berhasil diaktifkan dan kuota pengguna diperbarui."

    if normalized == "quota.inject":
        return "Admin menambahkan kuota dan/atau masa aktif ke akun pengguna."

    if normalized == "quota.set_unlimited":
        return "Status unlimited pengguna diperbarui dan profil hotspot disinkronkan."

    if normalized == "debt.add_manual":
        return "Admin mencatat tunggakan manual dan memberi kuota advance sesuai kebutuhan."

    if normalized.startswith("debt.apply_manual_payment:"):
        return "Pembayaran tunggakan manual tercatat ke item debt yang terbuka."

    if normalized == "debt.settle_auto_to_zero":
        return "Tunggakan otomatis dibersihkan agar saldo quota kembali sinkron."

    if normalized == "transactions.debt_settlement_success":
        return "Pembayaran berhasil dan tunggakan pengguna diperbarui otomatis."

    if normalized.startswith("policy.block_transition:"):
        return "Status blokir akun berubah sesuai kebijakan sistem atau tindakan admin."

    if normalized == "quota.adjust_direct":
        return "Super admin melakukan koreksi langsung pada saldo kuota pengguna."

    if normalized == "quota.reset_unlimited_counters":
        return "Counter pengguna unlimited direset agar baseline penggunaan kembali bersih."

    return _format_source_label(normalized)


def serialize_quota_history_entry(entry: QuotaMutationLedger) -> dict[str, Any]:
    source = str(getattr(entry, "source", "") or "").strip()
    created_at = getattr(entry, "created_at", None)
    before_state = _normalize_state(getattr(entry, "before_state", None))
    after_state = _normalize_state(getattr(entry, "after_state", None))
    event_details = _normalize_state(getattr(entry, "event_details", None))

    purchased_before = _state_float(before_state, "total_quota_purchased_mb")
    purchased_after = _state_float(after_state, "total_quota_purchased_mb")
    used_before = _state_float(before_state, "total_quota_used_mb")
    used_after = _state_float(after_state, "total_quota_used_mb")
    debt_before = _state_float(before_state, "quota_debt_total_mb")
    debt_after = _state_float(after_state, "quota_debt_total_mb")

    purchased_delta_mb = None
    if purchased_before is not None and purchased_after is not None:
        purchased_delta_mb = _round_optional(purchased_after - purchased_before)

    used_delta_mb = None
    if used_before is not None and used_after is not None:
        used_delta_mb = _round_optional(used_after - used_before)

    total_debt_delta_mb = None
    if debt_before is not None and debt_after is not None:
        total_debt_delta_mb = _round_optional(debt_after - debt_before)

    remaining_before_mb = None
    if purchased_before is not None and used_before is not None:
        remaining_before_mb = _round_optional(max(0.0, purchased_before - used_before))

    remaining_after_mb = None
    if purchased_after is not None and used_after is not None:
        remaining_after_mb = _round_optional(max(0.0, purchased_after - used_after))

    device_deltas = _normalize_device_deltas(event_details)
    rebaseline_events = _normalize_rebaseline_events(event_details)

    actor = getattr(entry, "actor", None)
    actor_name = str(getattr(actor, "full_name", "") or "").strip() or None

    return {
        "id": str(getattr(entry, "id", "") or ""),
        "source": source,
        "category": _format_category(source),
        "title": _format_source_label(source),
        "description": _build_description(
            source=source,
            event_details=event_details,
            purchased_delta_mb=purchased_delta_mb,
            used_delta_mb=used_delta_mb,
            device_deltas=device_deltas,
            rebaseline_events=rebaseline_events,
        ),
        "created_at": created_at.isoformat() if created_at else None,
        "created_at_display": _format_event_datetime(created_at),
        "actor_name": actor_name,
        "deltas": {
            "purchased_mb": purchased_delta_mb,
            "used_mb": used_delta_mb,
            "debt_total_mb": total_debt_delta_mb,
            "remaining_before_mb": remaining_before_mb,
            "remaining_after_mb": remaining_after_mb,
        },
        "deltas_display": {
            "purchased": _format_quota_text(purchased_delta_mb, signed=True),
            "used": _format_quota_text(used_delta_mb, signed=True),
            "debt_total": _format_quota_text(total_debt_delta_mb, signed=True),
            "remaining_before": _format_quota_text(remaining_before_mb),
            "remaining_after": _format_quota_text(remaining_after_mb),
        },
        "highlights": _build_highlights(
            source=source,
            event_details=event_details,
            purchased_delta_mb=purchased_delta_mb,
            used_delta_mb=used_delta_mb,
            total_debt_delta_mb=total_debt_delta_mb,
            remaining_after_mb=remaining_after_mb,
            device_deltas=device_deltas,
            rebaseline_events=rebaseline_events,
        ),
        "device_deltas": device_deltas,
        "rebaseline_events": rebaseline_events,
        "event_details": event_details,
    }


def get_user_quota_history_payload(
    *,
    user: User,
    page: int = 1,
    items_per_page: int = 50,
    include_all: bool = False,
) -> dict[str, Any]:
    safe_page = max(1, int(page or 1))
    safe_items_per_page = min(max(int(items_per_page or 50), 1), 200)

    total_items = int(
        db.session.scalar(select(func.count()).select_from(QuotaMutationLedger).where(QuotaMutationLedger.user_id == user.id))
        or 0
    )

    range_row = db.session.execute(
        select(func.min(QuotaMutationLedger.created_at), func.max(QuotaMutationLedger.created_at)).where(
            QuotaMutationLedger.user_id == user.id
        )
    ).one()

    query = (
        select(QuotaMutationLedger)
        .where(QuotaMutationLedger.user_id == user.id)
        .options(selectinload(QuotaMutationLedger.actor))
        .order_by(QuotaMutationLedger.created_at.desc())
    )
    if not include_all:
        query = query.limit(safe_items_per_page).offset((safe_page - 1) * safe_items_per_page)

    rows = db.session.scalars(query).all()
    items = [serialize_quota_history_entry(item) for item in rows]

    category_counts = Counter(item.get("category") for item in items)
    total_net_purchased_mb = round_mb(
        sum(float(item.get("deltas", {}).get("purchased_mb") or 0.0) for item in items)
    )
    total_net_used_mb = round_mb(sum(float(item.get("deltas", {}).get("used_mb") or 0.0) for item in items))

    return {
        "items": items,
        "total_items": total_items,
        "page": safe_page,
        "items_per_page": safe_items_per_page,
        "summary": {
            "page_items": len(items),
            "usage_events": int(category_counts.get("usage", 0)),
            "purchase_events": int(category_counts.get("purchase", 0)),
            "debt_events": int(category_counts.get("debt", 0)),
            "policy_events": int(category_counts.get("policy", 0)),
            "total_net_purchased_mb": total_net_purchased_mb,
            "total_net_used_mb": total_net_used_mb,
            "first_event_at": range_row[0].isoformat() if range_row[0] else None,
            "last_event_at": range_row[1].isoformat() if range_row[1] else None,
            "first_event_at_display": _format_event_datetime(range_row[0]),
            "last_event_at_display": _format_event_datetime(range_row[1]),
        },
    }