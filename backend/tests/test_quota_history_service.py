from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import app.services.quota_history_service as svc


class _ScalarResultStub:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return list(self._rows)


class _HistorySessionStub:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self, query):
        filtered_rows = list(self._rows)
        for criterion in getattr(query, "_where_criteria", ()):  # pragma: no branch - tiny helper
            filtered_rows = [row for row in filtered_rows if _matches_where_clause(row, criterion)]

        filtered_rows.sort(key=lambda row: getattr(row, "created_at", datetime.min.replace(tzinfo=timezone.utc)), reverse=True)
        return _ScalarResultStub(filtered_rows)


def _matches_where_clause(row, clause) -> bool:
    key = getattr(getattr(clause, "left", None), "key", None)
    right = getattr(clause, "right", None)
    value = getattr(right, "value", None)
    operator_name = getattr(getattr(clause, "operator", None), "__name__", "")
    actual = getattr(row, key)

    if operator_name == "eq":
        return actual == value
    if operator_name == "ge":
        return actual >= value
    if operator_name == "le":
        return actual <= value
    return True


def _make_history_entry(
    *,
    entry_id: str,
    user_id: str,
    source: str,
    created_at: datetime,
    before_state: dict,
    after_state: dict,
    event_details: dict | None = None,
    actor_name: str | None = None,
):
    return SimpleNamespace(
        id=entry_id,
        user_id=user_id,
        source=source,
        created_at=created_at,
        before_state=before_state,
        after_state=after_state,
        event_details=event_details or {},
        actor=SimpleNamespace(full_name=actor_name) if actor_name else None,
    )


def test_serialize_quota_history_entry_purchase_event_contains_business_highlights():
    entry = SimpleNamespace(
        id="history-1",
        source="quota.purchase_package",
        created_at=datetime(2026, 3, 15, 1, 30, tzinfo=timezone.utc),
        before_state={
            "total_quota_purchased_mb": 1024,
            "total_quota_used_mb": 256,
            "quota_debt_total_mb": 0,
        },
        after_state={
            "total_quota_purchased_mb": 11264,
            "total_quota_used_mb": 256,
            "quota_debt_total_mb": 0,
        },
        event_details={
            "order_id": "ORD-123",
            "package_name": "Paket 10 GB",
            "package_quota_gb": 10,
            "package_duration_days": 30,
        },
        actor=SimpleNamespace(full_name="Admin Test"),
    )

    item = svc.serialize_quota_history_entry(entry)

    assert item["title"] == "Paket berhasil diaktifkan"
    assert item["category"] == "purchase"
    assert item["deltas"]["purchased_mb"] == 10240.0
    assert item["actor_name"] == "Admin Test"
    assert any("Paket: Paket 10 GB" in highlight for highlight in item["highlights"])
    assert any("Order ID: ORD-123" in highlight for highlight in item["highlights"])


def test_serialize_quota_history_entry_rebaseline_event_humanizes_reason():
    entry = SimpleNamespace(
        id="history-2",
        source="hotspot.sync_rebaseline",
        created_at=datetime(2026, 3, 15, 2, 0, tzinfo=timezone.utc),
        before_state={
            "total_quota_purchased_mb": 4096,
            "total_quota_used_mb": 2048,
            "quota_debt_total_mb": 0,
        },
        after_state={
            "total_quota_purchased_mb": 4096,
            "total_quota_used_mb": 2048,
            "quota_debt_total_mb": 0,
        },
        event_details={
            "rebaseline_events": [
                {
                    "mac_address": "AA:BB:CC:DD:EE:FF",
                    "ip_address": "172.16.1.20",
                    "label": "HP Syaifudin",
                    "reason": "host_row_changed+counter_regressed",
                    "host_id": "host-22",
                    "previous_host_id": "host-11",
                }
            ]
        },
        actor=None,
    )

    item = svc.serialize_quota_history_entry(entry)

    assert item["title"] == "Baseline hotspot direfresh"
    assert item["category"] == "sync"
    assert item["description"].startswith("Counter hotspot direfresh")
    assert len(item["rebaseline_events"]) == 1
    assert item["rebaseline_events"][0]["reason_label"] == "baris host berganti, counter mundur"
    assert any("HP Syaifudin" in highlight for highlight in item["highlights"])


