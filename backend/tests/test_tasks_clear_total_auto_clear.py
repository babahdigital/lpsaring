from __future__ import annotations

import uuid as _uuid
from dataclasses import dataclass, field
from flask import Flask

import app.tasks as tasks


@dataclass
class _UserRow:
    phone_number: str
    # Sprint 12 BUG-3: task pakai snapshot id untuk DELETE WHERE id = ANY(...).
    id: _uuid.UUID = field(default_factory=_uuid.uuid4)


class _FakeQuery:
    def __init__(self, *, rows=None, first_row=None):
        self._rows = list(rows or [])
        self._first_row = first_row
        self.delete_calls: list[bool] = []

    def order_by(self, *_args, **_kwargs):
        return self

    def filter(self, *_args, **_kwargs):
        # Sprint 12 BUG-3: task sekarang pakai DELETE WHERE id IN (...).
        return self

    def with_for_update(self, *_args, **_kwargs):
        # Sprint 12 BUG-3: task sekarang pakai SELECT ... FOR UPDATE.
        return self

    def first(self):
        return self._first_row

    def all(self):
        return list(self._rows)

    def delete(self, *, synchronize_session=False):
        self.delete_calls.append(bool(synchronize_session))
        return len(self._rows)


class _FakeDialect:
    def __init__(self, name: str):
        self.name = name


class _FakeBind:
    def __init__(self, dialect_name: str):
        self.dialect = _FakeDialect(dialect_name)


class _FakeSession:
    def __init__(self, *, users, latest_submission, bind, get_bind_result):
        self._users = list(users)
        self._latest_submission = latest_submission
        self.bind = bind
        self._get_bind_result = get_bind_result

        self.user_query = _FakeQuery(rows=self._users)
        self.submission_query = _FakeQuery(first_row=self._latest_submission)

        self.executed_sql: list[str] = []
        self.committed = False

    def query(self, model):
        model_name = getattr(model, "__name__", "")
        if model_name == "User":
            return self.user_query
        return self.submission_query

    def get_bind(self):
        if isinstance(self._get_bind_result, Exception):
            raise self._get_bind_result
        return self._get_bind_result

    def execute(self, statement, params=None):
        # Sprint 12 BUG-3: task sekarang execute dengan params (pg_advisory_xact_lock,
        # UPDATE ... WHERE id = ANY(:ids)). Fake hanya record SQL string.
        self.executed_sql.append(str(statement))

    def commit(self):
        self.committed = True


class _FakeDb:
    def __init__(self, session: _FakeSession):
        self.session = session


def _make_app() -> Flask:
    app = Flask(__name__)
    app.config["SECRET_KEY"] = "unit-test-secret"
    app.config["UPDATE_ENABLE_SYNC"] = True
    app.config["UPDATE_ALLOW_DESTRUCTIVE_AUTO_CLEAR"] = True
    app.config["UPDATE_CLEAR_TOTAL_AFTER_DAYS"] = 3
    app.config["ENABLE_MIKROTIK_OPERATIONS"] = False
    return app


def test_clear_total_auto_clear_uses_scoped_delete_when_get_bind_postgresql(monkeypatch):
    app = _make_app()
    users = [_UserRow(phone_number="0811"), _UserRow(phone_number="0812")]
    session = _FakeSession(
        users=users,
        latest_submission=None,
        bind=None,
        get_bind_result=_FakeBind("postgresql+psycopg2"),
    )

    monkeypatch.setattr(tasks, "create_app", lambda: app)
    monkeypatch.setattr(tasks, "db", _FakeDb(session))

    result = tasks.clear_total_if_no_update_submission_task.run()

    assert result["success"] is True
    assert result["cleared_users"] == 2
    # Sprint 12 BUG-3: TRUNCATE diganti DELETE WHERE id = ANY(...) supaya
    # user baru yang lolos advisory lock tidak ke-clear secara tidak sengaja.
    assert any("DELETE FROM users WHERE id = ANY" in sql for sql in session.executed_sql)
    assert any("pg_advisory_xact_lock" in sql for sql in session.executed_sql)
    assert all("TRUNCATE TABLE users" not in sql for sql in session.executed_sql)
    assert session.user_query.delete_calls == []
    assert session.committed is True


def test_clear_total_auto_clear_fallback_uses_set_based_delete(monkeypatch):
    app = _make_app()
    users = [_UserRow(phone_number="0811"), _UserRow(phone_number="0812"), _UserRow(phone_number="0813")]
    session = _FakeSession(
        users=users,
        latest_submission=None,
        bind=_FakeBind("sqlite"),
        get_bind_result=_FakeBind("sqlite"),
    )

    monkeypatch.setattr(tasks, "create_app", lambda: app)
    monkeypatch.setattr(tasks, "db", _FakeDb(session))

    result = tasks.clear_total_if_no_update_submission_task.run()

    assert result["success"] is True
    assert result["cleared_users"] == 3
    assert any("UPDATE users SET approved_by_id = NULL" in sql for sql in session.executed_sql)
    assert session.user_query.delete_calls == [False]
    assert all("TRUNCATE TABLE users" not in sql for sql in session.executed_sql)
    assert session.committed is True


def test_clear_total_auto_clear_skips_when_destructive_guard_disabled(monkeypatch):
    app = _make_app()
    app.config["UPDATE_ALLOW_DESTRUCTIVE_AUTO_CLEAR"] = False
    session = _FakeSession(
        users=[_UserRow(phone_number="0811")],
        latest_submission=None,
        bind=_FakeBind("postgresql"),
        get_bind_result=_FakeBind("postgresql"),
    )

    monkeypatch.setattr(tasks, "create_app", lambda: app)
    monkeypatch.setattr(tasks, "db", _FakeDb(session))

    result = tasks.clear_total_if_no_update_submission_task.run()

    assert result["success"] is True
    assert result["skipped"] is True
    assert result["reason"] == "destructive_guard_disabled"
    assert session.executed_sql == []
    assert session.user_query.delete_calls == []
    assert session.committed is False
