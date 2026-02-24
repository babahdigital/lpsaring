import pytest

from flask import Flask


@pytest.fixture()
def app():
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY="test-secret",
    )
    return app


def test_get_notification_message_renders_spintax_before_format(monkeypatch, app):
    from app.services import notification_service

    monkeypatch.setattr(
        notification_service,
        "_load_templates",
        lambda: {
            "auth_send_otp": "{Kode OTP Anda|OTP login Anda}: *{otp_code}*. Berlaku {otp_expiry_minutes} menit.",
        },
    )
    monkeypatch.setattr(
        notification_service,
        "get_app_links",
        lambda: {
            "user_app": "https://example.test/user",
            "admin_app": "https://example.test/admin",
            "mikrotik_login": "https://example.test/login",
            "admin_app_change_password": "https://example.test/admin/change-password",
        },
    )

    with app.app_context():
        message = notification_service.get_notification_message(
            "auth_send_otp", {"otp_code": "123456", "otp_expiry_minutes": 5}
        )

    assert "123456" in message
    assert "5" in message
    assert "Peringatan:" not in message


def test_get_notification_message_missing_placeholder_returns_warning(monkeypatch, app):
    from app.services import notification_service

    monkeypatch.setattr(
        notification_service,
        "_load_templates",
        lambda: {
            "t": "Halo {name} {missing}",
        },
    )
    monkeypatch.setattr(
        notification_service,
        "get_app_links",
        lambda: {},
    )

    with app.app_context():
        message = notification_service.get_notification_message("t", {"name": "X"})

    assert message.startswith("Peringatan:")


def test_purchase_success_with_invoice_accepts_status_url(monkeypatch, app):
    from app.services import notification_service

    monkeypatch.setattr(
        notification_service,
        "_load_templates",
        lambda: {
            "purchase_success_with_invoice": "OK {full_name} {order_id} {package_name} {package_price} {status_url}",
        },
    )
    monkeypatch.setattr(notification_service, "get_app_links", lambda: {})

    with app.app_context():
        message = notification_service.get_notification_message(
            "purchase_success_with_invoice",
            {
                "full_name": "User",
                "order_id": "BD-LPSR-TEST",
                "package_name": "Paket",
                "package_price": "Rp 10.000",
                "status_url": "https://example.test/payment/status?order_id=BD-LPSR-TEST&t=tok",
            },
        )

    assert "Peringatan:" not in message
    assert "payment/status" in message
