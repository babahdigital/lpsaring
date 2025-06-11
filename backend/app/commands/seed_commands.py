# backend/app/commands/seed_commands.py
# VERSI FINAL: Disesuaikan dengan model Package terbaru (speed_limit_kbps)
# dan penambahan speed_limit_kbps serta contoh paket unlimited.
# PERBAIKAN: Memastikan akses data_quota_gb dan duration_days melalui PackageProfile.

import click
from flask.cli import with_appcontext
import uuid
from decimal import Decimal

from app.extensions import db
from app.infrastructure.db.models import Package, PackageProfile # Import PackageProfile juga

@click.command('seed-db')
@with_appcontext
def seed_db_command():
    """Mengisi database dengan data paket awal yang disesuaikan."""
    click.echo("Starting database seeding...")

    # Cek apakah sudah ada Package atau PackageProfile
    if db.session.query(Package).first() or db.session.query(PackageProfile).first():
        click.echo('Database already contains package or profile data. Seeding cancelled.')
        return

    click.echo("Creating sample PackageProfiles and Packages...")
    try:
        # --- Buat PackageProfile terlebih dahulu ---
        # Kita buat 1 profil default saja seperti yg disepakati,
        # data_quota_gb & duration_days disini deskriptif untuk profil itu sendiri.
        # Batasan sebenarnya akan diatur per user via Mikrotik Simple Queue.

        default_profile = PackageProfile(
            id=uuid.uuid4(),
            profile_name='default-hotspot-profile',
            data_quota_gb=Decimal('0.00'), # Ini adalah kuota deskriptif untuk profil, 0.00 berarti tidak ada kuota di level profil
            duration_days=0, # Ini adalah durasi deskriptif untuk profil, 0 berarti tidak ada durasi di level profil
            description='Profil default untuk semua pengguna hotspot, batasan diatur per user via API.'
        )
        db.session.add(default_profile)
        db.session.flush() # Agar default_profile.id terisi

        # --- Buat Paket-paket berdasarkan profil yang sudah dibuat ---
        # Paket ini akan memiliki kuota dan durasi yang melekat pada definisi paketnya,
        # yang kemudian akan memengaruhi total_quota_purchased_mb dan quota_expiry_date di User.
        # Catatan: models.py Anda tidak memiliki 'data_quota_mb' atau 'duration_days' di model Package.
        # Ini berarti PackagePublic schema akan mengambilnya dari Package.profile.
        # Jadi, jika Anda ingin kuota/durasi spesifik per Package, kolom ini harus ada di model Package.
        # Saat ini, Package hanya punya speed_limit_kbps.
        # Untuk konsistensi dengan yang kita diskusikan (kuota/durasi di User),
        # asumsikan kuota/durasi akan dihitung berdasarkan paket (misalnya, paket 1GB itu berarti paket yang memberikan 1GB).
        # Tapi *model database Package* Anda saat ini tidak punya kolom 'data_quota_gb' atau 'duration_days'.
        # package_schemas.py (PackagePublic) MENGAMBILNYA DARI PROFILE.
        # Jika kuota/durasi diatur PER PAKET, BUKAN PER PROFIL MIKROTIK, maka models.py HARUS diubah.
        # Saya akan asumsikan data_quota_gb dan duration_days di PackagePublic berasal dari PackageProfile
        # yang nantinya akan di-lookup saat transaksi.
        # Untuk seeding, kita hanya perlu mencocokkan field yang ada di model Package.

        package1 = Package(
            id=uuid.uuid4(), name='Paket Kuota 1GB',
            description='Kuota internet 1GB untuk 30 hari.',
            price=Decimal('10000.00'),
            profile_id=default_profile.id, # Asosiasikan dengan profil default
            speed_limit_kbps=51200, # Informasi deskriptif untuk aplikasi
            is_active=True
        )
        package2 = Package(
            id=uuid.uuid4(), name='Paket Kuota 5GB',
            description='Kuota internet 5GB untuk 30 hari.',
            price=Decimal('25000.00'),
            profile_id=default_profile.id, # Asosiasikan dengan profil default
            speed_limit_kbps=102400, # Informasi deskriptif untuk aplikasi
            is_active=True
        )
        package3 = Package(
            id=uuid.uuid4(), name='Paket Kuota 10GB',
            description='Kuota internet 10GB untuk 30 hari.',
            price=Decimal('50000.00'),
            profile_id=default_profile.id, # Asosiasikan dengan profil default
            speed_limit_kbps=None, # Tanpa batas kecepatan deskriptif
            is_active=True
        )
        package4 = Package(
            id=uuid.uuid4(), name='Paket Hemat 500MB (Non-Aktif)',
            description='Paket coba kuota 500MB untuk 7 hari.',
            price=Decimal('5000.00'),
            profile_id=default_profile.id, # Asosiasikan dengan profil default
            speed_limit_kbps=1024, # Informasi deskriptif untuk aplikasi
            is_active=False
        )
        # --- BARU DITAMBAHKAN: Paket Unlimited ---
        package5_unlimited = Package(
            id=uuid.uuid4(), name='Paket Unlimited 30 Hari',
            description='Internet tanpa kuota, berlaku 30 hari.',
            price=Decimal('75000.00'),
            profile_id=default_profile.id, # Asosiasikan dengan profil default
            speed_limit_kbps=None, # Kecepatan unlimited, diatur di Mikrotik Simple Queue
            is_active=True
        )
        # ----------------------------------------

        packages_to_add = [package1, package2, package3, package4, package5_unlimited]
        
        click.echo(f"Attempting to add {len(packages_to_add)} packages and 1 profile...")
        db.session.add_all(packages_to_add)
        db.session.commit()
        click.echo(f"Successfully seeded database with {len(packages_to_add)} initial packages and 1 profile.")

    except Exception as e:
        db.session.rollback()
        import traceback
        click.echo(f"Error while seeding database: {e}", err=True)
        click.echo(traceback.format_exc(), err=True)