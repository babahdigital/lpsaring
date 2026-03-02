"""add approval workflow fields to public database update submissions

Revision ID: 20260302_add_public_update_submission_approval_fields
Revises: 20260302_add_public_update_submission_whatsapp_tracking
Create Date: 2026-03-02

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.sql.type_api import TypeEngine


revision = "20260302_add_public_update_submission_approval_fields"
down_revision = "20260302_add_public_update_submission_whatsapp_tracking"
branch_labels = None
depends_on = None


def _uuid_type(bind) -> TypeEngine:
    if bind.dialect.name == "postgresql":
        return postgresql.UUID(as_uuid=True)
    return sa.String(length=36)


def _has_column(bind, table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(bind)
    return any(col["name"] == column_name for col in inspector.get_columns(table_name))


def _has_fk(bind, table_name: str, fk_name: str) -> bool:
    inspector = sa.inspect(bind)
    return any(fk.get("name") == fk_name for fk in inspector.get_foreign_keys(table_name))


def upgrade():
    bind = op.get_bind()
    uuid_col = _uuid_type(bind)
    table_name = "public_database_update_submissions"
    fk_name = "fk_public_update_submissions_processed_by_user"

    if not _has_column(bind, table_name, "approval_status"):
        op.add_column(
            table_name,
            sa.Column("approval_status", sa.String(length=20), nullable=False, server_default="PENDING"),
        )
    if not _has_column(bind, table_name, "processed_by_user_id"):
        op.add_column(
            table_name,
            sa.Column("processed_by_user_id", uuid_col, nullable=True),
        )
    if not _has_column(bind, table_name, "processed_at"):
        op.add_column(
            table_name,
            sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        )
    if not _has_column(bind, table_name, "rejection_reason"):
        op.add_column(
            table_name,
            sa.Column("rejection_reason", sa.String(length=255), nullable=True),
        )

    if _has_column(bind, table_name, "processed_by_user_id") and not _has_fk(bind, table_name, fk_name):
        op.create_foreign_key(
            fk_name,
            table_name,
            "users",
            ["processed_by_user_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade():
    op.drop_constraint(
        "fk_public_update_submissions_processed_by_user",
        "public_database_update_submissions",
        type_="foreignkey",
    )
    op.drop_column("public_database_update_submissions", "rejection_reason")
    op.drop_column("public_database_update_submissions", "processed_at")
    op.drop_column("public_database_update_submissions", "processed_by_user_id")
    op.drop_column("public_database_update_submissions", "approval_status")
