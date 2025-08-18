"""Add ip_address column to user_devices if missing

Revision ID: 20250811_01
Revises: 20250811_00
Create Date: 2025-08-11

Idempotent: checks existence before adding / dropping.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = '20250811_01'
down_revision = '20250811_00'
branch_labels = None
depends_on = None


def _column_exists(table: str, column: str) -> bool:
    bind = op.get_bind()
    insp = inspect(bind)
    for col in insp.get_columns(table):
        if col['name'] == column:
            return True
    return False


def upgrade():
    if not _column_exists('user_devices', 'ip_address'):
        with op.batch_alter_table('user_devices') as batch:
            batch.add_column(sa.Column('ip_address', sa.String(45), nullable=True))


def downgrade():
    # Safe reversible removal (only if exists)
    if _column_exists('user_devices', 'ip_address'):
        with op.batch_alter_table('user_devices') as batch:
            batch.drop_column('ip_address')
