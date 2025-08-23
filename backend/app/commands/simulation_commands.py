# backend/app/commands/simulation_commands.py
# pyright: reportArgumentType=false, reportCallIssue=false
import click
import logging
import datetime as dt_module
from datetime import timezone as dt_timezone
from flask import current_app
from flask.cli import with_appcontext
from sqlalchemy import select

from app.extensions import db
from app.infrastructure.db.models import User, UserLoginHistory
from app.utils.formatters import normalize_to_e164, format_datetime_to_wita, format_to_local_phone
from app.infrastructure.gateways.mikrotik_client import (
    get_ip_binding_details,
    get_host_details_by_mac,
    get_host_details_by_username,
    create_or_update_ip_binding,
    sync_address_list_for_user,
    activate_or_update_hotspot_user,
    ensure_ip_binding_status_matches_profile,
    move_user_to_inactive_list,
    purge_user_from_hotspot,
    get_mikrotik_connection,
    delete_hotspot_user,
)
import app.infrastructure.gateways.mikrotik_client as mk_client
from app.utils.mikrotik_helpers import determine_target_profile, get_server_for_user

logger = logging.getLogger(__name__)

# ==============================================================================
# GRUP PERINTAH: simulate
# ==============================================================================

@click.group('simulate')
def simulate_cli():
    """
    Kumpulan perintah simulasi untuk status pengguna, kuota, dan operasi MikroTik.
    """
    pass

# ------------------------------------------------------------------------------
# simulate user-status
# ------------------------------------------------------------------------------
@simulate_cli.command('user-status')
@click.option('--phone', required=True, help='Nomor telepon pengguna (format 08xx atau +62xx).')
@click.option('--status', type=click.Choice(['active','inactive','fup','habis','blocked','expired','unlimited'], case_sensitive=False), required=True, help='Status target untuk disimulasikan.')
@click.option('--push/--no-push', default=True, show_default=True, help='Sinkronkan perubahan ke MikroTik.')
@with_appcontext
def simulate_user_status_command(phone: str, status: str, push: bool):
    """Ubah status pengguna di DB dan (opsional) sinkronkan ke MikroTik."""
    click.echo(f"===== Simulasi Status Pengguna untuk: {phone} -> {status} =====")
    try:
        normalized_phone = normalize_to_e164(phone)
    except ValueError as e:
        click.secho(f"Error: {e}", fg='red')
        return

    user = db.session.scalar(select(User).filter_by(phone_number=normalized_phone))
    if not user:
        click.secho(f"Pengguna dengan nomor {normalized_phone} tidak ditemukan.", fg='red')
        return

    # Simpan status awal untuk log
    before = {
        'is_active': user.is_active,
        'is_blocked': user.is_blocked,
        'is_unlimited_user': user.is_unlimited_user,
        'purchased': float(user.total_quota_purchased_mb or 0),
        'used': float(user.total_quota_used_mb or 0),
        'expiry': user.quota_expiry_date,
    }

    # Mutasi sesuai status yang diminta
    status_l = status.lower()
    now_utc = dt_module.datetime.now(dt_timezone.utc)
    if status_l == 'active':
        user.is_active = True
        user.is_blocked = False
        user.is_unlimited_user = False
        # Jangan ubah kuota/expiry jika tidak perlu
    elif status_l == 'inactive':
        user.is_active = False
        user.is_blocked = False
        user.is_unlimited_user = False
    elif status_l == 'blocked':
        user.is_blocked = True
    elif status_l == 'expired':
        user.is_active = True
        user.is_blocked = False
        user.is_unlimited_user = False
        user.quota_expiry_date = now_utc - dt_module.timedelta(days=1)
    elif status_l == 'unlimited':
        user.is_active = True
        user.is_blocked = False
        user.is_unlimited_user = True
    elif status_l in ('fup', 'habis'):
        user.is_active = True
        user.is_blocked = False
        user.is_unlimited_user = False
        # Pastikan punya kuota purchased agar logika status bekerja
        purchased = float(user.total_quota_purchased_mb or 0)
        if purchased <= 0:
            purchased = 10240.0  # 10 GB default
            user.total_quota_purchased_mb = int(purchased)
        if status_l == 'habis':
            user.total_quota_used_mb = purchased  # habis tepat
        else:  # fup
            # set ke 90% agar melewati threshold FUP
            user.total_quota_used_mb = purchased * 0.9

    db.session.commit()

    click.echo("--- Ringkasan Perubahan ---")
    click.echo(f"Sebelum: {before}")
    click.echo(f"Sesudah: is_active={user.is_active}, is_blocked={user.is_blocked}, unlimited={user.is_unlimited_user}, purchased={user.total_quota_purchased_mb or 0}, used={user.total_quota_used_mb or 0}, expiry={user.quota_expiry_date}")

    if not push:
        click.secho("Lewati sinkronisasi MikroTik (--no-push)", fg='yellow')
        return

    # Sinkronisasi ke MikroTik
    try:
        mikrotik_username = format_to_local_phone(user.phone_number)
        target_profile = determine_target_profile(user)
        server = get_server_for_user(user)

        # Update hotspot user profile
        ok, msg = activate_or_update_hotspot_user(
            mikrotik_username, target_profile, hotspot_password=None, server=server, comment=mikrotik_username
        )
        click.echo(f"[hotspot-user] {msg}")

        # Ensure binding disabled sesuai profil (blokir -> disabled)
        ok2, msg2 = ensure_ip_binding_status_matches_profile(mikrotik_username, target_profile)
        click.echo(f"[ip-binding] {msg2}")

        # Address list sync (jika IP diketahui)
        target_ip = user.last_login_ip
        if not target_ip:
            # fallback host by username
            found, host, _ = get_host_details_by_username(mikrotik_username)
            if found and host:
                target_ip = host.get('address')

        if target_ip:
            # Sinkronisasi list menurut profil
            sync_address_list_for_user(
                username=mikrotik_username,
                new_ip_address=target_ip,
                target_profile_name=target_profile,
                old_ip_address=None
            )
            # Jika status inactive, pindahkan eksplisit ke inactive list
            if status_l == 'inactive':
                move_user_to_inactive_list(target_ip, mikrotik_username)

        click.secho("Sinkronisasi MikroTik selesai.", fg='green')
    except Exception as e:
        logger.error(f"[simulate user-status] Sync MikroTik gagal: {e}", exc_info=True)
        click.secho(f"Gagal sinkron ke MikroTik: {e}", fg='red')

