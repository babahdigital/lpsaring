# backend/app/commands/user/create.py (Versi Final - Berdasarkan models.py)
# pyright: reportCallIssue=false, reportArgumentType=false
import click
from datetime import datetime, timezone
from random import randint
from flask import current_app

from app.extensions import db
from app.infrastructure.db.models import User, UserRole, ApprovalStatus, UserBlok, UserKamar
from app.utils.formatters import normalize_to_e164, format_to_local_phone
from app.utils.security import generate_password_hash
from app.infrastructure.gateways.mikrotik_client import activate_or_update_hotspot_user
from app.infrastructure.gateways.whatsapp_client import send_whatsapp_message
from app.services import notification_service, settings_service

def _get_cli_actor():
    """Mencari SUPER_ADMIN yang ada untuk bertindak sebagai pelaku aksi dari CLI."""
    return User.query.filter_by(role=UserRole.SUPER_ADMIN).first()

@click.command(name='create', help='Membuat pengguna baru (DB + Mikrotik + Notifikasi) secara mandiri.')
@click.option('--name', required=True, help='Nama lengkap pengguna.')
@click.option('--phone', required=True, help='Nomor telepon (format 08xx).')
@click.option('--role', required=True, type=click.Choice([r.name for r in UserRole], case_sensitive=False), help='Peran pengguna.')
@click.option('--password', help='[Khusus Admin] Tentukan password portal web.')
@click.option('--blok', help='[Wajib untuk USER] Blok alamat.')
@click.option('--kamar', help='[Wajib untuk USER] Nomor kamar.')
def create_user(name, phone, role, password, blok, kamar):
    """
    Skrip mandiri untuk membuat pengguna, ditulis ulang berdasarkan definisi dari models.py.
    """
    try:
        role_enum = UserRole[role.upper()]
        
        actor = _get_cli_actor()
        if not actor and role_enum != UserRole.SUPER_ADMIN:
            click.secho("Kesalahan Kritis: Harus ada SUPER_ADMIN terlebih dahulu untuk membuat pengguna non-admin.", fg='red')
            return

        phone_e164 = normalize_to_e164(phone)
        if User.query.filter_by(phone_number=phone_e164).first():
            click.secho(f"Error: Nomor telepon {phone} sudah terdaftar.", fg='red')
            return

        is_admin_role = role_enum in [UserRole.ADMIN, UserRole.SUPER_ADMIN]

        if role_enum == UserRole.USER and (not blok or not kamar):
            click.secho("Error: --blok dan --kamar wajib diisi untuk peran USER.", fg='red')
            return

        blok_enum = UserBlok(blok) if blok else None
        kamar_enum = UserKamar(f"Kamar_{kamar}") if kamar else None
        
        password_hashed = None
        portal_password_to_notify = None
        if is_admin_role:
            portal_password_to_notify = password if password else str(randint(100000, 999999))
            password_hashed = generate_password_hash(portal_password_to_notify)

        new_user = User(
            full_name=name, phone_number=phone_e164, password_hash=password_hashed,
            role=role_enum, blok=blok_enum, kamar=kamar_enum,
            is_unlimited_user=is_admin_role, 
            mikrotik_password=str(randint(100000, 999999))
        )
        
        # Override default model jika rolenya admin
        if is_admin_role:
            new_user.is_active = True
            new_user.approval_status = ApprovalStatus.APPROVED
            new_user.approved_at = datetime.now(timezone.utc)
        
        # Tambahkan ke sesi database
        db.session.add(new_user)
        
        # Tentukan siapa yang menyetujui
        if is_admin_role:
            if actor:
                new_user.approved_by_id = actor.id
            else: # Kasus Super Admin pertama, setujui diri sendiri
                click.secho("Super Admin pertama terdeteksi, melakukan self-approval...", fg='cyan')
                db.session.flush() # Dapatkan ID untuk self-approval
                new_user.approved_by_id = new_user.id
        
        # Atur profil Mikrotik
        if role_enum == UserRole.SUPER_ADMIN:
            new_user.mikrotik_server_name = current_app.config.get('MIKROTIK_SERVER_SUPER_ADMIN', 'srv-support')
            new_user.mikrotik_profile_name = 'support'
        elif is_admin_role:
            new_user.mikrotik_server_name = current_app.config.get('MIKROTIK_SERVER_ADMIN', 'srv-komandan')
            new_user.mikrotik_profile_name = current_app.config.get('MIKROTIK_PROFILE_UNLIMITED', 'unlimited')
        else:
            new_user.mikrotik_server_name = current_app.config.get('MIKROTIK_SERVER_USER', 'srv-user')
            new_user.mikrotik_profile_name = 'profile-aktif'
        
        # Sinkronisasi ke Mikrotik jika admin
        if is_admin_role:
            click.secho("Peran Admin terdeteksi, sinkronisasi ke Mikrotik...", fg='cyan')
            success_mikrotik, msg_mikrotik = activate_or_update_hotspot_user(
                user_mikrotik_username=format_to_local_phone(new_user.phone_number),
                hotspot_password=new_user.mikrotik_password,
                mikrotik_profile_name=new_user.mikrotik_profile_name,
                server=new_user.mikrotik_server_name,
                comment=f"Created by CLI"
            )
            if success_mikrotik:
                new_user.mikrotik_user_exists = True
                click.secho(f"Mikrotik: {msg_mikrotik}", fg='green')
            else:
                click.secho(f"Mikrotik GAGAL: {msg_mikrotik}", fg='red')
        
        # Commit semua perubahan ke database
        db.session.commit()

        # Kirim notifikasi
        click.secho("\n--- Hasil Pembuatan Pengguna ---", bold=True)
        if is_admin_role:
            click.secho(f"SUKSES: Pengguna '{name}' berhasil dibuat dan aktif.", fg='green')
            click.secho(f"Password Portal Web: {portal_password_to_notify}", fg='yellow')
            
            context = { "password": portal_password_to_notify, "link_admin_app": settings_service.get_setting("LINK_ADMIN_APP", "") }
            message_body = notification_service.get_notification_message("admin_creation_success", context)
            send_whatsapp_message(phone_e164, message_body)

            click.secho("Notifikasi WhatsApp untuk Admin telah dikirim.", fg='cyan')
        else:
            click.secho(f"SUKSES: Pengguna '{name}' dibuat dan menunggu persetujuan.", fg='green')

        click.secho(f"Password Hotspot Mikrotik: {new_user.mikrotik_password}", fg='yellow')

    except Exception as e:
        db.session.rollback()
        click.secho(f"Terjadi kesalahan fatal: {e}", fg='red')
        import traceback
        click.echo(traceback.format_exc())