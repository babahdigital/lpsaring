from __future__ import annotations

from flask import Flask

from app.infrastructure.http.transactions import idempotency
from app.utils.metrics_utils import get_metrics


def _make_app() -> Flask:
    app = Flask(__name__)
    app.config["SECRET_KEY"] = "unit-test-secret"
    return app


def test_begin_order_effect_uses_db_fallback_when_redis_unavailable(monkeypatch):
    app = _make_app()
    setattr(app, "redis_client_otp", None)

    marker = {"checked": False}

    def _fake_is_effect_done_in_db(*, session, order_id, effect_name):
        marker["checked"] = True
        assert session is not None
        assert order_id == "ORD-1"
        assert effect_name == "hotspot_apply"
        return True

    monkeypatch.setattr(idempotency, "_is_effect_done_in_db", _fake_is_effect_done_in_db)

    with app.app_context():
        should_apply, lock_key = idempotency.begin_order_effect(
            order_id="ORD-1",
            effect_name="hotspot_apply",
            session=object(),
        )
        metrics = get_metrics(["payment.idempotency.redis_unavailable"])

    assert marker["checked"] is True
    assert should_apply is False
    assert lock_key is None
    assert metrics["payment.idempotency.redis_unavailable"] >= 1


def test_begin_order_effect_allows_when_db_marker_absent(monkeypatch):
    app = _make_app()
    setattr(app, "redis_client_otp", None)

    monkeypatch.setattr(idempotency, "_is_effect_done_in_db", lambda **_kwargs: False)

    with app.app_context():
        should_apply, lock_key = idempotency.begin_order_effect(
            order_id="ORD-2",
            effect_name="hotspot_apply",
            session=object(),
        )

    assert should_apply is True
    assert lock_key is None
