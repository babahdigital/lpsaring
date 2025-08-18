# backend/app/commands/user/helpers.py
import click
from sqlalchemy import or_
from app.infrastructure.db.models import User, UserRole
from app.utils.formatters import get_phone_number_variations

def get_cli_actor():
    """Mencari SUPER_ADMIN yang ada untuk bertindak sebagai pelaku aksi dari CLI."""
    actor = User.query.filter_by(role=UserRole.SUPER_ADMIN).first()
    if not actor:
        click.secho("Kesalahan Kritis: Tidak ada SUPER_ADMIN ditemukan untuk melakukan aksi ini.", fg='red')
    return actor

def find_user(identifier):
    """Mencari user berdasarkan nama atau nomor telepon."""
    phone_variations = get_phone_number_variations(identifier)
    user = User.query.filter(
        or_(
            User.full_name.ilike(f"%{identifier}%"),
            User.phone_number.in_(phone_variations)
        )
    ).first()
    if not user:
        click.secho(f"Error: Pengguna dengan identifier '{identifier}' tidak ditemukan.", fg='red')
    return user