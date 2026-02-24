"""add auto debt offset mb

Revision ID: 20260224_add_auto_debt_offset_mb
Revises: 20260224_expand_transaction_snap_redirect_url_to_text
Create Date: 2026-02-24

"""

from alembic import op
import sqlalchemy as sa


revision = "20260224_add_auto_debt_offset_mb"
down_revision = "20260224_expand_transaction_snap_redirect_url_to_text"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "users",
        sa.Column(
            "auto_debt_offset_mb",
            sa.BigInteger(),
            nullable=False,
            server_default="0",
        ),
    )


def downgrade():
    op.drop_column("users", "auto_debt_offset_mb")
