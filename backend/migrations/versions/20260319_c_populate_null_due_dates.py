"""populate due_date for existing debt records where due_date is NULL

For all existing manual debt records without a due_date, set due_date to the
last day of the same month as debt_date (or created_at if debt_date is NULL).
This ensures WhatsApp reminders work and display shows correct deadline.

Revision ID: 20260319_c_populate_null_due_dates
Revises: 20260319_add_price_rp_to_user_quota_debts
Create Date: 2026-03-19

"""

from alembic import op


revision = "20260319_c_populate_null_due_dates"
down_revision = "20260319_add_price_rp_to_user_quota_debts"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        UPDATE user_quota_debts
        SET due_date = (
            date_trunc('month', COALESCE(debt_date, created_at::date))
            + interval '1 month' - interval '1 day'
        )::date
        WHERE due_date IS NULL
        """
    )


def downgrade():
    # Cannot safely distinguish which records were auto-populated vs intentionally NULL.
    # Downgrade is a no-op.
    pass
