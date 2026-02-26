from __future__ import annotations

from flask import Flask

import app.tasks as tasks


def _make_app() -> Flask:
    app = Flask(__name__)
    app.config["SECRET_KEY"] = "unit-test-secret"
    return app


def test_sync_unauthorized_hosts_task_runs_apply(monkeypatch):
    app = _make_app()

    monkeypatch.setattr(tasks, "create_app", lambda: app)
    monkeypatch.setattr(tasks.settings_service, "get_setting", lambda key, default=None: "True")

    captured = {}

    def _fake_main(*, args=None, standalone_mode=True):
        captured["args"] = list(args or [])
        captured["standalone_mode"] = standalone_mode

    monkeypatch.setattr(tasks.sync_unauthorized_hosts_command, "main", _fake_main)

    tasks.sync_unauthorized_hosts_task.run()

    assert captured["args"] == ["--apply"]
    assert captured["standalone_mode"] is False


def test_sync_unauthorized_hosts_task_skips_when_mikrotik_disabled(monkeypatch):
    app = _make_app()

    monkeypatch.setattr(tasks, "create_app", lambda: app)
    monkeypatch.setattr(tasks.settings_service, "get_setting", lambda key, default=None: "False")

    called = {"value": False}

    def _fake_main(*, args=None, standalone_mode=True):
        called["value"] = True

    monkeypatch.setattr(tasks.sync_unauthorized_hosts_command, "main", _fake_main)

    tasks.sync_unauthorized_hosts_task.run()

    assert called["value"] is False
