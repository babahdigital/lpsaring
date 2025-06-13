"""Seed default package profile

Revision ID: 55bc4a16f788
Revises: 779e989a2bd7
Create Date: 2025-06-13 02:18:05.989303

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import table, column
from sqlalchemy import String, Text
from sqlalchemy.dialects.postgresql import UUID
import uuid
import datetime

# revision identifiers, used by Alembic.
revision = 'c4a3b2f5a2a6'  # GANTI DENGAN REVISION ID BARUMU
down_revision = 'a1b2c3d4e5f6'  # GANTI DENGAN REVISION ID SEBELUMNYA
branch_labels = None
depends_on = None

def upgrade():
    """
    Menambahkan data profil 'default' ke tabel package_profiles jika belum ada.
    """
    DEFAULT_PROFILE_NAME = "default"
    
    # Definisikan struktur tabel target
    package_profiles_table = table('package_profiles',
        column('id', UUID(as_uuid=True)),
        column('profile_name', String),
        column('description', Text),
        column('created_at', sa.DateTime),
        column('updated_at', sa.DateTime)
    )

    conn = op.get_bind()
    
    # Cek apakah data sudah ada
    exists = conn.execute(
        sa.select([sa.func.count()]).where(
            package_profiles_table.c.profile_name == DEFAULT_PROFILE_NAME
        )
    ).scalar() > 0

    # Insert hanya jika data belum ada
    if not exists:
        op.bulk_insert(
            package_profiles_table,
            [{
                'id': uuid.uuid4(),
                'profile_name': DEFAULT_PROFILE_NAME,
                'description': 'Profil default sistem. Jangan diubah atau dihapus.',
                'created_at': datetime.datetime.now(datetime.timezone.utc),
                'updated_at': datetime.datetime.now(datetime.timezone.utc)
            }]
        )
        print(f"✅ Data seeder: Profil '{DEFAULT_PROFILE_NAME}' berhasil ditambahkan.")
    else:
        print(f"ℹ️ Data seeder: Profil '{DEFAULT_PROFILE_NAME}' sudah ada, skip.")

def downgrade():
    """
    Menghapus data profil 'default' jika migrasi dibatalkan.
    """
    DEFAULT_PROFILE_NAME = "default"
    
    # Hapus berdasarkan nama profil
    op.execute(
        sa.text(f"DELETE FROM package_profiles WHERE profile_name = '{DEFAULT_PROFILE_NAME}'")
    )
    print(f"🗑️ Data seeder: Profil '{DEFAULT_PROFILE_NAME}' berhasil dihapus.")
