from types import SimpleNamespace
from typing import cast

from flask import Flask

from app.infrastructure.http import admin_routes
from app.infrastructure.db.models import User


def _unwrap_decorators(func):
    current = func
    while hasattr(current, "__wrapped__"):
        current = current.__wrapped__
    return current


def _fake_db():
    return SimpleNamespace(
        session=SimpleNamespace(remove=lambda: None),
        engine=SimpleNamespace(dispose=lambda: None),
    )


def _make_app() -> Flask:
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "postgresql://postgres:secret@localhost:5432/lpsaring"
    return app


def test_restore_backup_accepts_known_pg_restore_warning(monkeypatch, tmp_path):
    backup_file = tmp_path / "sample.dump"
    backup_file.write_text("dummy", encoding="utf-8")

    monkeypatch.setattr(admin_routes, "db", _fake_db())
    monkeypatch.setattr(admin_routes, "_get_backup_dir", lambda: str(tmp_path))
    monkeypatch.setattr(
        admin_routes.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=1,
            stderr='pg_restore: error: could not execute query: ERROR:  unrecognized configuration parameter "transaction_timeout"',
        ),
    )

    app = _make_app()
    restore_impl = _unwrap_decorators(admin_routes.restore_backup)

    with app.test_request_context(
        "/api/admin/backups/restore",
        method="POST",
        json={"filename": "sample.dump", "confirm": "RESTORE"},
    ):
        current_admin = cast(User, SimpleNamespace(id=1, username="tester"))
        response, status = restore_impl(current_admin=current_admin)

    assert status == 200
    assert response.get_json()["filename"] == "sample.dump"


def test_restore_backup_returns_500_for_unknown_pg_restore_error(monkeypatch, tmp_path):
    backup_file = tmp_path / "sample.dump"
    backup_file.write_text("dummy", encoding="utf-8")

    monkeypatch.setattr(admin_routes, "db", _fake_db())
    monkeypatch.setattr(admin_routes, "_get_backup_dir", lambda: str(tmp_path))
    monkeypatch.setattr(
        admin_routes.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=1,
            stderr="pg_restore: error: relation public.users does not exist",
        ),
    )

    app = _make_app()
    restore_impl = _unwrap_decorators(admin_routes.restore_backup)

    with app.test_request_context(
        "/api/admin/backups/restore",
        method="POST",
        json={"filename": "sample.dump", "confirm": "RESTORE"},
    ):
        current_admin = cast(User, SimpleNamespace(id=1, username="tester"))
        response, status = restore_impl(current_admin=current_admin)

    assert status == 500
    payload = response.get_json()
    assert payload["message"] == "Restore gagal dijalankan."
    assert "relation public.users" in payload["details"]


def test_restore_backup_sql_sanitizes_pg_dump_warning_lines(monkeypatch, tmp_path):
    backup_file = tmp_path / "sample.sql"
    backup_file.write_text(
        "pg_dump: warning: there are circular foreign-key constraints\n"
        "-- PostgreSQL database dump\n"
        "SELECT 1;\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(admin_routes, "db", _fake_db())
    monkeypatch.setattr(admin_routes, "_get_backup_dir", lambda: str(tmp_path))

    captured = {"cmd": None}

    def _fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return SimpleNamespace(returncode=0, stderr="")

    monkeypatch.setattr(admin_routes.subprocess, "run", _fake_run)

    app = _make_app()
    restore_impl = _unwrap_decorators(admin_routes.restore_backup)

    with app.test_request_context(
        "/api/admin/backups/restore",
        method="POST",
        json={"filename": "sample.sql", "confirm": "RESTORE"},
    ):
        current_admin = cast(User, SimpleNamespace(id=1, username="tester"))
        response, status = restore_impl(current_admin=current_admin)

    assert status == 200
    assert response.get_json()["filename"] == "sample.sql"
    assert isinstance(captured["cmd"], list)
    assert captured["cmd"] is not None
    assert captured["cmd"][-1].endswith(".sql")
    assert ".sanitized_" in captured["cmd"][-1]


def test_restore_backup_sql_replace_users_runs_preclean(monkeypatch, tmp_path):
    backup_file = tmp_path / "sample.sql"
    backup_file.write_text("SELECT 1;\n", encoding="utf-8")

    monkeypatch.setattr(admin_routes, "db", _fake_db())
    monkeypatch.setattr(admin_routes, "_get_backup_dir", lambda: str(tmp_path))

    captured_calls: list[list[str]] = []

    def _fake_run(cmd, **kwargs):
        captured_calls.append(cmd)
        return SimpleNamespace(returncode=0, stderr="")

    monkeypatch.setattr(admin_routes.subprocess, "run", _fake_run)

    app = _make_app()
    restore_impl = _unwrap_decorators(admin_routes.restore_backup)

    with app.test_request_context(
        "/api/admin/backups/restore",
        method="POST",
        json={"filename": "sample.sql", "confirm": "RESTORE", "restore_mode": "replace_users"},
    ):
        current_admin = cast(User, SimpleNamespace(id=1, username="tester"))
        response, status = restore_impl(current_admin=current_admin)

    assert status == 200
    assert response.get_json()["restore_mode"] == "replace_users"
    assert len(captured_calls) == 2
    assert captured_calls[0][0] == "psql"
    assert captured_calls[0][-2] == "-c"
    assert "TRUNCATE TABLE public.users" in captured_calls[0][-1]
    assert captured_calls[1][0] == "psql"
    assert captured_calls[1][-2] == "-f"
    assert captured_calls[1][-1].endswith("sample.sql")


def test_whatsapp_test_send_success(monkeypatch):
    monkeypatch.setattr(admin_routes, "send_whatsapp_message", lambda phone, message: True)

    app = _make_app()
    send_impl = _unwrap_decorators(admin_routes.send_whatsapp_test)

    with app.test_request_context(
        "/api/admin/whatsapp/test-send",
        method="POST",
        json={"phone_number": "08123456789", "message": "tes"},
    ):
        current_admin = cast(User, SimpleNamespace(id=1, username="tester"))
        response, status = send_impl(current_admin=current_admin)

    assert status == 200
    payload = response.get_json()
    assert payload["target"] == "08123456789"


def test_whatsapp_test_send_returns_400_when_gateway_fails(monkeypatch):
    monkeypatch.setattr(admin_routes, "send_whatsapp_message", lambda phone, message: False)

    app = _make_app()
    send_impl = _unwrap_decorators(admin_routes.send_whatsapp_test)

    with app.test_request_context(
        "/api/admin/whatsapp/test-send",
        method="POST",
        json={"phone_number": "08123456789", "message": "tes"},
    ):
        current_admin = cast(User, SimpleNamespace(id=1, username="tester"))
        response, status = send_impl(current_admin=current_admin)

    assert status == 400
    assert "Pengiriman WhatsApp gagal" in response.get_json()["message"]
