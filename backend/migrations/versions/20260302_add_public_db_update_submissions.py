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


def _has_column(bind, table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(bind)
    return any(col["name"] == column_name for col in inspector.get_columns(table_name))


def _has_index(bind, table_name: str, index_name: str) -> bool:
    inspector = sa.inspect(bind)
    return any(idx.get("name") == index_name for idx in inspector.get_indexes(table_name))


def upgrade():
    bind = op.get_bind()
    uuid_col = _uuid_type(bind)
    inspector = sa.inspect(bind)
    table_name = "public_database_update_submissions"

    if not inspector.has_table(table_name):
        op.create_table(
            table_name,
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
    else:
        if not _has_column(bind, table_name, "id"):
            op.add_column(table_name, sa.Column("id", uuid_col, nullable=False))
        if not _has_column(bind, table_name, "full_name"):
            op.add_column(table_name, sa.Column("full_name", sa.String(length=100), nullable=False))
        if not _has_column(bind, table_name, "role"):
            op.add_column(table_name, sa.Column("role", sa.String(length=20), nullable=False))
        if not _has_column(bind, table_name, "blok"):
            op.add_column(table_name, sa.Column("blok", sa.String(length=10), nullable=False))
        if not _has_column(bind, table_name, "kamar"):
            op.add_column(table_name, sa.Column("kamar", sa.String(length=20), nullable=False))
        if not _has_column(bind, table_name, "phone_number"):
            op.add_column(table_name, sa.Column("phone_number", sa.String(length=25), nullable=True))
        if not _has_column(bind, table_name, "source_ip"):
            op.add_column(table_name, sa.Column("source_ip", sa.String(length=64), nullable=True))
        if not _has_column(bind, table_name, "created_at"):
            op.add_column(
                table_name,
                sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            )
        if not _has_column(bind, table_name, "updated_at"):
            op.add_column(
                table_name,
                sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            )

    if not _has_index(bind, table_name, "ix_public_database_update_submissions_full_name"):
        op.create_index(
            "ix_public_database_update_submissions_full_name",
            table_name,
            ["full_name"],
            unique=False,
        )
    if not _has_index(bind, table_name, "ix_public_database_update_submissions_role"):
        op.create_index(
            "ix_public_database_update_submissions_role",
            table_name,
            ["role"],
            unique=False,
        )


def downgrade():
    op.drop_index("ix_public_database_update_submissions_role", table_name="public_database_update_submissions")
    op.drop_index("ix_public_database_update_submissions_full_name", table_name="public_database_update_submissions")
    op.drop_table("public_database_update_submissions")
