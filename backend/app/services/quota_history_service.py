from __future__ import annotations

import json
from collections import Counter
from datetime import date, datetime, time, timedelta, timezone as dt_timezone
from typing import Any, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from flask import current_app, has_app_context
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.extensions import db
from app.infrastructure.db.models import QuotaMutationLedger, User
from app.utils.formatters import format_mb_to_gb, get_app_local_datetime, get_app_timezone_name, round_mb


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
        return f"{sign}{format_mb_to_gb(value)}"
    return f"{sign}{int(round(value))} MB"


def _format_event_datetime(value: Any) -> Optional[str]:
    if value is None:
        return None
    try:
        return get_app_local_datetime(value).strftime("%d-%m-%Y %H:%M")
    except Exception:
        return None


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
        return datetime.fromisoformat(text)
    except Exception:
        return None


def _format_event_detail_datetime(value: Any) -> Optional[str]:
    coerced = _coerce_datetime(value)
    if coerced is None:
        return None
    return _format_event_datetime(coerced)


def _get_quota_history_retention_days() -> int:
    default_retention_days = 90
    try:
        raw_value = current_app.config.get("QUOTA_MUTATION_LEDGER_RETENTION_DAYS", default_retention_days) if has_app_context() else default_retention_days
        retention_days = int(raw_value)
    except Exception:
        retention_days = default_retention_days
    return min(90, max(30, retention_days))


def _get_app_tzinfo() -> dt_timezone | ZoneInfo:
    try:
        return ZoneInfo(get_app_timezone_name())
    except ZoneInfoNotFoundError:
        return dt_timezone.utc


def _parse_local_date(value: Any, *, field_name: str) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return get_app_local_datetime(value).date()
    if isinstance(value, date):
        return value

    text = str(value or "").strip()
    if not text:
        return None
    if "T" in text:
        text = text.split("T", 1)[0]

    try:
        return date.fromisoformat(text)
    except Exception as exc:
        raise ValueError(f"{field_name} tidak valid. Gunakan format YYYY-MM-DD.") from exc


def _format_local_date_display(value: Optional[date]) -> Optional[str]:
    if value is None:
        return None
    return value.strftime("%d-%m-%Y")


def _build_range_label(start_date: date, end_date: date) -> str:
    today_local = get_app_local_datetime(datetime.now(dt_timezone.utc)).date()
    range_days = (end_date - start_date).days + 1

    if start_date == end_date == today_local:
        return "Hari ini"
    if end_date == today_local and range_days == 3:
        return "3 hari terakhir"
    if end_date == today_local and range_days == 7:
        return "7 hari terakhir"
    if end_date == today_local and range_days == 30:
        return "30 hari terakhir"
    if end_date == today_local and range_days == 90:
        return "90 hari terakhir"
    if start_date == end_date:
        return _format_local_date_display(start_date) or "Periode terpilih"

    start_text = _format_local_date_display(start_date) or "-"
    end_text = _format_local_date_display(end_date) or "-"
    return f"{start_text} s.d. {end_text}"


def _resolve_history_filters(
    *,
    start_date: Any = None,
    end_date: Any = None,
    search: Any = None,
) -> dict[str, Any]:
    retention_days = _get_quota_history_retention_days()
    today_local = get_app_local_datetime(datetime.now(dt_timezone.utc)).date()
    earliest_local = today_local - timedelta(days=retention_days - 1)

    parsed_start = _parse_local_date(start_date, field_name="Tanggal mulai")
    parsed_end = _parse_local_date(end_date, field_name="Tanggal akhir")

    effective_start = parsed_start or earliest_local
    effective_end = parsed_end or today_local

    effective_start = min(max(effective_start, earliest_local), today_local)
    effective_end = min(max(effective_end, earliest_local), today_local)

    if effective_start > effective_end:
        raise ValueError("Tanggal akhir tidak boleh sebelum tanggal mulai.")

    tzinfo = _get_app_tzinfo()
    start_at_local = datetime.combine(effective_start, time.min, tzinfo=tzinfo)
    end_at_local = datetime.combine(effective_end, time.max, tzinfo=tzinfo)

    safe_search = str(search or "").strip()

    return {
        "search": safe_search,
        "start_at_utc": start_at_local.astimezone(dt_timezone.utc),
        "end_at_utc": end_at_local.astimezone(dt_timezone.utc),
        "meta": {
            "search": safe_search,
            "start_date": effective_start.isoformat(),
            "end_date": effective_end.isoformat(),
            "start_date_display": _format_local_date_display(effective_start),
            "end_date_display": _format_local_date_display(effective_end),
            "label": _build_range_label(effective_start, effective_end),
            "retention_days": retention_days,
        },
    }


