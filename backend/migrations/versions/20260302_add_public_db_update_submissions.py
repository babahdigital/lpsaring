"""add public database update submissions table

Revision ID: 20260302_add_public_db_update_submissions
Revises: 20260228_add_quota_mutation_ledger
Create Date: 2026-03-02

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.sql.type_api import TypeEngine


revision = "20260302_add_public_db_update_submissions"
down_revision = "20260228_add_quota_mutation_ledger"
branch_labels = None
depends_on = None


def _uuid_type(bind) -> TypeEngine:
    if bind.dialect.name == "postgresql":
        return postgresql.UUID(as_uuid=True)
    return sa.String(length=36)


def upgrade():
    bind = op.get_bind()
    uuid_col = _uuid_type(bind)

    op.create_table(
        "public_database_update_submissions",
        sa.Column("id", uuid_col, primary_key=True, nullable=False),
        sa.Column("full_name", sa.String(length=100), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("blok", sa.String(length=10), nullable=False),
        sa.Column("kamar", sa.String(length=20), nullable=False),
        sa.Column("phone_number", sa.String(length=25), nullable=True),
        sa.Column("source_ip", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_public_database_update_submissions_full_name",
        "public_database_update_submissions",
        ["full_name"],
        unique=False,
    )
    op.create_index(
        "ix_public_database_update_submissions_role",
        "public_database_update_submissions",
        ["role"],
        unique=False,
    )


def downgrade():
    op.drop_index("ix_public_database_update_submissions_role", table_name="public_database_update_submissions")
    op.drop_index("ix_public_database_update_submissions_full_name", table_name="public_database_update_submissions")
    op.drop_table("public_database_update_submissions")
