from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from flask import Flask

from app.services.user_management.user_profile import _build_debt_detail_lines
from app.services.user_management import helpers as user_management_helpers


def test_build_debt_detail_lines_accepts_string_dates_and_extracts_package_name():
    app = Flask(__name__)

    fake_debts = [
        SimpleNamespace(
            id="debt-1",
            amount_mb=10240,
            paid_mb=0,
            debt_date="2026-03-21",
            created_at="2026-03-21 00:30:34.749357+00:00",
            price_rp=100000,
            note="Paket: Paket Hemat (10 GB, Rp 100,000)",
        )
    ]

    query_mock = MagicMock()
    query_mock.filter.return_value.order_by.return_value.all.return_value = fake_debts
    fake_user = SimpleNamespace(id="user-1")

    with app.app_context():
        with patch("app.services.user_management.user_profile.db.session.query", return_value=query_mock):
            result = _build_debt_detail_lines(fake_user)

    assert "21-03-2026 07:30" in result
    assert "10.00 GB" in result
    assert "Rp 100.000" in result
    assert "Paket Hemat" in result
    assert "Rincian tidak tersedia" not in result


def test_build_debt_detail_lines_keeps_other_rows_when_one_row_is_invalid():
    app = Flask(__name__)

    fake_debts = [
        SimpleNamespace(
            id="debt-bad",
            amount_mb="invalid",
            paid_mb=0,
            debt_date=object(),
            created_at=None,
            price_rp=None,
            note=None,
        ),
        SimpleNamespace(
            id="debt-good",
            amount_mb=20480,
            paid_mb=1024,
            debt_date="2026-03-19",
            created_at="2026-03-19 10:00:00+00:00",
            price_rp=200000,
            note="Paket: Paket Pintar (20 GB, Rp 200,000)",
        ),
    ]

    query_mock = MagicMock()
    query_mock.filter.return_value.order_by.return_value.all.return_value = fake_debts
    fake_user = SimpleNamespace(id="user-2")

    with app.app_context():
        with patch("app.services.user_management.user_profile.db.session.query", return_value=query_mock):
            result = _build_debt_detail_lines(fake_user)

    assert "1. Detail item sedang direkonsiliasi sistem" in result
    assert "2. 19-03-2026 17:00" in result
    assert "19.00 GB" in result
    assert "Paket Pintar" in result


def test_send_whatsapp_notification_blocks_degraded_render(monkeypatch):
    app = Flask(__name__)

    metric_calls = []

    monkeypatch.setattr(
        user_management_helpers.settings_service,
        "get_setting",
        lambda *_args, **_kwargs: "True",
    )
    monkeypatch.setattr(
        "app.services.notification_service.get_notification_message",
        lambda *_args, **_kwargs: "Peringatan: placeholder hilang",
    )
    monkeypatch.setattr(
        "app.infrastructure.gateways.whatsapp_client.send_whatsapp_message",
        lambda *_args, **_kwargs: True,
    )
    monkeypatch.setattr(
        user_management_helpers,
        "increment_metric",
        lambda key, amount=1: metric_calls.append((key, amount)),
    )

    with app.app_context():
        sent = user_management_helpers._send_whatsapp_notification(
            "6281234567890",
            "user_debt_added",
            {"full_name": "Naru"},
        )

    assert sent is False
    assert ("notification.render.degraded", 1) in metric_calls
    assert ("notification.render.user_debt_added.degraded", 1) in metric_calls


def test_send_whatsapp_notification_tracks_degraded_debt_details(monkeypatch):
    app = Flask(__name__)

    metric_calls = []
    sent_payload = {}

    monkeypatch.setattr(
        user_management_helpers.settings_service,
        "get_setting",
        lambda *_args, **_kwargs: "True",
    )
    monkeypatch.setattr(
        "app.services.notification_service.get_notification_message",
        lambda *_args, **_kwargs: "ok",
    )

    def _fake_send(phone, message):
        sent_payload["phone"] = phone
        sent_payload["message"] = message
        return True

    monkeypatch.setattr(
        "app.infrastructure.gateways.whatsapp_client.send_whatsapp_message",
        _fake_send,
    )
    monkeypatch.setattr(
        user_management_helpers,
        "increment_metric",
        lambda key, amount=1: metric_calls.append((key, amount)),
    )

    with app.app_context():
        sent = user_management_helpers._send_whatsapp_notification(
            "6281234567890",
            "user_debt_added",
            {
                "full_name": "Naru",
                "_debt_detail_degraded": True,
                "_debt_detail_invalid_items": 2,
            },
        )

    assert sent is True
    assert sent_payload["phone"] == "6281234567890"
    assert ("notification.whatsapp.user_debt_added.detail_degraded", 1) in metric_calls
    assert ("notification.whatsapp.user_debt_added.detail_degraded.items", 2) in metric_calls