# ------------------------------------------------------------------------------
# simulate user-quota
# ------------------------------------------------------------------------------
@simulate_cli.command('user-quota')
@click.option('--phone', required=True, help='Nomor telepon pengguna (format 08xx atau +62xx).')
@click.option('--purchase-mb', type=int, help='Set total kuota dibeli (MB).')
@click.option('--used-mb', type=float, help='Set total kuota terpakai (MB).')
@click.option('--expire-now', is_flag=True, help='Set masa berlaku menjadi kadaluarsa sekarang.')
@click.option('--unlimited/--no-unlimited', default=None, help='Set sebagai pengguna unlimited atau bukan.')
@click.option('--push/--no-push', default=True, show_default=True, help='Sinkronkan perubahan ke MikroTik.')
@with_appcontext
def simulate_user_quota_command(phone: str, purchase_mb: int | None, used_mb: float | None, expire_now: bool, unlimited: bool | None, push: bool):
    """Manipulasi kuota dan masa berlaku pengguna, lalu (opsional) sinkronkan ke MikroTik."""
    click.echo(f"===== Simulasi Kuota untuk: {phone} =====")
    try:
        normalized_phone = normalize_to_e164(phone)
    except ValueError as e:
        click.secho(f"Error: {e}", fg='red')
        return

    user = db.session.scalar(select(User).filter_by(phone_number=normalized_phone))
    if not user:
        click.secho(f"Pengguna dengan nomor {normalized_phone} tidak ditemukan.", fg='red')
        return

    if purchase_mb is not None:
        user.total_quota_purchased_mb = int(max(0, purchase_mb))
    if used_mb is not None:
        user.total_quota_used_mb = float(max(0.0, used_mb))
    if expire_now:
        user.quota_expiry_date = dt_module.datetime.now(dt_timezone.utc) - dt_module.timedelta(seconds=1)
    if unlimited is not None:
        user.is_unlimited_user = bool(unlimited)
        # Unlimited implies active
        if unlimited:
            user.is_active = True

    db.session.commit()

    if not push:
        click.secho("Lewati sinkronisasi MikroTik (--no-push)", fg='yellow')
        return

    try:
        mikrotik_username = format_to_local_phone(user.phone_number)
        target_profile = determine_target_profile(user)
        server = get_server_for_user(user)

        ok, msg = activate_or_update_hotspot_user(
            mikrotik_username, target_profile, hotspot_password=None, server=server, comment=mikrotik_username
        )
        click.echo(f"[hotspot-user] {msg}")
        ensure_ip_binding_status_matches_profile(mikrotik_username, target_profile)

        target_ip = user.last_login_ip
        if not target_ip:
            found, host, _ = get_host_details_by_username(mikrotik_username)
            if found and host:
                target_ip = host.get('address')
        if target_ip:
            sync_address_list_for_user(
                username=mikrotik_username,
                new_ip_address=target_ip,
                target_profile_name=target_profile,
                old_ip_address=None
            )
        click.secho("Sinkronisasi MikroTik selesai.", fg='green')
    except Exception as e:
        logger.error(f"[simulate user-quota] Sync MikroTik gagal: {e}", exc_info=True)
        click.secho(f"Gagal sinkron ke MikroTik: {e}", fg='red')

