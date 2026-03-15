from __future__ import annotations

import json
from datetime import datetime, timezone
from types import SimpleNamespace
import uuid

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


def test_register_latest_expiry_candidate_prefers_newer_grant():
    user_id = uuid.uuid4()
    candidates: dict[tuple[uuid.UUID, bool], dict[str, object]] = {}

    older = cmd._build_expiry_candidate(
        user_id=user_id,
        grant_at=datetime(2026, 3, 10, 10, 0, tzinfo=timezone.utc),
        duration_days=30,
        source_kind="quota.purchase_package",
        grant_kind="purchase",
        is_unlimited=False,
        grant_reference="ORD-OLD",
        grant_label="Paket Lama",
    )
    newer = cmd._build_expiry_candidate(
        user_id=user_id,
        grant_at=datetime(2026, 3, 15, 9, 0, tzinfo=timezone.utc),
        duration_days=15,
        source_kind="quota.inject",
        grant_kind="admin_inject",
        is_unlimited=False,
        grant_reference="LEDGER-NEW",
        grant_label="Inject Admin",
    )

    cmd._register_latest_expiry_candidate(candidates, older)
    cmd._register_latest_expiry_candidate(candidates, newer)

    assert candidates[(user_id, False)]["grant_reference"] == "LEDGER-NEW"
    assert candidates[(user_id, False)]["duration_days"] == 15


def test_build_admin_debt_action_candidate_defaults_direct_manual_debt_to_30_days():
    user_id = uuid.uuid4()
    action_log = SimpleNamespace(
        id=uuid.uuid4(),
        target_user_id=user_id,
        created_at=datetime(2026, 3, 15, 7, 0, tzinfo=timezone.utc),
        details=json.dumps({"debt_add_mb": 10240}),
    )

    candidate = cmd._build_admin_debt_action_candidate(action_log, {})

    assert candidate is not None
    assert candidate["user_id"] == user_id
    assert candidate["duration_days"] == cmd.DEFAULT_MANUAL_DEBT_ADVANCE_DAYS
    assert candidate["grant_kind"] == "manual_debt_advance"
    assert candidate["is_unlimited"] is False
    assert "Manual debt advance" in str(candidate["grant_label"])