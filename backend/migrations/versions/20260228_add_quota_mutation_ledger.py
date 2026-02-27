"""add quota mutation ledger table

Revision ID: 20260228_add_quota_mutation_ledger
Revises: 20260227_add_safe_global_mac_unique_index
Create Date: 2026-02-28

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.sql.type_api import TypeEngine


revision = "20260228_add_quota_mutation_ledger"
down_revision = "20260227_add_safe_global_mac_unique_index"
branch_labels = None
depends_on = None


def _uuid_type(bind) -> TypeEngine:
    if bind.dialect.name == "postgresql":
        return postgresql.UUID(as_uuid=True)
    return sa.String(length=36)


def upgrade():
    bind = op.get_bind()
    uuid_col = _uuid_type(bind)

    op.create_table(
        "quota_mutation_ledger",
        sa.Column("id", uuid_col, primary_key=True, nullable=False),
        sa.Column("user_id", uuid_col, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("actor_user_id", uuid_col, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("source", sa.String(length=80), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("before_state", sa.JSON(), nullable=True),
        sa.Column("after_state", sa.JSON(), nullable=True),
        sa.Column("event_details", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint(
            "user_id",
            "source",
            "idempotency_key",
            name="uq_quota_mutation_ledger_user_source_idempotency",
        ),
    )
    op.create_index(
        "ix_quota_mutation_ledger_user_created",
        "quota_mutation_ledger",
        ["user_id", "created_at"],
        unique=False,
    )
    op.create_index("ix_quota_mutation_ledger_source", "quota_mutation_ledger", ["source"], unique=False)


def downgrade():
    op.drop_index("ix_quota_mutation_ledger_source", table_name="quota_mutation_ledger")
    op.drop_index("ix_quota_mutation_ledger_user_created", table_name="quota_mutation_ledger")
    op.drop_table("quota_mutation_ledger")
