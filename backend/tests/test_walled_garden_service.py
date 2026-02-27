from __future__ import annotations

from flask import Flask

from app.services import walled_garden_service as service


class _FakeMikrotikCtx:
    def __init__(self, api_obj: object):
        self._api_obj = api_obj

    def __enter__(self):
        return self._api_obj

    def __exit__(self, exc_type, exc, tb):
        return False


class _FakeAddressListResource:
    def __init__(self, rows: list[dict]):
        self._rows = rows

    def get(self, **kwargs):
        return self._rows


class _FakeApi:
    def __init__(self, address_list_rows: list[dict]):
        self._resource = _FakeAddressListResource(address_list_rows)

    def get_resource(self, path: str):
        if path == "/ip/firewall/address-list":
            return self._resource
        raise KeyError(path)


def _make_app() -> Flask:
    app = Flask(__name__)
    app.config["APP_PUBLIC_BASE_URL"] = "https://portal.example.com"
    app.config["FRONTEND_URL"] = "https://portal.example.com"
    app.config["APP_LINK_USER"] = "https://portal.example.com/login"
    app.config["APP_LINK_ADMIN"] = "https://portal.example.com/admin"
    app.config["APP_LINK_ADMIN_CHANGE_PASSWORD"] = "https://portal.example.com/akun"
    app.config["APP_LINK_MIKROTIK"] = "http://login.local"
    app.config["MIDTRANS_IS_PRODUCTION"] = False
    return app


def test_sync_walled_garden_auto_include_external_hosts(monkeypatch):
    app = _make_app()

    setting_map = {
        "WALLED_GARDEN_ENABLED": "True",
        "WALLED_GARDEN_ALLOWED_HOSTS": "[]",
        "WALLED_GARDEN_ALLOWED_IPS": "[]",
        "WALLED_GARDEN_AUTO_INCLUDE_EXTERNAL_HOSTS": "True",
        "WALLED_GARDEN_AUTO_INCLUDE_PORTAL_HOSTS": "True",
        "WALLED_GARDEN_INCLUDE_MIDTRANS_HOSTS": "True",
        "WALLED_GARDEN_INCLUDE_MESSAGING_HOSTS": "True",
        "WHATSAPP_API_URL": "https://api.fonnte.com/send",
        "WHATSAPP_VALIDATE_URL": "https://api.fonnte.com/validate",
        "TELEGRAM_API_BASE_URL": "https://api.telegram.org",
    }

    monkeypatch.setattr(service.settings_service, "get_setting", lambda key, default=None: setting_map.get(key, default))

    captured = {}

    def _fake_sync_rules(*, api_connection, allowed_hosts, allowed_ips, comment_prefix):
        captured["allowed_hosts"] = list(allowed_hosts)
        captured["allowed_ips"] = list(allowed_ips)
        captured["comment_prefix"] = comment_prefix
        return True, "ok"

    monkeypatch.setattr(service, "get_mikrotik_connection", lambda: _FakeMikrotikCtx(object()))
    monkeypatch.setattr(service, "sync_walled_garden_rules", _fake_sync_rules)

    with app.app_context():
        result = service.sync_walled_garden()

    assert result["status"] == "success"
    assert "portal.example.com" in captured["allowed_hosts"]
    assert "login.local" in captured["allowed_hosts"]
    assert "app.sandbox.midtrans.com" in captured["allowed_hosts"]
    assert "api.sandbox.midtrans.com" in captured["allowed_hosts"]
    assert "api.fonnte.com" in captured["allowed_hosts"]
    assert "api.telegram.org" in captured["allowed_hosts"]


def test_sync_walled_garden_auto_include_disabled_keeps_portal_fallback(monkeypatch):
    app = _make_app()

    setting_map = {
        "WALLED_GARDEN_ENABLED": "True",
        "WALLED_GARDEN_ALLOWED_HOSTS": "[]",
        "WALLED_GARDEN_ALLOWED_IPS": "[]",
        "WALLED_GARDEN_AUTO_INCLUDE_EXTERNAL_HOSTS": "False",
    }

    monkeypatch.setattr(service.settings_service, "get_setting", lambda key, default=None: setting_map.get(key, default))

    captured = {}

    def _fake_sync_rules(*, api_connection, allowed_hosts, allowed_ips, comment_prefix):
        captured["allowed_hosts"] = list(allowed_hosts)
        return True, "ok"

    monkeypatch.setattr(service, "get_mikrotik_connection", lambda: _FakeMikrotikCtx(object()))
    monkeypatch.setattr(service, "sync_walled_garden_rules", _fake_sync_rules)

    with app.app_context():
        result = service.sync_walled_garden()

    assert result["status"] == "success"
    assert "portal.example.com" in captured["allowed_hosts"]
    assert "app.sandbox.midtrans.com" not in captured["allowed_hosts"]


def test_sync_walled_garden_resolves_ips_from_address_list_names(monkeypatch):
    app = _make_app()

    setting_map = {
        "WALLED_GARDEN_ENABLED": "True",
        "WALLED_GARDEN_ALLOWED_HOSTS": "[]",
        "WALLED_GARDEN_ALLOWED_IPS": "[]",
        "WALLED_GARDEN_ALLOWED_IP_LIST_NAMES": '["klient_aktif","klient_fup"]',
        "WALLED_GARDEN_AUTO_INCLUDE_EXTERNAL_HOSTS": "False",
    }

    monkeypatch.setattr(service.settings_service, "get_setting", lambda key, default=None: setting_map.get(key, default))

    captured = {}

    def _fake_sync_rules(*, api_connection, allowed_hosts, allowed_ips, comment_prefix):
        captured["allowed_ips"] = list(allowed_ips)
        return True, "ok"

    fake_api = _FakeApi(
        [
            {"list": "klient_aktif", "address": "172.16.2.10"},
            {"list": "klient_fup", "address": "172.16.2.0/24"},
            {"list": "klient_aktif", "address": "172.16.2.10"},
            {"list": "klient_blocked", "address": "172.16.2.99"},
            {"list": "klient_fup", "address": "172.16.2.3-7"},
        ]
    )

    monkeypatch.setattr(service, "get_mikrotik_connection", lambda: _FakeMikrotikCtx(fake_api))
    monkeypatch.setattr(service, "sync_walled_garden_rules", _fake_sync_rules)

    with app.app_context():
        result = service.sync_walled_garden()

    assert result["status"] == "success"
    assert sorted(captured["allowed_ips"]) == ["172.16.2.0/24", "172.16.2.10"]
