from datetime import date, datetime, timezone
from types import SimpleNamespace
from uuid import uuid4


class _ScalarResult:
    def __init__(self, items):
        self._items = items

    def all(self):
        return list(self._items)


def _fake_schema_payload(item):
    return SimpleNamespace(
        model_dump=lambda: {
            "id": str(item.id),
            "debt_date": item.debt_date.isoformat() if item.debt_date else None,
            "created_at": item.created_at.isoformat() if item.created_at else None,
            "updated_at": item.updated_at.isoformat() if item.updated_at else None,
            "paid_at": item.paid_at.isoformat() if item.paid_at else None,
            "price_rp": item.price_rp,
            "note": item.note,
        }
    )


def test_manual_debt_report_context_sums_open_item_prices(monkeypatch):
    from app.services import manual_debt_report_service as svc

    debts = [
        SimpleNamespace(
            id=uuid4(),
            amount_mb=20 * 1024,
            paid_mb=0,
            is_paid=False,
            price_rp=200_000,
            debt_date=date(2026, 3, 31),
            due_date=date(2026, 3, 31),
            created_at=datetime(2026, 3, 21, tzinfo=timezone.utc),
            updated_at=datetime(2026, 3, 21, tzinfo=timezone.utc),
            paid_at=None,
            note="Paket Pintar (20 GB, Rp 200,000)",
        ),
        SimpleNamespace(
            id=uuid4(),
            amount_mb=20 * 1024,
            paid_mb=0,
            is_paid=False,
            price_rp=200_000,
            debt_date=date(2026, 3, 31),
            due_date=date(2026, 3, 31),
            created_at=datetime(2026, 3, 21, tzinfo=timezone.utc),
            updated_at=datetime(2026, 3, 21, tzinfo=timezone.utc),
            paid_at=None,
            note="Paket Pintar (20 GB, Rp 200,000)",
        ),
    ]
    user = SimpleNamespace(
        id=uuid4(),
        full_name="Bobby Dermawan",
        phone_number="+628123456789",
        quota_debt_auto_mb=0,
        quota_debt_manual_mb=40 * 1024,
        quota_debt_total_mb=40 * 1024,
    )

    monkeypatch.setattr(svc.db.session, "scalars", lambda _query: _ScalarResult(debts))
    monkeypatch.setattr(svc.UserQuotaDebtItemResponseSchema, "from_orm", _fake_schema_payload)
    monkeypatch.setattr(
        svc,
        "estimate_debt_rp_for_mb",
        lambda value_mb: SimpleNamespace(
            estimated_rp_rounded=0 if not value_mb else 270_000,
            package_name="Paket Estimator",
        ),
    )

    context = svc.build_user_manual_debt_report_context(user)

    assert context["debt_manual_mb"] == 40 * 1024
    assert context["debt_manual_estimated_rp"] == 400_000
    assert context["debt_total_estimated_rp"] == 400_000
    assert len(context["open_items"]) == 2
    assert [item["remaining_rp"] for item in context["open_items"]] == [200_000, 200_000]


def test_manual_debt_report_context_prorates_partial_item_price(monkeypatch):
    from app.services import manual_debt_report_service as svc

    debt = SimpleNamespace(
        id=uuid4(),
        amount_mb=20 * 1024,
        paid_mb=10 * 1024,
        is_paid=False,
        price_rp=200_000,
        debt_date=date(2026, 3, 31),
        due_date=date(2026, 3, 31),
        created_at=datetime(2026, 3, 21, tzinfo=timezone.utc),
        updated_at=datetime(2026, 3, 21, tzinfo=timezone.utc),
        paid_at=None,
        note="Paket Pintar (20 GB, Rp 200,000)",
    )
    user = SimpleNamespace(
        id=uuid4(),
        full_name="Bobby Dermawan",
        phone_number="+628123456789",
        quota_debt_auto_mb=0,
        quota_debt_manual_mb=10 * 1024,
        quota_debt_total_mb=10 * 1024,
    )

    monkeypatch.setattr(svc.db.session, "scalars", lambda _query: _ScalarResult([debt]))
    monkeypatch.setattr(svc.UserQuotaDebtItemResponseSchema, "from_orm", _fake_schema_payload)
    monkeypatch.setattr(
        svc,
        "estimate_debt_rp_for_mb",
        lambda value_mb: SimpleNamespace(
            estimated_rp_rounded=0 if not value_mb else 90_000,
            package_name="Paket Estimator",
        ),
    )

    context = svc.build_user_manual_debt_report_context(user)

    assert context["debt_manual_estimated_rp"] == 100_000
    assert context["open_items"][0]["remaining_rp"] == 100_000
    assert context["open_items"][0]["remaining_amount_display"] == "Rp 100.000"