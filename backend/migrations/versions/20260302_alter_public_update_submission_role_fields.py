"""alter public update submission role fields

Revision ID: 20260302_alter_public_update_submission_role_fields
Revises: 20260302_add_public_update_submission_approval_fields
Create Date: 2026-03-02

"""

from alembic import op
import sqlalchemy as sa


revision = "20260302_alter_public_update_submission_role_fields"
down_revision = "20260302_add_public_update_submission_approval_fields"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column("public_database_update_submissions", "blok", existing_type=sa.String(length=10), nullable=True)
    op.alter_column("public_database_update_submissions", "kamar", existing_type=sa.String(length=20), nullable=True)
    op.add_column(
        "public_database_update_submissions",
        sa.Column("tamping_type", sa.String(length=50), nullable=True),
    )


def downgrade():
    op.drop_column("public_database_update_submissions", "tamping_type")
    op.alter_column("public_database_update_submissions", "kamar", existing_type=sa.String(length=20), nullable=False)
    op.alter_column("public_database_update_submissions", "blok", existing_type=sa.String(length=10), nullable=False)
