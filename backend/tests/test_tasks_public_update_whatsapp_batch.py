from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from flask import Flask

import app.tasks as tasks


@dataclass
class _Submission:
    full_name: str
    phone_number: str
    role: str = "KOMANDAN"
    blok: str = "A"
    kamar: str = "Kamar_1"
    created_at: datetime = datetime.now(timezone.utc)
    whatsapp_notify_attempts: int = 0
    whatsapp_notified_at: datetime | None = None
    whatsapp_notify_last_error: str | None = None


class _FakeQuery:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return list(self._rows)


class _FakeSession:
    def __init__(self, rows):
        self.rows = rows
        self.committed = False

    def query(self, _model):
        return _FakeQuery(self.rows)

    def commit(self):
        self.committed = True


class _FakeDb:
    def __init__(self, rows):
        self.session = _FakeSession(rows)


def _make_app() -> Flask:
    app = Flask(__name__)
    app.config["SECRET_KEY"] = "unit-test-secret"
    app.config["UPDATE_ENABLE_SYNC"] = True
    app.config["UPDATE_WHATSAPP_BATCH_SIZE"] = 3
    app.config[
        "UPDATE_WHATSAPP_IMPORT_MESSAGE_TEMPLATE"
    ] = "Halo {full_name}, data pemutakhiran Anda sudah kami terima dan sedang diproses."
    return app


def test_send_public_update_submission_whatsapp_batch_limits_to_3_numbers(monkeypatch):
    app = _make_app()
    monkeypatch.setattr(tasks, "create_app", lambda: app)
    monkeypatch.setattr(tasks.settings_service, "get_setting", lambda key, default=None: "True")

    base_time = datetime.now(timezone.utc)
    rows = [
        _Submission(full_name="A", phone_number="0811", created_at=base_time - timedelta(minutes=5)),
        _Submission(full_name="B", phone_number="0812", created_at=base_time - timedelta(minutes=4)),
        _Submission(full_name="C", phone_number="0813", created_at=base_time - timedelta(minutes=3)),
        _Submission(full_name="D", phone_number="0814", created_at=base_time - timedelta(minutes=2)),
        _Submission(full_name="E", phone_number="0815", created_at=base_time - timedelta(minutes=1)),
    ]

    fake_db = _FakeDb(rows)
    monkeypatch.setattr(tasks, "db", fake_db)

    sent_targets: list[str] = []

    def _fake_send(phone: str, message: str) -> bool:
        sent_targets.append(phone)
        return True

    monkeypatch.setattr(tasks, "send_whatsapp_message", _fake_send)

    result = tasks.send_public_update_submission_whatsapp_batch_task.run()

    assert result["success"] is True
    assert result["sent_numbers"] == 3
    assert len(sent_targets) == 3
    assert fake_db.session.committed is True

    sent_rows = [row for row in rows if row.whatsapp_notified_at is not None]
    unsent_rows = [row for row in rows if row.whatsapp_notified_at is None]
    assert len(sent_rows) == 3
    assert len(unsent_rows) == 2


def test_send_public_update_submission_whatsapp_batch_deduplicates_same_number(monkeypatch):
    app = _make_app()
    monkeypatch.setattr(tasks, "create_app", lambda: app)
    monkeypatch.setattr(tasks.settings_service, "get_setting", lambda key, default=None: "True")

    base_time = datetime.now(timezone.utc)
    rows = [
        _Submission(full_name="A", phone_number="0811", created_at=base_time - timedelta(minutes=3)),
        _Submission(full_name="A2", phone_number="+62 811", created_at=base_time - timedelta(minutes=2)),
        _Submission(full_name="B", phone_number="0812", created_at=base_time - timedelta(minutes=1)),
    ]

    fake_db = _FakeDb(rows)
    monkeypatch.setattr(tasks, "db", fake_db)

    sent_targets: list[str] = []

    def _fake_send(phone: str, message: str) -> bool:
        sent_targets.append(phone)
        return True

    monkeypatch.setattr(tasks, "send_whatsapp_message", _fake_send)

    result = tasks.send_public_update_submission_whatsapp_batch_task.run()

    assert result["success"] is True
    assert result["sent_numbers"] == 2
    assert len(sent_targets) == 2
    assert all(row.whatsapp_notified_at is not None for row in rows)


def test_send_public_update_submission_whatsapp_batch_skips_when_sync_disabled(monkeypatch):
    app = _make_app()
    app.config["UPDATE_ENABLE_SYNC"] = False

    monkeypatch.setattr(tasks, "create_app", lambda: app)
    monkeypatch.setattr(tasks.settings_service, "get_setting", lambda key, default=None: "True")

    rows = [_Submission(full_name="A", phone_number="0811")]
    fake_db = _FakeDb(rows)
    monkeypatch.setattr(tasks, "db", fake_db)

    called = {"value": False}

    def _fake_send(phone: str, message: str) -> bool:
        called["value"] = True
        return True

    monkeypatch.setattr(tasks, "send_whatsapp_message", _fake_send)

    result = tasks.send_public_update_submission_whatsapp_batch_task.run()

    assert result["success"] is True
    assert result["skipped"] is True
    assert result["reason"] == "update_sync_disabled"
    assert called["value"] is False
