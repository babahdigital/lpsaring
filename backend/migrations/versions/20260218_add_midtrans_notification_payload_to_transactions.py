"""add midtrans notification payload to transactions

Revision ID: 20260218_add_midtrans_notification_payload_to_transactions
Revises: 20260217_expand_notification_type_varchar_length
Create Date: 2026-02-18

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20260218_add_midtrans_notification_payload_to_transactions'
down_revision = '20260217_expand_notification_type_varchar_length'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('transactions', sa.Column('midtrans_notification_payload', sa.Text(), nullable=True))


def downgrade():
    op.drop_column('transactions', 'midtrans_notification_payload')
