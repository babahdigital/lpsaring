"""Regression tests for overdue debt block task fixes."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone as dt_timezone
from types import SimpleNamespace

import pytest
from flask import Flask

from app.infrastructure.db.models import ApprovalStatus, UserRole
from app.tasks import enforce_overdue_debt_block_task


class _FakeQuery:
    def __init__(self, debts):
        self._debts = debts
        self.options_calls = []

    def options(self, *args):
        self.options_calls.append(args)
        return self

    def filter(self, *_args, **_kwargs):
        return self

    def all(self):
        return self._debts


class _FakeSession:
    def __init__(self, debts):
        self.query_obj = _FakeQuery(debts)
        self.remove_calls = 0
        self.commit_calls = 0
        self.rollback_calls = 0
        self.added = []

    def query(self, *_args, **_kwargs):
        return self.query_obj

    def add(self, value):
        self.added.append(value)

    def commit(self):
        self.commit_calls += 1

    def rollback(self):
        self.rollback_calls += 1

    def remove(self):
        self.remove_calls += 1


def _make_user(*, user_id: str, role=UserRole.USER, approval_status=ApprovalStatus.APPROVED, devices=None):
    return SimpleNamespace(
        id=user_id,
        phone_number=f"+62812{user_id[-4:]}",
        approval_status=approval_status,
        role=role,
        is_active=True,
        is_unlimited_user=False,
        is_blocked=False,
        mikrotik_password="123456",
        mikrotik_server_name="router-a",
        devices=list(devices or []),
        blocked_reason=None,
        blocked_at=None,
        blocked_by_id=None,
    )


def _make_debt(user, amount_mb: int, due_date):
    return SimpleNamespace(user=user, amount_mb=amount_mb, due_date=due_date)


@pytest.fixture
def app():
    flask_app = Flask(__name__)
    flask_app.config.update(APP_PUBLIC_BASE_URL="https://lpsaring.babahdigital.net")
    return flask_app


@pytest.fixture
def overdue_context():
    today = datetime(2026, 3, 22, tzinfo=dt_timezone.utc)
    old_date = (today - timedelta(days=10)).date()

    regular_user = _make_user(
        user_id="user-0001",
        devices=[SimpleNamespace(mac_address="AA:BB:CC:DD:EE:FF", ip_address="172.16.2.10")],
    )
    komandan_user = _make_user(user_id="user-0002", role=UserRole.KOMANDAN)
    pending_user = _make_user(user_id="user-0003", approval_status=ApprovalStatus.PENDING_APPROVAL)

    debts = [
        _make_debt(regular_user, 1000, old_date),
        _make_debt(komandan_user, 500, old_date),
        _make_debt(pending_user, 2000, old_date),
    ]
    return today, debts, regular_user


def _settings_getter(overrides=None):
    values = {
        "ENABLE_OVERDUE_DEBT_BLOCK": "True",
        "ENABLE_MIKROTIK_OPERATIONS": "True",
        "MIKROTIK_BLOCKED_PROFILE": "inactive",
        "MIKROTIK_ADDRESS_LIST_BLOCKED": "blocked",
        "ENABLE_WHATSAPP_NOTIFICATIONS": "False",
        "MIKROTIK_ADDRESS_LIST_ACTIVE": "active",
        "MIKROTIK_ADDRESS_LIST_FUP": "fup",
        "MIKROTIK_ADDRESS_LIST_INACTIVE": "inactive",
        "MIKROTIK_ADDRESS_LIST_EXPIRED": "expired",
        "MIKROTIK_ADDRESS_LIST_HABIS": "habis",
    }
    values.update(overrides or {})
    return lambda key, default=None: values.get(key, default)


def _run_task(monkeypatch, app, fake_session, now_local, settings_overrides=None):
    @contextmanager
    def _fake_connection():
        yield SimpleNamespace()

    monkeypatch.setattr("app.tasks.create_app", lambda config_name=None: app)
    monkeypatch.setattr("app.tasks.db", SimpleNamespace(session=fake_session))
    monkeypatch.setattr("app.tasks.get_app_local_datetime", lambda: now_local)
    monkeypatch.setattr("app.tasks.settings_service.get_setting", _settings_getter(settings_overrides))
    monkeypatch.setattr("app.tasks.settings_service.get_ip_binding_type_setting", lambda *_args, **_kwargs: "blocked")
    monkeypatch.setattr("app.tasks.format_to_local_phone", lambda value: value)
    monkeypatch.setattr("app.tasks.lock_user_quota_row", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("app.tasks.snapshot_user_quota_state", lambda user: {"blocked": getattr(user, "is_blocked", False)})
    monkeypatch.setattr("app.tasks.append_quota_mutation_event", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("app.tasks.increment_metric", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("app.tasks.send_whatsapp_message", lambda *_args, **_kwargs: True)
    monkeypatch.setattr("app.tasks._handle_mikrotik_operation", lambda *_args, **_kwargs: (True, None))
    monkeypatch.setattr("app.tasks.get_mikrotik_connection", _fake_connection)
    monkeypatch.setattr("app.tasks.get_hotspot_host_usage_map", lambda *_args, **_kwargs: (True, {}, None))
    monkeypatch.setattr("app.tasks.upsert_ip_binding", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("app.tasks.upsert_address_list_entry", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("app.tasks.remove_address_list_entry", lambda *_args, **_kwargs: None)
    return enforce_overdue_debt_block_task.apply().get()


def test_selectinload_devices_no_detached_instance_error(app, monkeypatch, overdue_context):
    now_local, debts, regular_user = overdue_context
    fake_session = _FakeSession(debts)

    result = _run_task(monkeypatch, app, fake_session, now_local)

    assert result["checked"] == 3
    assert result["blocked"] == 1
    assert result["block_failed"] == 0
    assert regular_user.is_blocked is True
    assert fake_session.query_obj.options_calls


def test_counter_labels_non_user_role(app, monkeypatch, overdue_context):
    now_local, debts, _regular_user = overdue_context
    fake_session = _FakeSession(debts)

    result = _run_task(monkeypatch, app, fake_session, now_local)

    assert result["skipped_non_user_role"] == 1
    assert result["skipped_non_approved"] == 1


def test_enable_mikrotik_operations_guard(app, monkeypatch, overdue_context):
    now_local, debts, _regular_user = overdue_context
    fake_session = _FakeSession(debts)

    result = _run_task(
        monkeypatch,
        app,
        fake_session,
        now_local,
        settings_overrides={"ENABLE_MIKROTIK_OPERATIONS": "False"},
    )

    assert result == {"skipped": "mikrotik_disabled"}
    assert fake_session.commit_calls == 0


def test_session_cleanup_at_end(app, monkeypatch, overdue_context):
    now_local, debts, _regular_user = overdue_context
    fake_session = _FakeSession(debts)

    _run_task(monkeypatch, app, fake_session, now_local)

    assert fake_session.remove_calls == 1
