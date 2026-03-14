"""add user device hotspot host tracking

Revision ID: 20260315_add_user_device_host_tracking
Revises: 20260302_alter_public_update_submission_role_fields
Create Date: 2026-03-15
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260315_add_user_device_host_tracking"
down_revision = "20260302_alter_public_update_submission_role_fields"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("user_devices", sa.Column("last_hotspot_host_id", sa.String(length=64), nullable=True))
    op.add_column("user_devices", sa.Column("last_hotspot_uptime_seconds", sa.Integer(), nullable=True))


def downgrade():
    op.drop_column("user_devices", "last_hotspot_uptime_seconds")
    op.drop_column("user_devices", "last_hotspot_host_id")