from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import app.services.quota_history_service as svc


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