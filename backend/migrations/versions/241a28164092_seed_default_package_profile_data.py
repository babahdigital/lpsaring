"""Seed default package profile data

Revision ID: 241a28164092
Revises: 
Create Date: 2025-06-13 02:31:00.496403

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import table, column
from sqlalchemy import String, Text, DateTime
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
import uuid
import datetime

def upgrade():
    DEFAULT_PROFILE_NAME = "default"
    package_profiles_table = table('package_profiles',
        column('id', PG_UUID), column('profile_name', String),
        column('description', Text), column('created_at', DateTime),
        column('updated_at', DateTime)
    )
    conn = op.get_bind()
    result = conn.execute(
        sa.text(f"SELECT id FROM package_profiles WHERE profile_name = '{DEFAULT_PROFILE_NAME}'")
    ).scalar_one_or_none()
    if result is None:
        op.bulk_insert(
            package_profiles_table,
            [{
                'id': uuid.uuid4(), 'profile_name': DEFAULT_PROFILE_NAME,
                'description': 'Profil default sistem. Jangan diubah atau dihapus.',
                'created_at': datetime.datetime.now(datetime.timezone.utc),
                'updated_at': datetime.datetime.now(datetime.timezone.utc)
            }]
        )
        print(f"Data seeder: Profil '{DEFAULT_PROFILE_NAME}' berhasil ditambahkan.")
    else:
        print(f"Data seeder: Profil '{DEFAULT_PROFILE_NAME}' sudah ada, tidak ada yang dilakukan.")

def downgrade():
    DEFAULT_PROFILE_NAME = "default"
    op.execute(
        f"DELETE FROM package_profiles WHERE profile_name = '{DEFAULT_PROFILE_NAME}'"
    )
    print(f"Data seeder: Profil '{DEFAULT_PROFILE_NAME}' berhasil dihapus.")
