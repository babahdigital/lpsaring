from __future__ import annotations

from types import SimpleNamespace

from flask import Flask

from app.commands import prune_hotspot_status_without_binding_command as cmd


class _Resource:
    def __init__(self, rows):
        self._rows = list(rows)

    def get(self, **kwargs):
        if not kwargs:
            return list(self._rows)

        result = []
        for row in self._rows:
            matched = True
            for key, value in kwargs.items():
                if row.get(key) != value:
                    matched = False
                    break
            if matched:
                result.append(row)
        return result


class _Api:
    def __init__(self, address_rows, binding_rows):
        self._address_resource = _Resource(address_rows)
        self._binding_resource = _Resource(binding_rows)

    def get_resource(self, path):
        if path == "/ip/firewall/address-list":
            return self._address_resource
        if path == "/ip/hotspot/ip-binding":
            return self._binding_resource
        raise AssertionError(path)


class _ConnCtx:
    def __init__(self, api):
        self._api = api

    def __enter__(self):
        return self._api

    def __exit__(self, exc_type, exc, tb):
        return False


def _patch_settings(monkeypatch):
    mapping = {
        "MIKROTIK_ADDRESS_LIST_ACTIVE": "active",
        "MIKROTIK_ADDRESS_LIST_FUP": "fup",
        "MIKROTIK_ADDRESS_LIST_INACTIVE": "inactive",
        "MIKROTIK_ADDRESS_LIST_EXPIRED": "expired",
        "MIKROTIK_ADDRESS_LIST_HABIS": "habis",
        "MIKROTIK_ADDRESS_LIST_BLOCKED": "blocked",
        "MIKROTIK_ADDRESS_LIST_UNAUTHORIZED": "unauthorized",
    }

    monkeypatch.setattr(cmd.settings_service, "get_setting", lambda key, default=None: mapping.get(key, default))


def _make_app():
    app = Flask(__name__)
    app.cli.add_command(cmd.prune_hotspot_status_without_binding_command)
    return app


def test_prune_hotspot_status_without_binding_dry_run_overlap_only(monkeypatch):
    _patch_settings(monkeypatch)

    address_rows = [
        {
            "list": "active",
            "address": "172.16.2.10",
            "comment": "lpsaring|status=active|user=0811111111",
        },
        {
            "list": "fup",
            "address": "172.16.2.20",
            "comment": "lpsaring|status=fup|user=0812222222",
        },
        {
            "list": "active",
            "address": "172.16.2.30",
            "comment": "lpsaring|status=active|user=0813333333",
        },
        {
            "list": "unauthorized",
            "address": "172.16.2.10",
            "comment": "lpsaring:unauthorized mac=AA:00:00:00:00:10",
        },
    ]
    binding_rows = [
        {
            "mac-address": "AA:BB:CC:DD:EE:33",
            "type": "bypassed",
            "address": "172.16.2.30",
            "comment": "authorized|user=0813333333|uid=uid-333",
        }
    ]

    monkeypatch.setattr(cmd, "get_mikrotik_connection", lambda: _ConnCtx(_Api(address_rows, binding_rows)))
    monkeypatch.setattr(
        cmd,
        "_build_user_indexes",
        lambda: (
            {"uid-111": SimpleNamespace(id="uid-111"), "uid-222": SimpleNamespace(id="uid-222")},
            {"0811111111": "uid-111", "0812222222": "uid-222", "0813333333": "uid-333"},
            {
                "uid-111": {"AA:BB:CC:DD:EE:11"},
                "uid-222": {"AA:BB:CC:DD:EE:22"},
                "uid-333": {"AA:BB:CC:DD:EE:33"},
            },
        ),
    )

    remove_calls = {"count": 0}

    def _fake_remove_address_list_entry(*, api_connection, address, list_name):
        remove_calls["count"] += 1
        return True, "ok"

    monkeypatch.setattr(cmd, "remove_address_list_entry", _fake_remove_address_list_entry)

    app = _make_app()
    runner = app.test_cli_runner()
    result = runner.invoke(
        args=[
            "prune-hotspot-status-without-binding",
            "--dry-run",
            "--overlap-unauthorized-only",
            "--no-resync-users",
        ]
    )

    assert result.exit_code == 0
    assert "without_binding=2" in result.output
    assert "overlap_without_binding=1" in result.output
    assert "candidates=1" in result.output
    assert "removed=0" in result.output
    assert remove_calls["count"] == 0


def test_prune_hotspot_status_without_binding_apply_all_candidates(monkeypatch):
    _patch_settings(monkeypatch)

    address_rows = [
        {
            "list": "active",
            "address": "172.16.2.10",
            "comment": "lpsaring|status=active|user=0811111111",
        },
        {
            "list": "fup",
            "address": "172.16.2.20",
            "comment": "lpsaring|status=fup|user=0812222222",
        },
        {
            "list": "unauthorized",
            "address": "172.16.2.10",
            "comment": "lpsaring:unauthorized mac=AA:00:00:00:00:10",
        },
    ]
    binding_rows = []

    monkeypatch.setattr(cmd, "get_mikrotik_connection", lambda: _ConnCtx(_Api(address_rows, binding_rows)))
    monkeypatch.setattr(
        cmd,
        "_build_user_indexes",
        lambda: (
            {"uid-111": SimpleNamespace(id="uid-111"), "uid-222": SimpleNamespace(id="uid-222")},
            {"0811111111": "uid-111", "0812222222": "uid-222"},
            {"uid-111": set(), "uid-222": set()},
        ),
    )

    remove_calls = {"count": 0}

    def _fake_remove_address_list_entry(*, api_connection, address, list_name):
        remove_calls["count"] += 1
        return True, "ok"

    monkeypatch.setattr(cmd, "remove_address_list_entry", _fake_remove_address_list_entry)

    app = _make_app()
    runner = app.test_cli_runner()
    result = runner.invoke(
        args=[
            "prune-hotspot-status-without-binding",
            "--apply",
            "--all-candidates",
            "--no-resync-users",
        ]
    )

    assert result.exit_code == 0
    assert "candidates=2" in result.output
    assert "removed=2" in result.output
    assert "remove_failed=0" in result.output
    assert remove_calls["count"] == 2
