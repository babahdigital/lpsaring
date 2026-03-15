from __future__ import annotations

import sys
import uuid
from types import SimpleNamespace
from typing import cast

from flask import Flask

from app.infrastructure.db.models import User
from app.infrastructure.http.admin import user_management_routes


def _unwrap_decorators(func):
    current = func
    while hasattr(current, "__wrapped__"):
        current = current.__wrapped__
    return current


def _make_app() -> Flask:
    app = Flask(__name__)
    app.config["SECRET_KEY"] = "unit-test-secret"
    app.config["APP_PUBLIC_BASE_URL"] = "https://example.test"
    return app


def test_get_user_quota_history_passes_filter_params(monkeypatch):
    user_id = uuid.uuid4()
    target_user = SimpleNamespace(id=user_id, role="USER")
    captured: dict[str, object] = {}

    monkeypatch.setattr(user_management_routes, "db", SimpleNamespace(session=SimpleNamespace(get=lambda *_args: target_user)))
    monkeypatch.setattr(user_management_routes, "_deny_non_super_admin_target_access", lambda *_args: None)

    def _fake_payload(**kwargs):
        captured.update(kwargs)
        return {
            "items": [],
            "summary": {"page_items": 0},
            "filters": {"search": "lapangan", "label": "3 hari terakhir"},
            "total_items": 0,
            "page": 1,
            "items_per_page": 50,
        }

    monkeypatch.setattr(user_management_routes, "get_user_quota_history_payload", _fake_payload)

    app = _make_app()
    impl = _unwrap_decorators(user_management_routes.get_user_quota_history)

    with app.app_context(), app.test_request_context(
        f"/api/admin/users/{user_id}/quota-history?startDate=2026-03-13&endDate=2026-03-15&search=lapangan",
        method="GET",
    ):
        current_admin = cast(User, SimpleNamespace(id=uuid.uuid4(), is_super_admin_role=True))
        response, status = impl(current_admin=current_admin, user_id=user_id)

    assert status == 200
    assert captured["user"] is target_user
    assert captured["start_date"] == "2026-03-13"
    assert captured["end_date"] == "2026-03-15"
    assert captured["search"] == "lapangan"
    payload = response.get_json()
    assert payload["filters"]["label"] == "3 hari terakhir"


def test_get_user_quota_history_returns_400_for_invalid_filter(monkeypatch):
    user_id = uuid.uuid4()
    target_user = SimpleNamespace(id=user_id, role="USER")

    monkeypatch.setattr(user_management_routes, "db", SimpleNamespace(session=SimpleNamespace(get=lambda *_args: target_user)))
    monkeypatch.setattr(user_management_routes, "_deny_non_super_admin_target_access", lambda *_args: None)
    monkeypatch.setattr(
        user_management_routes,
        "get_user_quota_history_payload",
        lambda **_kwargs: (_ for _ in ()).throw(ValueError("Tanggal mulai tidak valid. Gunakan format YYYY-MM-DD.")),
    )

    app = _make_app()
    impl = _unwrap_decorators(user_management_routes.get_user_quota_history)

    with app.app_context(), app.test_request_context(
        f"/api/admin/users/{user_id}/quota-history?startDate=2026-99-99",
        method="GET",
    ):
        current_admin = cast(User, SimpleNamespace(id=uuid.uuid4(), is_super_admin_role=True))
        response, status = impl(current_admin=current_admin, user_id=user_id)

    assert status == 400
    assert "Tanggal mulai tidak valid" in response.get_json()["message"]


def test_export_user_quota_history_pdf_passes_filter_context(monkeypatch):
    user_id = uuid.uuid4()
    target_user = SimpleNamespace(id=user_id, role="USER", full_name="Ikhsan", phone_number="08123456789")
    captured: dict[str, object] = {}

    class _FakeHTML:
        def __init__(self, *, string: str, base_url: str):
            captured["html_string"] = string
            captured["base_url"] = base_url

        def write_pdf(self):
            return b"%PDF-test"

    monkeypatch.setitem(sys.modules, "weasyprint", SimpleNamespace(HTML=_FakeHTML))
    monkeypatch.setattr(user_management_routes, "db", SimpleNamespace(session=SimpleNamespace(get=lambda *_args: target_user)))
    monkeypatch.setattr(user_management_routes, "_deny_non_super_admin_target_access", lambda *_args: None)
    monkeypatch.setattr(
        user_management_routes,
        "get_user_quota_history_payload",
        lambda **_kwargs: {
            "items": [],
            "summary": {"page_items": 0, "total_net_purchased_mb": 0, "total_net_used_mb": 0, "first_event_at_display": None, "last_event_at_display": None},
            "filters": {
                "search": "manual",
                "label": "3 hari terakhir",
                "start_date_display": "13-03-2026",
                "end_date_display": "15-03-2026",
            },
            "total_items": 0,
            "page": 1,
            "items_per_page": 200,
        },
    )

    def _fake_render_template(template_name: str, **context):
        captured["template_name"] = template_name
        captured["context"] = context
        return "<html>ok</html>"

    monkeypatch.setattr(user_management_routes, "render_template", _fake_render_template)

    app = _make_app()
    impl = _unwrap_decorators(user_management_routes.export_user_quota_history_pdf)

    with app.app_context(), app.test_request_context(
        f"/api/admin/users/{user_id}/quota-history/export?format=pdf&startDate=2026-03-13&endDate=2026-03-15&search=manual",
        method="GET",
    ):
        current_admin = cast(User, SimpleNamespace(id=uuid.uuid4(), is_super_admin_role=True))
        response = impl(current_admin=current_admin, user_id=user_id)

    assert response.status_code == 200
    assert response.get_data() == b"%PDF-test"
    assert captured["template_name"] == "quota_history_report.html"
    assert captured["context"]["filters"]["search"] == "manual"
    assert captured["context"]["filters"]["label"] == "3 hari terakhir"