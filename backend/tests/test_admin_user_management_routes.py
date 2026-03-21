from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
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


class _FakeSession:
    def __init__(self, *, users_by_id):
        self._users_by_id = users_by_id
        self.commit_calls = 0
        self.rollback_calls = 0
        self.refresh_calls = 0

    def get(self, model, user_id):
        if model is User:
            return self._users_by_id.get(user_id)
        return None

    def commit(self):
        self.commit_calls += 1

    def rollback(self):
        self.rollback_calls += 1

    def refresh(self, _obj):
        self.refresh_calls += 1
        raise AssertionError("update_user_by_admin should reload the user instead of refreshing the returned instance")


def _make_app() -> Flask:
    return Flask(__name__)


def test_update_user_by_admin_serializes_reloaded_user_after_commit(monkeypatch):
    user_id = uuid.uuid4()
    stale_user = SimpleNamespace(
        id=user_id,
        phone_number="081234567890",
        full_name="Sebelum Update",
        role=SimpleNamespace(value="USER"),
    )
    reloaded_user = SimpleNamespace(
        id=user_id,
        phone_number="081234567890",
        full_name="Sesudah Update",
        role=SimpleNamespace(value="USER"),
    )
    fake_session = _FakeSession(users_by_id={user_id: stale_user})

    monkeypatch.setattr(user_management_routes, "db", SimpleNamespace(session=fake_session))
    monkeypatch.setattr(user_management_routes, "_deny_non_super_admin_target_access", lambda *_args, **_kwargs: None)

    def _fake_update_user(_user, _current_admin, _payload):
        fake_session._users_by_id[user_id] = reloaded_user
        return True, "ok", SimpleNamespace(id=user_id)

    monkeypatch.setattr(
        user_management_routes.user_profile_service,
        "update_user_by_admin_comprehensive",
        _fake_update_user,
    )

    class _FakeUserResponseSchema:
        @staticmethod
        def from_orm(user):
            return SimpleNamespace(
                model_dump=lambda: {
                    "id": str(user.id),
                    "phone_number": user.phone_number,
                    "full_name": user.full_name,
                }
            )

    monkeypatch.setattr(user_management_routes, "UserResponseSchema", _FakeUserResponseSchema)

    app = _make_app()
    impl = _unwrap_decorators(user_management_routes.update_user_by_admin)

    with app.test_request_context(
        f"/api/admin/users/{user_id}",
        method="PUT",
        json={"debt_add_mb": 1024},
    ):
        current_admin = cast(User, SimpleNamespace(is_super_admin_role=True))
        response, status = impl(current_admin=current_admin, user_id=user_id)

    assert status == 200
    assert response.get_json() == {
        "id": str(user_id),
        "phone_number": "081234567890",
        "full_name": "Sesudah Update",
    }
    assert fake_session.commit_calls == 1
    assert fake_session.rollback_calls == 0
    assert fake_session.refresh_calls == 0


def test_update_user_by_admin_validates_and_normalizes_debt_date(monkeypatch):
    user_id = uuid.uuid4()
    fake_user = SimpleNamespace(id=user_id, role=SimpleNamespace(value="USER"), is_admin_role=False)
    fake_session = _FakeSession(users_by_id={user_id: fake_user})

    monkeypatch.setattr(user_management_routes, "db", SimpleNamespace(session=fake_session))
    monkeypatch.setattr(user_management_routes, "_deny_non_super_admin_target_access", lambda *_args, **_kwargs: None)

    captured_payload = {}

    def _fake_update_user(_user, _current_admin, payload):
        captured_payload.update(payload)
        return True, "ok", SimpleNamespace(id=user_id)

    monkeypatch.setattr(
        user_management_routes.user_profile_service,
        "update_user_by_admin_comprehensive",
        _fake_update_user,
    )

    class _FakeUserResponseSchema:
        @staticmethod
        def from_orm(user):
            return SimpleNamespace(model_dump=lambda: {"id": str(user.id)})

    monkeypatch.setattr(user_management_routes, "UserResponseSchema", _FakeUserResponseSchema)

    app = _make_app()
    impl = _unwrap_decorators(user_management_routes.update_user_by_admin)

    with app.test_request_context(
        f"/api/admin/users/{user_id}",
        method="PUT",
        json={"debt_add_mb": 1024, "debt_date": "2026-03-21"},
    ):
        current_admin = cast(User, SimpleNamespace(is_super_admin_role=True))
        _response, status = impl(current_admin=current_admin, user_id=user_id)

    assert status == 200
    assert captured_payload["debt_add_mb"] == 1024
    assert captured_payload["debt_date"] == date(2026, 3, 21)
    assert "debt_due_date" not in captured_payload


