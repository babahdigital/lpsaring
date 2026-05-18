"""Expand admin_action_type_enum: add RESET_USER_PASSWORD, TRANSACTION_RECONCILE, SEND_WHATSAPP_NOTIFICATION

Model `AdminActionType` (models.py:111) sudah mendefinisikan 3 nilai tersebut dan
code paths produksi (user_management_routes.py, transactions/contexts, WA notifier)
sudah menulisnya. Tanpa migrasi ini, INSERT akan trigger CheckViolation karena
constraint admin_action_type_enum versi terakhir (20260223) belum mengenal nilai-nilai itu.

Revision ID: 20260518_expand_admin_action_type_enum_v3
Revises: 20260326_fix_fk_ondelete_set_null
Create Date: 2026-05-18
"""

from alembic import op
import sqlalchemy as sa


revision = "20260518_expand_admin_action_type_enum_v3"
down_revision = "20260326_fix_fk_ondelete_set_null"
branch_labels = None
depends_on = None


_PREV_VALUES = (
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
    "BLOCK_USER",
    "UNBLOCK_USER",
    "RESET_USER_LOGIN",
    "CREATE_QRIS_BILL",
    "ADMIN_API_MUTATION",
)


_NEW_VALUES = (
    *_PREV_VALUES,
    "RESET_USER_PASSWORD",
    "TRANSACTION_RECONCILE",
    "SEND_WHATSAPP_NOTIFICATION",
)


def upgrade():
    op.alter_column(
        "admin_action_logs",
        "action_type",
        existing_type=sa.Enum(*_PREV_VALUES, name="admin_action_type_enum", native_enum=False),
        type_=sa.Enum(*_NEW_VALUES, name="admin_action_type_enum", native_enum=False),
        existing_nullable=False,
    )


def downgrade():
    # WARNING: akan gagal jika ada baris yang sudah memakai nilai baru.
    op.alter_column(
        "admin_action_logs",
        "action_type",
        existing_type=sa.Enum(*_NEW_VALUES, name="admin_action_type_enum", native_enum=False),
        type_=sa.Enum(*_PREV_VALUES, name="admin_action_type_enum", native_enum=False),
        existing_nullable=False,
    )
