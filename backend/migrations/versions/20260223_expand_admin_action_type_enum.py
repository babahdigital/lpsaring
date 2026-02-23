"""expand admin_action_type_enum

Revision ID: 20260223_expand_admin_action_type_enum
Revises: 20260223_allow_nullable_transaction_package_id
Create Date: 2026-02-23

"""

from alembic import op
import sqlalchemy as sa


revision = "20260223_expand_admin_action_type_enum"
down_revision = "20260223_allow_nullable_transaction_package_id"
branch_labels = None
depends_on = None


_OLD_VALUES = (
    "CREATE_USER",
    "APPROVE_USER",
    "REJECT_USER",
    "CHANGE_USER_ROLE",
    "UPGRADE_TO_ADMIN",
    "DOWNGRADE_TO_USER",
    "DOWNGRADE_FROM_ADMIN",
    "INJECT_QUOTA",
    "SET_UNLIMITED_STATUS",
    "REVOKE_UNLIMITED_STATUS",
    "ACTIVATE_USER",
    "DEACTIVATE_USER",
    "RESET_HOTSPOT_PASSWORD",
    "GENERATE_ADMIN_PASSWORD",
    "MANUAL_USER_DELETE",
    "UPDATE_USER_PROFILE",
    "PROCESS_QUOTA_REQUEST_APPROVE",
    "PROCESS_QUOTA_REQUEST_REJECT",
    "PROCESS_QUOTA_REQUEST_PARTIALLY_APPROVED",
)


_NEW_VALUES = (
    *_OLD_VALUES,
    "BLOCK_USER",
    "UNBLOCK_USER",
    "RESET_USER_LOGIN",
    "CREATE_QRIS_BILL",
)


def upgrade():
    op.alter_column(
        "admin_action_logs",
        "action_type",
        existing_type=sa.Enum(*_OLD_VALUES, name="admin_action_type_enum", native_enum=False),
        type_=sa.Enum(*_NEW_VALUES, name="admin_action_type_enum", native_enum=False),
        existing_nullable=False,
    )


def downgrade():
    # NOTE: Downgrade will fail if there are rows using the new action types.
    op.alter_column(
        "admin_action_logs",
        "action_type",
        existing_type=sa.Enum(*_NEW_VALUES, name="admin_action_type_enum", native_enum=False),
        type_=sa.Enum(*_OLD_VALUES, name="admin_action_type_enum", native_enum=False),
        existing_nullable=False,
    )
