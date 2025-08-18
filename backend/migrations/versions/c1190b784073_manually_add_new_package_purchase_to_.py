"""Manually add NEW_PACKAGE_PURCHASE to enum

Revision ID: c1190b784073
Revises: eeb1e7f91a6c
Create Date: 2025-07-15 15:49:55.107215

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c1190b784073'
down_revision = 'eeb1e7f91a6c'
branch_labels = None
depends_on = None

# Definisikan nama constraint dan nama tabel untuk kemudahan
CONSTRAINT_NAME = 'notification_type_enum'
TABLE_NAME = 'notification_recipients'
COLUMN_NAME = 'notification_type'

# Daftar nilai ENUM sebelum perubahan (untuk downgrade)
OLD_VALUES = (
    'NEW_USER_REGISTRATION',
    'NEW_KOMANDAN_REQUEST',
    'ROLE_UPGRADE_TO_ADMIN',
    'ROLE_DOWNGRADE_TO_USER'
)

# Daftar nilai ENUM setelah perubahan (untuk upgrade)
NEW_VALUES = (
    'NEW_USER_REGISTRATION',
    'NEW_KOMANDAN_REQUEST',
    'ROLE_UPGRADE_TO_ADMIN',
    'ROLE_DOWNGRADE_TO_USER',
    'NEW_PACKAGE_PURCHASE'
)


def upgrade():
    """Idempotent penambahan nilai baru pada enum notification_type.

    Logika:
    1. Cek apakah constraint dengan nama CONSTRAINT_NAME sudah ada.
    2. Jika sudah ada DAN sudah memuat nilai baru, lewati.
    3. Jika ada tapi belum memuat nilai baru, drop lalu create ulang.
    4. Jika tidak ada, langsung create dengan nilai baru.
    """

    # Gunakan blok DO agar seluruh operasi atomic & mudah diulang tanpa error.
    op.execute(
        """
        DO $$
        DECLARE
            con_exists BOOLEAN := FALSE;
            con_has_new BOOLEAN := FALSE;
            conname TEXT; -- diperlukan untuk loop
        BEGIN
            SELECT TRUE, (pg_get_constraintdef(con.oid) LIKE '%NEW_PACKAGE_PURCHASE%')
              INTO con_exists, con_has_new
              FROM pg_constraint con
              JOIN pg_class rel ON rel.oid = con.conrelid
             WHERE rel.relname = 'notification_recipients'
               AND con.contype = 'c'
               AND con.conname = 'notification_type_enum'
             LIMIT 1;

            IF con_exists AND con_has_new THEN
                RETURN; -- sudah up to date
            END IF;

            IF con_exists THEN
                EXECUTE 'ALTER TABLE notification_recipients DROP CONSTRAINT notification_type_enum';
            ELSE
                -- Drop semua check constraint yang menyentuh kolom notification_type (nama lama tidak pasti)
                FOR conname IN
                    SELECT con.conname
                      FROM pg_constraint con
                      JOIN pg_class rel2 ON rel2.oid = con.conrelid
                     WHERE rel2.relname='notification_recipients'
                       AND con.contype='c'
                       AND pg_get_constraintdef(con.oid) LIKE '%notification_type%'
                LOOP
                    EXECUTE 'ALTER TABLE notification_recipients DROP CONSTRAINT ' || quote_ident(conname);
                END LOOP;
            END IF;

            EXECUTE 'ALTER TABLE notification_recipients ADD CONSTRAINT notification_type_enum '
                 || 'CHECK (notification_type IN (''NEW_USER_REGISTRATION'', ''NEW_KOMANDAN_REQUEST'', ''ROLE_UPGRADE_TO_ADMIN'', ''ROLE_DOWNGRADE_TO_USER'', ''NEW_PACKAGE_PURCHASE''))';
        END; $$;
        """
    )


def downgrade():
    """Revert constraint ke daftar nilai lama (idempotent)."""
    op.execute(
        """
        DO $$
        DECLARE
            con_exists BOOLEAN := FALSE;
            con_has_new BOOLEAN := FALSE;
        BEGIN
            SELECT TRUE, (pg_get_constraintdef(con.oid) LIKE '%NEW_PACKAGE_PURCHASE%')
            INTO con_exists, con_has_new
            FROM pg_constraint con
            JOIN pg_class rel ON rel.oid = con.conrelid
            WHERE rel.relname = 'notification_recipients'
              AND con.contype = 'c'
              AND con.conname = 'notification_type_enum'
            LIMIT 1;

            IF NOT con_exists THEN
                RETURN; -- Tidak ada constraint, tidak perlu apa-apa
            END IF;

            -- Jika constraint sudah memuat nilai baru maka revert ke daftar lama
            IF con_has_new THEN
                EXECUTE 'ALTER TABLE notification_recipients DROP CONSTRAINT notification_type_enum';
                EXECUTE 'ALTER TABLE notification_recipients ADD CONSTRAINT notification_type_enum \n'
                     || 'CHECK (notification_type IN (''NEW_USER_REGISTRATION'', ''NEW_KOMANDAN_REQUEST'', ''ROLE_UPGRADE_TO_ADMIN'', ''ROLE_DOWNGRADE_TO_USER''))';
            END IF; -- kalau sudah lama, no-op
        END;
        $$;
        """
    )