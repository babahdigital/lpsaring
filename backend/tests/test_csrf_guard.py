from flask import Flask

from app.infrastructure.http.decorators import _passes_csrf_guard


def _make_app(strict: bool, allowed_ips: list[str]) -> Flask:
    app = Flask(__name__)
    app.config.update(
        CSRF_PROTECT_ENABLED=True,
        CSRF_STRICT_NO_ORIGIN=strict,
        CSRF_NO_ORIGIN_ALLOWED_IPS=allowed_ips,
    )
    return app


def test_csrf_guard_allows_no_origin_when_not_strict():
    app = _make_app(False, [])
    with app.test_request_context("/api/test", method="POST", environ_base={"REMOTE_ADDR": "10.10.83.1"}):
        assert _passes_csrf_guard() is True


def test_csrf_guard_allows_no_origin_with_allowlist():
    app = _make_app(True, ["10.10.83.1"])
    with app.test_request_context("/api/test", method="POST", environ_base={"REMOTE_ADDR": "10.10.83.1"}):
        assert _passes_csrf_guard() is True


def test_csrf_guard_blocks_no_origin_without_allowlist():
    app = _make_app(True, ["10.10.83.1"])
    with app.test_request_context("/api/test", method="POST", environ_base={"REMOTE_ADDR": "10.10.83.2"}):
        assert _passes_csrf_guard() is False


def test_csrf_guard_allows_no_origin_with_cidr():
    app = _make_app(True, ["172.16.0.0/12"])
    with app.test_request_context("/api/test", method="POST", environ_base={"REMOTE_ADDR": "172.18.0.5"}):
        assert _passes_csrf_guard() is True