# ------------------------------------------------------------------------------
# simulate remove-user-mikrotik (aman: hanya sesi/host, opsional hapus user/binding)
# ------------------------------------------------------------------------------
@simulate_cli.command('remove-user-mikrotik')
@click.option('--phone', required=True, help='Nomor telepon pengguna (format 08xx atau +62xx).')
@click.option('--delete-user', is_flag=True, help='Ikut hapus user hotspot dan IP binding (hati-hati).')
@with_appcontext
def simulate_remove_user_mikrotik_command(phone: str, delete_user: bool):
    """Hapus sesi/host aktif user dari MikroTik. Opsional: hapus user & ip-binding."""
    try:
        normalized_phone = normalize_to_e164(phone)
    except ValueError as e:
        click.secho(f"Error: {e}", fg='red')
        return

    user = db.session.scalar(select(User).filter_by(phone_number=normalized_phone))
    if not user:
        click.secho(f"Pengguna dengan nomor {normalized_phone} tidak ditemukan.", fg='red')
        return

    mikrotik_username = format_to_local_phone(user.phone_number)
    click.echo(f"Purging active sessions/hosts for '{mikrotik_username}'...")
    ok, msg = purge_user_from_hotspot(mikrotik_username)
    click.echo(f"[purge] {msg}")

    if delete_user:
        click.echo("Menghapus hotspot user dan IP binding...")
        try:
            with get_mikrotik_connection() as api:
                ok_u, msg_u = delete_hotspot_user(api, mikrotik_username)
                click.echo(f"[delete-user] {msg_u}")
            # Hapus IP binding by comment jika tersedia; fallback: disable saja
            if hasattr(mk_client, 'delete_ip_binding_by_comment'):
                ok_b, msg_b = mk_client.delete_ip_binding_by_comment(mikrotik_username)  # type: ignore[attr-defined]
            else:
                ok_b, msg_b = mk_client.disable_ip_binding_by_comment(mikrotik_username)  # type: ignore[assignment]
            click.echo(f"[delete-binding] {msg_b}")
        except Exception as e:
            click.secho(f"Gagal hapus user/binding: {e}", fg='red')