def test_update_user_by_admin_rejects_invalid_debt_date(monkeypatch):
    user_id = uuid.uuid4()
    fake_user = SimpleNamespace(id=user_id, role=SimpleNamespace(value="USER"), is_admin_role=False)
    fake_session = _FakeSession(users_by_id={user_id: fake_user})

    monkeypatch.setattr(user_management_routes, "db", SimpleNamespace(session=fake_session))
    monkeypatch.setattr(user_management_routes, "_deny_non_super_admin_target_access", lambda *_args, **_kwargs: None)

    app = _make_app()
    impl = _unwrap_decorators(user_management_routes.update_user_by_admin)

    with app.test_request_context(
        f"/api/admin/users/{user_id}",
        method="PUT",
        json={"debt_add_mb": 1024, "debt_date": "21/03/2026"},
    ):
        current_admin = cast(User, SimpleNamespace(is_super_admin_role=True))
        response, status = impl(current_admin=current_admin, user_id=user_id)

    assert status == 400
    body = response.get_json()
    assert body["message"] == "Data tidak valid."
    assert fake_session.rollback_calls == 1


def test_serialize_public_update_submission_adds_display_dates():
    created_at = datetime(2026, 3, 21, 1, 2, 3, tzinfo=timezone.utc)
    processed_at = datetime(2026, 3, 21, 4, 5, 6, tzinfo=timezone.utc)
    item = SimpleNamespace(
        id=uuid.uuid4(),
        full_name="Naru",
        role="USER",
        blok="A",
        kamar="1",
        tamping_type=None,
        phone_number="081234567890",
        source_ip="10.0.0.1",
        approval_status="PENDING",
        processed_by_user_id=None,
        processed_at=processed_at,
        rejection_reason=None,
        created_at=created_at,
    )

    payload = user_management_routes._serialize_public_update_submission(item)

    assert payload["processed_at"] == processed_at.isoformat()
    assert payload["created_at"] == created_at.isoformat()
    assert payload["processed_at_display"] == "21-03-2026 12:05:06"
    assert payload["created_at_display"] == "21-03-2026 09:02:03"


def test_get_user_detail_summary_returns_operational_payload(monkeypatch):
    user_id = uuid.uuid4()
    fake_user = SimpleNamespace(id=user_id, role=SimpleNamespace(value="USER"), is_admin_role=False)
    fake_session = _FakeSession(users_by_id={user_id: fake_user})

    monkeypatch.setattr(user_management_routes, "db", SimpleNamespace(session=fake_session))
    monkeypatch.setattr(user_management_routes, "_deny_non_super_admin_target_access", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        user_management_routes,
        "_get_user_mikrotik_status_payload",
        lambda _user: {
            "live_available": True,
            "exists_on_mikrotik": True,
            "message": "Data live MikroTik berhasil dimuat.",
            "reason": None,
        },
    )
    monkeypatch.setattr(
        user_management_routes,
        "_build_user_detail_report_context",
        lambda _user, mikrotik_status=None: {
            "profile_display_name": "default",
            "profile_source": "Live MikroTik",
            "mikrotik_account_label": "Terverifikasi live di MikroTik",
            "mikrotik_account_hint": "Akun hotspot ditemukan dan statusnya dibaca langsung dari MikroTik.",
            "access_status_label": "Layanan aktif",
            "access_status_hint": "Akun aktif dan masih memiliki kuota.",
            "access_status_tone": "success",
            "device_count": 2,
            "device_count_label": "2 perangkat",
            "last_login_label": "22-03-2026 08:10:00",
            "debt_auto_mb": 0.0,
            "debt_manual_mb": 0,
            "debt_total_mb": 0.0,
            "open_debt_items": 0,
            "recent_purchases": [{
                "order_id": "ORD-1",
                "package_name": "Paket Hemat",
                "amount_display": "Rp 20.000",
                "paid_at_display": "22-03-2026 07:00:00",
                "payment_method": "qris",
            }],
            "purchase_count_30d": 1,
            "purchase_total_amount_30d": 20000,
            "purchase_total_amount_30d_display": "Rp 20.000",
            "admin_whatsapp_default": "+6282211111111",
        },
    )

    app = _make_app()
    impl = _unwrap_decorators(user_management_routes.get_user_detail_summary)

    with app.test_request_context(f"/api/admin/users/{user_id}/detail-summary", method="GET"):
        current_admin = cast(User, SimpleNamespace(is_super_admin_role=True))
        response, status = impl(current_admin=current_admin, user_id=user_id)

    assert status == 200
    payload = response.get_json()
    assert payload["profile_display_name"] == "default"
    assert payload["mikrotik"]["live_available"] is True
    assert payload["debt"]["total_mb"] == 0.0
    assert payload["recent_purchases"][0]["package_name"] == "Paket Hemat"
    assert payload["admin_whatsapp_default"] == "+6282211111111"


