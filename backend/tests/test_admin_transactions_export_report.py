from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

from flask import Flask
import sqlalchemy as sa

from app.infrastructure.db.models import ApprovalStatus, Package, Transaction, TransactionStatus, User, UserQuotaDebt, UserRole
from app.infrastructure.http.admin_contexts import transactions as transactions_context


class _FakeExecuteResult:
    def __init__(self, payload):
        self.payload = payload

    def one(self):
        return self.payload

    def all(self):
        return list(self.payload)

    def scalar_one_or_none(self):
        return self.payload


class _FakeScalarResult:
    def __init__(self, payload):
        self.payload = payload

    def all(self):
        return list(self.payload)


class _FakeSession:
    def __init__(self, *, execute_payloads, scalar_payloads):
        self._execute_payloads = list(execute_payloads)
        self._scalar_payloads = list(scalar_payloads)

    def execute(self, _query):
        if not self._execute_payloads:
            raise AssertionError("Unexpected execute() call")
        return _FakeExecuteResult(self._execute_payloads.pop(0))

    def scalars(self, _query):
        if not self._scalar_payloads:
            raise AssertionError("Unexpected scalars() call")
        return _FakeScalarResult(self._scalar_payloads.pop(0))


class _FakeDB:
    def __init__(self, *, execute_payloads, scalar_payloads):
        self.session = _FakeSession(execute_payloads=execute_payloads, scalar_payloads=scalar_payloads)


class _FakeHTML:
    def __init__(self, *, string: str, base_url: str):
        self.string = string
        self.base_url = base_url

    def write_pdf(self):
        return b"%PDF-test"


def _make_app() -> Flask:
    app = Flask(__name__)
    app.config["SECRET_KEY"] = "unit-test-secret"
    app.config["APP_PUBLIC_BASE_URL"] = "https://example.test"
    app.config["BUSINESS_NAME"] = "LPSaring"
    return app


def test_export_transactions_uses_open_manual_debt_prices_for_snapshot(monkeypatch):
    captured: dict[str, object] = {}

    def _fake_render_template(template_name: str, **context):
        captured["template_name"] = template_name
        captured["context"] = context
        return "<html>ok</html>"

    monkeypatch.setattr(transactions_context, "render_template", _fake_render_template)

    manual_user = SimpleNamespace(
        id=uuid4(),
        full_name="Bobby Dermawan",
        phone_number="082213631573",
        role=UserRole.USER,
        is_active=True,
        approval_status=ApprovalStatus.APPROVED,
        is_unlimited_user=False,
        quota_debt_auto_mb=0,
        quota_debt_manual_mb=50 * 1024,
        manual_debt_mb=50 * 1024,
    )
    unlimited_user = SimpleNamespace(
        id=uuid4(),
        full_name="Ikhsan Fajar",
        phone_number="083167629438",
        role=UserRole.USER,
        is_active=True,
        approval_status=ApprovalStatus.APPROVED,
        is_unlimited_user=True,
        quota_debt_auto_mb=0,
        quota_debt_manual_mb=1,
        manual_debt_mb=1,
    )

    manual_open_debt = SimpleNamespace(
        user_id=manual_user.id,
        amount_mb=50 * 1024,
        paid_mb=0,
        price_rp=500_000,
        note="Paket Manual 50 GB",
        is_paid=False,
        created_at=datetime(2026, 3, 27, tzinfo=timezone.utc),
    )
    unlimited_open_debt = SimpleNamespace(
        user_id=unlimited_user.id,
        amount_mb=1,
        paid_mb=0,
        price_rp=1_040_000,
        note="Unlimited debt manual",
        is_paid=False,
        created_at=datetime(2026, 3, 27, tzinfo=timezone.utc),
    )

    fake_db = _FakeDB(
        execute_payloads=[
            (46, 10_340_000),
            [("Paket Hebat", 13, 2_600_000)],
            [("qris", 45, 10_000_000)],
            SimpleNamespace(name="Paket Hemat"),
        ],
        scalar_payloads=[
            [manual_user, unlimited_user],
            [manual_open_debt, unlimited_open_debt],
        ],
    )

    app = _make_app()

    with app.app_context(), app.test_request_context(
        "/api/admin/transactions/export?format=pdf&start_date=2026-02-28&end_date=2026-03-26&group_by=none",
        method="GET",
    ):
        response = transactions_context.export_transactions_impl(
            db=fake_db,
            WEASYPRINT_AVAILABLE=True,
            HTML=_FakeHTML,
            parse_local_date_range_to_utc=lambda *_args: (
                datetime(2026, 2, 27, 16, 0, tzinfo=timezone.utc),
                datetime(2026, 3, 26, 16, 0, tzinfo=timezone.utc),
            ),
            get_local_tz=lambda: timezone.utc,
            estimate_debt_rp_from_cheapest_package=lambda **_kwargs: None,
            format_to_local_phone=lambda value: str(value),
            Package=Package,
            Transaction=Transaction,
            TransactionStatus=TransactionStatus,
            User=User,
            UserRole=UserRole,
            ApprovalStatus=ApprovalStatus,
            func=sa.func,
            select=sa.select,
            desc=sa.desc,
        )

    assert response.status_code == 200
    assert captured["template_name"] == "admin_sales_report.html"

    context = captured["context"]
    assert context["debt_users_total_count"] == 2
    assert context["estimated_debt_total_rp"] == 1_540_000

    debt_rows = context["debt_users"]
    assert debt_rows[0]["full_name"] == "Bobby Dermawan"
    assert debt_rows[0]["debt_manual_mb"] == 50 * 1024
    assert debt_rows[0]["debt_estimated_rp"] == 500_000
    assert debt_rows[1]["full_name"] == "Ikhsan Fajar"
    assert debt_rows[1]["is_unlimited_debt"] is True
    assert debt_rows[1]["debt_estimated_rp"] == 1_040_000