# ==============================================================================
# [PERINTAH BARU] SIMULASI OTORISASI PERANGKAT BARU
# ==============================================================================
@click.command('simulate-authorize-device')
@click.option('--phone', required=True, help='Nomor telepon pengguna yang akan diotorisasi (format 08xx atau +62xx).')
@click.option('--new-ip', required=True, help='Alamat IP baru dari perangkat yang akan diotorisasi.')
@click.option('--new-mac', required=True, help='Alamat MAC baru (acak) dari perangkat yang akan diotorisasi.')
@with_appcontext
def simulate_authorize_device_command(phone, new_ip, new_mac):
    """
    [SIMULASI] Memicu logika otorisasi perangkat baru secara eksplisit.
    Ini meniru endpoint /api/auth/authorize-device.
    """
    click.echo(f"===== Memulai Simulasi Otorisasi Perangkat untuk Nomor: {phone} =====")
    
    try:
        normalized_phone = normalize_to_e164(phone)
        user = db.session.scalar(select(User).filter_by(phone_number=normalized_phone))

        if not user:
            click.secho(f"Error: Pengguna dengan nomor {normalized_phone} tidak ditemukan.", fg='red')
            return

        click.echo("\n--- Status Awal dari Database ---")
        click.secho(f"Pengguna ditemukan : {user.full_name} (ID: {user.id})", fg='green')
        click.echo(f"  - Last Login IP  : {user.last_login_ip or 'Belum tercatat'}")
        click.echo(f"  - Last Login MAC : {user.last_login_mac or 'Belum tercatat'}")
        click.echo("---------------------------------")

        if not click.confirm(click.style(f"\nAnda akan mengubah IP Binding untuk {user.full_name} ke IP '{new_ip}' dan MAC '{new_mac}'. Lanjutkan?", fg='yellow')):
            click.secho("Operasi dibatalkan oleh pengguna.", fg='red')
            return

        click.echo("\nMemulai proses otorisasi dan sinkronisasi...")
        mikrotik_username = format_to_local_phone(user.phone_number)
        old_ip_address = user.last_login_ip  # Simpan IP lama untuk pembersihan

        # 1. Perbarui atau Buat IP Binding dengan MAC dan IP baru
        target_server = get_server_for_user(user)
        create_or_update_ip_binding(
            mac_address=new_mac.upper(),
            ip_address=new_ip,
            comment=mikrotik_username,
            server=target_server,
            type='bypassed'
        )
        click.echo(f"   - [OK] IP Binding untuk '{mikrotik_username}' telah diperbarui dengan MAC '{new_mac.upper()}' dan IP '{new_ip}'.")

        # 2. Sinkronkan Address List
        target_profile = determine_target_profile(user)
        sync_address_list_for_user(
            username=mikrotik_username,
            new_ip_address=new_ip,
            target_profile_name=target_profile,
            old_ip_address=old_ip_address
        )
        click.echo(f"   - [OK] Address List untuk IP lama '{old_ip_address}' dibersihkan dan IP baru '{new_ip}' disinkronkan.")

        # 3. Perbarui database aplikasi
        user.last_login_ip = new_ip
        user.last_login_mac = new_mac.upper()
        user.last_login_at = dt_module.datetime.now(dt_timezone.utc)
        db.session.add(UserLoginHistory(user_id=user.id, ip_address=new_ip, mac_address=new_mac.upper(), user_agent_string="CLI Simulation"))
        db.session.commit()
        click.echo(f"   - [OK] Database aplikasi diperbarui dengan IP dan MAC terbaru.")
        
        click.secho("\nOtorisasi perangkat baru berhasil disimulasikan!", fg='green', bold=True)

    except Exception as e:
        db.session.rollback()
        logger.error(f"[SimulateAuthorize] Error kritis saat simulasi untuk {phone}: {e}", exc_info=True)
        click.secho(f"Terjadi error: {e}", fg='red')

