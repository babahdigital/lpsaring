# backend/app/commands/seed_commands.py
# VERSI: Disesuaikan dengan model Package terbaru (duration_days, data_quota_gb).

import click
from flask.cli import with_appcontext
import uuid
from decimal import Decimal

from app.extensions import db
from app.infrastructure.db.models import Package

@click.command('seed-db')
@with_appcontext
def seed_db_command():
    """Mengisi database dengan data paket awal yang disesuaikan."""
    click.echo("Starting database seeding...")

    if db.session.query(Package).first():
        click.echo('Database already contains package data. Seeding cancelled.')
        return

    click.echo("Creating sample packages with new model structure...")
    try:
        package1 = Package(
            id=uuid.uuid4(), name='Paket Kuota 1GB',
            description='Kuota internet 1GB untuk 30 hari, Speed Up To 50Mbps.',
            price=Decimal('10000.00'),
            duration_days=30, # WAJIB ADA
            data_quota_gb=Decimal('1.00'),  # WAJIB ADA - Contoh 1GB
            speed_limit_kbps=51200,
            mikrotik_profile_name='profile-quota-1gb',
            is_active=True
        )
        package2 = Package(
            id=uuid.uuid4(), name='Paket Kuota 5GB',
            description='Kuota internet 5GB untuk 30 hari, Speed Up To 100Mbps.',
            price=Decimal('25000.00'),
            duration_days=30, # WAJIB ADA
            data_quota_gb=Decimal('5.00'),  # WAJIB ADA - Contoh 5GB
            speed_limit_kbps=102400,
            mikrotik_profile_name='profile-quota-5gb',
            is_active=True
        )
        package3 = Package(
            id=uuid.uuid4(), name='Paket Kuota 10GB',
            description='Kuota internet 10GB untuk 30 hari, kecepatan tanpa batas.',
            price=Decimal('50000.00'),
            duration_days=30, # WAJIB ADA
            data_quota_gb=Decimal('10.00'), # WAJIB ADA - Contoh 10GB
            speed_limit_kbps=None,
            mikrotik_profile_name='profile-quota-10gb',
            is_active=True
        )
        package4 = Package(
            id=uuid.uuid4(), name='Paket Hemat 500MB (Non-Aktif)',
            description='Paket coba kuota 500MB untuk 7 hari.',
            price=Decimal('5000.00'),
            duration_days=7,   # WAJIB ADA
            data_quota_gb=Decimal('0.50'), # WAJIB ADA - Contoh 500MB
            speed_limit_kbps=1024,
            mikrotik_profile_name='profile-nonaktif-500mb',
            is_active=False
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