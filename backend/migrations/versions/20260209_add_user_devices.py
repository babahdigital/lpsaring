"""add user_devices table

Revision ID: 20260209_add_user_devices
Revises: 20260208_add_quota_notification_levels
Create Date: 2026-02-09
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '20260209_add_user_devices'
down_revision = '20260208_add_quota_notification_levels'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'user_devices',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('mac_address', sa.String(length=32), nullable=False),
        sa.Column('ip_address', sa.String(length=45), nullable=True),
        sa.Column('user_agent', sa.String(length=255), nullable=True),
        sa.Column('label', sa.String(length=100), nullable=True),
        sa.Column('is_authorized', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('first_seen_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('last_seen_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('authorized_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('deauthorized_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'mac_address', name='uq_user_devices_user_mac')
    )
    op.create_index('ix_user_devices_user_id', 'user_devices', ['user_id'], unique=False)
    op.create_index('ix_user_devices_mac_address', 'user_devices', ['mac_address'], unique=False)


def downgrade():
    op.drop_index('ix_user_devices_mac_address', table_name='user_devices')
    op.drop_index('ix_user_devices_user_id', table_name='user_devices')
    op.drop_table('user_devices')
