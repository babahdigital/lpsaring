"""expand notification_type varchar length

Revision ID: 20260217_expand_notification_type_varchar_length
Revises: 20260217_add_quota_debt_notification_type
Create Date: 2026-02-17

"""

from alembic import op


# revision identifiers, used by Alembic.
revision = '20260217_expand_notification_type_varchar_length'
down_revision = '20260217_add_quota_debt_notification_type'
branch_labels = None
depends_on = None


def upgrade():
    # SQLAlchemy Enum(native_enum=False) uses VARCHAR with a fixed length.
    # New NotificationType values (ex: QUOTA_DEBT_LIMIT_EXCEEDED) exceed the old length (22),
    # so we expand to a safe length.
    op.execute(
        "ALTER TABLE notification_recipients ALTER COLUMN notification_type TYPE VARCHAR(64);"
    )


def downgrade():
    # Best-effort rollback. This can fail if rows already contain values longer than 22 chars.
    op.execute(
        "ALTER TABLE notification_recipients ALTER COLUMN notification_type TYPE VARCHAR(22);"
    )
