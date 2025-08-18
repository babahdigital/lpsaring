# backend/app/commands/user/manage.py (Final)
# pyright: reportArgumentType=false
import click
from flask import current_app
from datetime import datetime, timezone, timedelta

from app.extensions import db
from app.infrastructure.db.models import User, UserRole, ApprovalStatus
from app.utils.formatters import format_to_local_phone
from app.infrastructure.gateways.mikrotik_client import activate_or_update_hotspot_user, purge_user_from_hotspot
from app.infrastructure.gateways.whatsapp_client import send_whatsapp_message
from app.services import notification_service, settings_service
# --- [PENAMBAHAN] Impor fungsi untuk hashing password ---
from app.utils.security import generate_password_hash

# Impor dari helper terpusat
from .helpers import get_cli_actor, find_user

@click.command(name='approve', help='Menyetujui pendaftaran pengguna (DB + Mikrotik + WA).')
@click.argument('identifier')
def approve_user(identifier):
    actor = get_cli_actor()
    if not actor: return
    user = find_user(identifier)
    if not user: return
    
    if user.approval_status != ApprovalStatus.PENDING_APPROVAL:
        click.secho("Error: Pengguna ini tidak dalam status menunggu persetujuan.", fg='red')
        return

    try:
        initial_quota_mb = settings_service.get_setting_as_int('USER_INITIAL_QUOTA_MB', 0)
        initial_duration_days = settings_service.get_setting_as_int('USER_INITIAL_DURATION_DAYS', 30)
        user.total_quota_purchased_mb = initial_quota_mb
        user.quota_expiry_date = datetime.now(timezone.utc) + timedelta(days=initial_duration_days) if initial_quota_mb > 0 else None
        
        success_mikrotik, msg_mikrotik = activate_or_update_hotspot_user(
            user_mikrotik_username=format_to_local_phone(user.phone_number),
            hotspot_password=user.mikrotik_password,
            mikrotik_profile_name=current_app.config.get('MIKROTIK_PROFILE_AKTIF', 'profile-aktif'),
            server=user.mikrotik_server_name or 'all',
            comment=f"Approved by CLI: {actor.full_name}"
        )

        if not success_mikrotik:
            click.secho(f"GAGAL: Tidak dapat mengaktifkan di Mikrotik: {msg_mikrotik}", fg='red')
            db.session.rollback()
            return
        
        user.approval_status = ApprovalStatus.APPROVED
        user.is_active = True
        user.approved_at = datetime.now(timezone.utc)
        user.approved_by_id = actor.id
        user.mikrotik_user_exists = True

        db.session.commit()
        
        click.secho(f"SUKSES: Pengguna '{user.full_name}' telah disetujui dan diaktifkan di Mikrotik.", fg='green')
        
        context = {
            'full_name': user.full_name,
            'hotspot_username': format_to_local_phone(user.phone_number),
            'hotspot_password': user.mikrotik_password
        }
        message_body = notification_service.get_notification_message("user_approve_success", context)
        send_whatsapp_message(user.phone_number, message_body)
        click.secho("Notifikasi WhatsApp telah dikirim.", fg='cyan')

    except Exception as e:
        db.session.rollback()
        click.secho(f"Terjadi kesalahan fatal saat approve: {e}", fg='red')

@click.command(name='reject', help='Menolak pendaftaran (hapus dari DB & Mikrotik).')
@click.argument('identifier')
def reject_user(identifier):
    actor = get_cli_actor()
    if not actor: return
    user = find_user(identifier)
    if not user: return
    
    if user.approval_status != ApprovalStatus.PENDING_APPROVAL:
        click.secho("Error: Pengguna ini tidak dalam status menunggu persetujuan.", fg='red')
        return

    try:
        user_name_log, user_phone_log = user.full_name, user.phone_number
        mikrotik_username = format_to_local_phone(user_phone_log)

        click.secho(f"Menolak '{user_name_log}'. Membersihkan dari Mikrotik...", fg='yellow')
        success_mikrotik, msg_mikrotik = purge_user_from_hotspot(mikrotik_username)
        if not success_mikrotik:
            click.secho(f"Peringatan: Gagal membersihkan dari Mikrotik: {msg_mikrotik}", fg='yellow')

        db.session.delete(user)
        db.session.commit()
        
        click.secho(f"SUKSES: Pendaftaran '{user_name_log}' ditolak. Data dari DB dan jejak di Mikrotik telah dihapus.", fg='green')
        
        message_body = notification_service.get_notification_message("user_reject_notification", {"full_name": user_name_log})
        send_whatsapp_message(user_phone_log, message_body)
        click.secho("Notifikasi penolakan via WhatsApp telah dikirim.", fg='cyan')

    except Exception as e:
        db.session.rollback()
        click.secho(f"Terjadi kesalahan fatal saat reject: {e}", fg='red')

@click.command(name='delete', help='Menghapus pengguna permanen (DB & Mikrotik).')
@click.argument('identifier')
def delete_user(identifier):
    actor = get_cli_actor()
    if not actor: return
    user = find_user(identifier)
    if not user: return
    
    if user.role == UserRole.SUPER_ADMIN:
        click.secho("Error: Super Admin tidak dapat dihapus.", fg='red')
        return
        
    click.confirm(f"Yakin ingin menghapus '{user.full_name}' dari DB dan Mikrotik? Aksi ini permanen.", abort=True)

    try:
        user_name_log = user.full_name
        mikrotik_username = format_to_local_phone(user.phone_number)
        
        click.secho(f"Menghapus '{user_name_log}' dari Mikrotik...", fg='yellow')
        success_mikrotik, msg_mikrotik = purge_user_from_hotspot(mikrotik_username)
        if not success_mikrotik:
            if not click.confirm(f"Peringatan: Gagal hapus dari Mikrotik ({msg_mikrotik}). Tetap hapus dari DB?", default=False, abort=True):
                return

        db.session.delete(user)
        db.session.commit()
        
        click.secho(f"SUKSES: Pengguna '{user_name_log}' berhasil dihapus secara permanen.", fg='green')

    except Exception as e:
        db.session.rollback()
        click.secho(f"Terjadi kesalahan fatal saat delete: {e}", fg='red')

# --- [PERINTAH BARU] ---
@click.command(name='set-password', help='Mengatur atau mereset password portal web untuk Admin/Super Admin.')
@click.argument('identifier')
@click.argument('new_password')
def set_password(identifier, new_password):
    """
    IDENTIFIER: Nama atau nomor telepon admin.
    NEW_PASSWORD: Password baru yang akan digunakan.
    """
    user = find_user(identifier)
    if not user:
        return

    if not user.is_admin_role:
        click.secho(f"Error: Pengguna '{user.full_name}' bukan Admin atau Super Admin. Password tidak dapat diatur.", fg='red')
        return

    if len(new_password) < 6:
        click.secho("Error: Password harus memiliki minimal 6 karakter.", fg='red')
        return

    try:
        user.password_hash = generate_password_hash(new_password)
        db.session.commit()
        click.secho(f"SUKSES: Password untuk '{user.full_name}' ({user.phone_number}) telah berhasil diatur.", fg='green')
    except Exception as e:
        db.session.rollback()
        click.secho(f"Terjadi kesalahan saat mengatur password: {e}", fg='red')