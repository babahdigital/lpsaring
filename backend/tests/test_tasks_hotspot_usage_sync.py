from __future__ import annotations

from types import SimpleNamespace

import app.tasks as tasks


def test_load_quota_sync_interval_seconds_releases_session(monkeypatch):
    removed = []

    monkeypatch.setattr(tasks.settings_service, "get_setting_as_int", lambda _key, default=0: 180)
    monkeypatch.setattr(tasks, "db", SimpleNamespace(session=SimpleNamespace(remove=lambda: removed.append(True))))

    assert tasks._load_quota_sync_interval_seconds() == 180
    assert removed == [True]