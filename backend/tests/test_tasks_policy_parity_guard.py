from __future__ import annotations

import json
from contextlib import contextmanager
from types import SimpleNamespace

from flask import Flask

import app.tasks as tasks


class _FakeQuery:
    def __init__(self, users):
        self._users = users

    def options(self, *_args, **_kwargs):
        return self

    def filter(self, *_args, **_kwargs):
        return self

    def all(self):
        return list(self._users)


class _FakeRedis:
    def __init__(self):
        self.values = {}

    def set(self, key, value, ex=None):
        self.values[key] = {"value": value, "ex": ex}


def _make_app() -> Flask:
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY="unit-test-secret",
        ENABLE_POLICY_PARITY_AUTO_REMEDIATION=True,
        POLICY_PARITY_AUTO_REMEDIATION_MAX_USERS=5,
        POLICY_PARITY_AUTO_REMEDIATION_RUN_UNAUTHORIZED_SYNC=True,
    )
    app.redis_client_otp = _FakeRedis()
    return app


def test_policy_parity_guard_auto_remediates_unique_users(monkeypatch):
    app = _make_app()

    monkeypatch.setattr(tasks, "create_app", lambda: app)
    monkeypatch.setattr(tasks.settings_service, "get_setting", lambda key, default=None: "True")
    monkeypatch.setattr(tasks, "increment_metric", lambda *_args, **_kwargs: None)

    reports = [
        {
            "ok": True,
            "summary": {
                "mismatches": 2,
                "mismatch_types": {
                    "binding_type": 1,
                    "address_list": 1,
                    "address_list_multi_status": 0,
                },
            },
            "items": [
                {
                    "user_id": "user-1",
                    "phone_number": "+628111111111",
                    "ip": "172.16.2.98",
                    "mismatches": ["missing_ip_binding", "address_list"],
                    "auto_fixable": True,
                    "parity_relevant": True,
                },
                {
                    "user_id": "user-1",
                    "phone_number": "+628111111111",
                    "ip": "172.16.2.99",
                    "mismatches": ["address_list_multi_status"],
                    "auto_fixable": True,
                    "parity_relevant": True,
                },
                {
                    "user_id": "user-2",
                    "phone_number": "+628122222222",
                    "ip": "172.16.3.112",
                    "mismatches": ["binding_type"],
                    "auto_fixable": True,
                    "parity_relevant": True,
                },
                {
                    "user_id": "user-3",
                    "phone_number": "+628133333333",
                    "ip": "172.16.3.120",
                    "mismatches": ["dhcp_lease_missing"],
                    "auto_fixable": True,
                    "parity_relevant": False,
                },
            ],
        },
        {
            "ok": True,
            "summary": {
                "mismatches": 0,
                "mismatch_types": {
                    "binding_type": 0,
                    "address_list": 0,
                    "address_list_multi_status": 0,
                },
            },
            "items": [],
        },
    ]

    def _fake_collect_access_parity_report(*, max_items=500):
        return reports.pop(0)

    monkeypatch.setattr(tasks, "collect_access_parity_report", _fake_collect_access_parity_report)

    fake_db = SimpleNamespace(
        session=SimpleNamespace(
            query=lambda *_args, **_kwargs: _FakeQuery(
                [
                    SimpleNamespace(id="user-1", devices=[]),
                    SimpleNamespace(id="user-2", devices=[]),
                ]
            ),
            remove=lambda: None,
        )
    )
    monkeypatch.setattr(tasks, "db", fake_db)

    sync_calls = []

    def _fake_sync_address_list_for_single_user(user, client_ip=None, api_connection=None):
        sync_calls.append((str(user.id), client_ip, api_connection))
        return True

    monkeypatch.setattr(tasks, "sync_address_list_for_single_user", _fake_sync_address_list_for_single_user)

    unauthorized_calls = []

    def _fake_sync_unauthorized_main(*, args=None, standalone_mode=True):
        unauthorized_calls.append((list(args or []), standalone_mode))

    monkeypatch.setattr(tasks.sync_unauthorized_hosts_command, "main", _fake_sync_unauthorized_main)

    @contextmanager
    def _fake_mikrotik_connection():
        yield object()

    monkeypatch.setattr(tasks, "get_mikrotik_connection", _fake_mikrotik_connection)

    tasks.policy_parity_guard_task.run()

    assert len(sync_calls) == 2
    assert [call[0] for call in sync_calls] == ["user-1", "user-2"]
    assert [call[1] for call in sync_calls] == ["172.16.2.98", "172.16.3.112"]
    assert unauthorized_calls == [(["--apply"], False)]

    cached = app.redis_client_otp.values["policy_parity:last_report"]["value"]
    payload = json.loads(cached)
    assert payload["summary"]["mismatches"] == 0
    assert payload["auto_remediation"]["candidate_users"] == 2
    assert payload["auto_remediation"]["remediated_users"] == 2
    assert payload["auto_remediation"]["unauthorized_sync_triggered"] is True


def test_policy_parity_guard_skips_auto_remediation_when_disabled(monkeypatch):
    app = _make_app()
    app.config["ENABLE_POLICY_PARITY_AUTO_REMEDIATION"] = False

    monkeypatch.setattr(tasks, "create_app", lambda: app)
    monkeypatch.setattr(tasks.settings_service, "get_setting", lambda key, default=None: "True")
    monkeypatch.setattr(tasks, "increment_metric", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        tasks,
        "collect_access_parity_report",
        lambda *, max_items=500: {
            "ok": True,
            "summary": {
                "mismatches": 1,
                "mismatch_types": {
                    "binding_type": 1,
                    "address_list": 0,
                    "address_list_multi_status": 0,
                },
            },
            "items": [
                {
                    "user_id": "user-1",
                    "phone_number": "+628111111111",
                    "ip": "172.16.2.98",
                    "mismatches": ["binding_type"],
                    "auto_fixable": True,
                    "parity_relevant": True,
                }
            ],
        },
    )

    called = {"value": False}

    def _fake_sync_address_list_for_single_user(user, client_ip=None, api_connection=None):
        called["value"] = True
        return True

    monkeypatch.setattr(tasks, "sync_address_list_for_single_user", _fake_sync_address_list_for_single_user)

    tasks.policy_parity_guard_task.run()

    assert called["value"] is False
    cached = app.redis_client_otp.values["policy_parity:last_report"]["value"]
    payload = json.loads(cached)
    assert payload["auto_remediation"]["enabled"] is False
    assert payload["auto_remediation"]["candidate_users"] == 0