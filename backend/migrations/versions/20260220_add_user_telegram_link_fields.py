"""add user telegram link fields

Revision ID: 20260220_add_user_telegram_link_fields
Revises: 20260218_add_transaction_events_table
Create Date: 2026-02-20

"""

from alembic import op
import sqlalchemy as sa


revision = '20260220_add_user_telegram_link_fields'
down_revision = '20260218_add_transaction_events_table'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('users', sa.Column('telegram_chat_id', sa.String(length=64), nullable=True))
    op.add_column('users', sa.Column('telegram_username', sa.String(length=64), nullable=True))
    op.add_column('users', sa.Column('telegram_linked_at', sa.DateTime(timezone=True), nullable=True))


def downgrade():
    op.drop_column('users', 'telegram_linked_at')
    op.drop_column('users', 'telegram_username')
    op.drop_column('users', 'telegram_chat_id')