def test_serialize_quota_history_entry_imported_purchase_event_mentions_backfill():
    entry = SimpleNamespace(
        id="history-3",
        source="quota.purchase_package.imported",
        created_at=datetime(2026, 2, 10, 9, 15, tzinfo=timezone.utc),
        before_state=None,
        after_state=None,
        event_details={
            "imported_from_transaction": True,
            "order_id": "ORD-LEGACY-1",
            "package_name": "Paket Unlimited 30 Hari",
            "package_quota_gb": 0,
            "package_duration_days": 30,
        },
        actor=None,
    )

    item = svc.serialize_quota_history_entry(entry)

    assert item["title"] == "Paket berhasil diaktifkan"
    assert item["category"] == "purchase"
    assert any("Riwayat pembelian lama diimpor" in highlight for highlight in item["highlights"])
    assert item["description"].startswith("Riwayat pembelian Paket Unlimited 30 Hari diimpor")


def test_serialize_quota_history_entry_normalize_expiry_mentions_grant_reference():
    entry = SimpleNamespace(
        id="history-4",
        source="quota.normalize_expiry",
        created_at=datetime(2026, 3, 15, 10, 0, tzinfo=timezone.utc),
        before_state={
            "total_quota_purchased_mb": 10240,
            "total_quota_used_mb": 512,
            "quota_debt_total_mb": 0,
        },
        after_state={
            "total_quota_purchased_mb": 10240,
            "total_quota_used_mb": 512,
            "quota_debt_total_mb": 0,
        },
        event_details={
            "grant_kind": "manual_debt_advance",
            "grant_label": "Manual debt advance 10 GB",
            "grant_reference": "log-123",
            "grant_at": "2026-03-15T10:00:00+00:00",
            "duration_days": 30,
            "previous_expiry_at": "2026-04-30T10:00:00+00:00",
            "normalized_expiry_at": "2026-04-14T10:00:00+00:00",
        },
        actor=None,
    )

    item = svc.serialize_quota_history_entry(entry)

    assert item["title"] == "Masa aktif dinormalisasi"
    assert item["category"] == "policy"
    assert any("Grant acuan: Manual debt advance 10 GB" in highlight for highlight in item["highlights"])
    assert any("Referensi: log-123" in highlight for highlight in item["highlights"])
    assert item["description"].startswith("Masa aktif akun pengguna diselaraskan ulang")


def test_serialize_quota_history_entry_auto_debt_advance_event_is_localized_in_indonesian():
    entry = SimpleNamespace(
        id="history-5",
        source="debt.consume_injected_auto_only:admin_debt_advance_pkg",
        created_at=datetime(2026, 3, 15, 5, 29, tzinfo=timezone.utc),
        before_state={
            "total_quota_purchased_mb": 0,
            "total_quota_used_mb": 0,
            "quota_debt_total_mb": 138,
        },
        after_state={
            "total_quota_purchased_mb": 0,
            "total_quota_used_mb": 0,
            "quota_debt_total_mb": 0,
        },
        event_details={
            "paid_auto_mb": 138,
            "remaining_injected_mb": 0,
        },
        actor=SimpleNamespace(full_name="Abdullah"),
    )

    item = svc.serialize_quota_history_entry(entry)

    assert item["title"] == "Tunggakan otomatis dikurangi"
    assert item["category"] == "debt"
    assert item["description"] == "Kuota paket advance admin dipakai untuk mengurangi tunggakan otomatis sebelum sisa kuota diberikan ke pengguna."
    assert any("Tunggakan otomatis dibayar: 138 MB" in highlight for highlight in item["highlights"])
    assert any("Sisa kuota advance: 0 KB" in highlight for highlight in item["highlights"])