def test_send_user_detail_report_whatsapp_queues_pdf(monkeypatch):
    user_id = uuid.uuid4()
    fake_user = SimpleNamespace(
        id=user_id,
        role=SimpleNamespace(value="USER"),
        is_admin_role=False,
        phone_number="082213631573",
        full_name="Bobby Dermawan",
    )
    fake_session = _FakeSession(users_by_id={user_id: fake_user})
    queued = {}

    class _FakeTask:
        def delay(self, *args):
            queued["args"] = args

    monkeypatch.setattr(user_management_routes, "db", SimpleNamespace(session=fake_session))
    monkeypatch.setattr(user_management_routes, "_deny_non_super_admin_target_access", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(user_management_routes, "_get_user_mikrotik_status_payload", lambda _user: {"live_available": True, "exists_on_mikrotik": True, "message": "ok"})
    monkeypatch.setattr(
        user_management_routes,
        "_build_user_detail_report_context",
        lambda _user, mikrotik_status=None: {
            "access_status_label": "Layanan aktif",
            "mikrotik_account_label": "Terverifikasi live di MikroTik",
            "profile_display_name": "default",
            "device_count_label": "1 perangkat",
            "last_login_label": "22-03-2026 08:00:00",
            "debt_summary_line": "",
            "recent_purchase_summary_line": "",
        },
    )
    monkeypatch.setattr(user_management_routes, "_resolve_public_base_url", lambda: "https://example.test")
    monkeypatch.setattr(user_management_routes, "generate_temp_user_detail_report_token", lambda _user_id: "temp-detail-token")
    monkeypatch.setattr(user_management_routes, "get_notification_message", lambda _name, context: f"CAPTION {context['detail_pdf_url']}")
    monkeypatch.setattr(user_management_routes, "normalize_to_e164", lambda raw: "+6282213631573")
    monkeypatch.setattr(user_management_routes, "send_whatsapp_invoice_task", _FakeTask())

    app = _make_app()
    impl = _unwrap_decorators(user_management_routes.send_user_detail_report_whatsapp)

    with app.test_request_context(
        f"/api/admin/users/{user_id}/detail-report/send-whatsapp",
        method="POST",
        json={"recipient_phone": "082213631573"},
    ):
        current_admin = cast(User, SimpleNamespace(id=uuid.uuid4(), is_super_admin_role=True))
        response, status = impl(current_admin=current_admin, user_id=user_id)

    assert status == 200
    payload = response.get_json()
    assert payload == {"message": "Laporan detail pengguna berhasil diantrikan ke WhatsApp.", "queued": True}
    assert queued["args"][0] == "+6282213631573"
    assert queued["args"][2] == "https://example.test/api/admin/users/detail-report/temp/temp-detail-token.pdf"
    assert queued["args"][5] is None
    assert queued["args"][6] == "detail_report"
