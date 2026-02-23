"""expand transaction snap_redirect_url to text

Revision ID: 20260224_expand_transaction_snap_redirect_url_to_text
Revises: 20260223_add_admin_api_mutation_action_type
Create Date: 2026-02-24

"""

from alembic import op
import sqlalchemy as sa


revision = "20260224_expand_transaction_snap_redirect_url_to_text"
down_revision = "20260223_add_admin_api_mutation_action_type"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column(
        "transactions",
        "snap_redirect_url",
        existing_type=sa.String(length=255),
        type_=sa.Text(),
        existing_nullable=True,
    )


def downgrade():
    # NOTE: Downgrade may fail if existing snap_redirect_url values exceed 255 characters.
    op.alter_column(
        "transactions",
        "snap_redirect_url",
        existing_type=sa.Text(),
        type_=sa.String(length=255),
        existing_nullable=True,
    )