def test_get_user_quota_history_payload_filters_by_date_and_search(monkeypatch):
    now_utc = datetime.now(timezone.utc)
    today_local = svc.get_app_local_datetime(now_utc).date()
    user = SimpleNamespace(id="user-1")

    session = _HistorySessionStub(
        [
            _make_history_entry(
                entry_id="history-today-purchase",
                user_id="user-1",
                source="quota.purchase_package",
                created_at=now_utc,
                before_state={"total_quota_purchased_mb": 0, "total_quota_used_mb": 0, "quota_debt_total_mb": 0},
                after_state={"total_quota_purchased_mb": 1024, "total_quota_used_mb": 0, "quota_debt_total_mb": 0},
                event_details={"package_name": "Paket Harian"},
                actor_name="Admin A",
            ),
            _make_history_entry(
                entry_id="history-debt-note",
                user_id="user-1",
                source="debt.add_manual",
                created_at=now_utc - timedelta(days=1),
                before_state={"total_quota_purchased_mb": 1024, "total_quota_used_mb": 128, "quota_debt_total_mb": 0},
                after_state={"total_quota_purchased_mb": 1024, "total_quota_used_mb": 128, "quota_debt_total_mb": 512},
                event_details={"amount_mb": 512, "note": "Manual lapangan shift malam"},
                actor_name="Petugas Debt",
            ),
            _make_history_entry(
                entry_id="history-old-adjust",
                user_id="user-1",
                source="quota.adjust_direct",
                created_at=now_utc - timedelta(days=40),
                before_state={"total_quota_purchased_mb": 1024, "total_quota_used_mb": 128, "quota_debt_total_mb": 0},
                after_state={"total_quota_purchased_mb": 2048, "total_quota_used_mb": 128, "quota_debt_total_mb": 0},
                event_details={"reason": "Audit lama"},
                actor_name="Super Admin",
            ),
        ]
    )

    monkeypatch.setattr(svc.db, "session", session, raising=False)

    payload = svc.get_user_quota_history_payload(
        user=user,  # type: ignore[arg-type]
        page=1,
        items_per_page=50,
        start_date=(today_local - timedelta(days=2)).isoformat(),
        end_date=today_local.isoformat(),
        search="lapangan",
    )

    assert payload["total_items"] == 1
    assert len(payload["items"]) == 1
    assert payload["items"][0]["source"] == "debt.add_manual"
    assert payload["filters"]["search"] == "lapangan"
    assert payload["filters"]["label"] == "3 hari terakhir"
    assert payload["summary"]["debt_events"] == 1


def test_get_user_quota_history_payload_clamps_requested_range_to_retention(monkeypatch):
    now_utc = datetime.now(timezone.utc)
    today_local = svc.get_app_local_datetime(now_utc).date()
    user = SimpleNamespace(id="user-2")

    recent_entry = _make_history_entry(
        entry_id="history-recent",
        user_id="user-2",
        source="quota.purchase_package",
        created_at=now_utc - timedelta(days=5),
        before_state={"total_quota_purchased_mb": 0, "total_quota_used_mb": 0, "quota_debt_total_mb": 0},
        after_state={"total_quota_purchased_mb": 2048, "total_quota_used_mb": 0, "quota_debt_total_mb": 0},
        event_details={"package_name": "Paket Bulanan"},
    )
    stale_entry = _make_history_entry(
        entry_id="history-stale",
        user_id="user-2",
        source="quota.adjust_direct",
        created_at=now_utc - timedelta(days=130),
        before_state={"total_quota_purchased_mb": 0, "total_quota_used_mb": 0, "quota_debt_total_mb": 0},
        after_state={"total_quota_purchased_mb": 512, "total_quota_used_mb": 0, "quota_debt_total_mb": 0},
        event_details={"reason": "Di luar retensi"},
    )

    monkeypatch.setattr(svc.db, "session", _HistorySessionStub([recent_entry, stale_entry]), raising=False)

    payload = svc.get_user_quota_history_payload(
        user=user,  # type: ignore[arg-type]
        page=1,
        items_per_page=50,
        start_date=(today_local - timedelta(days=150)).isoformat(),
        end_date=today_local.isoformat(),
    )

    assert payload["filters"]["start_date"] == (today_local - timedelta(days=89)).isoformat()
    assert payload["total_items"] == 1
    assert payload["items"][0]["id"] == "history-recent"