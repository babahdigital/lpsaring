"""Seed default package profile data

Revision ID: 241a28164092
Revises: 
Create Date: 2025-06-13 02:31:00.496403

"""
from alembic import op
import sqlalchemy as sa
# Impor tambahan yang dibutuhkan untuk migrasi data
from sqlalchemy.sql import table, column
from sqlalchemy import String, Text, DateTime
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
import uuid
import datetime


# revision identifiers, used by Alembic.
# Bagian ini sudah benar dan dibuat secara otomatis. Jangan diubah.
revision = '241a28164092'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    """
    Menambahkan data profil 'default' ke tabel package_profiles jika belum ada.
    """
    DEFAULT_PROFILE_NAME = "default"

    # Definisikan struktur tabel target untuk operasi data
    package_profiles_table = table('package_profiles',
        column('id', PG_UUID),
        column('profile_name', String),
        column('description', Text),
        column('created_at', DateTime),
        column('updated_at', DateTime)
    )

    # Dapatkan koneksi saat ini untuk eksekusi perintah
    conn = op.get_bind()

    # Periksa apakah profil 'default' sudah ada untuk mencegah duplikasi
    result = conn.execute(
        sa.text(f"SELECT id FROM package_profiles WHERE profile_name = '{DEFAULT_PROFILE_NAME}'")
    ).scalar_one_or_none()

    # Jika tidak ada (hasilnya None), maka masukan data baru
    if result is None:
        op.bulk_insert(
            package_profiles_table,
            [
                {
                    'id': uuid.uuid4(), # Generate ID baru saat insert
                    'profile_name': DEFAULT_PROFILE_NAME,
                    'description': 'Profil default sistem. Jangan diubah atau dihapus.',
                    'created_at': datetime.datetime.now(datetime.timezone.utc),
                    'updated_at': datetime.datetime.now(datetime.timezone.utc)
                }
            ]
        )
        print(f"Data seeder: Profil '{DEFAULT_PROFILE_NAME}' berhasil ditambahkan.")
    else:
        print(f"Data seeder: Profil '{DEFAULT_PROFILE_NAME}' sudah ada, tidak ada yang dilakukan.")


def downgrade():
    """
    Menghapus data profil 'default' jika migrasi dibatalkan.
    """
    DEFAULT_PROFILE_NAME = "default"
    
    # Hapus data yang ditambahkan pada saat upgrade berdasarkan nama profil
    op.execute(
        f"DELETE FROM package_profiles WHERE profile_name = '{DEFAULT_PROFILE_NAME}'"
    )
    print(f"Data seeder: Profil '{DEFAULT_PROFILE_NAME}' berhasil dihapus.")