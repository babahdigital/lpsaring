"""Seed expired package profile data

Revision ID: a6f464955c05
Revises: 241a28164092
Create Date: 2025-06-13 02:47:54.363378

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
revision = 'a6f464955c05'
down_revision = '241a28164092'
branch_labels = None
depends_on = None


def upgrade():
    """
    Menambahkan data profil 'expired' ke tabel package_profiles jika belum ada.
    """
    EXPIRED_PROFILE_NAME = "expired"

    package_profiles_table = table('package_profiles',
        column('id', PG_UUID),
        column('profile_name', String),
        column('description', Text),
        column('created_at', DateTime),
        column('updated_at', DateTime)
    )

    conn = op.get_bind()

    result = conn.execute(
        sa.text(f"SELECT id FROM package_profiles WHERE profile_name = '{EXPIRED_PROFILE_NAME}'")
    ).scalar_one_or_none()

    if result is None:
        op.bulk_insert(
            package_profiles_table,
            [
                {
                    'id': uuid.uuid4(),
                    'profile_name': EXPIRED_PROFILE_NAME,
                    'description': 'Profil sistem untuk pengguna yang ditolak/kadaluarsa. Jangan diubah atau dihapus.',
                    'created_at': datetime.datetime.now(datetime.timezone.utc),
                    'updated_at': datetime.datetime.now(datetime.timezone.utc)
                }
            ]
        )
        print(f"Data seeder: Profil '{EXPIRED_PROFILE_NAME}' berhasil ditambahkan.")
    else:
        print(f"Data seeder: Profil '{EXPIRED_PROFILE_NAME}' sudah ada, tidak ada yang dilakukan.")


def downgrade():
    """
    Menghapus data profil 'expired' jika migrasi dibatalkan.
    """
    EXPIRED_PROFILE_NAME = "expired"
    op.execute(
        f"DELETE FROM package_profiles WHERE profile_name = '{EXPIRED_PROFILE_NAME}'"
    )
    print(f"Data seeder: Profil '{EXPIRED_PROFILE_NAME}' berhasil dihapus.")
