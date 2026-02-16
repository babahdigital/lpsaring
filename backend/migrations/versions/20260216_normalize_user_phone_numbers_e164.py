"""normalize user phone numbers to e164

Revision ID: 20260216_normalize_user_phone_numbers_e164
Revises: 20260213_add_device_last_bytes
Create Date: 2026-02-16

Idempotent data migration:
- Normalizes users.phone_number into E.164 where possible.
- Skips updates that would conflict with existing unique phone_number values.

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "20260216_normalize_user_phone_numbers_e164"
down_revision = "20260213_add_device_last_bytes"
branch_labels = None
depends_on = None


def upgrade():
    # Postgres-only (project uses PostgreSQL). Using regexp_replace for safe digits-only extraction.
    op.execute(
        """
        WITH normalized AS (
            SELECT
                u.id,
                u.phone_number AS old_phone,
                regexp_replace(u.phone_number, '[^0-9]', '', 'g') AS digits
            FROM users u
            WHERE u.phone_number IS NOT NULL
        ),
        computed AS (
            SELECT
                id,
                old_phone,
                CASE
                    WHEN old_phone LIKE '+%' THEN old_phone
                    WHEN digits = '' THEN old_phone
                    WHEN digits LIKE '00%' AND length(digits) > 2 THEN '+' || substring(digits from 3)
                    WHEN digits LIKE '0%' THEN '+62' || substring(digits from 2)
                    WHEN digits LIKE '8%' THEN '+62' || digits
                    WHEN digits LIKE '62%' THEN '+' || digits
                    ELSE '+' || digits
                END AS new_phone
            FROM normalized
        )
        UPDATE users u
        SET phone_number = c.new_phone
        FROM computed c
        WHERE u.id = c.id
          AND c.new_phone IS NOT NULL
          AND c.new_phone <> c.old_phone
          AND NOT EXISTS (
              SELECT 1
              FROM users u2
              WHERE u2.phone_number = c.new_phone
                AND u2.id <> u.id
          );
        """
    )


def downgrade():
    # Data migration: no safe automatic downgrade.
    pass
