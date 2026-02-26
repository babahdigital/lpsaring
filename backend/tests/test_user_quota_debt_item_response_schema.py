import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

from app.infrastructure.http.schemas.user_schemas import UserQuotaDebtItemResponseSchema


def test_user_quota_debt_item_response_schema_from_orm_allows_computed_fields_default():
    now = datetime.now(timezone.utc)

    debt = SimpleNamespace(
        id=uuid.uuid4(),
        debt_date=None,
        amount_mb=123,
        paid_mb=0,
        # NOTE: remaining_mb is computed in routes; schema must not require it from ORM.
        is_paid=False,
        paid_at=None,
        note=None,
        created_at=now,
        updated_at=now,
        last_paid_source=None,
    )

    payload = UserQuotaDebtItemResponseSchema.model_validate(debt).model_dump()
    assert payload["amount_mb"] == 123
    assert payload["paid_mb"] == 0
    assert payload["remaining_mb"] == 0
