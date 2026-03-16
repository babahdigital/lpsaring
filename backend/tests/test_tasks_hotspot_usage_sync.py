from __future__ import annotations

from types import SimpleNamespace

from flask import Flask

import app.tasks as tasks


class _FakeRedis:
    def __init__(self, values: dict[str, object] | None = None):
        self.values = dict(values or {})
        self.set_calls: list[tuple[str, object, bool, object]] = []
        self.delete_calls: list[str] = []

    def get(self, key: str):
        return self.values.get(key)

    def set(self, key: str, value, nx: bool = False, ex=None):
        self.set_calls.append((key, value, nx, ex))
        if nx and key in self.values:
            return False
        self.values[key] = value
        return True

    def delete(self, *keys: str):
        removed = 0
        for key in keys:
            self.delete_calls.append(key)
            if key in self.values:
                del self.values[key]
                removed += 1
        return removed


def _make_app(redis_client: _FakeRedis) -> Flask:
    app = Flask(__name__)
    app.config.update(SECRET_KEY="unit-test-secret")
    app.redis_client_otp = redis_client
    return app


def test_load_quota_sync_interval_seconds_releases_session(monkeypatch):
    removed = []

    monkeypatch.setattr(tasks.settings_service, "get_setting_as_int", lambda _key, default=0: 180)
    monkeypatch.setattr(tasks, "db", SimpleNamespace(session=SimpleNamespace(remove=lambda: removed.append(True))))

    assert tasks._load_quota_sync_interval_seconds() == 180
    assert removed == [True]


def test_has_other_active_celery_task_ignores_current_task(monkeypatch):
    class _FakeInspector:
        def active(self):
            return {
                "worker@1": [
                    {"name": "sync_hotspot_usage_task", "id": "current-task"},
                ]
            }

    monkeypatch.setattr(
        tasks.celery_app,
        "control",
        SimpleNamespace(inspect=lambda timeout=1.0: _FakeInspector()),
    )

    assert tasks._has_other_active_celery_task(
        "sync_hotspot_usage_task",
        current_task_id="current-task",
    ) is False


def test_sync_hotspot_usage_task_reclaims_stale_lock_without_other_active_task(monkeypatch):
    redis_client = _FakeRedis({tasks._QUOTA_SYNC_LOCK_KEY: "stale-task"})
    app = _make_app(redis_client)
    sync_calls: list[bool] = []

    monkeypatch.setattr(tasks, "create_app", lambda: app)
    monkeypatch.setattr(tasks, "_load_quota_sync_interval_seconds", lambda: 300)
    monkeypatch.setattr(tasks, "_has_other_active_celery_task", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(
        tasks,
        "sync_hotspot_usage_and_profiles",
        lambda: sync_calls.append(True) or {"processed": 1, "failed": 0},
    )
    tasks.sync_hotspot_usage_task.push_request(id="current-task", retries=0)
    try:
        tasks.sync_hotspot_usage_task.run()
    finally:
        tasks.sync_hotspot_usage_task.pop_request()

    assert sync_calls == [True]
    assert redis_client.delete_calls == [tasks._QUOTA_SYNC_LOCK_KEY, tasks._QUOTA_SYNC_LOCK_KEY]
    assert tasks._QUOTA_SYNC_LOCK_KEY not in redis_client.values
    assert isinstance(redis_client.values[tasks._QUOTA_SYNC_LAST_RUN_KEY], int)


def test_sync_hotspot_usage_task_keeps_skip_when_other_active_task_exists(monkeypatch):
    redis_client = _FakeRedis({tasks._QUOTA_SYNC_LOCK_KEY: "other-task"})
    app = _make_app(redis_client)
    sync_calls: list[bool] = []

    monkeypatch.setattr(tasks, "create_app", lambda: app)
    monkeypatch.setattr(tasks, "_load_quota_sync_interval_seconds", lambda: 300)
    monkeypatch.setattr(tasks, "_has_other_active_celery_task", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(
        tasks,
        "sync_hotspot_usage_and_profiles",
        lambda: sync_calls.append(True) or {"processed": 1, "failed": 0},
    )
    tasks.sync_hotspot_usage_task.push_request(id="current-task", retries=0)
    try:
        tasks.sync_hotspot_usage_task.run()
    finally:
        tasks.sync_hotspot_usage_task.pop_request()

    assert sync_calls == []
    assert redis_client.delete_calls == []
    assert redis_client.values[tasks._QUOTA_SYNC_LOCK_KEY] == "other-task"
    assert tasks._QUOTA_SYNC_LAST_RUN_KEY not in redis_client.values