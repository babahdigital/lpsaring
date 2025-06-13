# migrations/versions/120625_seed_default_mikrotik_profile_data.py
"""Seed default Mikrotik profile data

Revision ID: 130625
Revises:
Create Date: 2025-06-13 10:01:00.676418

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import table, column
from sqlalchemy import String, Text, DateTime, UUID as PG_UUID
import uuid
import datetime

# revision identifiers, used by Alembic.
revision = '<your_revision_id>'
down_revision = '<previous_revision_id>'
branch_labels = None
depends_on = None

# Nama profil default yang akan digunakan secara konsisten
DEFAULT_PROFILE_NAME = "default"
DEFAULT_PROFILE_ID = str(uuid.uuid4()) # Generate ID yang konsisten untuk operasi ini

def upgrade():
    # Dapatkan koneksi saat ini untuk eksekusi perintah
    conn = op.get_bind()

    # Periksa apakah profil 'default' sudah ada
    result = conn.execute(
        sa.text(f"SELECT id FROM package_profiles WHERE profile_name = '{DEFAULT_PROFILE_NAME}'")
    ).scalar_one_or_none()

    # Jika tidak ada, maka masukan data
    if result is None:
        # Definisikan struktur tabel untuk bulk insert
        package_profiles_table = table('package_profiles',
            column('id', PG_UUID),
            column('profile_name', String),
            column('description', Text),
            column('created_at', DateTime),
            column('updated_at', DateTime)
        )

        op.bulk_insert(
            package_profiles_table,
            [
                {
                    'id': DEFAULT_PROFILE_ID,
                    'profile_name': DEFAULT_PROFILE_NAME,
                    'description': 'Profil default sistem. JANGAN DIHAPUS atau DIUBAH.',
                    'created_at': datetime.datetime.now(datetime.timezone.utc),
                    'updated_at': datetime.datetime.now(datetime.timezone.utc)
                }
            ]
        )
        print(f"Default profile '{DEFAULT_PROFILE_NAME}' has been seeded.")
    else:
        print(f"Default profile '{DEFAULT_PROFILE_NAME}' already exists. Skipping seed.")


def downgrade():
    # Logika untuk menghapus data jika migrasi dibatalkan
    # Ini opsional tapi merupakan praktik yang baik
    op.execute(
        f"DELETE FROM package_profiles WHERE profile_name = '{DEFAULT_PROFILE_NAME}'"
    )
    print(f"Default profile '{DEFAULT_PROFILE_NAME}' has been removed.")