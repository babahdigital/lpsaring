# backend/app/commands/user/view.py (Final)
import click
from sqlalchemy import or_
from app.extensions import db
from app.infrastructure.db.models import User
from app.utils.formatters import get_phone_number_variations, format_datetime_to_wita

# Impor dari helper terpusat
from .helpers import find_user

@click.command(name='list', help='Menampilkan daftar pengguna.')
@click.option('--limit', default=20, help='Jumlah pengguna yang ditampilkan.')
def list_users(limit):
    users = User.query.order_by(User.created_at.desc()).limit(limit).all()
    if not users:
        click.echo("Tidak ada pengguna di database.")
        return

    header = "{:<38} {:<15} {:<20} {:<6} {:<8} {:<18} {:<15} {:<8}"
    click.secho(header.format("ID", "No. Telepon", "Nama", "Blok", "Kamar", "Status", "Peran", "Aktif?"), bold=True)
    click.echo("-" * 130)

    for user in users:
        blok_display = user.blok.value if user.blok else "N/A"
        kamar_display = user.kamar.value.replace('Kamar_', '') if user.kamar else "N/A"
        status_display = user.approval_status.value if user.approval_status else "N/A"
        role_display = user.role.value if user.role else "N/A"
        
        click.echo(header.format(
            str(user.id),
            user.phone_number,
            user.full_name[:18],
            blok_display,
            kamar_display,
            status_display,
            role_display,
            str(user.is_active)
        ))

@click.command(name='search', help='Mencari pengguna berdasarkan nama atau no. HP.')
@click.option('--query', required=True, help="Nama atau nomor HP yang dicari.")
def search_user(query):
    users = find_user(query) # Menggunakan helper find_user
    if not users:
        # Pesan error sudah ditangani oleh find_user
        return

    click.secho(f"Hasil pencarian untuk '{query}':", bold=True)
    # find_user hanya mengembalikan satu, kita buat seolah-olah list agar konsisten
    user_list = [users] if not isinstance(users, list) else users 
    for user in user_list:
        click.echo(f"- {user.full_name} ({user.phone_number}) - Role: {user.role.value}")

@click.command(name='quota', help='Melihat sisa kuota pengguna.')
@click.argument('identifier')
def check_quota(identifier):
    """IDENTIFIER: Nama atau nomor telepon pengguna yang akan dicek kuotanya."""
    user = find_user(identifier)
    
    if not user:
        return
    
    sisa_kuota = (user.total_quota_purchased_mb or 0) - (user.total_quota_used_mb or 0)
    kadaluarsa_wita = format_datetime_to_wita(user.quota_expiry_date) if user.quota_expiry_date else 'Tidak diatur'

    click.echo(f"Detail Kuota untuk: {user.full_name}")
    click.echo(f"  - Total Kuota Dibeli: {user.total_quota_purchased_mb or 0} MB")
    click.echo(f"  - Total Kuota Terpakai: {user.total_quota_used_mb or 0:.2f} MB")
    click.secho(f"  - Sisa Kuota: {sisa_kuota:.2f} MB", fg='green', bold=True)
    click.echo(f"  - Kadaluarsa pada: {kadaluarsa_wita}")