# ==============================================================================
# PERINTAH SIMULASI SINKRONISASI PERANGKAT (TETAP ADA UNTUK KASUS PERPINDAHAN IP)
# ==============================================================================
@click.command('simulate-sync-device')
@click.option('--phone', required=True, help='Nomor telepon pengguna (format 08xx atau +62xx).')
@with_appcontext
def simulate_sync_device_command(phone):
    """
    [SIMULASI] Memicu logika sinkronisasi perangkat dari Skenario C.
    Perintah ini akan meniru endpoint /api/auth/sync-device untuk backend testing.
    """
    click.echo(f"===== Memulai Simulasi Sinkronisasi untuk Nomor: {phone} =====")
    
    try:
        normalized_phone = normalize_to_e164(phone)
        user = db.session.scalar(select(User).filter_by(phone_number=normalized_phone))

        if not user:
            click.secho(f"Error: Pengguna dengan nomor {normalized_phone} tidak ditemukan.", fg='red')
            return
        
        click.echo("\n--- Status Awal dari Database ---")
        click.secho(f"Pengguna ditemukan : {user.full_name} (ID: {user.id})", fg='green')
        click.echo(f"  - Last Login IP  : {user.last_login_ip or 'Belum tercatat'}")
        click.echo(f"  - Last Login MAC : {user.last_login_mac or 'Belum tercatat'}")
        click.echo("---------------------------------")
        
        mikrotik_username = format_to_local_phone(user.phone_number)
        
        click.echo("\n1. Mencari 'Jangkar' di MikroTik (/ip/hotspot/ip-binding)...")
        binding_found, binding_details, msg = get_ip_binding_details(mikrotik_username)
        if not binding_found or not binding_details:
            click.secho(f"Peringatan: IP Binding untuk '{mikrotik_username}' tidak ditemukan. Tidak dapat melanjutkan. Pesan: {msg}", fg='yellow')
            return
        
        official_mac = binding_details.get('mac-address')
        if not official_mac:
            click.secho(f"Error: IP Binding untuk '{mikrotik_username}' ada tapi tidak memiliki MAC address.", fg='red')
            return
            
        click.echo(f"   -> Jangkar ditemukan. MAC Address resmi: {official_mac}")

        click.echo("\n2. Mencari Host aktif di MikroTik (/ip/hotspot/host)...")
        host_found, host_details, msg = get_host_details_by_mac(official_mac)
        if not host_found or not host_details:
            click.secho(f"   -> Info: Host aktif untuk MAC {official_mac} tidak ditemukan. Perangkat mungkin offline. Pesan: {msg}", fg='blue')
            return

        new_ip_address = host_details.get('address')
        if not new_ip_address:
            click.secho(f"   -> Peringatan: Host untuk MAC {official_mac} ditemukan tapi tidak punya IP Address.", fg='yellow')
            return

        click.echo(f"   -> Host aktif ditemukan. IP baru saat ini: {new_ip_address}")

        click.echo("\n3. Membandingkan IP baru dengan data di database...")
        last_known_ip = user.last_login_ip
        if new_ip_address == last_known_ip:
            click.secho("   -> IP baru sama dengan IP terakhir. Tidak ada aksi diperlukan.", fg='green', bold=True)
            return
            
        click.secho(f"   -> Perubahan IP terdeteksi! (DB: {last_known_ip} vs MikroTik: {new_ip_address})", fg='cyan', bold=True)
        
        if not click.confirm(click.style("\nApakah Anda yakin ingin melanjutkan dan melakukan sinkronisasi?", fg='yellow')):
            click.secho("Operasi dibatalkan oleh pengguna.", fg='red')
            return

        click.echo("\n4. Memulai proses sinkronisasi...")
        target_server = get_server_for_user(user)
        target_profile = determine_target_profile(user)

        create_or_update_ip_binding(
            mac_address=official_mac,
            ip_address=new_ip_address,
            comment=mikrotik_username,
            server=target_server,
            type='bypassed'
        )
        click.echo(f"   - [OK] IP Binding untuk '{mikrotik_username}' telah diperbarui ke IP {new_ip_address}.")
        
        sync_address_list_for_user(
            username=mikrotik_username,
            new_ip_address=new_ip_address,
            target_profile_name=target_profile,
            old_ip_address=last_known_ip
        )
        click.echo(f"   - [OK] Address List untuk IP lama '{last_known_ip}' dibersihkan dan IP baru '{new_ip_address}' disinkronkan.")
        
        user.last_login_ip = new_ip_address
        user.last_login_mac = official_mac
        user.last_login_at = dt_module.datetime.now(dt_timezone.utc)
        db.session.commit()
        click.echo(f"   - [OK] Database aplikasi diperbarui dengan IP dan waktu login terbaru.")

        click.secho("\nSinkronisasi otomatis berhasil disimulasikan!", fg='green', bold=True)

    except Exception as e:
        db.session.rollback()
        logger.error(f"[SimulateSync] Error kritis saat simulasi untuk {phone}: {e}", exc_info=True)
        click.secho(f"Terjadi error: {e}", fg='red')


