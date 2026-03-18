"""add due_date to user_quota_debts for reminder notifications

Revision ID: 20260318_add_due_date_to_manual_quota_debt
Revises: 20260315_add_user_device_host_tracking
Create Date: 2026-03-18

"""

from alembic import op
import sqlalchemy as sa


revision = "20260318_add_due_date_to_manual_quota_debt"
down_revision = "20260315_add_user_device_host_tracking"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "user_quota_debts",
        sa.Column("due_date", sa.Date(), nullable=True),
    )
    op.create_index(
        "ix_user_quota_debts_due_date",
        "user_quota_debts",
        ["due_date"],
        unique=False,
        postgresql_where=sa.text("is_paid = false AND due_date IS NOT NULL"),
    )


def downgrade():
    op.drop_index("ix_user_quota_debts_due_date", table_name="user_quota_debts")
    op.drop_column("user_quota_debts", "due_date")
