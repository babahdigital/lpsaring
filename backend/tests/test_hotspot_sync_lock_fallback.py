from __future__ import annotations

from flask import Flask

from app.services import hotspot_sync_service
from app.utils.metrics_utils import get_metrics


def _make_app() -> Flask:
    app = Flask(__name__)
    app.config["SECRET_KEY"] = "unit-test-secret"
    return app


def test_global_sync_lock_uses_local_fallback_when_redis_unavailable():
    app = _make_app()

    with app.app_context():
        first_ok, first_token = hotspot_sync_service._acquire_global_sync_lock(None)
        second_ok, second_token = hotspot_sync_service._acquire_global_sync_lock(None)

        assert first_ok is True
        assert first_token == hotspot_sync_service.LOCAL_GLOBAL_SYNC_LOCK_TOKEN
        assert second_ok is False
        assert second_token == ""

        hotspot_sync_service._release_global_sync_lock(None, first_token)

        third_ok, third_token = hotspot_sync_service._acquire_global_sync_lock(None)
        hotspot_sync_service._release_global_sync_lock(None, third_token)

        metrics = get_metrics(["hotspot.sync.lock.degraded"])

    assert third_ok is True
    assert third_token == hotspot_sync_service.LOCAL_GLOBAL_SYNC_LOCK_TOKEN
    assert metrics["hotspot.sync.lock.degraded"] >= 1
