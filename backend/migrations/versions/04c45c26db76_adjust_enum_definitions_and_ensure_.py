"""Adjust enum definitions and ensure model registration

Revision ID: 04c45c26db76
Revises: 76badf8cb3dc
Create Date: 2025-05-08 13:24:16.848534

"""
from alembic import op
import sqlalchemy as sa
# sqlalchemy.dialects.postgresql mungkin tidak secara eksplisit dibutuhkan di sini
# jika kita tidak mendefinisikan existing_type dengan postgresql.ENUM secara detail

# revision identifiers, used by Alembic.
revision = '04c45c26db76'
down_revision = '76badf8cb3dc'
branch_labels = None
depends_on = None


def upgrade():
    # Asumsi: Tipe ENUM baru ('userblokenum', 'userkamarenum')
    # sudah berhasil dibuat oleh Alembic/SQLAlchemy berdasarkan definisi di models.py
    # (karena create_type=True dan perbaikan impor di env.py).
    # Error utama yang kita atasi di sini adalah DatatypeMismatch saat ALTER COLUMN.

    # Tipe ENUM target (baru)
    userblokenum_target_type = sa.Enum('A', 'B', 'C', 'D', 'E', 'F', name='userblokenum', inherit_schema=True)
    userkamarenum_target_type = sa.Enum('1', '2', '3', '4', '5', '6', name='userkamarenum', inherit_schema=True)

    # Opsional: Jaring pengaman untuk memastikan tipe baru ada.
    # Jika Anda sangat yakin create_type=True di model sudah cukup, ini bisa di-skip.
    # Namun, mengingat histori masalah, ini tetap direkomendasikan.
    userblokenum_target_type.create(op.get_bind(), checkfirst=True)
    userkamarenum_target_type.create(op.get_bind(), checkfirst=True)

    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.alter_column('blok',
               # existing_type bisa disederhanakan jika tidak ingin detail,
               # namun lebih akurat jika mencerminkan tipe lama.
               # Untuk PostgreSQL, nama tipe lama penting untuk diketahui.
               existing_type=sa.Enum(name='user_blok_enum', create_type=False), # Minimal nama tipe lama
               type_=userblokenum_target_type,
               existing_nullable=True,
               postgresql_using='blok::text::userblokenum')

        batch_op.alter_column('kamar',
               existing_type=sa.Enum(name='user_kamar_enum', create_type=False), # Minimal nama tipe lama
               type_=userkamarenum_target_type,
               existing_nullable=True,
               postgresql_using='kamar::text::userkamarenum')

    # Catatan: Jika nilai-nilai ENUM ('A', 'B', 'C', dll.) juga berubah
    # antara tipe lama dan baru, klausa USING mungkin perlu logika yang lebih kompleks.
    # Saat ini, kita berasumsi nilai anggota ENUM tetap sama, hanya nama tipenya yang berubah.

def downgrade():
    # Tipe ENUM target untuk downgrade (kembali ke nama lama)
    userblok_downgrade_target_type = sa.Enum('A', 'B', 'C', 'D', 'E', 'F', name='user_blok_enum', inherit_schema=True)
    userkamar_downgrade_target_type = sa.Enum('1', '2', '3', '4', '5', '6', name='user_kamar_enum', inherit_schema=True)

    # Opsional: Pastikan tipe tujuan downgrade ada/dibuat.
    userblok_downgrade_target_type.create(op.get_bind(), checkfirst=True)
    userkamar_downgrade_target_type.create(op.get_bind(), checkfirst=True)

    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.alter_column('kamar',
               existing_type=sa.Enum(name='userkamarenum', create_type=False), # Tipe saat ini sebelum downgrade
               type_=userkamar_downgrade_target_type,
               existing_nullable=True,
               postgresql_using='kamar::text::user_kamar_enum')

        batch_op.alter_column('blok',
               existing_type=sa.Enum(name='userblokenum', create_type=False), # Tipe saat ini sebelum downgrade
               type_=userblok_downgrade_target_type,
               existing_nullable=True,
               postgresql_using='blok::text::user_blok_enum')

    # Jika Anda ingin menghapus tipe ENUM 'userblokenum' dan 'userkamarenum'
    # saat downgrade (PERHATIAN: ini menghapus definisi tipe dari DB):
    # op.execute('DROP TYPE IF EXISTS userblokenum;')
    # op.execute('DROP TYPE IF EXISTS userkamarenum;')
    # Lakukan ini hanya jika Anda yakin dan tidak akan kembali ke revisi ini.