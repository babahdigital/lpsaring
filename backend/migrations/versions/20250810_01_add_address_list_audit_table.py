"""add address_list_audit table

Revision ID: 20250810_01
Revises: eeb1e7f91a6c
Create Date: 2025-08-10
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision = '20250810_01'
down_revision = 'eeb1e7f91a6c'
branch_labels = None
depends_on = None

def upgrade():
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = inspector.get_table_names()

    if 'address_list_audit' not in tables:
        op.create_table(
            'address_list_audit',
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            # Perubahan: Menghapus index=True dari kolom berikut
            sa.Column('user_id', sa.String(length=64), nullable=True),
            sa.Column('phone_comment', sa.String(length=32), nullable=True),
            sa.Column('old_ip', sa.String(length=64), nullable=True),
            sa.Column('new_ip', sa.String(length=64), nullable=True),
            sa.Column('old_mac', sa.String(length=32), nullable=True),
            sa.Column('new_mac', sa.String(length=32), nullable=True),
            sa.Column('action_source', sa.String(length=64), nullable=True, server_default='authorize-device'),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )

    # Blok ini sudah benar, pengecekan index dilakukan secara eksplisit dan idempotent.
    # Kita akan melakukan inspeksi ulang setelah tabel dipastikan ada.
    inspector = inspect(bind) # Inspeksi ulang untuk memastikan inspector tahu tentang tabel yang baru dibuat.
    existing_indexes = {ix['name'] for ix in inspector.get_indexes('address_list_audit')}
    
    if 'ix_address_list_audit_user_id' not in existing_indexes:
        op.create_index('ix_address_list_audit_user_id', 'address_list_audit', ['user_id'])
    if 'ix_address_list_audit_phone_comment' not in existing_indexes:
        op.create_index('ix_address_list_audit_phone_comment', 'address_list_audit', ['phone_comment'])
    if 'ix_address_list_audit_created_at' not in existing_indexes:
        op.create_index('ix_address_list_audit_created_at', 'address_list_audit', ['created_at'])

def downgrade():
    # Fungsi downgrade sudah benar, tidak perlu diubah.
    op.drop_index('ix_address_list_audit_created_at', table_name='address_list_audit', if_exists=True)
    op.drop_index('ix_address_list_audit_phone_comment', table_name='address_list_audit', if_exists=True)
    op.drop_index('ix_address_list_audit_user_id', table_name='address_list_audit', if_exists=True)
    op.drop_table('address_list_audit', if_exists=True)