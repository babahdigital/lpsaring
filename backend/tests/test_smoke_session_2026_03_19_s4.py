"""
Smoke tests — Session 2026-03-19 (S4): WA Template Fix + Auto-Unblock + Verify-Rules

Covers changes made in the 4th session of 2026-03-19:
1. WA template user_debt_added — tambah package_name, price_rp_display, sufiks GB benar
2. WA template user_debt_partial_payment_unblock — template baru untuk auto-unblock
3. settle_single_manual_debt — auto-unblock ketika semua debt lunas
4. verify_mikrotik_rules endpoint — verifikasi firewall filter rule kritis
"""

from __future__ import annotations

import json
import os
import sys
import pytest
from unittest.mock import MagicMock, patch

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


@pytest.fixture()
def app():
    from flask import Flask
    a = Flask(__name__)
    a.config.update(SECRET_KEY="smoke-test-secret")
    return a


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_templates() -> dict:
    templates_path = os.path.join(PROJECT_ROOT, "app", "notifications", "templates.json")
    with open(templates_path, encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# 1. WA Template: user_debt_added — placeholders baru wajib ada
# ---------------------------------------------------------------------------

def test_user_debt_added_template_has_package_name():
    """Template user_debt_added harus punya placeholder {package_name}."""
    templates = _load_templates()
    assert "user_debt_added" in templates
    tpl = templates["user_debt_added"]
    assert "{package_name}" in tpl, "Template harus mengandung {package_name}"


def test_user_debt_added_template_has_price_rp_display():
    """Template user_debt_added harus punya placeholder {price_rp_display}."""
    templates = _load_templates()
    tpl = templates["user_debt_added"]
    assert "{price_rp_display}" in tpl, "Template harus mengandung {price_rp_display}"


def test_user_debt_added_template_has_due_date_summary():
    templates = _load_templates()
    tpl = templates["user_debt_added"]
    assert "{due_date_summary}" in tpl


def test_user_debt_added_template_debt_gb_not_ambiguous():
    """Template user_debt_added tidak boleh punya placeholder {debt_gb} tanpa konteks GB yang jelas.
    Payload sekarang dikirim dengan sufiks ' GB', sehingga template tidak perlu tambahkan sendiri.
    Hanya cek bahwa template punya {debt_gb} (diisi payload yang sudah punya 'GB').
    """
    templates = _load_templates()
    tpl = templates["user_debt_added"]
    assert "{debt_gb}" in tpl, "Template harus mengandung {debt_gb}"


def test_user_debt_added_template_total_manual_debt_gb_present():
    """Template user_debt_added harus punya {total_manual_debt_gb} (payload sekarang berisi ' GB')."""
    templates = _load_templates()
    tpl = templates["user_debt_added"]
    assert "{total_manual_debt_gb}" in tpl


def test_user_debt_added_template_total_manual_debt_amount_present():
    """Template user_debt_added harus punya {total_manual_debt_amount_display}."""
    templates = _load_templates()
    tpl = templates["user_debt_added"]
    assert "{total_manual_debt_amount_display}" in tpl


def test_user_debt_added_template_has_debt_detail_lines():
    """Template user_debt_added harus punya placeholder {debt_detail_lines} untuk rincian tunggakan."""
    templates = _load_templates()
    tpl = templates["user_debt_added"]
    assert "{debt_detail_lines}" in tpl, "Template harus mengandung {debt_detail_lines}"


def test_user_debt_added_template_renders_correctly_with_package():
    """Template user_debt_added bisa dirender dengan semua placeholder terisi."""
    templates = _load_templates()
    tpl = templates["user_debt_added"]
    ctx = {
        "full_name": "Ikhsan Fajar",
        "debt_date": "19-03-2026 17:52",
        "due_date_summary": "akhir bulan (otomatis)",
        "package_name": "Paket Pintar 20 GB",
        "price_rp_display": "Rp 200.000",
        "debt_gb": "20.00 GB",
        "auto_debt_deducted_gb": "0.00 GB",
        "effective_quota_gb": "20.00 GB",
        "access_grant_summary": "Kuota efektif yang bisa dipakai: *20.00 GB*.",
        "total_manual_debt_gb": "30.00 GB",
        "total_manual_debt_amount_display": "Rp 300.000",
        "debt_detail_lines": "1. 19-03-2026 — 20.00 GB | Rp 200.000\n2. 15-03-2026 — 10.00 GB | –",
        "link_user_app": "https://lpsaring.babahdigital.net/login",
    }
    result = tpl.format(**ctx)
    assert "Ikhsan Fajar" in result
    assert "akhir bulan (otomatis)" in result
    assert "Paket Pintar 20 GB" in result
    assert "Rp 200.000" in result
    assert "20.00 GB" in result
    assert "30.00 GB" in result
    assert "Rp 300.000" in result
    # Tidak ada angka ambigu "20.00" tanpa "GB"
    assert "20.00\n" not in result
    assert ": *20.00*" not in result


def test_user_debt_added_template_renders_correctly_manual_only():
    """Template user_debt_added bisa dirender untuk kasus debt_add_mb (tanpa paket)."""
    templates = _load_templates()
    tpl = templates["user_debt_added"]
    ctx = {
        "full_name": "Budi Santoso",
        "debt_date": "19-03-2026 10:00",
        "due_date_summary": "akhir bulan (otomatis)",
        "package_name": "Tunggakan Manual",
        "price_rp_display": "–",
        "debt_gb": "10.00 GB",
        "auto_debt_deducted_gb": "0.00 GB",
        "effective_quota_gb": "10.00 GB",
        "access_grant_summary": "Kuota efektif yang bisa dipakai: *10.00 GB*.",
        "total_manual_debt_gb": "10.00 GB",
        "total_manual_debt_amount_display": "–",
        "debt_detail_lines": "1. 19-03-2026 — 10.00 GB | –",
        "link_user_app": "https://lpsaring.babahdigital.net/login",
    }
    result = tpl.format(**ctx)
    assert "Tunggakan Manual" in result
    assert "–" in result
    assert "10.00 GB" in result


def test_user_unlimited_activated_template_does_not_expose_expiry():
    templates = _load_templates()
    tpl = templates["user_unlimited_activated_by_admin"]
    assert "{profile_name}" in tpl
    assert "{expiry_date}" not in tpl


def test_user_unlimited_activated_template_renders_simple_unlimited_message():
    templates = _load_templates()
    tpl = templates["user_unlimited_activated_by_admin"]
    result = tpl.format(full_name="Abdullah", profile_name="Unlimited")
    assert "Profil akses: *Unlimited*" in result
    assert "Masa aktif unlimited" not in result


# ---------------------------------------------------------------------------
# 2. WA Template: user_debt_partial_payment_unblock — template baru P1
# ---------------------------------------------------------------------------

def test_user_debt_partial_payment_unblock_template_exists():
    """Template user_debt_partial_payment_unblock harus ada di templates.json."""
    templates = _load_templates()
    assert "user_debt_partial_payment_unblock" in templates, (
        "Template user_debt_partial_payment_unblock harus ada untuk auto-unblock P1"
    )


def test_user_debt_partial_payment_unblock_has_required_fields():
    """Template unblock harus punya semua placeholder yang sama dengan partial_payment."""
    templates = _load_templates()
    tpl = templates["user_debt_partial_payment_unblock"]
    for field in ["{full_name}", "{debt_date}", "{paid_at}", "{paid_manual_debt_gb}",
                  "{paid_manual_debt_amount_display}", "{paid_total_debt_gb}", "{paid_total_debt_amount_display}",
                  "{payment_channel_label}", "{remaining_manual_debt_gb}", "{remaining_quota_gb}", "{expiry_date}", "{receipt_url}"]:
        assert field in tpl, f"Template unblock harus punya {field}"


def test_user_debt_partial_payment_unblock_renders_correctly():
    """Template user_debt_partial_payment_unblock bisa dirender dengan semua placeholder."""
    templates = _load_templates()
    tpl = templates["user_debt_partial_payment_unblock"]
    ctx = {
        "full_name": "Ikhsan Fajar",
        "debt_date": "19-03-2026",
        "paid_at": "19-03-2026 18:00",
        "paid_manual_debt_gb": "20.00 GB",
        "paid_manual_debt_amount_display": "Rp 200.000",
        "paid_total_debt_gb": "20.00 GB",
        "paid_total_debt_amount_display": "Rp 200.000",
        "payment_channel_label": "Pelunasan manual oleh Admin",
        "remaining_manual_debt_gb": "0.00 GB",
        "remaining_quota_gb": "15.00 GB",
        "expiry_date": "31-03-2026",
        "receipt_url": "https://example.test/receipt.pdf",
        "link_user_app": "https://lpsaring.babahdigital.net/login",
    }
    result = tpl.format(**ctx)
    assert "Ikhsan Fajar" in result
    assert "dibuka kembali" in result
    assert "20.00 GB" in result


# ---------------------------------------------------------------------------
# 3. P1: Auto-unblock logic — settle_single_manual_debt
# ---------------------------------------------------------------------------

def test_settle_single_debt_sets_unblocked_true_when_all_paid(app):
    """Auto-unblock harus terjadi ketika is_blocked=True karena debt dan quota_debt_total_mb=0 setelah bayar."""
    import uuid
    from app.utils.block_reasons import is_debt_block_reason

    user_id = uuid.uuid4()
    debt_id = uuid.uuid4()

    fake_user = MagicMock()
    fake_user.id = user_id
    fake_user.full_name = "Test User"
    fake_user.phone_number = "+6281234567890"
    fake_user.is_blocked = True
    fake_user.blocked_reason = "tunggakan_overdue|debt_mb=20480.00|due=2026-03-31|days_overdue=3"
    fake_user.blocked_at = None
    fake_user.blocked_by_id = None
    fake_user.quota_debt_manual_mb = 20 * 1024
    fake_user.quota_debt_total_mb = 0  # 0 setelah bayar
    fake_user.total_quota_purchased_mb = 20 * 1024
    fake_user.total_quota_used_mb = 0
    fake_user.quota_expiry_date = None

    fake_debt = MagicMock()
    fake_debt.user_id = user_id
    fake_debt.debt_date = None
    fake_debt.paid_at = None

    # Verifikasi bahwa blocked_reason ini dikenal sebagai debt reason
    assert is_debt_block_reason("tunggakan_overdue|debt_mb=20480.00|due=2026-03-31|days_overdue=3"), \
        "tunggakan_overdue| harus dikenal sebagai debt block reason"

    with app.test_request_context():
        with (
            patch("app.infrastructure.http.admin.user_management_routes.db") as mock_db,
            patch("app.infrastructure.http.admin.user_management_routes.user_debt_service") as mock_svc,
            patch("app.infrastructure.http.admin.user_management_routes._send_whatsapp_notification"),
            patch("app.infrastructure.http.admin.user_management_routes.format_app_datetime", return_value="19-03-2026 18:00"),
            patch("app.infrastructure.http.admin.user_management_routes.format_mb_to_gb", return_value="20.00 GB"),
            patch("app.infrastructure.http.admin.user_management_routes._deny_non_super_admin_target_access", return_value=None),
        ):
            mock_db.session.get.side_effect = lambda model, oid: (
                fake_user if model.__name__ == "User" else fake_debt
            )
            mock_svc.settle_manual_debt_item_to_zero.return_value = 20 * 1024

            from app.infrastructure.http.admin.user_management_routes import settle_single_manual_debt
            admin_mock = MagicMock()
            admin_mock.id = uuid.uuid4()
            resp = settle_single_manual_debt.__wrapped__(admin_mock, user_id, debt_id)
            data = resp[0].get_json()
            assert data.get("unblocked") is True, "unblocked harus True ketika semua debt lunas dan user diblok karena debt"
            assert fake_user.is_blocked is False


# ---------------------------------------------------------------------------
# 4. P2: verify_mikrotik_rules endpoint — format response
# ---------------------------------------------------------------------------

def test_verify_mikrotik_rules_ok_when_all_rules_present(app):
    """verify_mikrotik_rules harus return status=ok ketika semua 4 rule kritis ada di tabel yang benar."""
    filter_rules = [
        {"chain": "hs-unauth", "action": "return", "src-address-list": "klient_aktif", "disabled": "false"},
        {"chain": "hs-unauth", "action": "return", "src-address-list": "klient_fup",   "disabled": "false"},
    ]
    raw_rules = [
        {"chain": "prerouting", "action": "drop", "src-address-list": "klient_inactive", "disabled": "false"},
        {"chain": "prerouting", "action": "drop", "dst-address-list": "klient_inactive", "disabled": "false"},
    ]

    def _get_resource(path):
        m = MagicMock()
        m.get.return_value = filter_rules if path == "/ip/firewall/filter" else raw_rules
        return m

    mock_api = MagicMock()
    mock_api.get_resource.side_effect = _get_resource

    with app.test_request_context():
        with (
            patch("app.infrastructure.http.admin.user_management_routes.get_mikrotik_connection") as mock_conn,
            patch("app.infrastructure.http.admin.user_management_routes._deny_non_super_admin_target_access", return_value=None),
        ):
            mock_conn.return_value.__enter__.return_value = mock_api

            from app.infrastructure.http.admin.user_management_routes import verify_mikrotik_rules
            admin_mock = MagicMock()
            resp = verify_mikrotik_rules.__wrapped__(admin_mock)
            data = resp[0].get_json()
            assert data["status"] == "ok"
            assert data["all_found"] is True
            assert len(data["checks"]) == 4
            assert all(c["found"] for c in data["checks"])


def test_verify_mikrotik_rules_error_when_rule_missing(app):
    """verify_mikrotik_rules harus return status=error ketika salah satu rule tidak ada."""
    # Missing: raw drop for klient_inactive src (dst-only present)
    filter_rules = [
        {"chain": "hs-unauth", "action": "return", "src-address-list": "klient_aktif", "disabled": "false"},
        {"chain": "hs-unauth", "action": "return", "src-address-list": "klient_fup",   "disabled": "false"},
    ]
    raw_rules = [
        # Only the dst variant is present; src variant is missing
        {"chain": "prerouting", "action": "drop", "dst-address-list": "klient_inactive", "disabled": "false"},
    ]

    def _get_resource(path):
        m = MagicMock()
        m.get.return_value = filter_rules if path == "/ip/firewall/filter" else raw_rules
        return m

    mock_api = MagicMock()
    mock_api.get_resource.side_effect = _get_resource

    with app.test_request_context():
        with (
            patch("app.infrastructure.http.admin.user_management_routes.get_mikrotik_connection") as mock_conn,
            patch("app.infrastructure.http.admin.user_management_routes._deny_non_super_admin_target_access", return_value=None),
        ):
            mock_conn.return_value.__enter__.return_value = mock_api

            from app.infrastructure.http.admin.user_management_routes import verify_mikrotik_rules
            admin_mock = MagicMock()
            resp = verify_mikrotik_rules.__wrapped__(admin_mock)
            data = resp[0].get_json()
            assert data["status"] == "error"
            assert data["all_found"] is False
            missing = [c for c in data["checks"] if not c["found"]]
            assert len(missing) == 1
            assert "klient_inactive" in missing[0]["label"]
            assert "src=" in missing[0]["label"]


def test_verify_mikrotik_rules_error_when_order_wrong(app):
    """verify_mikrotik_rules harus return status=error ketika rules ada di chain yang salah (disabled diabaikan)."""
    # Semua rule ada tapi satu di-disabled — harus dianggap tidak ditemukan
    filter_rules = [
        {"chain": "hs-unauth", "action": "return", "src-address-list": "klient_aktif", "disabled": "false"},
        {"chain": "hs-unauth", "action": "return", "src-address-list": "klient_fup",   "disabled": "true"},  # disabled!
    ]
    raw_rules = [
        {"chain": "prerouting", "action": "drop", "src-address-list": "klient_inactive", "disabled": "false"},
        {"chain": "prerouting", "action": "drop", "dst-address-list": "klient_inactive", "disabled": "false"},
    ]

    def _get_resource(path):
        m = MagicMock()
        m.get.return_value = filter_rules if path == "/ip/firewall/filter" else raw_rules
        return m

    mock_api = MagicMock()
    mock_api.get_resource.side_effect = _get_resource

    with app.test_request_context():
        with (
            patch("app.infrastructure.http.admin.user_management_routes.get_mikrotik_connection") as mock_conn,
            patch("app.infrastructure.http.admin.user_management_routes._deny_non_super_admin_target_access", return_value=None),
        ):
            mock_conn.return_value.__enter__.return_value = mock_api

            from app.infrastructure.http.admin.user_management_routes import verify_mikrotik_rules
            admin_mock = MagicMock()
            resp = verify_mikrotik_rules.__wrapped__(admin_mock)
            data = resp[0].get_json()
            assert data["status"] == "error"
            assert data["all_found"] is False
            fup_check = next((c for c in data["checks"] if "klient_fup" in c["label"]), None)
            assert fup_check is not None
            assert fup_check["found"] is False
