"""backfill price_rp for existing debt records where price_rp is NULL

Extract price from the note field which was stored as:
  "Paket: {name} ({quota_str}, Rp {price:,})"

For records whose note doesn't match the pattern (old free-text notes),
price_rp stays NULL — that is acceptable; frontend already falls back to
estimated_rp.

Revision ID: 20260319_d_backfill_price_rp_from_note
Revises: 20260319_c_populate_null_due_dates
Create Date: 2026-03-19

"""

from alembic import op
import sqlalchemy as sa


revision = "20260319_d_backfill_price_rp_from_note"
down_revision = "20260319_c_populate_null_due_dates"
branch_labels = None
depends_on = None


def upgrade():
    # Extract Rp amount from note pattern: "Paket: ... (... , Rp 50.000)"
    # Regex: "Rp " followed by digits/dots/commas/spaces, capture digits only.
    # PostgreSQL regexp_replace removes dots/commas to get plain integer string.
    op.execute(
        """
        UPDATE user_quota_debts
        SET price_rp = (
            regexp_replace(
                (regexp_match(note, 'Rp\\s+([\\d.,]+)'))[1],
                '[.,]',
                '',
                'g'
            )::bigint
        )
        WHERE price_rp IS NULL
          AND note IS NOT NULL
          AND note ~ 'Rp\\s+[\\d.,]+'
        """
    )


def downgrade():
    # Cannot reliably reverse — we don't know which rows were updated.
    # This is a safe data enrichment migration; downgrade is a no-op.
    pass
