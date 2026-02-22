"""add user blocking fields

Revision ID: 20260210_add_user_blocking_fields
Revises: 20260209_add_user_devices
Create Date: 2026-02-10
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "20260210_add_user_blocking_fields"
down_revision = "20260209_add_user_devices"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("is_blocked", sa.Boolean(), server_default=sa.text("false"), nullable=False))
    op.add_column("users", sa.Column("blocked_reason", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("blocked_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("blocked_by_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key("fk_users_blocked_by_id_users", "users", "users", ["blocked_by_id"], ["id"])


def downgrade():
    op.drop_constraint("fk_users_blocked_by_id_users", "users", type_="foreignkey")
    op.drop_column("users", "blocked_by_id")
    op.drop_column("users", "blocked_at")
    op.drop_column("users", "blocked_reason")
    op.drop_column("users", "is_blocked")
