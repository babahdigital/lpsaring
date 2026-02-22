"""Add tamping fields to users

Revision ID: 20260208_add_tamping_fields
Revises: 20260208_align_server_defaults
Create Date: 2026-02-08 10:00:00.000000

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20260208_add_tamping_fields"
down_revision = "20260208_align_server_defaults"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("is_tamping", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("users", sa.Column("tamping_type", sa.String(length=50), nullable=True))


def downgrade():
    op.drop_column("users", "tamping_type")
    op.drop_column("users", "is_tamping")
