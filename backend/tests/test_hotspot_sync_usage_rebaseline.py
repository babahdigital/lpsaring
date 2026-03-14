from __future__ import annotations

from types import SimpleNamespace

import pytest

import app.services.hotspot_sync_service as svc


class _FakeRedis:
    def __init__(self, values: dict[str, int] | None = None):
        self.values = dict(values or {})

    def exists(self, key: str) -> int:
        return 1 if key in self.values else 0

    def get(self, key: str):
        return self.values.get(key)

    def set(self, key: str, value):
        self.values[key] = int(value)
        return True


def test_calculate_usage_update_rebaselines_when_host_row_changes():
    user = SimpleNamespace(
        total_quota_used_mb=100.0,
        devices=[
            SimpleNamespace(
                mac_address="AA:BB:CC:DD:EE:FF",
                ip_address="172.16.1.10",
                label="HP Bobby",
                last_bytes_total=2_000_000,
                last_bytes_updated_at=None,
                last_hotspot_host_id="host-prev",
                last_hotspot_uptime_seconds=120,
            )
        ],
    )

    result = svc._calculate_usage_update(
        user=user,
        host_usage_map={
            "AA:BB:CC:DD:EE:FF": {
                "bytes_in": 1_500_000,
                "bytes_out": 1_000_000,
                "host_id": "host-new",
                "uptime_seconds": 30,
                "source_address": "10.0.0.1",
                "to_address": "10.0.0.2",
            }
        },
        redis_client=None,
    )

    assert result is not None
    assert result.delta_mb == pytest.approx(0.0)
    assert result.new_total_usage_mb == pytest.approx(100.0)
    assert len(result.rebaseline_events) == 1
    assert result.rebaseline_events[0].reason == "host_row_changed+uptime_regressed"
    assert user.devices[0].last_bytes_total == 2_500_000
    assert user.devices[0].last_hotspot_host_id == "host-new"
    assert user.devices[0].last_hotspot_uptime_seconds == 30


def test_calculate_usage_update_prefers_max_redis_and_db_baseline():
    device = SimpleNamespace(
        mac_address="AA:BB:CC:DD:EE:11",
        ip_address="172.16.1.11",
        label="Laptop",
        last_bytes_total=2_000_000,
        last_bytes_updated_at=None,
        last_hotspot_host_id="host-1",
        last_hotspot_uptime_seconds=300,
    )
    user = SimpleNamespace(total_quota_used_mb=50.0, devices=[device])
    redis_client = _FakeRedis({f"{svc.REDIS_LAST_BYTES_PREFIX}AA:BB:CC:DD:EE:11": 5_000_000})

    result = svc._calculate_usage_update(
        user=user,
        host_usage_map={
            "AA:BB:CC:DD:EE:11": {
                "bytes_in": 3_000_000,
                "bytes_out": 3_000_000,
                "host_id": "host-1",
                "uptime_seconds": 360,
            }
        },
        redis_client=redis_client,
    )

    assert result is not None
    assert result.delta_mb == pytest.approx(0.95)
    assert result.new_total_usage_mb == pytest.approx(50.95)
    assert len(result.device_deltas) == 1
    assert result.device_deltas[0].previous_bytes_total == 5_000_000
    assert device.last_bytes_total == 6_000_000