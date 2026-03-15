from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import app.commands.quota_remediation_command as cmd


def test_build_spike_candidate_prefers_large_device_delta_and_marks_high_confidence():
    entry = SimpleNamespace(
        event_details={
            "delta_mb": 9216,
            "device_deltas": [
                {"delta_mb": 8704, "label": "HP Abdullah", "mac_address": "AA:BB:CC:DD:EE:FF"},
                {"delta_mb": 512, "label": "Laptop Tamu", "mac_address": "11:22:33:44:55:66"},
            ],
        },
        before_state={"total_quota_used_mb": 1024},
        after_state={"total_quota_used_mb": 10240},
    )

    candidate = cmd._build_spike_candidate(
        entry,
        min_delta_mb=4096,
        min_device_delta_mb=2048,
        max_device_count=2,
    )

    assert candidate is not None
    assert candidate["delta_mb"] == 9216.0
    assert candidate["refundable_mb"] == 8704.0
    assert candidate["confidence"] == "high"
    assert candidate["large_device_count"] == 1


def test_build_purchase_import_details_marks_imported_transaction_context():
    payment_time = datetime(2026, 3, 12, 14, 0, tzinfo=timezone.utc)
    transaction = SimpleNamespace(
        id="tx-legacy-1",
        midtrans_order_id="ORD-LEGACY-77",
        payment_time=payment_time,
        created_at=datetime(2026, 3, 12, 13, 55, tzinfo=timezone.utc),
        package=SimpleNamespace(name="Paket 10 GB", data_quota_gb=10, duration_days=30),
    )

    details = cmd._build_purchase_import_details(transaction)

    assert details["imported_from_transaction"] is True
    assert details["order_id"] == "ORD-LEGACY-77"
    assert details["package_name"] == "Paket 10 GB"
    assert details["package_quota_gb"] == 10.0
    assert details["package_duration_days"] == 30
    assert details["payment_time"] == payment_time.isoformat()