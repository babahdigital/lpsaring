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
    assert payload["reliability_signals"]["payment_idempotency_degraded"] is True
    assert payload["reliability_signals"]["hotspot_sync_lock_degraded"] is False
    assert payload["reliability_signals"]["policy_parity_degraded"] is True


def test_get_access_parity_returns_empty_summary_when_no_users(monkeypatch):
    class _EmptyScalars:
        def all(self):
            return []

    monkeypatch.setattr(metrics_routes.db.session, "scalars", lambda *_args, **_kwargs: _EmptyScalars())

    app = _make_app()
    impl = _unwrap_decorators(metrics_routes.get_access_parity)

    with app.app_context():
        resp, status = impl(current_admin=SimpleNamespace(id="admin-1"))

    assert status == 200
    payload = resp.get_json()
    assert payload == {"items": [], "summary": {"users": 0, "mismatches": 0}}