def _build_searchable_quota_history_text(item: dict[str, Any]) -> str:
    parts: list[str] = []

    for key in ("title", "description", "source", "actor_name", "created_at_display"):
        value = item.get(key)
        if value:
            parts.append(str(value))

    for highlight in item.get("highlights") or []:
        if highlight:
            parts.append(str(highlight))

    for key in ("deltas_display", "event_details", "device_deltas", "rebaseline_events"):
        value = item.get(key)
        if not value:
            continue
        try:
            parts.append(json.dumps(value, ensure_ascii=False, default=str))
        except Exception:
            parts.append(str(value))

    return " ".join(parts).casefold()


def _apply_search_filter(items: list[dict[str, Any]], search: str) -> list[dict[str, Any]]:
    normalized_search = str(search or "").strip().casefold()
    if not normalized_search:
        return items

    return [item for item in items if normalized_search in _build_searchable_quota_history_text(item)]


def _build_history_summary(items: list[dict[str, Any]], *, page_items: int) -> dict[str, Any]:
    category_counts = Counter(item.get("category") for item in items)
    total_net_purchased_mb = round_mb(
        sum(float(item.get("deltas", {}).get("purchased_mb") or 0.0) for item in items)
    )
    total_net_used_mb = round_mb(sum(float(item.get("deltas", {}).get("used_mb") or 0.0) for item in items))

    created_at_values = [
        created_at
        for created_at in (_coerce_datetime(item.get("created_at")) for item in items)
        if created_at is not None
    ]
    first_event_at = min(created_at_values) if created_at_values else None
    last_event_at = max(created_at_values) if created_at_values else None

    # Hitung saldo awal & akhir dari state
    balance_before_mb = None
    balance_after_mb = None

    if items:
        # Saldo awal = first item's before_state
        first_item = items[-1]  # Items sorted DESC, jadi last index adalah oldest
        before_state = _normalize_state(first_item.get("before_state"))
        purchased_before = _state_float(before_state, "total_quota_purchased_mb") or 0
        used_before = _state_float(before_state, "total_quota_used_mb") or 0
        balance_before_mb = round_mb(max(0, purchased_before - used_before))

        # Saldo akhir = last item's after_state (first index karena DESC)
        last_item = items[0]
        after_state = _normalize_state(last_item.get("after_state"))
        purchased_after = _state_float(after_state, "total_quota_purchased_mb") or 0
        used_after = _state_float(after_state, "total_quota_used_mb") or 0
        balance_after_mb = round_mb(max(0, purchased_after - used_after))

    return {
        "page_items": page_items,
        "usage_events": int(category_counts.get("usage", 0)),
        "purchase_events": int(category_counts.get("purchase", 0)),
        "debt_events": int(category_counts.get("debt", 0)),
        "policy_events": int(category_counts.get("policy", 0)),
        "total_net_purchased_mb": total_net_purchased_mb,
        "total_net_used_mb": total_net_used_mb,
        "balance_before_mb": balance_before_mb,
        "balance_after_mb": balance_after_mb,
        "first_event_at": first_event_at.isoformat() if first_event_at else None,
        "last_event_at": last_event_at.isoformat() if last_event_at else None,
        "first_event_at_display": _format_event_datetime(first_event_at),
        "last_event_at_display": _format_event_datetime(last_event_at),
    }


