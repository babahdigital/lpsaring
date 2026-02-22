"""Align server defaults with models

Revision ID: 20260208_align_server_defaults
Revises: c81cfcd63139
Create Date: 2026-02-08 08:30:00.000000

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20260208_align_server_defaults"
down_revision = "c81cfcd63139"
branch_labels = None
depends_on = None


def upgrade():
    # users
    op.alter_column(
        "users",
        "role",
        existing_type=sa.Enum("USER", "KOMANDAN", "ADMIN", "SUPER_ADMIN", name="user_role_enum", native_enum=False),
        server_default="USER",
    )
    op.alter_column(
        "users",
        "approval_status",
        existing_type=sa.Enum(
            "PENDING_APPROVAL", "APPROVED", "REJECTED", name="approval_status_enum", native_enum=False
        ),
        server_default="PENDING_APPROVAL",
    )

    # packages
    op.alter_column(
        "packages",
        "is_active",
        existing_type=sa.Boolean(),
        server_default=sa.text("true"),
    )
    op.alter_column(
        "packages",
        "data_quota_gb",
        existing_type=sa.Numeric(precision=8, scale=2),
        server_default=sa.text("0"),
    )
    op.alter_column(
        "packages",
        "duration_days",
        existing_type=sa.Integer(),
        server_default=sa.text("30"),
    )

    # promo_events
    op.alter_column(
        "promo_events",
        "event_type",
        existing_type=sa.Enum(
            "BONUS_REGISTRATION", "GENERAL_ANNOUNCEMENT", name="promo_event_type_enum", native_enum=False
        ),
        server_default="GENERAL_ANNOUNCEMENT",
    )
    op.alter_column(
        "promo_events",
        "status",
        existing_type=sa.Enum(
            "DRAFT", "ACTIVE", "SCHEDULED", "EXPIRED", "ARCHIVED", name="promo_event_status_enum", native_enum=False
        ),
        server_default="DRAFT",
    )

    # transactions
    op.alter_column(
        "transactions",
        "status",
        existing_type=sa.Enum(
            "PENDING",
            "SUCCESS",
            "FAILED",
            "EXPIRED",
            "CANCELLED",
            "UNKNOWN",
            name="transaction_status_enum",
            native_enum=False,
        ),
        server_default="PENDING",
    )

    # quota_requests
    op.alter_column(
        "quota_requests",
        "status",
        existing_type=sa.Enum(
            "PENDING", "APPROVED", "REJECTED", "PARTIALLY_APPROVED", name="request_status_enum", native_enum=False
        ),
        server_default="PENDING",
    )


def downgrade():
    # users
    op.alter_column(
        "users",
        "role",
        existing_type=sa.Enum("USER", "KOMANDAN", "ADMIN", "SUPER_ADMIN", name="user_role_enum", native_enum=False),
        server_default=None,
    )
    op.alter_column(
        "users",
        "approval_status",
        existing_type=sa.Enum(
            "PENDING_APPROVAL", "APPROVED", "REJECTED", name="approval_status_enum", native_enum=False
        ),
        server_default=None,
    )

    # packages
    op.alter_column(
        "packages",
        "is_active",
        existing_type=sa.Boolean(),
        server_default=None,
    )
    op.alter_column(
        "packages",
        "data_quota_gb",
        existing_type=sa.Numeric(precision=8, scale=2),
        server_default=None,
    )
    op.alter_column(
        "packages",
        "duration_days",
        existing_type=sa.Integer(),
        server_default=None,
    )

    # promo_events
    op.alter_column(
        "promo_events",
        "event_type",
        existing_type=sa.Enum(
            "BONUS_REGISTRATION", "GENERAL_ANNOUNCEMENT", name="promo_event_type_enum", native_enum=False
        ),
        server_default=None,
    )
    op.alter_column(
        "promo_events",
        "status",
        existing_type=sa.Enum(
            "DRAFT", "ACTIVE", "SCHEDULED", "EXPIRED", "ARCHIVED", name="promo_event_status_enum", native_enum=False
        ),
        server_default=None,
    )

    # transactions
    op.alter_column(
        "transactions",
        "status",
        existing_type=sa.Enum(
            "PENDING",
            "SUCCESS",
            "FAILED",
            "EXPIRED",
            "CANCELLED",
            "UNKNOWN",
            name="transaction_status_enum",
            native_enum=False,
        ),
        server_default=None,
    )

    # quota_requests
    op.alter_column(
        "quota_requests",
        "status",
        existing_type=sa.Enum(
            "PENDING", "APPROVED", "REJECTED", "PARTIALLY_APPROVED", name="request_status_enum", native_enum=False
        ),
        server_default=None,
    )
