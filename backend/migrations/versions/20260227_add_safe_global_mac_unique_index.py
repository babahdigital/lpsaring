"""add safe global mac unique index

Revision ID: 20260227_add_safe_global_mac_unique_index
Revises: 20260224_add_auto_debt_offset_mb
Create Date: 2026-02-27

"""

from alembic import op


revision = "20260227_add_safe_global_mac_unique_index"
down_revision = "20260224_add_auto_debt_offset_mb"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_user_devices_mac_authorized
        ON user_devices (mac_address)
        WHERE is_authorized = TRUE;
        """
    )

    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM (
                    SELECT UPPER(mac_address) AS mac_norm
                    FROM user_devices
                    WHERE is_authorized = TRUE
                    GROUP BY UPPER(mac_address)
                    HAVING COUNT(*) > 1
                ) dup
            ) THEN
                CREATE UNIQUE INDEX IF NOT EXISTS uq_user_devices_authorized_mac_global
                ON user_devices (UPPER(mac_address))
                WHERE is_authorized = TRUE;
            END IF;
        END
        $$;
        """
    )


def downgrade():
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.execute("DROP INDEX IF EXISTS uq_user_devices_authorized_mac_global;")
    op.execute("DROP INDEX IF EXISTS ix_user_devices_mac_authorized;")
