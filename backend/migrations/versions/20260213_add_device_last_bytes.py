"""add device last bytes fields

Revision ID: 20260213_add_device_last_bytes
Revises: 20260210_add_user_blocking_fields
Create Date: 2026-02-13
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20260213_add_device_last_bytes'
down_revision = '20260210_add_user_blocking_fields'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('user_devices', sa.Column('last_bytes_total', sa.BigInteger(), nullable=True))
    op.add_column('user_devices', sa.Column('last_bytes_updated_at', sa.DateTime(timezone=True), nullable=True))


def downgrade():
    op.drop_column('user_devices', 'last_bytes_updated_at')
    op.drop_column('user_devices', 'last_bytes_total')