# ==============================================================================
# PERINTAH SIMULASI KUOTA RENDAH
# ==============================================================================
@click.command('simulate-low-quota')
@with_appcontext
@click.argument('phone_number', required=False)
@click.option('--purchase', default=10240, help='Total kuota yang disimulasikan dibeli (MB). Default: 10240 (10 GB).')
@click.option('--usage', default=10100, help='Total kuota yang disimulasikan terpakai (MB). Default: 10100 (~9.86 GB).')
def simulate_low_quota_command(phone_number: str, purchase: int, usage: int):
    """
    Memanipulasi data pengguna untuk mensimulasikan kondisi kuota rendah.
    """
    target_phone = phone_number
    if not target_phone:
        test_numbers = current_app.config.get('SYNC_TEST_PHONE_NUMBERS', [])
        if not test_numbers:
            click.secho("Error: Tidak ada nomor telepon yang diberikan dan SYNC_TEST_PHONE_NUMBERS di .env kosong.", fg='red', bold=True)
            return
        target_phone = test_numbers[0]
        click.secho(f"Info: Menggunakan nomor telepon dari .env: {target_phone}", fg='blue')

    click.echo(f"Mencari pengguna dengan nomor: {target_phone}...")

    try:
        normalized_phone = normalize_to_e164(target_phone)
    except ValueError as e:
        click.secho(f"Error: Format nomor telepon tidak valid. {e}", fg='red')
        return

    user = db.session.scalar(select(User).filter_by(phone_number=normalized_phone))

    if not user:
        click.secho(f"Pengguna dengan nomor {normalized_phone} tidak ditemukan.", fg='red')
        return

    click.secho(f"Pengguna ditemukan: {user.full_name} (ID: {user.id})", fg='green')
    
    click.echo("\n--- Status Sebelum Simulasi ---")
    click.echo(f"  - Kuota Dibeli  : {user.total_quota_purchased_mb or 0} MB")
    click.echo(f"  - Kuota Terpakai: {user.total_quota_used_mb or 0.0:.2f} MB")
    sisa_sebelum = (user.total_quota_purchased_mb or 0) - (user.total_quota_used_mb or 0)
    click.echo(f"  - Sisa Kuota    : {max(0, sisa_sebelum):.2f} MB")
    notif_time_before = format_datetime_to_wita(user.last_low_quota_notif_at) if user.last_low_quota_notif_at else "Belum Pernah"
    click.echo(f"  - Notif Terakhir: {notif_time_before}")
    click.echo("---------------------------------")

    if not click.confirm(click.style("\nApakah Anda yakin ingin melanjutkan dan mengubah data pengguna ini di database?", fg='yellow')):
        click.secho("Operasi dibatalkan oleh pengguna.", fg='red')
        return

    click.echo("\nMemulai simulasi kondisi kuota rendah...")

    try:
        user.is_active = True
        user.is_unlimited_user = False
        user.total_quota_purchased_mb = purchase
        user.total_quota_used_mb = usage
        user.last_low_quota_notif_at = None

        db.session.commit()

        click.echo("\n--- Status Setelah Simulasi ---")
        click.echo(f"  - Kuota Dibeli  : {user.total_quota_purchased_mb} MB")
        click.echo(f"  - Kuota Terpakai: {user.total_quota_used_mb:.2f} MB")
        remaining_mb = user.total_quota_purchased_mb - user.total_quota_used_mb
        click.echo(f"  - Sisa Kuota    : {max(0, remaining_mb):.2f} MB")
        click.echo("  - Timer notifikasi kuota rendah telah di-reset.")
        click.echo("-----------------------------------")

        click.secho("\nSimulasi BERHASIL! Data pengguna telah diperbarui di database.", fg='cyan', bold=True)
        click.echo("=================================================================")
        click.echo("Langkah Selanjutnya:")
        click.echo("1. Buka terminal baru, masuk ke environment Anda, dan jalankan Celery shell:")
        click.secho("   celery -A app.extensions:celery_app shell", fg='yellow')
        
        click.echo("\n2. Untuk tes notifikasi WhatsApp (jika pengguna memenuhi syarat), jalankan di dalam shell:")
        click.secho("   >>> from app.tasks import check_low_quota_task", fg='yellow')
        click.secho("   >>> check_low_quota_task.delay()", fg='yellow')
        
        click.echo("\n3. Untuk tes perubahan profil MikroTik (FUP/Habis), jalankan di dalam shell:")
        click.secho("   >>> from app.tasks import sync_single_user_status", fg='yellow')
        click.secho(f"   >>> sync_single_user_status.delay(user_id='{user.id}')", fg='yellow')

        click.echo("\n4. Pantau log di terminal Celery Worker untuk melihat prosesnya.")

    except Exception as e:
        db.session.rollback()
        click.secho(f"\nTerjadi kesalahan saat melakukan simulasi: {e}", fg='red')