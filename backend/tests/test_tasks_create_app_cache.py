import app.tasks as tasks


def test_tasks_create_app_caches_default_app_per_process(monkeypatch):
    calls = {"count": 0}
    tasks._TASK_APP_CACHE.clear()

    def _factory(config_name=None):
        calls["count"] += 1
        return {"config_name": config_name, "instance": calls["count"]}

    monkeypatch.setattr(tasks, "_flask_create_app", _factory)

    first = tasks.create_app()
    second = tasks.create_app()

    assert first is second
    assert calls["count"] == 1


def test_tasks_create_app_caches_separately_per_config_name(monkeypatch):
    calls = {"count": 0}
    tasks._TASK_APP_CACHE.clear()

    def _factory(config_name=None):
        calls["count"] += 1
        return {"config_name": config_name, "instance": calls["count"]}

    monkeypatch.setattr(tasks, "_flask_create_app", _factory)

    default_app = tasks.create_app()
    testing_app = tasks.create_app("testing")
    testing_app_again = tasks.create_app("testing")

    assert default_app is not testing_app
    assert testing_app is testing_app_again
    assert calls["count"] == 2