# backend/app/commands/seed_commands.py
# Saat Fresh Install
# 1. docker-compose exec backend flask db upgrade
# 2. docker-compose exec backend flask seed-db
import click
from flask.cli import with_appcontext
import uuid
from decimal import Decimal

from app.extensions import db
from app.infrastructure.db.models import Package

@click.command('seed-db')
@with_appcontext
def seed_db_command():
    """Mengisi database dengan data paket awal (versi kuota)."""
    click.echo("Starting database seeding...")

    if db.session.query(Package).first():
        click.echo('Database already contains package data. Seeding cancelled.')
        return

    click.echo("Creating sample packages...")
    try:
        # Paket sekarang berbasis kuota, data_quota_mb WAJIB ADA.
        package1 = Package(
            id=uuid.uuid4(), name='Paket Kuota 1GB',
            description='Kuota internet 1GB, Speed Up To 50Mbps.',
            price=Decimal('10000.00'),
            # duration_days dihilangkan
            speed_limit_kbps=51200, # 1Mbps
            data_quota_mb=1024,  # WAJIB ADA - Contoh 1GB
            mikrotik_profile_name='profile-quota-1gb', # Nama profile di Mikrotik
            is_active=True
        )
        package2 = Package(
            id=uuid.uuid4(), name='Paket Kuota 5GB',
            description='Kuota internet 5GB, Speed Up To 100Mbps.',
            price=Decimal('25000.00'),
            speed_limit_kbps=102400,
            data_quota_mb=5120,  # WAJIB ADA - Contoh 5GB
            mikrotik_profile_name='profile-quota-5gb',
            is_active=True
        )
        package3 = Package(
            id=uuid.uuid4(), name='Paket Kuota 10GB',
            description='Kuota internet 10GB, kecepatan tanpa batas.',
            price=Decimal('50000.00'),
            speed_limit_kbps=None, # None berarti Unlimited
            data_quota_mb=10240, # WAJIB ADA - Contoh 10GB
            mikrotik_profile_name='profile-quota-10gb',
            is_active=True
        )
        package4 = Package(
            id=uuid.uuid4(), name='Paket Hemat 500MB (Non-Aktif)',
            description='Paket coba kuota 500MB.',
            price=Decimal('5000.00'),
            speed_limit_kbps=1024, # 1Mbps
            data_quota_mb=500,   # WAJIB ADA - Contoh 500MB
            mikrotik_profile_name='profile-nonaktif-500mb',
            is_active=False # Contoh paket tidak aktif
        )

        packages_to_add = [package1, package2, package3, package4]
        click.echo(f"Attempting to add {len(packages_to_add)} packages...")
        db.session.add_all(packages_to_add)
        db.session.commit()
        click.echo(f"Successfully seeded database with {len(packages_to_add)} initial packages.")

    except Exception as e:
        db.session.rollback()
        import traceback
        click.echo(f"Error while seeding database: {e}", err=True)
        click.echo(traceback.format_exc(), err=True)