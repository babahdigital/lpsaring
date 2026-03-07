from __future__ import annotations

from types import SimpleNamespace

from flask import Flask

from app.infrastructure.http.admin import metrics_routes


def _unwrap_decorators(func):
    current = func
    while hasattr(current, "__wrapped__"):
        current = current.__wrapped__
    return current


def _make_app() -> Flask:
    app = Flask(__name__)
    app.config["SECRET_KEY"] = "unit-test-secret"
    return app


class _FakeRedis:
    def __init__(self, payload: bytes | str | None):
        self._payload = payload

    def get(self, _key: str):
        return self._payload


def test_get_admin_metrics_exposes_reliability_signals(monkeypatch):
    captured = {"keys": []}

    def _fake_get_metrics(keys):
        captured["keys"] = list(keys)
        return {
            "otp.request.success": 3,
            "otp.request.failed": 1,
            "otp.verify.success": 2,
            "otp.verify.failed": 0,
            "payment.success": 10,
            "payment.failed": 2,
            "payment.webhook.duplicate": 4,
            "payment.idempotency.redis_unavailable": 1,
            "hotspot.sync.lock.degraded": 0,
            "policy.mismatch.auto_debt_blocked_ip_binding": 2,
            "policy.mismatch.auto_debt_blocked_ip_binding.devices": 4,
            "admin.login.success": 7,
            "admin.login.failed": 1,
        }

    monkeypatch.setattr(metrics_routes, "get_metrics", _fake_get_metrics)
    monkeypatch.setattr(metrics_routes, "_read_cached_policy_parity_mismatch_count", lambda: 7)

    app = _make_app()
    impl = _unwrap_decorators(metrics_routes.get_admin_metrics)

    with app.app_context():
        resp, status = impl(current_admin=SimpleNamespace(id="admin-1"))

    assert status == 200
    payload = resp.get_json()

    assert "payment.idempotency.redis_unavailable" in captured["keys"]
    assert "hotspot.sync.lock.degraded" in captured["keys"]
    assert "payment.webhook.duplicate" in captured["keys"]
    assert "policy.mismatch.auto_debt_blocked_ip_binding" in captured["keys"]

    assert payload["metrics"]["payment.webhook.duplicate"] == 4
    assert payload["metrics"]["policy.mismatch.auto_debt_blocked_ip_binding"] == 2
    assert payload["metrics"]["policy.parity.latest_mismatches"] == 7
    assert payload["reliability_signals"]["payment_idempotency_degraded"] is True
    assert payload["reliability_signals"]["hotspot_sync_lock_degraded"] is False
    assert payload["reliability_signals"]["policy_parity_degraded"] is True


def test_get_access_parity_returns_empty_summary_when_no_users(monkeypatch):
    monkeypatch.setattr(
        metrics_routes,
        "collect_access_parity_report",
        lambda **_kwargs: {
            "ok": True,
            "items": [],
            "summary": {
                "users": 0,
                "mismatches": 0,
                "mismatch_types": {
                    "binding_type": 0,
                    "address_list": 0,
                    "address_list_multi_status": 0,
                },
            },
        },
    )

    app = _make_app()
    impl = _unwrap_decorators(metrics_routes.get_access_parity)

    with app.app_context():
        resp, status = impl(current_admin=SimpleNamespace(id="admin-1"))

    assert status == 200
    payload = resp.get_json()
    assert payload["items"] == []
    assert payload["summary"]["users"] == 0
    assert payload["summary"]["mismatches"] == 0


def test_get_access_parity_hides_non_parity_items_by_default(monkeypatch):
    monkeypatch.setattr(
        metrics_routes,
        "collect_access_parity_report",
        lambda **_kwargs: {
            "ok": True,
            "items": [
                {
                    "user_id": "u-1",
                    "phone_number": "+6281000000001",
                    "mismatches": ["no_authorized_device"],
                    "parity_relevant": False,
                },
                {
                    "user_id": "u-2",
                    "phone_number": "+6281000000002",
                    "mismatches": ["missing_ip_binding"],
                    "parity_relevant": True,
                },
            ],
            "summary": {
                "users": 2,
                "mismatches": 1,
                "mismatches_total": 2,
                "non_parity_mismatches": 1,
            },
        },
    )

    app = _make_app()
    impl = _unwrap_decorators(metrics_routes.get_access_parity)

    with app.app_context(), app.test_request_context("/admin/metrics/access-parity"):
        resp, status = impl(current_admin=SimpleNamespace(id="admin-1"))

    assert status == 200
    payload = resp.get_json()
    assert len(payload["items"]) == 1
    assert payload["items"][0]["user_id"] == "u-2"
    assert payload["summary"]["mismatches"] == 1


def test_get_access_parity_can_include_non_parity_items(monkeypatch):
    monkeypatch.setattr(
        metrics_routes,
        "collect_access_parity_report",
        lambda **_kwargs: {
            "ok": True,
            "items": [
                {
                    "user_id": "u-1",
                    "phone_number": "+6281000000001",
                    "mismatches": ["no_authorized_device"],
                    "parity_relevant": False,
                },
                {
                    "user_id": "u-2",
                    "phone_number": "+6281000000002",
                    "mismatches": ["missing_ip_binding"],
                    "parity_relevant": True,
                },
            ],
            "summary": {
                "users": 2,
                "mismatches": 1,
                "mismatches_total": 2,
                "non_parity_mismatches": 1,
            },
        },
    )

    app = _make_app()
    impl = _unwrap_decorators(metrics_routes.get_access_parity)

    with app.app_context(), app.test_request_context("/admin/metrics/access-parity?include_non_parity=true"):
        resp, status = impl(current_admin=SimpleNamespace(id="admin-1"))

    assert status == 200
    payload = resp.get_json()
    assert len(payload["items"]) == 2


def test_fix_access_parity_requires_user_id():
    app = _make_app()
    impl = _unwrap_decorators(metrics_routes.fix_access_parity)

    with app.app_context(), app.test_request_context(json={"mac": "AA:BB:CC:DD:EE:FF"}):
        resp, status = impl(current_admin=SimpleNamespace(id="admin-1"))

    assert status == 400
    payload = resp.get_json()
    assert "user_id" in str(payload.get("message", "")).lower()


def test_read_cached_policy_parity_mismatch_count_legacy_payload_excludes_no_authorized_device():
    app = _make_app()
    app.redis_client_otp = _FakeRedis(
        (
            '{"summary":{"mismatches":40,"mismatch_types":'
            '{"no_authorized_device":40,"binding_type":0}}}'
        ).encode("utf-8")
    )

    with app.app_context():
        result = metrics_routes._read_cached_policy_parity_mismatch_count()

    assert result == 0


def test_read_cached_policy_parity_mismatch_count_new_payload_uses_actionable_value():
    app = _make_app()
    app.redis_client_otp = _FakeRedis(
        (
            '{"summary":{"mismatches":2,"mismatches_total":9,'
            '"no_authorized_device_count":7}}'
        ).encode("utf-8")
    )

    with app.app_context():
        result = metrics_routes._read_cached_policy_parity_mismatch_count()

    assert result == 2
