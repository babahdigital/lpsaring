"""add quota debt notification type

Revision ID: 20260217_add_quota_debt_notification_type
Revises: 20260216_add_refresh_tokens
Create Date: 2026-02-17

"""

from alembic import op


# revision identifiers, used by Alembic.
revision = '20260217_add_quota_debt_notification_type'
down_revision = '20260216_add_refresh_tokens'
branch_labels = None
depends_on = None


_ALLOWED = (
    'NEW_USER_REGISTRATION',
    'NEW_KOMANDAN_REQUEST',
    'ROLE_UPGRADE_TO_ADMIN',
    'ROLE_DOWNGRADE_TO_USER',
    'QUOTA_DEBT_LIMIT_EXCEEDED',
)


def upgrade():
    # SQLAlchemy Enum(native_enum=False) creates a CHECK constraint in Postgres.
    allowed_sql = ', '.join([f"'{v}'" for v in _ALLOWED])

    # Try common constraint names to be resilient across environments.
    op.execute(
        """
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'notification_type_enum') THEN
    ALTER TABLE notification_recipients DROP CONSTRAINT notification_type_enum;
  END IF;
  IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'notification_recipients_notification_type_check') THEN
    ALTER TABLE notification_recipients DROP CONSTRAINT notification_recipients_notification_type_check;
  END IF;
END $$;
"""
    )

    op.execute(
        f"ALTER TABLE notification_recipients ADD CONSTRAINT notification_type_enum CHECK (notification_type IN ({allowed_sql}));"
    )


def downgrade():
    allowed = (
        'NEW_USER_REGISTRATION',
        'NEW_KOMANDAN_REQUEST',
        'ROLE_UPGRADE_TO_ADMIN',
        'ROLE_DOWNGRADE_TO_USER',
    )
    allowed_sql = ', '.join([f"'{v}'" for v in allowed])

    op.execute(
        """
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'notification_type_enum') THEN
    ALTER TABLE notification_recipients DROP CONSTRAINT notification_type_enum;
  END IF;
  IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'notification_recipients_notification_type_check') THEN
    ALTER TABLE notification_recipients DROP CONSTRAINT notification_recipients_notification_type_check;
  END IF;
END $$;
"""
    )
    op.execute(
        f"ALTER TABLE notification_recipients ADD CONSTRAINT notification_type_enum CHECK (notification_type IN ({allowed_sql}));"
    )
