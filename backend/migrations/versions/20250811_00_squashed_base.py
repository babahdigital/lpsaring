"""Squashed base schema (optional fresh deploy)

Revision ID: 20250811_00
Revises: 20250810_02
Create Date: 2025-08-11

WARNING:
  - Dipakai hanya untuk fresh install baru (stamp langsung ke revisi ini) tanpa menjalankan seluruh sejarah.
  - Environment existing yang sudah jalan TIDAK perlu (dan jangan) menjalankan migrasi ini.
  - Idempotent: cek tabel sebelum create agar aman pada rerun.
"""
from alembic import op
import sqlalchemy as sa

revision = '20250811_00'
down_revision = '20250810_02'
branch_labels = None
depends_on = None

def _table_exists(conn, name: str) -> bool:
    insp = sa.inspect(conn)
    return name in insp.get_table_names()

def upgrade():
    conn = op.get_bind()
    # Contoh subset penting (ringkas). Tambah tabel lain bila perlu.
    # USERS
    if not _table_exists(conn, 'users'):
        op.create_table('users',
            sa.Column('id', sa.UUID(), primary_key=True),
            sa.Column('phone_number', sa.String(25), nullable=False, unique=True),
            sa.Column('password_hash', sa.String(255)),
            sa.Column('full_name', sa.String(100), nullable=False),
            sa.Column('blok', sa.String(10)),
            sa.Column('kamar', sa.String(20)),
            sa.Column('previous_blok', sa.String(10)),
            sa.Column('previous_kamar', sa.String(20)),
            sa.Column('is_active', sa.Boolean(), server_default=sa.text('false'), nullable=False),
            sa.Column('is_blocked', sa.Boolean(), server_default=sa.text('false'), nullable=False),
            sa.Column('blocking_reason', sa.String(255)),
            sa.Column('trusted_mac_address', sa.String(17)),
            sa.Column('role', sa.String(20), nullable=False),
            sa.Column('approval_status', sa.String(30), nullable=False, server_default=sa.text("'PENDING_APPROVAL'")),
            sa.Column('mikrotik_user_exists', sa.Boolean(), server_default=sa.text('false'), nullable=False),
            sa.Column('mikrotik_server_name', sa.String(100)),
            sa.Column('mikrotik_profile_name', sa.String(100)),
            sa.Column('mikrotik_password', sa.String(255)),
            sa.Column('total_quota_purchased_mb', sa.BigInteger(), server_default='0', nullable=False),
            sa.Column('total_quota_used_mb', sa.Numeric(15,2), server_default='0.0', nullable=False),
            sa.Column('quota_expiry_date', sa.DateTime(timezone=True)),
            sa.Column('is_unlimited_user', sa.Boolean(), server_default=sa.text('false'), nullable=False),
            sa.Column('device_brand', sa.String(100)),
            sa.Column('device_model', sa.String(100)),
            sa.Column('raw_user_agent', sa.Text()),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
            sa.Column('approved_at', sa.DateTime(timezone=True)),
            sa.Column('approved_by_id', sa.UUID()),
            sa.Column('rejected_by_id', sa.UUID()),
            sa.Column('last_login_at', sa.DateTime(timezone=True)),
            sa.Column('last_login_ip', sa.String(45)),
            sa.Column('last_login_mac', sa.String(17)),
            sa.Column('last_low_quota_notif_at', sa.DateTime(timezone=True)),
            sa.Column('last_fup_notif_at', sa.DateTime(timezone=True)),
            sa.Column('last_habis_notif_at', sa.DateTime(timezone=True)),
            sa.Column('last_expiry_notif_at', sa.DateTime(timezone=True)),
        )
    # USER DEVICES
    if not _table_exists(conn, 'user_devices'):
        op.create_table('user_devices',
            sa.Column('id', sa.UUID(), primary_key=True),
            sa.Column('user_id', sa.UUID(), nullable=False),
            sa.Column('ip_address', sa.String(45)),
            sa.Column('mac_address', sa.String(17), nullable=False),
            sa.Column('device_name', sa.String(100)),
            sa.Column('last_seen_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
            sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        )
    # TRANSACTIONS
    if not _table_exists(conn, 'transactions'):
        op.create_table('transactions',
            sa.Column('id', sa.UUID(), primary_key=True),
            sa.Column('user_id', sa.UUID()),
            sa.Column('package_id', sa.UUID(), nullable=False),
            sa.Column('midtrans_order_id', sa.String(100), nullable=False),
            sa.Column('midtrans_transaction_id', sa.String(100)),
            sa.Column('snap_token', sa.String(200)),
            sa.Column('snap_redirect_url', sa.String(255)),
            sa.Column('amount', sa.BigInteger(), nullable=False),
            sa.Column('status', sa.String(30), nullable=False),
            sa.Column('payment_method', sa.String(50)),
            sa.Column('payment_time', sa.DateTime(timezone=True)),
            sa.Column('expiry_time', sa.DateTime(timezone=True)),
            sa.Column('va_number', sa.String(50)),
            sa.Column('payment_code', sa.String(50)),
            sa.Column('biller_code', sa.String(20)),
            sa.Column('qr_code_url', sa.String(512)),
            sa.Column('hotspot_password', sa.String(255)),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        )
    # ADDRESS LIST AUDIT
    if not _table_exists(conn, 'address_list_audit'):
        op.create_table('address_list_audit',
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('user_id', sa.String(64)),
            sa.Column('phone_comment', sa.String(32)),
            sa.Column('old_ip', sa.String(64)),
            sa.Column('new_ip', sa.String(64)),
            sa.Column('old_mac', sa.String(32)),
            sa.Column('new_mac', sa.String(32)),
            sa.Column('action_source', sa.String(64), server_default='authorize-device'),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        )

def downgrade():
    pass
