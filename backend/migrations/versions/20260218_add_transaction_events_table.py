"""add transaction events table

Revision ID: 20260218_add_transaction_events_table
Revises: 20260218_add_midtrans_notification_payload_to_transactions
Create Date: 2026-02-18

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260218_add_transaction_events_table"
down_revision = "20260218_add_midtrans_notification_payload_to_transactions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "transaction_events",
        sa.Column("id", sa.UUID(), primary_key=True, nullable=False),
        sa.Column("transaction_id", sa.UUID(), nullable=False),
        sa.Column(
            "source",
            sa.Enum(
                "APP",
                "MIDTRANS_WEBHOOK",
                "MIDTRANS_STATUS",
                name="transaction_event_source_enum",
                native_enum=False,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "PENDING",
                "SUCCESS",
                "FAILED",
                "EXPIRED",
                "CANCELLED",
                "UNKNOWN",
                name="transaction_status_enum",
                native_enum=False,
            ),
            nullable=True,
        ),
        sa.Column("payload", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["transaction_id"],
            ["transactions.id"],
            name="fk_transaction_events_transaction_id_transactions",
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_transaction_events_transaction_id", "transaction_events", ["transaction_id"], unique=False)
    op.create_index("ix_transaction_events_created_at", "transaction_events", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_transaction_events_created_at", table_name="transaction_events")
    op.drop_index("ix_transaction_events_transaction_id", table_name="transaction_events")
    op.drop_table("transaction_events")
