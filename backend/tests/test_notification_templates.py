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


def test_user_debt_report_with_pdf_accepts_summary_and_pdf_url(monkeypatch, app):
    from app.services import notification_service

    monkeypatch.setattr(
        notification_service,
        "_load_templates",
        lambda: {
            "user_debt_report_with_pdf": "Debt {full_name} {total_manual_debt_gb} {total_manual_debt_amount_display} {open_items} {debt_detail_lines} {debt_pdf_url}",
        },
    )
    monkeypatch.setattr(notification_service, "get_app_links", lambda: {})

    with app.app_context():
        message = notification_service.get_notification_message(
            "user_debt_report_with_pdf",
            {
                "full_name": "User",
                "total_manual_debt_gb": "40.00 GB",
                "total_manual_debt_amount_display": "Rp 400.000",
                "open_items": 2,
                "debt_detail_lines": "1. 31 Mar 2026 — 20.00 GB | Rp 200.000",
                "debt_pdf_url": "https://example.test/api/admin/users/debts/temp/token.pdf",
            },
        )

    assert "Peringatan:" not in message
    assert "40.00 GB" in message
    assert "debts/temp/token.pdf" in message


def test_temp_debt_report_token_roundtrip(monkeypatch, app):
    from app.services import notification_service

    with app.app_context():
        token = notification_service.generate_temp_debt_report_token("user-123")
        resolved = notification_service.verify_temp_debt_report_token(token, max_age_seconds=3600)

    assert resolved == "user-123"


def test_temp_debt_settlement_receipt_token_roundtrip(monkeypatch, app):
    from app.services import notification_service

    with app.app_context():
        token = notification_service.generate_temp_debt_settlement_receipt_token("entry-123")
        resolved = notification_service.verify_temp_debt_settlement_receipt_token(token, max_age_seconds=3600)

    assert resolved == "entry-123"


def test_user_debt_partial_payment_accepts_receipt_fields(monkeypatch, app):
    from app.services import notification_service

    monkeypatch.setattr(
        notification_service,
        "_load_templates",
        lambda: {
            "user_debt_partial_payment": "Debt {full_name} {payment_channel_label} {paid_manual_debt_amount_display} {paid_total_debt_gb} {paid_total_debt_amount_display} {receipt_url}",
        },
    )
    monkeypatch.setattr(notification_service, "get_app_links", lambda: {})

    with app.app_context():
        message = notification_service.get_notification_message(
            "user_debt_partial_payment",
            {
                "full_name": "User",
                "payment_channel_label": "Pelunasan manual oleh Admin",
                "paid_manual_debt_amount_display": "Rp 25.000",
                "paid_total_debt_gb": "2.00 GB",
                "paid_total_debt_amount_display": "Rp 25.000",
                "receipt_url": "https://example.test/api/admin/users/debt-settlements/temp/token.pdf",
            },
        )

    assert "Peringatan:" not in message
    assert "debt-settlements/temp/token.pdf" in message


def test_user_manual_debt_reminder_accepts_detail_and_invoice_fields(monkeypatch, app):
    from app.services import notification_service

    monkeypatch.setattr(
        notification_service,
        "_load_templates",
        lambda: {
            "user_manual_debt_reminder_1day": "Reminder {full_name} {debt_gb} {debt_amount_display} {due_date} {total_manual_debt_gb} {total_manual_debt_amount_display} {open_items} {debt_detail_lines} {debt_invoice_url}",
        },
    )
    monkeypatch.setattr(notification_service, "get_app_links", lambda: {})

    with app.app_context():
        message = notification_service.get_notification_message(
            "user_manual_debt_reminder_1day",
            {
                "full_name": "User",
                "debt_gb": "10.00 GB",
                "debt_amount_display": "Rp 100.000",
                "due_date": "31-03-2026",
                "total_manual_debt_gb": "30.00 GB",
                "total_manual_debt_amount_display": "Rp 300.000",
                "open_items": 2,
                "debt_detail_lines": "1. 31 Mar 2026 — 10.00 GB | Rp 100.000 | Tunggakan manual",
                "debt_invoice_url": "https://example.test/api/admin/users/debts/temp/token.pdf",
            },
        )

    assert "Peringatan:" not in message
    assert "Rp 300.000" in message
    assert "debts/temp/token.pdf" in message


def test_user_access_blocked_humanizes_legacy_reason(monkeypatch, app):
    from app.services import notification_service

    monkeypatch.setattr(
        notification_service,
        "_load_templates",
        lambda: {
            "user_access_blocked": "Halo {full_name}. Alasan: {reason_human}",
        },
    )
    monkeypatch.setattr(notification_service, "get_app_links", lambda: {})

    with app.app_context():
        message = notification_service.get_notification_message(
            "user_access_blocked",
            {
                "full_name": "M Ragil Saputra",
                "reason": "quota_debt_limit|debt_mb=25600.00|source=manual_enforce_2026-02-26",
            },
        )

    assert "quota_debt_limit|" not in message
    assert "batas pengaman" in message


def test_quota_debt_warning_templates_accept_new_placeholders(monkeypatch, app):
    from app.services import notification_service

    monkeypatch.setattr(
        notification_service,
        "_load_templates",
        lambda: {
            "user_quota_debt_warning": "User {full_name} debt={debt_mb} warn={warning_threshold_mb} limit={limit_mb} est={estimated_rp} paket={base_package_name}",
            "admin_quota_debt_warning": "Admin {full_name} phone={phone_number} debt={debt_mb} warn={warning_threshold_mb} limit={limit_mb}",
        },
    )
    monkeypatch.setattr(notification_service, "get_app_links", lambda: {})

    payload = {
        "full_name": "Bobby",
        "phone_number": "+628123456789",
        "debt_mb": "420",
        "warning_threshold_mb": "400",
        "limit_mb": "500",
        "estimated_rp": "12.000",
        "base_package_name": "Paket 10 GB",
    }

    with app.app_context():
        user_message = notification_service.get_notification_message("user_quota_debt_warning", payload)
        admin_message = notification_service.get_notification_message("admin_quota_debt_warning", payload)

    assert "Peringatan:" not in user_message
    assert "Peringatan:" not in admin_message
    assert "420" in user_message
    assert "+628123456789" in admin_message
