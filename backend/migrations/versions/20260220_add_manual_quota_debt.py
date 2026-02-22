"""add manual quota debt

Revision ID: 20260220_add_manual_quota_debt
Revises: 20260220_add_user_telegram_link_fields
Create Date: 2026-02-20

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260220_add_manual_quota_debt"
down_revision = "20260220_add_user_telegram_link_fields"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("manual_debt_mb", sa.BigInteger(), nullable=False, server_default="0"))
    op.add_column("users", sa.Column("manual_debt_updated_at", sa.DateTime(timezone=True), nullable=True))

    op.create_table(
        "user_quota_debts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("last_paid_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("debt_date", sa.Date(), nullable=True),
        sa.Column("amount_mb", sa.BigInteger(), nullable=False),
        sa.Column("paid_mb", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("is_paid", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_paid_source", sa.String(length=50), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["last_paid_by_id"], ["users.id"], ondelete="SET NULL"),
    )

    op.create_index("ix_user_quota_debts_user_id", "user_quota_debts", ["user_id"], unique=False)
    op.create_index("ix_user_quota_debts_is_paid", "user_quota_debts", ["is_paid"], unique=False)


def downgrade():
    op.drop_index("ix_user_quota_debts_is_paid", table_name="user_quota_debts")
    op.drop_index("ix_user_quota_debts_user_id", table_name="user_quota_debts")
    op.drop_table("user_quota_debts")

    op.drop_column("users", "manual_debt_updated_at")
    op.drop_column("users", "manual_debt_mb")
