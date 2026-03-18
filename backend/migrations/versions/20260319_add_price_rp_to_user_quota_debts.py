"""add price_rp to user_quota_debts to store actual package price

Revision ID: 20260319_add_price_rp_to_user_quota_debts
Revises: 20260318_add_due_date_to_manual_quota_debt
Create Date: 2026-03-19

"""

from alembic import op
import sqlalchemy as sa


revision = "20260319_add_price_rp_to_user_quota_debts"
down_revision = "20260318_add_due_date_to_manual_quota_debt"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "user_quota_debts",
        sa.Column("price_rp", sa.BigInteger(), nullable=True),
    )


def downgrade():
    op.drop_column("user_quota_debts", "price_rp")
