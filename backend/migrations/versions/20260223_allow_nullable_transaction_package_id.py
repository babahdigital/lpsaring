"""allow nullable transaction package_id

Revision ID: 20260223_allow_nullable_transaction_package_id
Revises: 20260220_add_manual_quota_debt
Create Date: 2026-02-23

"""

from alembic import op
from sqlalchemy.dialects import postgresql


revision = "20260223_allow_nullable_transaction_package_id"
down_revision = "20260220_add_manual_quota_debt"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column(
        "transactions",
        "package_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=True,
    )


def downgrade():
    # NOTE: Downgrade will fail if there are rows with NULL package_id.
    op.alter_column(
        "transactions",
        "package_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=False,
    )
