from types import SimpleNamespace

from flask import Flask

from app.commands import heal_hotspot_status_address_list_command as cmd


class _AddressListResource:
    def __init__(self, rows):
        self._rows = list(rows)

    def get(self):
        return list(self._rows)


class _Api:
    def __init__(self, rows):
        self._resource = _AddressListResource(rows)

    def get_resource(self, path):
        assert path == "/ip/firewall/address-list"
        return self._resource


class _ConnCtx:
    def __init__(self, api):
        self._api = api

    def __enter__(self):
        return self._api

    def __exit__(self, exc_type, exc, tb):
        return False


def _make_app():
    app = Flask(__name__)
    app.config["MIKROTIK_UNAUTHORIZED_CIDRS"] = ["172.16.2.0/23"]
    app.config["MIKROTIK_ADDRESS_LIST_ACTIVE"] = "klient_aktif"
    app.config["MIKROTIK_ADDRESS_LIST_FUP"] = "klient_fup"
    app.config["MIKROTIK_ADDRESS_LIST_INACTIVE"] = "klient_habis"
    app.config["MIKROTIK_ADDRESS_LIST_EXPIRED"] = "klient_habis"
    app.config["MIKROTIK_ADDRESS_LIST_HABIS"] = "klient_habis"
    app.config["MIKROTIK_ADDRESS_LIST_BLOCKED"] = "unauthorized"
    app.cli.add_command(cmd.heal_hotspot_status_address_list_command)
    return app


def test_heal_hotspot_status_dry_run_only_reports(monkeypatch):
    rows = [
        {
            "list": "klient_aktif",
            "address": "172.16.2.10",
            "comment": "lpsaring|status=active|user=0811111111",
        },
        {
            "list": "klient_aktif",
            "address": "10.0.99.40",
            "comment": "lpsaring|status=active|user=0812222222",
        },
        {
            "list": "klient_aktif",
            "address": "10.0.99.41",
            "comment": "manual-entry",
        },
    ]

    monkeypatch.setattr(cmd, "get_mikrotik_connection", lambda: _ConnCtx(_Api(rows)))

    remove_calls = {"count": 0}

    def _fake_remove_address_list_entry(*, api_connection, address, list_name):
        remove_calls["count"] += 1
        return True, "ok"

    monkeypatch.setattr(cmd, "remove_address_list_entry", _fake_remove_address_list_entry)

    app = _make_app()
    runner = app.test_cli_runner()
    result = runner.invoke(
        args=["heal-hotspot-status-address-list", "--dry-run", "--no-resync-users"]
    )

    assert result.exit_code == 0
    assert "DRY-RUN remove list=klient_aktif ip=10.0.99.40" in result.output
    assert "managed=2" in result.output
    assert "out_of_cidr=1" in result.output
    assert "removed=0" in result.output
    assert remove_calls["count"] == 0


def test_heal_hotspot_status_apply_removes_and_resyncs(monkeypatch):
    rows = [
        {
            "list": "klient_aktif",
            "address": "10.0.99.40",
            "comment": "lpsaring|status=active|user=0811111111",
        },
        {
            "list": "klient_fup",
            "address": "172.16.8.22",
            "comment": "lpsaring|status=fup|user=0819999999",
        },
    ]

    monkeypatch.setattr(cmd, "get_mikrotik_connection", lambda: _ConnCtx(_Api(rows)))

    remove_calls = {"count": 0}

    def _fake_remove_address_list_entry(*, api_connection, address, list_name):
        remove_calls["count"] += 1
        return True, "ok"

    monkeypatch.setattr(cmd, "remove_address_list_entry", _fake_remove_address_list_entry)

    monkeypatch.setattr(
        cmd,
        "_find_user_by_phone",
        lambda phone: SimpleNamespace(id=101)
        if phone == "0811111111"
        else None,
    )

    resync_calls = {"count": 0}

    def _fake_sync_address_list_for_single_user(user):
        resync_calls["count"] += 1
        return True

    monkeypatch.setattr(cmd, "sync_address_list_for_single_user", _fake_sync_address_list_for_single_user)

    app = _make_app()
    runner = app.test_cli_runner()
    result = runner.invoke(
        args=["heal-hotspot-status-address-list", "--apply", "--resync-users"]
    )

    assert result.exit_code == 0
    assert "out_of_cidr=2" in result.output
    assert "removed=2" in result.output
    assert "affected_users=2" in result.output
    assert "resynced_ok=1" in result.output
    assert "resync_user_not_found=1" in result.output
    assert remove_calls["count"] == 2
    assert resync_calls["count"] == 1
