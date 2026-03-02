"""add whatsapp tracking columns to public database update submissions

Revision ID: 20260302_add_public_update_submission_whatsapp_tracking
Revises: 20260302_add_public_db_update_submissions
Create Date: 2026-03-02

"""

from alembic import op
import sqlalchemy as sa


revision = "20260302_add_public_update_submission_whatsapp_tracking"
down_revision = "20260302_add_public_db_update_submissions"
branch_labels = None
depends_on = None


def _has_column(bind, table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(bind)
    return any(col["name"] == column_name for col in inspector.get_columns(table_name))


def upgrade():
    bind = op.get_bind()
    table_name = "public_database_update_submissions"

    if not _has_column(bind, table_name, "whatsapp_notify_attempts"):
        op.add_column(
            table_name,
            sa.Column("whatsapp_notify_attempts", sa.Integer(), nullable=False, server_default="0"),
        )
    if not _has_column(bind, table_name, "whatsapp_notified_at"):
        op.add_column(
            table_name,
            sa.Column("whatsapp_notified_at", sa.DateTime(timezone=True), nullable=True),
        )
    if not _has_column(bind, table_name, "whatsapp_notify_last_error"):
        op.add_column(
            table_name,
            sa.Column("whatsapp_notify_last_error", sa.String(length=255), nullable=True),
        )


def downgrade():
    op.drop_column("public_database_update_submissions", "whatsapp_notify_last_error")
    op.drop_column("public_database_update_submissions", "whatsapp_notified_at")
    op.drop_column("public_database_update_submissions", "whatsapp_notify_attempts")