def _format_source_label(source: str) -> str:
    normalized = str(source or "").strip()
    if normalized == "hotspot.sync_usage":
        return "Pemakaian hotspot tersinkron"
    if normalized == "hotspot.sync_rebaseline":
        return "Baseline hotspot direfresh"
    if normalized.startswith("quota.purchase_package"):
        return "Paket berhasil diaktifkan"
    if normalized == "quota.inject":
        return "Inject kuota oleh admin"
    if normalized.startswith("quota.debt_advance:"):
        return "Kuota advance dari debt"
    if normalized == "quota.set_unlimited":
        return "Status unlimited diperbarui"
    if normalized == "quota.hotspot_spike_refund":
        return "Refund lonjakan kuota hotspot"
    if normalized == "quota.normalize_expiry":
        return "Masa aktif dinormalisasi"
    if normalized == "quota.normalize_unlimited_expiry":
        return "Masa aktif unlimited dinormalisasi"
    if normalized == "debt.add_manual":
        return "Tunggakan manual ditambahkan"
    if normalized.startswith("debt.consume_injected_auto_only:"):
        return "Tunggakan otomatis dikurangi"
    if normalized.startswith("debt.consume_injected:"):
        return "Tunggakan dikurangi"
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
    if normalized.startswith("quota.inject") or normalized in {"quota.adjust_direct", "quota.hotspot_spike_refund"}:
        return "adjustment"
    if normalized.startswith("quota.set_unlimited") or normalized in {"quota.normalize_expiry", "quota.normalize_unlimited_expiry"} or normalized.startswith("policy.block_transition:"):
        return "policy"
    if normalized.startswith("quota.debt_advance:"):
        return "debt"
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

    if normalized.startswith("quota.purchase_package"):
        package_name = str(event_details.get("package_name") or "").strip()
        package_quota_gb = event_details.get("package_quota_gb")
        package_duration_days = event_details.get("package_duration_days")
        order_id = str(event_details.get("order_id") or "").strip()
        if event_details.get("imported_from_transaction") is True:
            highlights.append("Riwayat pembelian lama diimpor dari transaksi sukses")
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

    if normalized == "quota.hotspot_spike_refund":
        refunded_mb = _as_float(event_details.get("refunded_mb_applied"))
        confidence = str(event_details.get("confidence") or "").strip()
        original_event_at = _format_event_detail_datetime(event_details.get("original_event_created_at"))
        detection_reason = str(event_details.get("detection_reason") or "").strip()
        if refunded_mb and refunded_mb > 0:
            highlights.append(f"Kuota dikembalikan: {_format_quota_text(refunded_mb, signed=True)}")
        if original_event_at:
            highlights.append(f"Event asal: {original_event_at}")
        if confidence:
            highlights.append(f"Confidence audit: {confidence}")
        if detection_reason:
            highlights.append(f"Deteksi: {detection_reason}")

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

    if normalized.startswith("quota.debt_advance:"):
        credit_mb = _as_float(event_details.get("credit_mb"))
        paid_auto_mb = _as_float(event_details.get("paid_auto_debt_mb"))
        net_added_mb = _as_float(event_details.get("net_added_mb"))
        added_days = event_details.get("added_days")
        grant_label = str(event_details.get("grant_label") or "").strip()
        normalized_expiry = _format_event_detail_datetime(event_details.get("normalized_expiry_at"))
        if grant_label:
            highlights.append(f"Grant: {grant_label}")
        if credit_mb and credit_mb > 0:
            highlights.append(f"Kuota advance: {_format_quota_text(credit_mb, signed=True)}")
        if paid_auto_mb and paid_auto_mb > 0:
            highlights.append(f"Auto debt dibayar: {_format_quota_text(paid_auto_mb)}")
        if net_added_mb and net_added_mb > 0:
            highlights.append(f"Kuota efektif: {_format_quota_text(net_added_mb, signed=True)}")
        if added_days not in (None, "", 0):
            highlights.append(f"Tambah masa aktif: {added_days} hari")
        if normalized_expiry:
            highlights.append(f"Expiry baru: {normalized_expiry}")

    if normalized in {"quota.normalize_expiry", "quota.normalize_unlimited_expiry"}:
        previous_expiry = _format_event_detail_datetime(event_details.get("previous_expiry_at"))
        normalized_expiry = _format_event_detail_datetime(event_details.get("normalized_expiry_at"))
        grant_at = _format_event_detail_datetime(event_details.get("purchase_at") or event_details.get("grant_at"))
        grant_reference = str(event_details.get("order_id") or event_details.get("grant_reference") or "").strip()
        duration_days = event_details.get("duration_days")
        grant_label = str(event_details.get("package_name") or event_details.get("grant_label") or "").strip()
        grant_kind = str(event_details.get("grant_kind") or "").strip()
        if grant_label:
            highlights.append(f"Grant acuan: {grant_label}")
        if grant_kind:
            highlights.append(f"Jenis grant: {grant_kind}")
        if grant_at:
            highlights.append(f"Tanggal grant acuan: {grant_at}")
        if previous_expiry:
            highlights.append(f"Expiry lama: {previous_expiry}")
        if normalized_expiry:
            highlights.append(f"Expiry baru: {normalized_expiry}")
        if duration_days not in (None, ""):
            highlights.append(f"Durasi grant: {duration_days} hari")
        if grant_reference:
            highlights.append(f"Referensi: {grant_reference}")

    if normalized == "debt.add_manual":
        amount_mb = _as_float(event_details.get("amount_mb"))
        note = str(event_details.get("note") or "").strip()
        if amount_mb and amount_mb > 0:
            highlights.append(f"Tunggakan baru: {_format_quota_text(amount_mb, signed=True)}")
        if note:
            highlights.append(f"Catatan: {note}")

    if normalized.startswith("debt.consume_injected_auto_only:"):
        paid_auto_mb = _as_float(event_details.get("paid_auto_mb"))
        remaining_injected_mb = _as_float(event_details.get("remaining_injected_mb"))
        if paid_auto_mb and paid_auto_mb > 0:
            highlights.append(f"Tunggakan otomatis dibayar: {_format_quota_text(paid_auto_mb)}")
        if remaining_injected_mb is not None:
            highlights.append(f"Sisa kuota advance: {_format_quota_text(remaining_injected_mb)}")

    if normalized.startswith("debt.consume_injected:"):
        paid_auto_mb = _as_float(event_details.get("paid_auto_mb"))
        paid_manual_mb = _as_float(event_details.get("paid_manual_mb"))
        remaining_injected_mb = _as_float(event_details.get("remaining_injected_mb"))
        if paid_auto_mb and paid_auto_mb > 0:
            highlights.append(f"Tunggakan otomatis dibayar: {_format_quota_text(paid_auto_mb)}")
        if paid_manual_mb and paid_manual_mb > 0:
            highlights.append(f"Tunggakan manual dibayar: {_format_quota_text(paid_manual_mb)}")
        if remaining_injected_mb is not None:
            highlights.append(f"Sisa kuota inject: {_format_quota_text(remaining_injected_mb)}")

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

    if normalized.startswith("quota.purchase_package"):
        if event_details.get("imported_from_transaction") is True:
            package_name = str(event_details.get("package_name") or "paket").strip()
            return f"Riwayat pembelian {package_name} diimpor dari transaksi sukses lama agar tampil di histori kuota."
        package_name = str(event_details.get("package_name") or "paket").strip()
        return f"Pembelian {package_name} berhasil diaktifkan dan kuota pengguna diperbarui."

    if normalized == "quota.inject":
        return "Admin menambahkan kuota dan/atau masa aktif ke akun pengguna."

    if normalized.startswith("quota.debt_advance:"):
        return "Admin mencatat tunggakan manual, memberi kuota advance, dan menetapkan masa aktif baru dari transaksi tersebut."

    if normalized == "quota.set_unlimited":
        return "Status unlimited pengguna diperbarui dan profil hotspot disinkronkan."

    if normalized == "debt.add_manual":
        return "Admin mencatat tunggakan manual dan memberi kuota advance sesuai kebutuhan."

    if normalized.startswith("debt.consume_injected_auto_only:"):
        source_suffix = normalized.split(":", 1)[1].strip() if ":" in normalized else ""
        if source_suffix == "admin_debt_advance_pkg":
            return "Kuota paket advance admin dipakai untuk mengurangi tunggakan otomatis sebelum sisa kuota diberikan ke pengguna."
        return "Kuota yang diinjeksikan dipakai untuk mengurangi tunggakan otomatis sebelum sisa kuota diberikan ke pengguna."

    if normalized.startswith("debt.consume_injected:"):
        return "Kuota yang diinjeksikan dipakai untuk melunasi tunggakan otomatis dan manual sebelum sisa kuota diberikan ke pengguna."

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

    if normalized == "quota.hotspot_spike_refund":
        return "Sistem mengembalikan kuota yang sebelumnya tersedot oleh lonjakan sinkronisasi hotspot yang mencurigakan."

    if normalized == "quota.normalize_expiry":
        return "Masa aktif akun pengguna diselaraskan ulang ke grant kuota terakhir agar tidak akumulatif."

    if normalized == "quota.normalize_unlimited_expiry":
        return "Masa aktif user unlimited diselaraskan ulang ke tanggal pembelian paket terakhir agar tidak akumulatif."

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
    start_date: Any = None,
    end_date: Any = None,
    search: Any = None,
) -> dict[str, Any]:
    safe_page = max(1, int(page or 1))
    safe_items_per_page = min(max(int(items_per_page or 50), 1), 200)
    resolved_filters = _resolve_history_filters(start_date=start_date, end_date=end_date, search=search)

    query = (
        select(QuotaMutationLedger)
        .where(
            QuotaMutationLedger.user_id == user.id,
            QuotaMutationLedger.created_at >= resolved_filters["start_at_utc"],
            QuotaMutationLedger.created_at <= resolved_filters["end_at_utc"],
        )
        .options(selectinload(QuotaMutationLedger.actor))
        .order_by(QuotaMutationLedger.created_at.desc())
    )

    rows = db.session.scalars(query).all()
    all_items = [serialize_quota_history_entry(item) for item in rows]
    filtered_items = _apply_search_filter(all_items, resolved_filters["search"])
    total_items = len(filtered_items)

    if include_all:
        items = filtered_items
    else:
        offset = (safe_page - 1) * safe_items_per_page
        items = filtered_items[offset:offset + safe_items_per_page]

    summary = _build_history_summary(filtered_items, page_items=len(items))

    return {
        "items": items,
        "total_items": total_items,
        "page": safe_page,
        "items_per_page": safe_items_per_page,
        "summary": summary,
        "filters": resolved_filters["meta"],
    }