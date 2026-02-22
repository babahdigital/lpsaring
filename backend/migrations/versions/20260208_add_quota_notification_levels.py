"""Add quota/expiry notification levels to users

Revision ID: 20260208_add_quota_notification_levels
Revises: 20260208_add_tamping_fields
Create Date: 2026-02-08 12:00:00.000000

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20260208_add_quota_notification_levels"
down_revision = "20260208_add_tamping_fields"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("last_quota_notification_level", sa.Integer(), nullable=True))
    op.add_column("users", sa.Column("last_expiry_notification_level", sa.Integer(), nullable=True))


def downgrade():
    op.drop_column("users", "last_expiry_notification_level")
    op.drop_column("users", "last_quota_notification_level")
