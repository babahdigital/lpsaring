# backend/app/commands/user_commands.py

import click
from flask import current_app
from flask.cli import AppGroup, with_appcontext
from app.extensions import db
import re
import uuid
import enum
import random
import string
from datetime import datetime, timezone as dt_timezone, date, timedelta
from typing import Optional, Any, Dict, List

# --- Impor Model & Helper ---
MODELS_AVAILABLE = False
try:
    from app.infrastructure.db.models import User, UserRole, ApprovalStatus, UserBlok, UserKamar, DailyUsageLog, PackageProfile
    MODELS_AVAILABLE = True
except ImportError:
    # Fallback definitions if models cannot be imported (e.g., during testing or setup issues)
    print("CRITICAL ERROR: Could not import User/DailyUsageLog/PackageProfile models in user_commands.py. CLI functions may be limited.")
    class UserRole(str, enum.Enum): USER = "USER"; ADMIN = "ADMIN"; SUPER_ADMIN = "SUPER_ADMIN" # type: ignore
    class ApprovalStatus(str, enum.Enum): PENDING_APPROVAL = "PENDING_APPROVAL"; APPROVED = "APPROVED"; REJECTED = "REJECTED" # type: ignore
    class UserBlok(str, enum.Enum): A="A"; B="B"; C="C"; D="D"; E="E"; F="F"; # type: ignore
    class UserKamar(str, enum.Enum): # type: ignore
        Kamar_1="Kamar_1"; Kamar_2="Kamar_2"; Kamar_3="Kamar_3"; Kamar_4="Kamar_4"; Kamar_5="Kamar_5"; Kamar_6="Kamar_6" # type: ignore
    class User(object): # type: ignore
        id: uuid.UUID
        phone_number: str
        full_name: str
        role: Any
        approval_status: Any
        is_active: bool
        mikrotik_password: Optional[str]
        total_quota_purchased_mb: int
        total_quota_used_mb: float
        quota_expiry_date: Optional[datetime]
        is_unlimited_user: bool
        blok: Optional[str]
        kamar: Optional[str]
        device_brand: Optional[str]
        device_model: Optional[str]
        created_at: datetime
        updated_at: datetime
        password_hash: Optional[str]
        approved_at: Optional[datetime]
        approved_by_id: Optional[uuid.UUID]
        rejected_at: Optional[datetime]
        rejected_by_id: Optional[uuid.UUID]
        @property
        def is_admin_role(self):
            if isinstance(self.role, enum.Enum):
                return self.role in [UserRole.ADMIN, UserRole.SUPER_ADMIN]
            return self.role in ["ADMIN", "SUPER_ADMIN"]

    class DailyUsageLog(object): # type: ignore
        user_id: uuid.UUID
        log_date: datetime.date
        usage_mb: float
    class PackageProfile(object): # type: ignore
        id: uuid.UUID
        profile_name: str


try:
    from werkzeug.security import generate_password_hash
    generate_password_hash_func = generate_password_hash
except ImportError:
    def dummy_hash(password: str) -> str: return f"hashed_{password}" # type: ignore
    generate_password_hash_func = dummy_hash

WHATSAPP_AVAILABLE = False
try:
    from app.infrastructure.gateways.whatsapp_client import send_whatsapp_message
    WHATSAPP_AVAILABLE = True
except ImportError:
    def send_whatsapp_message(to: str, body: str) -> bool: return False # type: ignore

MIKROTIK_CLIENT_AVAILABLE = False
try:
    from app.infrastructure.gateways.mikrotik_client import (
        get_mikrotik_connection,
        activate_or_update_hotspot_user,
        format_to_local_phone,
        delete_hotspot_user,
        set_hotspot_user_profile,
        add_mikrotik_hotspot_user_profile
    )
    MIKROTIK_CLIENT_AVAILABLE = True
except ImportError:
    def get_mikrotik_connection(): return None # type: ignore
    def activate_or_update_hotspot_user(api_connection: Any, user_mikrotik_username: str, mikrotik_profile_name: str, hotspot_password: str, comment:str="", limit_bytes_total: Optional[int] = None, session_timeout_seconds: Optional[int] = None, force_update_profile: bool = False): return False, "Mikrotik client not available/not implemented." # type: ignore
    def format_to_local_phone(phone: str | None) -> str | None: return phone if not (phone and phone.startswith('+62')) else '0' + phone[3:] # type: ignore
    def delete_hotspot_user(api_connection: Any, username: str): return False, "Mikrotik client not available/not implemented." # type: ignore
    def set_hotspot_user_profile(api_connection: Any, username_or_id: str, new_profile_name: str): return False, "Mikrotik client not available/not implemented." # type: ignore
    def add_mikrotik_hotspot_user_profile(api_connection: Any, profile_name: str, rate_limit: Optional[str] = None, shared_users: Optional[int] = None, comment: Optional[str] = None): return False, "Mikrotik client not available/not implemented." # type: ignore


NOTIFICATION_SERVICE_AVAILABLE = False
try:
    from app.services.notification_service import get_notification_message
    NOTIFICATION_SERVICE_AVAILABLE = True
except ImportError:
    def get_notification_message(template_key: str, context: Dict[str, Any] = None) -> str: # type: ignore
        if hasattr(current_app, 'logger'):
            current_app.logger.warning(f"Notification service not available. Template: {template_key}")
        else:
            print(f"WARNING: Notification service not available (no app context). Template: {template_key}")
        return f"Warning: Notification template '{template_key}' not found or service unavailable."

from app.services import settings_service
from app.utils.formatters import normalize_to_e164, format_to_local_phone, get_phone_number_variations

# --- Role choice mapping for create-admin ---
if MODELS_AVAILABLE:
    ROLE_INPUT_MAP_ADMIN_CREATE = {
        '1': UserRole.SUPER_ADMIN,
        '2': UserRole.ADMIN,
        '3': UserRole.USER
    }
    ROLE_DESCRIPTIONS_ADMIN_CREATE = [f"{num}: {ROLE_INPUT_MAP_ADMIN_CREATE[num].value}" for num in sorted(ROLE_INPUT_MAP_ADMIN_CREATE.keys())]
else:
    ROLE_INPUT_MAP_ADMIN_CREATE = {'1': "SUPER_ADMIN_FALLBACK", '2': "ADMIN_FALLBACK", '3': "USER_FALLBACK"}
    ROLE_DESCRIPTIONS_ADMIN_CREATE = ["1: SUPER_ADMIN (fallback)", "2: ADMIN (fallback)", "3: USER (fallback)"]

# --- Definisi Grup CLI dan Fungsi Helper ---
@click.group(name='user', help="Perintah terkait manajemen pengguna aplikasi hotspot.")
def user_cli_bp():
    pass

def normalize_phone_for_cli(phone_number_input: str) -> str:
    """Normalizes phone number input from CLI using common utility."""
    try:
        return normalize_to_e164(phone_number_input)
    except ValueError as e:
        raise click.BadParameter(str(e))
    except TypeError as e:
        raise click.BadParameter(f"Input nomor telepon harus berupa string: {str(e)}")

def generate_random_password(length=6, type='numeric'):
    """Generates a random password of specified type and length."""
    if type == 'numeric':
        return "".join(random.choices(string.digits, k=length))
    elif type == 'alphanumeric':
        alphabet = string.ascii_letters + string.digits
        return "".join(random.choices(alphabet, k=length))
    else:
        return "".join(random.choices(string.digits, k=length))


# --- Perintah create-admin ---
@user_cli_bp.command('create-admin', help="Membuat pengguna Admin/Super Admin/User baru (langsung aktif & diapprove).")
@click.option('--phone', required=True, prompt="Nomor Telepon (format 08... atau +62...)", help="Nomor telepon unik.")
@click.option('--name', required=True, prompt="Nama Lengkap", help="Nama lengkap.")
@click.option('--role',
              type=click.Choice(list(ROLE_INPUT_MAP_ADMIN_CREATE.keys())),
              default='2',
              prompt=f"Pilih Role ({', '.join(ROLE_DESCRIPTIONS_ADMIN_CREATE)})",
              show_default=True,
              show_choices=False,
              help=f"Tentukan role untuk pengguna. {', '.join(ROLE_DESCRIPTIONS_ADMIN_CREATE)}.")
@click.option('--blok',
              default="",
              prompt=f"Blok Rumah ({', '.join(b.value for b in UserBlok)}) (Opsional untuk Admin, Wajib untuk User)" if MODELS_AVAILABLE and UserBlok else "Blok Rumah (A-F) (Opsional untuk Admin, Wajib untuk User)",
              help=f"Blok rumah. Pilihan: {', '.join(b.value for b in UserBlok) if MODELS_AVAILABLE and UserBlok else 'A-F'}. Kosongkan untuk Admin. Wajib untuk User.",
              type=click.Choice([b.value for b in UserBlok] + [""] if MODELS_AVAILABLE and UserBlok else ["A","B","C","D","E","F",""], case_sensitive=False),
              show_default=False,
              show_choices=False)
@click.option('--kamar',
              default="",
              prompt=f"Nomor Kamar ({', '.join(k.value for k in UserKamar)}) (Opsional untuk Admin, Wajib untuk User)" if MODELS_AVAILABLE and UserKamar else "Nomor Kamar (Kamar_1-Kamar_6) (Opsional untuk Admin, Wajib untuk User)",
              help=f"Nomor kamar. Pilihan: {', '.join(k.value for k in UserKamar) if MODELS_AVAILABLE and UserKamar else 'Kamar_1-Kamar_6'}. Kosongkan untuk Admin. Wajib untuk User.",
              type=click.Choice([k.value for k in UserKamar] + [""] if MODELS_AVAILABLE and UserKamar else ["Kamar_1","Kamar_2","Kamar_3","Kamar_4","Kamar_5","Kamar_6",""], case_sensitive=False),
              show_default=False,
              show_choices=False)
@click.option('--mikrotik-password', default=None, help="Password Mikrotik khusus (opsional, hanya jika role USER, jika kosong akan digenerate).")
@click.option('--portal-password', required=False, help="Password Portal (hanya untuk Admin/Super Admin. Jika kosong, akan digenerate).")
@with_appcontext
def create_admin(phone, name, role, blok, kamar, mikrotik_password, portal_password):
    if not MODELS_AVAILABLE or not hasattr(db, 'session') or not User or not ApprovalStatus or not UserRole:
        click.echo(click.style("ERROR: Model User, ApprovalStatus, UserRole atau database session tidak dapat dimuat. Perintah create-admin tidak bisa dijalankan.", fg='red')); return
    
    if not generate_password_hash_func:
        click.echo(click.style("ERROR: Fungsi hashing password tidak tersedia. Perintah create-admin tidak bisa dijalankan.", fg='red')); return

    try:
        normalized_phone = normalize_phone_for_cli(phone)
        
        try:
            role_enum = ROLE_INPUT_MAP_ADMIN_CREATE[role]
        except KeyError:
            click.echo(click.style(f"ERROR: Pilihan role internal '{role}' tidak valid.", fg='red'))
            return
        
        blok_clean = blok.strip().upper() if blok else ""
        kamar_clean = kamar.strip() if kamar else ""

        blok_val_for_db = None
        kamar_val_for_db = None
        
        if role_enum == UserRole.USER:
            if not blok_clean:
                click.echo(click.style("ERROR: Blok wajib diisi untuk peran USER.", fg='red')); return
            if not kamar_clean:
                click.echo(click.style("ERROR: Kamar wajib diisi untuk peran USER.", fg='red')); return
            
            if MODELS_AVAILABLE and UserBlok and blok_clean in [b.value for b in UserBlok]:
                blok_val_for_db = blok_clean
            else:
                click.echo(click.style(f"ERROR: Nilai Blok '{blok}' tidak valid untuk peran USER. Pilihan: {[b.value for b in UserBlok]}", fg='red')); return

            if kamar_clean.isdigit() and 1 <= int(kamar_clean) <= 6:
                kamar_val_for_db = f"Kamar_{kamar_clean}"
            elif MODELS_AVAILABLE and UserKamar and kamar_clean in [k.value for k in UserKamar]:
                kamar_val_for_db = kamar_clean
            else:
                click.echo(click.style(f"ERROR: Nilai Kamar '{kamar}' tidak valid untuk peran USER. Pilihan: {[k.value for k in UserKamar]} atau angka 1-6.", fg='red')); return
        else: # Role ADMIN atau SUPER_ADMIN
            if blok_clean and MODELS_AVAILABLE and UserBlok and blok_clean in [b.value for b in UserBlok]:
                blok_val_for_db = blok_clean
            elif blok_clean:
                click.echo(click.style(f"WARNING: Nilai Blok '{blok}' tidak valid untuk Admin. Dikosongkan. Pilihan: {[b.value for b in UserBlok]}", fg='yellow'))
                blok_val_for_db = None
            
            if kamar_clean:
                if kamar_clean.isdigit() and 1 <= int(kamar_clean) <= 6:
                    kamar_val_for_db = f"Kamar_{kamar_clean}"
                elif MODELS_AVAILABLE and UserKamar and kamar_clean in [k.value for k in UserKamar]:
                    kamar_val_for_db = kamar_clean
                else:
                    click.echo(click.style(f"WARNING: Nilai Kamar '{kamar}' tidak valid untuk Admin. Dikosongkan. Pilihan: {[k.value for k in UserKamar]} atau angka 1-6.", fg='yellow'))
                    kamar_val_for_db = None

    except (ValueError, TypeError) as e:
        click.echo(click.style(f"ERROR: Input tidak valid - {str(e)}", fg='red')); return
    except Exception as e:
        current_app.logger.error(f"Terjadi kesalahan tidak terduga saat parsing input: {e}", exc_info=True)
        click.echo(click.style(f"ERROR: Terjadi kesalahan tidak terduga saat parsing input: {str(e)}", fg='red')); return


    if db.session.execute(db.select(User).filter_by(phone_number=normalized_phone)).scalar_one_or_none():
        click.echo(click.style(f"ERROR: Nomor telepon '{normalized_phone}' sudah terdaftar.", fg='red')); return

    hashed_portal_password = None
    password_portal_plain_text = None

    if role_enum == UserRole.USER:
        click.echo(click.style("INFO: Password portal tidak diperlukan untuk peran USER.", fg='blue'))
        password_portal_plain_text = None
        hashed_portal_password = None
    elif role_enum == UserRole.ADMIN:
        password_portal_plain_text = generate_random_password(length=6, type='numeric')
        hashed_portal_password = generate_password_hash_func(password_portal_plain_text)
        click.echo(click.style(f"INFO: Password portal otomatis digenerate (6 digit angka) untuk peran ADMIN.", fg='blue'))
    elif role_enum == UserRole.SUPER_ADMIN:
        if portal_password:
            if len(portal_password) < 6:
                click.echo(click.style("ERROR: Password portal minimal 6 karakter.", fg='red')); return
            password_portal_plain_text = portal_password
            hashed_portal_password = generate_password_hash_func(password_portal_plain_text)
            click.echo(click.style("INFO: Password portal manual digunakan untuk peran SUPER_ADMIN.", fg='blue'))
        else:
            password_portal_plain_text = generate_random_password(length=6, type='numeric')
            hashed_portal_password = generate_password_hash_func(password_portal_plain_text)
            click.echo(click.style("INFO: Password portal otomatis digenerate (6 digit angka) untuk peran SUPER_ADMIN.", fg='blue'))
    else:
        click.echo(click.style("ERROR: Role tidak valid. Password tidak diproses.", fg='red')); return


    final_mikrotik_password_for_db = None
    if role_enum == UserRole.USER:
        final_mikrotik_password_for_db = mikrotik_password if mikrotik_password else generate_random_password(length=8, type='numeric')
    elif mikrotik_password:
        click.echo(click.style("WARNING: Password Mikrotik diabaikan untuk peran Admin/Super Admin.", fg='yellow'))
    
    new_user = User(
        phone_number=normalized_phone,
        full_name=name,
        blok=blok_val_for_db,
        kamar=kamar_val_for_db,
        password_hash=hashed_portal_password,
        mikrotik_password=final_mikrotik_password_for_db,
        role=role_enum,
        approval_status=ApprovalStatus.APPROVED,
        is_active=True,
        approved_at=datetime.now(dt_timezone.utc),
        total_quota_purchased_mb=0,
        total_quota_used_mb=0,
        quota_expiry_date=None,
        is_unlimited_user=False
    )

    db.session.add(new_user)
    db.session.flush()

    if role_enum == UserRole.USER and MIKROTIK_CLIENT_AVAILABLE:
        try:
            with get_mikrotik_connection() as mikrotik_api_conn:
                if mikrotik_api_conn:
                    mikrotik_profile_name = current_app.config.get('MIKROTIK_DEFAULT_PROFILE', 'default')
                    
                    mikrotik_kwargs = {
                        "api_connection": mikrotik_api_conn,
                        "user_mikrotik_username": format_to_local_phone(new_user.phone_number),
                        "mikrotik_profile_name": mikrotik_profile_name,
                        "hotspot_password": new_user.mikrotik_password,
                        "comment": f"Created by CLI admin ({new_user.full_name})"
                    }
                    
                    if current_app.config.get('MIKROTIK_SEND_LIMIT_BYTES_TOTAL', False):
                        mikrotik_kwargs['limit_bytes_total'] = int(new_user.total_quota_purchased_mb * 1024 * 1024)
                    
                    if current_app.config.get('MIKROTIK_SEND_SESSION_TIMEOUT', False):
                        if new_user.quota_expiry_date:
                            time_remaining = (new_user.quota_expiry_date - datetime.now(dt_timezone.utc)).total_seconds()
                            mikrotik_kwargs['session_timeout_seconds'] = max(0, int(time_remaining))
                        else:
                            mikrotik_kwargs['session_timeout_seconds'] = 0

                    activate_success, mikrotik_msg = activate_or_update_hotspot_user(**mikrotik_kwargs)

                    if activate_success:
                        click.echo(click.style(f"INFO: Akun Mikrotik untuk user '{new_user.full_name}' berhasil dibuat/diupdate. Mikrotik: {mikrotik_msg}", fg='blue'))
                    else:
                        click.echo(click.style(f"WARNING: Gagal membuat/mengupdate akun Mikrotik untuk user '{new_user.full_name}': {mikrotik_msg}", fg='yellow'))
                else:
                    click.echo(click.style("WARNING: Gagal mendapatkan koneksi Mikrotik untuk pembuatan user.", fg='yellow'))
        except Exception as e_mt:
            current_app.logger.error(f"ERROR: Exception saat membuat akun Mikrotik untuk user '{new_user.full_name}': {str(e_mt)}", exc_info=True)
            click.echo(click.style(f"ERROR: Exception saat membuat akun Mikrotik untuk user '{new_user.full_name}': {str(e_mt)}", fg='red'))


    try:
        db.session.commit()
        db.session.refresh(new_user)
        click.echo(click.style(f"SUKSES: Pengguna {role_enum.value} '{new_user.full_name}' (ID: {new_user.id}) berhasil dibuat.", fg='green'))
        
        from app.services import settings_service 
        if WHATSAPP_AVAILABLE and NOTIFICATION_SERVICE_AVAILABLE and settings_service.get_setting('ENABLE_WHATSAPP_NOTIFICATIONS', 'False') == 'True':
            message_body = ""
            if new_user.role == UserRole.ADMIN or new_user.role == UserRole.SUPER_ADMIN:
                context = {"phone_number": format_to_local_phone(new_user.phone_number), "password": password_portal_plain_text}
                message_body = get_notification_message("admin_creation_success", context)
            elif new_user.role == UserRole.USER:
                context = {
                    "full_name": new_user.full_name,
                    "username": format_to_local_phone(new_user.phone_number),
                    "password": new_user.mikrotik_password
                }
                message_body = get_notification_message("user_created_by_admin_with_password", context)
                
            if message_body:
                send_whatsapp_message(new_user.phone_number, message_body)
                click.echo(click.style(f"INFO: Notifikasi WhatsApp dikirim ke {new_user.phone_number}.", fg='blue'))

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error creating user via CLI: {str(e)}", exc_info=True)
        click.echo(click.style(f"ERROR: Gagal menyimpan pengguna baru: {str(e)}", fg='red'))

# --- Perintah create-superadmin ---
@user_cli_bp.command('create-superadmin', help="Membuat pengguna Super Admin baru dengan password otomatis (dikirim WA).")
@click.option('--phone', required=True, prompt="Nomor Telepon Super Admin (format 08... atau +62...)", help="Nomor telepon unik Super Admin.")
@click.option('--name', required=True, prompt="Nama Lengkap Super Admin", help="Nama lengkap Super Admin.")
@click.option('--blok',
              default="",
              prompt=f"Blok Rumah ({', '.join(b.value for b in UserBlok)}) (Opsional)" if MODELS_AVAILABLE and UserBlok else "Blok Rumah (A-F) (Opsional)",
              help=f"Blok rumah. Pilihan: {', '.join(b.value for b in UserBlok) if MODELS_AVAILABLE and UserBlok else 'A-F'}. Kosongkan jika tidak relevan.",
              type=click.Choice([b.value for b in UserBlok] + [""] if MODELS_AVAILABLE and UserBlok else ["A","B","C","D","E","F",""], case_sensitive=False),
              show_default=False,
              show_choices=False)
@click.option('--kamar',
              default="",
              prompt=f"Nomor Kamar ({', '.join(k.value for k in UserKamar)}) (Opsional)" if MODELS_AVAILABLE and UserKamar else "Nomor Kamar (Kamar_1-Kamar_6) (Opsional)",
              help=f"Nomor kamar. Pilihan: {', '.join(k.value for k in UserKamar) if MODELS_AVAILABLE and UserKamar else 'Kamar_1-Kamar_6'}. Kosongkan jika tidak relevan.",
              type=click.Choice([k.value for k in UserKamar] + [""] if MODELS_AVAILABLE and UserKamar else ["Kamar_1","Kamar_2","Kamar_3","Kamar_4","Kamar_5","Kamar_6",""], case_sensitive=False),
              show_default=False,
              show_choices=False)
@with_appcontext
def create_superadmin(phone, name, blok, kamar):
    if not MODELS_AVAILABLE or not hasattr(db, 'session') or not User or not ApprovalStatus or not UserRole:
        click.echo(click.style("ERROR: Model User, ApprovalStatus, UserRole atau database session tidak dapat dimuat. Perintah create-superadmin tidak bisa dijalankan.", fg='red')); return
    if not generate_password_hash_func:
        click.echo(click.style("ERROR: Fungsi hashing password tidak tersedia. Perintah create-superadmin tidak bisa dijalankan.", fg='red')); return

    try:
        normalized_phone = normalize_phone_for_cli(phone)
        blok_clean = blok.strip().upper() if blok else ""
        kamar_clean = kamar.strip() if kamar else ""

        blok_val_for_db = blok_clean if MODELS_AVAILABLE and UserBlok and blok_clean in [b.value for b in UserBlok] else None
        
        if kamar_clean.isdigit() and 1 <= int(kamar_clean) <= 6:
            kamar_val_for_db = f"Kamar_{kamar_clean}"
        elif MODELS_AVAILABLE and UserKamar and kamar_clean in [k.value for k in UserKamar]:
            kamar_val_for_db = kamar_clean
        else:
            kamar_val_for_db = None


    except click.BadParameter as e:
        click.echo(click.style(f"ERROR: {str(e.message)}", fg='red')); return
    except Exception as e:
        current_app.logger.error(f"Terjadi kesalahan tidak terduga saat parsing input: {e}", exc_info=True)
        click.echo(click.style(f"ERROR: Terjadi kesalahan tidak terduga saat parsing input: {str(e)}", fg='red')); return

    if db.session.execute(db.select(User).filter_by(phone_number=normalized_phone)).scalar_one_or_none():
        click.echo(click.style(f"ERROR: Nomor telepon '{normalized_phone}' sudah terdaftar.", fg='red')); return

    password_portal_plain_text = generate_random_password(length=6, type='numeric')
    hashed_portal_password = generate_password_hash_func(password_portal_plain_text)
    
    new_user = User(
        phone_number=normalized_phone,
        full_name=name,
        blok=blok_val_for_db,
        kamar=kamar_val_for_db,
        password_hash=hashed_portal_password,
        mikrotik_password=None,
        role=UserRole.SUPER_ADMIN,
        approval_status=ApprovalStatus.APPROVED,
        is_active=True,
        approved_at=datetime.now(dt_timezone.utc),
        total_quota_purchased_mb=0,
        total_quota_used_mb=0,
        quota_expiry_date=None,
        is_unlimited_user=False
    )

    db.session.add(new_user)
    try:
        db.session.commit()
        db.session.refresh(new_user)
        click.echo(click.style(f"SUKSES: Pengguna Super Admin '{new_user.full_name}' (ID: {new_user.id}) berhasil dibuat.", fg='green'))
        
        from app.services import settings_service

        if WHATSAPP_AVAILABLE and NOTIFICATION_SERVICE_AVAILABLE and settings_service.get_setting('ENABLE_WHATSAPP_NOTIFICATIONS', 'False') == 'True':
            context = {"phone_number": format_to_local_phone(new_user.phone_number), "password": password_portal_plain_text}
            message_body = get_notification_message("admin_creation_success", context)
            if message_body:
                send_whatsapp_message(new_user.phone_number, message_body)
                click.echo(click.style(f"INFO: Notifikasi WhatsApp berisi password dikirim ke {new_user.phone_number}.", fg='blue'))
            else:
                current_app.logger.warning("Gagal mendapatkan pesan notifikasi WhatsApp. Password tidak terkirim via WA.")
                click.echo(click.style("WARNING: Gagal mendapatkan pesan notifikasi WhatsApp. Password tidak terkirim via WA.", fg='yellow'))
                click.echo(click.style(f"  PASSWORD SUPER ADMIN: {password_portal_plain_text}", fg='magenta', bold=True))
        else:
            current_app.logger.info("Notifikasi WhatsApp dinonaktifkan di pengaturan atau klien/service tidak tersedia.")
            click.echo(click.style("INFO: Notifikasi WhatsApp dinonaktifkan di pengaturan atau klien/service tidak tersedia. Password tidak terkirim via WA.", fg='yellow'))
            click.echo(click.style(f"  PASSWORD SUPER ADMIN: {password_portal_plain_text}", fg='magenta', bold=True))

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error creating Super Admin via CLI: {str(e)}", exc_info=True)
        click.echo(click.style(f"ERROR: Gagal menyimpan Super Admin baru: {str(e)}", fg='red'))

# --- Perintah update ---
@user_cli_bp.command('update', help="Memperbarui data pengguna yang sudah ada.")
@click.argument('phone_number', type=str)
@click.option('--nama', default=None, help="Nama lengkap baru.")
@click.option('--blok', default=None, help="Blok baru (A/B/C...) atau 'kosong' untuk menghapus. Wajib untuk User.")
@click.option('--kamar', default=None, help="Kamar baru (Kamar_1/Kamar_2/...) atau 'kosong' untuk menghapus. Wajib untuk User.")
@click.option('--aktif', default=None, type=click.BOOL, help="Set status aktif (true/false).")
@click.option('--admin-id', '-a', type=str, default=None, help="UUID Admin yang melakukan aksi (opsional, untuk log).")
@click.option('--is-unlimited', type=click.BOOL, default=None, help="Set status unlimited (true/false).")
@click.option('--expiry-date', type=str, default=None, help="Tanggal kadaluarsa kuota (YYYY-MM-DD).")
@with_appcontext
def update_user(phone_number, nama, blok, kamar, aktif, admin_id, is_unlimited, expiry_date):
    if not MODELS_AVAILABLE or not hasattr(db, 'session') or not User or not UserBlok or not UserKamar or not UserRole:
        click.echo(click.style("ERROR: Model User, UserBlok, UserKamar, UserRole atau database session tidak dapat dimuat.", fg='red')); return

    admin_performing_update = None; admin_id_for_log_upd = "Tidak Diketahui"
    if admin_id:
        try:
            admin_uuid_upd = uuid.UUID(admin_id)
            fetched_admin = db.session.get(User, admin_uuid_upd)
            if fetched_admin and fetched_admin.is_admin_role:
                admin_performing_update = fetched_admin
                admin_id_for_log_upd = str(admin_performing_update.id)
            elif fetched_admin:
                click.echo(click.style(f"WARNING: Pengguna '{fetched_admin.full_name}' bukan Admin (Role: {fetched_admin.role.value}).", fg='yellow'))
            else:
                click.echo(click.style(f"WARNING: Admin ID '{admin_id}' tidak ditemukan.", fg='yellow'))
        except (ValueError, AttributeError) as e:
            current_app.logger.warning(f"Tidak dapat verifikasi role admin untuk admin_id '{admin_id}': {e}", exc_info=True)
            click.echo(click.style(f"WARNING: Tidak dapat verifikasi role admin untuk admin_id '{admin_id}'.", fg='yellow'))


    try:
        normalized_phone = normalize_phone_for_cli(phone_number)
    except click.BadParameter as e:
        click.echo(click.style(f"ERROR: {str(e.message)}", fg='red')); return

    user_to_update = db.session.execute(db.select(User).filter_by(phone_number=normalized_phone)).scalar_one_or_none()

    if not user_to_update:
        click.echo(click.style(f"ERROR: Pengguna '{normalized_phone}' tidak ditemukan.", fg='red')); return

    updated_fields = []
    user_updated = False

    if nama is not None:
        if user_to_update.full_name != nama:
            user_to_update.full_name = nama
            updated_fields.append(f"Nama menjadi '{nama}'")
            user_updated = True
        else:
            click.echo(click.style(f"INFO: Nama pengguna sudah '{nama}'.", fg='blue'))

    # Handle blok update
    if blok is not None:
        if blok.lower() == "kosong":
            if user_to_update.role == UserRole.USER:
                click.echo(click.style("ERROR: Blok tidak bisa dikosongkan untuk peran USER (wajib diisi).", fg='red')); return
            if user_to_update.blok is not None:
                user_to_update.blok = None
                updated_fields.append("Blok dikosongkan")
                user_updated = True
            else:
                click.echo(click.style("INFO: Blok pengguna sudah kosong.", fg='blue'))
        else:
            if MODELS_AVAILABLE and UserBlok and blok.upper() in [b.value for b in UserBlok]:
                blok_val_for_db = blok.upper()
                if user_to_update.blok != blok_val_for_db:
                    user_to_update.blok = blok_val_for_db
                    updated_fields.append(f"Blok menjadi '{blok_val_for_db}'")
                    user_updated = True
                else:
                    click.echo(click.style(f"INFO: Blok pengguna sudah '{blok_val_for_db}'.", fg='blue'))
            else:
                click.echo(click.style(f"ERROR: Nilai blok '{blok}' tidak valid. Pilihan: {[b.value for b in UserBlok]}", fg='red')); return

    # Handle kamar update
    if kamar is not None:
        if kamar.lower() == "kosong":
            if user_to_update.role == UserRole.USER:
                click.echo(click.style("ERROR: Kamar tidak bisa dikosongkan untuk peran USER (wajib diisi).", fg='red')); return
            if user_to_update.kamar is not None:
                user_to_update.kamar = None
                updated_fields.append("Kamar dikosongkan")
                user_updated = True
            else:
                click.echo(click.style("INFO: Kamar pengguna sudah kosong.", fg='blue'))
        else:
            if kamar.isdigit() and 1 <= int(kamar) <= 6:
                kamar_val_for_db = f"Kamar_{kamar}"
            elif MODELS_AVAILABLE and UserKamar and kamar in [k.value for k in UserKamar]:
                kamar_val_for_db = kamar
            else:
                click.echo(click.style(f"ERROR: Nilai kamar '{kamar}' tidak valid. Pilihan: {[k.value for k in UserKamar]} atau angka 1-6.", fg='red')); return

            if user_to_update.kamar != kamar_val_for_db:
                user_to_update.kamar = kamar_val_for_db
                updated_fields.append(f"Kamar menjadi '{kamar_val_for_db}'")
                user_updated = True
            else:
                click.echo(click.style(f"INFO: Kamar pengguna sudah '{kamar_val_for_db}'.", fg='blue'))

    if aktif is not None:
        if user_to_update.is_active != aktif:
            user_to_update.is_active = aktif
            updated_fields.append(f"Status aktif menjadi '{'Ya' if aktif else 'Tidak'}'")
            user_updated = True
        else:
            click.echo(click.style(f"INFO: Status aktif pengguna sudah '{'Ya' if aktif else 'Tidak'}'.", fg='blue'))

    if is_unlimited is not None:
        if user_to_update.is_unlimited_user != is_unlimited:
            user_to_update.is_unlimited_user = is_unlimited
            updated_fields.append(f"Status unlimited menjadi '{'Ya' if is_unlimited else 'Tidak'}'")
            user_updated = True
        else:
            click.echo(click.style(f"INFO: Status unlimited pengguna sudah '{'Ya' if is_unlimited else 'Tidak'}'.", fg='blue'))

    if expiry_date is not None:
        if expiry_date.lower() == "kosong":
            if user_to_update.quota_expiry_date is not None:
                user_to_update.quota_expiry_date = None
                updated_fields.append("Tanggal kadaluarsa kuota dikosongkan")
                user_updated = True
            else:
                click.echo(click.style("INFO: Tanggal kadaluarsa kuota pengguna sudah kosong.", fg='blue'))
        else:
            try:
                parsed_date = datetime.strptime(expiry_date, '%Y-%m-%d').replace(tzinfo=dt_timezone.utc)
                if user_to_update.quota_expiry_date != parsed_date:
                    user_to_update.quota_expiry_date = parsed_date
                    updated_fields.append(f"Tanggal kadaluarsa kuota menjadi '{expiry_date}'")
                    user_updated = True
                else:
                    click.echo(click.style(f"INFO: Tanggal kadaluarsa kuota pengguna sudah '{expiry_date}'.", fg='blue'))
            except ValueError:
                click.echo(click.style(f"ERROR: Format tanggal kadaluarsa '{expiry_date}' tidak valid. Gunakan YYYY-MM-DD.", fg='red')); return


    if not user_updated:
        click.echo(click.style("Tidak ada perubahan data yang dilakukan.", fg='yellow'))
        return

    try:
        user_to_update.updated_at = datetime.now(dt_timezone.utc)
        db.session.commit()
        log_msg = f"User data updated: ID={user_to_update.id}, Phone={normalized_phone}, Name='{user_to_update.full_name}'. Changes: {'; '.join(updated_fields)}. Admin ID: {admin_id_for_log_upd if admin_performing_update else 'System/CLI'}."
        current_app.logger.info(log_msg)
        click.echo(click.style(f"SUKSES: Data pengguna '{user_to_update.full_name}' ({normalized_phone}) berhasil diperbarui.", fg='green'))
        click.echo(f"  Perubahan: {', '.join(updated_fields)}")
    except Exception as e_db_update:
        db.session.rollback()
        current_app.logger.error(f"Error update user {normalized_phone}: {str(e_db_update)}", exc_info=True)
        click.echo(click.style(f"ERROR: Gagal memperbarui data pengguna: {str(e_db_update)}", fg='red'))


# --- Perintah list ---
@user_cli_bp.command('list', help="Menampilkan daftar pengguna dengan filter.")
@click.option('--status', '-s', type=click.Choice([s.value for s in ApprovalStatus] if MODELS_AVAILABLE and ApprovalStatus else [], case_sensitive=False), default=None, help="Filter status approval.")
@click.option('--role', '-r', type=click.Choice([r.value for r in UserRole] if MODELS_AVAILABLE and UserRole else [], case_sensitive=False), default=None, help="Filter role.")
@click.option('--active', '-ac', type=click.BOOL, default=None, help="Filter status aktif (True/False).")
@click.option('--limit', '-l', type=int, default=20, show_default=True, help="Jumlah maksimal pengguna.")
@click.option('--search', '-q', type=str, default=None, help="Cari nama atau nomor telepon.")
@with_appcontext
def list_users(status, role, active, limit, search):
    if not MODELS_AVAILABLE or not hasattr(db, 'session') or not User or not ApprovalStatus or not UserRole:
        click.echo(click.style("ERROR: Model User, ApprovalStatus, UserRole atau database session tidak dapat dimuat.", fg='red')); return

    query = db.select(User)
    if status:
        try: query = query.filter(User.approval_status == ApprovalStatus(status.upper()))
        except ValueError: click.echo(click.style(f"ERROR: Status '{status}' tidak valid.", fg='red')); return
    if role:
        try: query = query.filter(User.role == UserRole(role.upper()))
        except ValueError: click.echo(click.style(f"ERROR: Role '{role}' tidak valid.", fg='red')); return
    if active is not None:
        query = query.filter(User.is_active == active)
    if search:
        search_term_general = f"%{search}%"
        
        normalized_search_phone_e164 = None
        try:
            temp_normalized = normalize_to_e164(search)
            if temp_normalized.startswith('+62'):
                normalized_search_phone_e164 = temp_normalized
        except ValueError:
            pass

        search_conditions = [User.full_name.ilike(search_term_general)]
        
        search_conditions.append(User.phone_number.ilike(search_term_general))
        if normalized_search_phone_e164:
            search_conditions.append(User.phone_number.ilike(f"%{normalized_search_phone_e164}%"))
        
        phone_variations_for_search = get_phone_number_variations(search)
        for variation in phone_variations_for_search:
            search_conditions.append(User.phone_number.ilike(f"%{variation}%"))

        query = query.filter(db.or_(*search_conditions))

    users_to_list = db.session.execute(query.order_by(User.created_at.desc()).limit(limit)).scalars().all()

    if not users_to_list:
        click.echo("Tidak ada pengguna ditemukan."); return

    click.echo(click.style("Daftar Pengguna:", fg='cyan', bold=True))
    header = "{:<37} {:<15} {:<20} {:<7} {:<7} {:<18} {:<13} {:<7} {:<15} {:<15} {:<10} {:<18}".format(
        "ID Pengguna", "No. Telepon", "Nama", "Blok", "Kamar", "Status Approval", "Role", "Aktif?", "Device Brand", "Device Model", "Unlimited?", "Tgl Kadaluarsa"
    )
    line_length_exact = len("ID Pengguna                         No. Telepon     Nama                   Blok    Kamar  Status Approval    Role         Aktif? Device Brand    Device Model    Unlimited? Tgl Kadaluarsa  ")
    click.echo(click.style(header, fg='yellow'))
    click.echo(click.style("-" * line_length_exact, fg='cyan'))

    for user_obj in users_to_list:
        blok_display = user_obj.blok if user_obj.blok else "N/A"
        kamar_display = user_obj.kamar if user_obj.kamar else "N/A"
        
        if kamar_display.startswith("Kamar_") and kamar_display[6:].isdigit():
            kamar_display = kamar_display[6:]
        
        is_unlimited_display = "Ya" if user_obj.is_unlimited_user else "Tidak"
        expiry_date_display = user_obj.quota_expiry_date.strftime('%Y-%m-%d') if user_obj.quota_expiry_date else "N/A"

        user_line = "{:<37} {:<15} {:<20} {:<7} {:<7} {:<18} {:<13} {:<7} {:<15} {:<15} {:<10} {:<18}".format(
            str(user_obj.id),
            user_obj.phone_number,
            (user_obj.full_name or "")[:18] + ('..' if len(user_obj.full_name or "") > 18 else ''),
            blok_display[:5] + ('..' if len(blok_display) > 5 else ''),
            kamar_display[:5] + ('..' if len(kamar_display) > 5 else ''),
            user_obj.approval_status.value if isinstance(user_obj.approval_status, enum.Enum) else str(user_obj.approval_status),
            user_obj.role.value if isinstance(user_obj.role, enum.Enum) else str(user_obj.role),
            "Ya" if user_obj.is_active else "Tidak",
            (user_obj.device_brand or "N/A")[:13] + ('..' if len(user_obj.device_brand or "") > 13 else ''),
            (user_obj.device_model or "N/A")[:13] + ('..' if len(user_obj.device_model or "") > 13 else ''),
            is_unlimited_display,
            expiry_date_display
        )
        click.echo(user_line)
    click.echo(click.style("-" * line_length_exact, fg='cyan'))
    click.echo(f"Menampilkan {len(users_to_list)} pengguna (limit: {limit}).")

# --- Perintah approve ---
@user_cli_bp.command('approve', help="Menyetujui pengguna PENDING atau sinkronisasi ulang pengguna APPROVED ke Mikrotik.")
@click.argument('phone_number', type=str)
@click.option('--admin-id', '-a', type=str, default=None, help="UUID Admin yang melakukan aksi (opsional, untuk pencatatan).")
@click.option('--force-sync', '-fs', is_flag=True, help="Paksa sinkronisasi (generate password Mikrotik baru & update ke Mikrotik) meskipun pengguna sudah APPROVED.")
@with_appcontext
def approve_user(phone_number, admin_id, force_sync):
    if not MODELS_AVAILABLE or not hasattr(db, 'session') or not User or not ApprovalStatus or not UserRole:
        click.echo(click.style("ERROR: Model User/ApprovalStatus/UserRole atau database session tidak dapat dimuat.", fg='red'))
        return
    if not MIKROTIK_CLIENT_AVAILABLE or not WHATSAPP_AVAILABLE or not NOTIFICATION_SERVICE_AVAILABLE:
        current_app.logger.error("Klien Mikrotik, WhatsApp, atau Notification Service tidak termuat. Perintah tidak bisa dijalankan.")
        click.echo(click.style("ERROR: Klien Mikrotik, WhatsApp, atau Notification Service tidak termuat. Perintah tidak bisa dijalankan.", fg='red'))
        return

    admin_performing_action = None
    admin_id_for_log = "System/CLI"
    if admin_id:
        try:
            admin_uuid = uuid.UUID(admin_id)
            fetched_admin = db.session.get(User, admin_uuid)
            if fetched_admin and fetched_admin.is_admin_role:
                admin_performing_action = fetched_admin
                admin_id_for_log = str(admin_performing_action.id)
            elif fetched_admin:
                current_app.logger.warning(f"Pengguna '{fetched_admin.full_name}' bukan Admin (Role: {fetched_admin.role.value}).")
                click.echo(click.style(f"WARNING: Pengguna '{fetched_admin.full_name}' bukan Admin (Role: {fetched_admin.role.value}).", fg='yellow'))
            else:
                current_app.logger.warning(f"Admin ID '{admin_id}' tidak ditemukan.")
                click.echo(click.style(f"WARNING: Admin ID '{admin_id}' tidak ditemukan.", fg='yellow'))
        except (ValueError, AttributeError) as e:
            current_app.logger.warning(f"Tidak dapat verifikasi role admin untuk admin_id '{admin_id}': {e}", exc_info=True)
            click.echo(click.style(f"WARNING: Tidak dapat verifikasi role admin untuk admin_id '{admin_id}'.", fg='yellow'))

    try:
        normalized_phone = normalize_phone_for_cli(phone_number)
    except click.BadParameter as e:
        click.echo(click.style(f"ERROR: {str(e.message)}", fg='red')); return

    user_to_process = db.session.execute(db.select(User).filter_by(phone_number=normalized_phone)).scalar_one_or_none()

    if not user_to_process:
        click.echo(click.style(f"ERROR: Pengguna '{normalized_phone}' tidak ditemukan.", fg='red')); return

    is_initial_approval = (user_to_process.approval_status == ApprovalStatus.PENDING_APPROVAL)

    if not is_initial_approval and user_to_process.approval_status == ApprovalStatus.REJECTED:
        click.echo(click.style(f"ERROR: Pengguna '{user_to_process.full_name}' berstatus REJECTED.", fg='red')); return

    if not is_initial_approval and user_to_process.approval_status == ApprovalStatus.APPROVED and not force_sync:
        click.echo(click.style(f"INFO: Pengguna '{user_to_process.full_name}' sudah {user_to_process.approval_status.value}.", fg='yellow'))
        click.echo(click.style("Gunakan --force-sync untuk membuat password baru dan sinkronisasi ulang.", fg='yellow'))
        return

    action_description = "Penyetujuan" if is_initial_approval else "Sinkronisasi Ulang (Force Sync)"
    click.echo(click.style(f"Memulai {action_description} untuk '{user_to_process.full_name}'...", fg='cyan'))

    password_untuk_mikrotik = ""
    password_generated_for_this_action = False

    if force_sync:
        password_untuk_mikrotik = generate_random_password(length=8, type='numeric')
        password_generated_for_this_action = True
        click.echo(click.style(f"  [INFO] Force Sync: Password Mikrotik baru '{password_untuk_mikrotik}' akan dibuat.", fg='blue'))
    elif is_initial_approval:
        if user_to_process.mikrotik_password and len(user_to_process.mikrotik_password) >= 6 and user_to_process.mikrotik_password.isdigit():
            password_untuk_mikrotik = user_to_process.mikrotik_password
            click.echo(click.style(f"  [INFO] Initial Approval: Menggunakan password yang sudah ada: '{password_untuk_mikrotik}'.", fg='blue'))
        else:
            password_untuk_mikrotik = generate_random_password(length=8, type='numeric')
            password_generated_for_this_action = True
            click.echo(click.style(f"  [INFO] Initial Approval: Password Mikrotik baru '{password_untuk_mikrotik}' dibuat (sebelumnya kosong/tidak valid).", fg='blue'))
    else:
        if user_to_process.mikrotik_password and len(user_to_process.mikrotik_password) >= 6 and user_to_process.mikrotik_password.isdigit():
            password_untuk_mikrotik = user_to_process.mikrotik_password
        else:
            password_untuk_mikrotik = generate_random_password(length=8, type='numeric')
            password_generated_for_this_action = True
        click.echo(click.style(f"  [INFO] Menggunakan/membuat password: '{password_untuk_mikrotik}'.", fg='blue'))

    try:
        if is_initial_approval:
            if user_to_process.role == UserRole.USER:
                if not user_to_process.blok:
                    current_app.logger.error(f"Pengguna '{user_to_process.full_name}' (role USER) tidak memiliki data Blok. Penyetujuan dibatalkan.")
                    click.echo(click.style(f"  [DB] ERROR: Pengguna '{user_to_process.full_name}' (role USER) tidak memiliki data Blok. Penyetujuan dibatalkan.", fg='red'))
                    return
                if not user_to_process.kamar:
                    current_app.logger.error(f"Pengguna '{user_to_process.full_name}' (role USER) tidak memiliki data Kamar. Penyetujuan dibatalkan.")
                    click.echo(click.style(f"  [DB] ERROR: Pengguna '{user_to_process.full_name}' (role USER) tidak memiliki data Kamar. Penyetujuan dibatalkan.", fg='red'))
                    return
            user_to_process.approval_status = ApprovalStatus.APPROVED
            user_to_process.is_active = True
            user_to_process.approved_at = datetime.now(dt_timezone.utc)
            if admin_performing_action: user_to_process.approved_by_id = admin_performing_action.id
            user_to_process.rejected_at = None
            user_to_process.rejected_by_id = None
            user_to_process.total_quota_purchased_mb = 0
            user_to_process.total_quota_used_mb = 0
            user_to_process.quota_expiry_date = None
            user_to_process.is_unlimited_user = False
        
        user_to_process.mikrotik_password = password_untuk_mikrotik
        user_to_process.updated_at = datetime.now(dt_timezone.utc)

        db.session.commit()
        db.session.refresh(user_to_process)
        admin_log_info_db = f" oleh Admin ID '{admin_id_for_log}'" if admin_performing_action else " (System/CLI)" 
        password_log_info_db = f" Password Mikrotik diupdate ke '{password_untuk_mikrotik}'." if password_generated_for_this_action or force_sync else " Password Mikrotik tidak berubah."
        current_app.logger.info(f"Status pengguna diperbarui{admin_log_info_db}.{password_log_info_db}")
        click.echo(click.style(f"  [DB] SUKSES: Status pengguna diperbarui{admin_log_info_db}.{password_log_info_db}", fg='green'))
    except Exception as e_db_approve:
        db.session.rollback()
        current_app.logger.error(f"Error DB {action_description} untuk {normalized_phone}: {str(e_db_approve)}", exc_info=True)
        click.echo(click.style(f"  [DB] ERROR: {str(e_db_approve)}", fg='red'))
        return

    mikrotik_update_success = False
    mikrotik_message_detail = "Klien Mikrotik tidak tersedia."
    if MIKROTIK_CLIENT_AVAILABLE:
        mikrotik_profile_to_use = current_app.config.get('MIKROTIK_DEFAULT_PROFILE', 'default')
        mikrotik_username_mt = format_to_local_phone(user_to_process.phone_number)

        if not mikrotik_username_mt:
            current_app.logger.warning(f"Tidak dapat konversi nomor ke username Mikrotik. Update Mikrotik dilewati untuk {user_to_process.id}.")
            click.echo(click.style(f"  [Mikrotik] WARNING: Tidak dapat konversi nomor ke username Mikrotik. Update Mikrotik dilewati.", fg='yellow'))
            mikrotik_message_detail = "Format username Mikrotik tidak valid."
        else:
            try:
                with get_mikrotik_connection() as mikrotik_api_conn:
                    if mikrotik_api_conn:
                        current_app.logger.info(f"Mencoba update Mikrotik untuk '{mikrotik_username_mt}' (ID DB: {user_to_process.id}) profile: {mikrotik_profile_to_use} dengan password '{password_untuk_mikrotik}'")
                        click.echo(f"  [Mikrotik] INFO: Mencoba update Mikrotik untuk '{mikrotik_username_mt}' (ID DB: {user_to_process.id}) profile: {mikrotik_profile_to_use} dengan password '{password_untuk_mikrotik}'")
                        
                        kamar_val_for_comment = user_to_process.kamar if user_to_process.kamar else 'N/A'
                        blok_val_for_comment = user_to_process.blok if user_to_process.blok else 'N/A'
                        comment_for_mikrotik = f"{user_to_process.full_name or 'N/A'} | Blk {blok_val_for_comment} Km {kamar_val_for_comment} | ID:{str(user_to_process.id)[:8]}"

                        mikrotik_kwargs = {
                            "api_connection": mikrotik_api_conn,
                            "user_mikrotik_username": mikrotik_username_mt,
                            "mikrotik_profile_name": mikrotik_profile_to_use,
                            "hotspot_password": password_untuk_mikrotik,
                            "comment": comment_for_mikrotik
                        }

                        if current_app.config.get('MIKROTIK_SEND_LIMIT_BYTES_TOTAL', False):
                            limit_bytes_total_val = int(max(0, user_to_process.total_quota_purchased_mb - (user_to_process.total_quota_used_mb or 0)) * 1024 * 1024)
                            if limit_bytes_total_val > 0:
                                mikrotik_kwargs['limit_bytes_total'] = limit_bytes_total_val
                        else:
                            mikrotik_kwargs['limit_bytes_total'] = 0

                        if current_app.config.get('MIKROTIK_SEND_SESSION_TIMEOUT', False):
                            session_timeout_seconds_val = None
                            if user_to_process.quota_expiry_date:
                                time_remaining = (user_to_process.quota_expiry_date - datetime.now(dt_timezone.utc)).total_seconds()
                                session_timeout_seconds_val = int(time_remaining) if time_remaining > 0 else 0
                            
                            if session_timeout_seconds_val is not None:
                                mikrotik_kwargs['session_timeout_seconds'] = session_timeout_seconds_val
                        else:
                            mikrotik_kwargs['session_timeout_seconds'] = 0

                        mikrotik_kwargs['force_update_profile'] = True

                        mikrotik_update_success, mikrotik_message_detail = activate_or_update_hotspot_user(**mikrotik_kwargs)

                        if mikrotik_update_success:
                            current_app.logger.info(f"Mikrotik update SUKSES untuk {mikrotik_username_mt}: {mikrotik_message_detail}")
                            click.echo(click.style(f"  [Mikrotik] SUKSES: {mikrotik_message_detail}", fg='green'))
                        else:
                            current_app.logger.error(f"Mikrotik update GAGAL untuk {mikrotik_username_mt}: {mikrotik_message_detail}")
                            click.echo(click.style(f"  [Mikrotik] ERROR: {mikrotik_message_detail}", fg='red'))
                    else:
                        current_app.logger.error("Gagal koneksi Mikrotik.")
                        click.echo(click.style("  [Mikrotik] ERROR: Gagal koneksi Mikrotik.", fg='red'))
                        mikrotik_message_detail = "Koneksi Mikrotik gagal."
            except Exception as e_mt_approve:
                current_app.logger.error(f"Exception Mikrotik untuk {mikrotik_username_mt}: {str(e_mt_approve)}", exc_info=True)
                click.echo(click.style(f"  [Mikrotik] ERROR Exception: {str(e_mt_approve)}", fg='red'))
                mikrotik_message_detail = str(e_mt_approve)

    whatsapp_notification_success = False
    if WHATSAPP_AVAILABLE and NOTIFICATION_SERVICE_AVAILABLE and user_to_process.phone_number and settings_service.get_setting('ENABLE_WHATSAPP_NOTIFICATIONS', 'False') == 'True' and (is_initial_approval or (force_sync and password_generated_for_this_action)):
        try:
            username_display_for_wa = format_to_local_phone(user_to_process.phone_number) or user_to_process.phone_number
            
            context = {
                "full_name": user_to_process.full_name,
                "username": username_display_for_wa,
                "password": password_untuk_mikrotik
            }
            
            message_body_wa = ""
            if is_initial_approval:
                message_body_wa = get_notification_message("user_approve_success", context)
            elif force_sync and password_generated_for_this_action:
                message_body_wa = get_notification_message("user_hotspot_password_reset_by_user", context)
                if not message_body_wa or "Peringatan: Template" in message_body_wa:
                     message_body_wa = (f"Hai {user_to_process.full_name},\n\nAkun hotspot Anda telah disinkronkan ulang.\n"
                                       f"Username: {username_display_for_wa}\nPassword Baru: {password_untuk_mikrotik}\n\nTerima kasih.")

            if message_body_wa:
                whatsapp_notification_success = send_whatsapp_message(user_to_process.phone_number, message_body_wa)
                if whatsapp_notification_success:
                    current_app.logger.info(f"Notifikasi & password dikirim ke {user_to_process.phone_number}.")
                    click.echo(click.style(f"  [WhatsApp] SUKSES: Notifikasi & password dikirim ke {user_to_process.phone_number}.", fg='green'))
                else:
                    current_app.logger.error(f"Gagal kirim notifikasi ke {user_to_process.phone_number}.")
                    click.echo(click.style(f"  [WhatsApp] ERROR: Gagal kirim notifikasi ke {user_to_process.phone_number}.", fg='red'))
        except Exception as e_wa_approve:
            current_app.logger.error(f"Exception WA untuk {user_to_process.phone_number}: {str(e_wa_approve)}", exc_info=True)
            click.echo(click.style(f"  [WhatsApp] ERROR Exception: {str(e_wa_approve)}", fg='red'))
    elif not user_to_process.phone_number:
        current_app.logger.warning("Tidak ada nomor telepon, notifikasi dilewati.")
        click.echo(click.style("  [WhatsApp] INFO: Tidak ada nomor telepon, notifikasi dilewati.", fg='yellow'))
    elif not WHATSAPP_AVAILABLE:
        current_app.logger.warning("Klien WhatsApp tidak tersedia, notifikasi dilewati.")
        click.echo(click.style("  [WhatsApp] INFO: Klien WhatsApp tidak tersedia, notifikasi dilewati.", fg='yellow'))
        if is_initial_approval or (force_sync and password_generated_for_this_action):
            click.echo(click.style(f"    -> Info Admin: Password Mikrotik {user_to_process.full_name}: {password_untuk_mikrotik}", fg='blue'))
    elif not NOTIFICATION_SERVICE_AVAILABLE:
        current_app.logger.warning("Notification Service tidak tersedia, notifikasi dilewati.")
        click.echo(click.style("  [WhatsApp] INFO: Notification Service tidak tersedia, notifikasi dilewati.", fg='yellow'))
    elif settings_service.get_setting('ENABLE_WHATSAPP_NOTIFICATIONS', 'False') != 'True':
        current_app.logger.info("Notifikasi WhatsApp dinonaktifkan di pengaturan.")
        click.echo(click.style("  [WhatsApp] INFO: Notifikasi WhatsApp dinonaktifkan di pengaturan, notifikasi dilewati.", fg='yellow'))


    click.echo(click.style(f"\nProses {action_description} untuk '{user_to_process.full_name}' SELESAI.", bold=True))
    if not mikrotik_update_success and MIKROTIK_CLIENT_AVAILABLE and (is_initial_approval or force_sync):
        click.echo(click.style(f"  -> PENTING: Update Mikrotik GAGAL. Detail: {mikrotik_message_detail}", fg='yellow'))
        click.echo(click.style(f"     Password Mikrotik yang seharusnya digunakan: {password_untuk_mikrotik}. Perlu tindakan manual.", fg='yellow'))
    if not whatsapp_notification_success and WHATSAPP_AVAILABLE and user_to_process.phone_number and (is_initial_approval or (force_sync and password_generated_for_this_action)):
        click.echo(click.style(f"  -> PENTING: Notifikasi WhatsApp GAGAL. Pastikan pengguna tahu password baru: {password_untuk_mikrotik}", fg='yellow'))
        
# --- Perintah reject ---
@user_cli_bp.command('reject', help="Menolak & MENGHAPUS pendaftaran pengguna (khusus status PENDING).")
@click.argument('phone_number', type=str)
@click.option('--admin-id', '-a', type=str, default=None, help="UUID Admin yang melakukan penolakan (opsional, untuk log).")
@click.option('--reason', '-msg', type=str, default="Pendaftaran Anda tidak dapat kami setujui saat ini.", help="Pesan alasan penolakan untuk dikirim ke pengguna.")
@click.option('--force', '-f', is_flag=True, help="Lewati konfirmasi penghapusan setelah penolakan.")
@with_appcontext
def reject_user(phone_number, admin_id, reason, force):
    if not MODELS_AVAILABLE or not hasattr(db, 'session') or not User or not ApprovalStatus:
        click.echo(click.style("ERROR: Model User/ApprovalStatus atau database session tidak dapat dimuat.", fg='red')); return
    if not MIKROTIK_CLIENT_AVAILABLE or not NOTIFICATION_SERVICE_AVAILABLE:
        current_app.logger.error("Klien Mikrotik atau Notification Service tidak termuat. Perintah tidak bisa dijalankan.")
        click.echo(click.style("ERROR: Klien Mikrotik atau Notification Service tidak termuat. Perintah tidak bisa dijalankan.", fg='red'))
        return


    admin_performing_rejection = None; admin_id_for_log = "Tidak Diketahui"
    if admin_id:
        try:
            admin_uuid = uuid.UUID(admin_id)
            fetched_admin = db.session.get(User, admin_uuid)
            if fetched_admin and fetched_admin.is_admin_role:
                admin_performing_rejection = fetched_admin
                admin_id_for_log = str(admin_performing_rejection.id)
            elif fetched_admin:
                current_app.logger.warning(f"Pengguna '{fetched_admin.full_name}' bukan Admin (Role: {fetched_admin.role.value}).")
                click.echo(click.style(f"WARNING: Pengguna '{fetched_admin.full_name}' bukan Admin (Role: {fetched_admin.role.value}).", fg='yellow'))
            else:
                current_app.logger.warning(f"Admin ID '{admin_id}' tidak ditemukan.")
                click.echo(click.style(f"WARNING: Admin ID '{admin_id}' tidak ditemukan.", fg='yellow'))
        except (ValueError, AttributeError) as e:
            current_app.logger.warning(f"Tidak dapat verifikasi role admin untuk admin_id '{admin_id}': {e}", exc_info=True)
            click.echo(click.style(f"WARNING: Tidak dapat verifikasi role admin untuk admin_id '{admin_id}'.", fg='yellow'))

    try: normalized_phone = normalize_phone_for_cli(phone_number)
    except click.BadParameter as e: click.echo(click.style(f"ERROR: {str(e.message)}", fg='red')); return

    user_to_reject = db.session.execute(db.select(User).filter_by(phone_number=normalized_phone)).scalar_one_or_none()

    if not user_to_reject: click.echo(click.style(f"ERROR: Pengguna '{normalized_phone}' tidak ditemukan.", fg='red')); return

    if user_to_reject.approval_status != ApprovalStatus.PENDING_APPROVAL:
        current_status_val = user_to_reject.approval_status.value if isinstance(user_to_reject.approval_status, enum.Enum) else str(user_to_reject.approval_status)
        click.echo(click.style(f"INFO: Pengguna '{user_to_reject.full_name}' tidak PENDING (Status: {current_status_val}).", fg='yellow'))
        click.echo(click.style("Gunakan 'delete' untuk status lain.", fg='yellow')); return

    if not force:
        click.echo(click.style(f"\nDETAIL PENGGUNA AKAN DITOLAK & DIHAPUS:", fg='yellow', bold=True))
        click.echo(f"  Nama: {user_to_reject.full_name}, Telp: {user_to_reject.phone_number}, Status: {user_to_reject.approval_status.value}")
        click.confirm(click.style("\nAnda YAKIN MENOLAK dan MENGHAPUS PERMANEN pendaftaran ini?", fg='red', bold=True), abort=True)

    user_full_name_for_log = user_to_reject.full_name; user_id_for_log = str(user_to_reject.id); user_phone_for_notif = user_to_reject.phone_number

    mikrotik_status_action = "Tidak dicoba."
    mikrotik_username_target = format_to_local_phone(user_phone_for_notif)
    if MIKROTIK_CLIENT_AVAILABLE and mikrotik_username_target and user_to_reject.mikrotik_password:
        try:
            with get_mikrotik_connection() as mikrotik_api_conn:
                if mikrotik_api_conn:
                    expired_profile_name = current_app.config.get('MIKROTIK_EXPIRED_PROFILE', 'expired')
                    success_profile, msg_profile = set_hotspot_user_profile(mikrotik_api_conn, mikrotik_username_target, expired_profile_name)
                    mikrotik_status_action = f"Mikrotik: {'Berhasil' if success_profile else 'Gagal'} pindah ke profil '{expired_profile_name}' ({msg_profile})."
                    if success_profile:
                        current_app.logger.info(f"Mikrotik: {mikrotik_status_action}")
                        click.echo(click.style(f"  [Mikrotik] SUKSES: {mikrotik_status_action}", fg='green'))
                    else:
                        current_app.logger.error(f"Mikrotik: {mikrotik_status_action}")
                        click.echo(click.style(f"  [Mikrotik] ERROR: {mikrotik_status_action}", fg='red'))
                else:
                    current_app.logger.error("Gagal koneksi Mikrotik.")
                    click.echo(click.style("  [Mikrotik] ERROR: Gagal koneksi Mikrotik.", fg='red'))
                    mikrotik_status_action = "Koneksi Mikrotik gagal."
        except Exception as e_mt:
            current_app.logger.error(f"Exception Mikrotik pindah profil untuk {user_to_reject.id} saat penolakan: {str(e_mt)}", exc_info=True)
            click.echo(click.style(f"  [Mikrotik] ERROR Exception: {str(e_mt)}", fg='red'))
            mikrotik_status_action = str(e_mt)

    notification_sent_reject = False
    if WHATSAPP_AVAILABLE and NOTIFICATION_SERVICE_AVAILABLE and user_phone_for_notif and settings_service.get_setting('ENABLE_WHATSAPP_NOTIFICATIONS', 'False') == 'True':
        try:
            phone_display_local = format_to_local_phone(user_phone_for_notif) or user_phone_for_notif
            context = {"full_name": user_full_name_for_log, "phone_number": phone_display_local, "reason": reason}
            message_body_reject = get_notification_message("user_reject_notification", context)
            
            if message_body_reject:
                whatsapp_notification_sent = send_whatsapp_message(user_phone_for_notif, message_body_reject)
                if whatsapp_notification_sent:
                    current_app.logger.info(f"Notifikasi penolakan dikirim ke {user_phone_for_notif}.")
                    click.echo(click.style(f"  [WhatsApp] INFO: Notifikasi penolakan dikirim ke {user_phone_for_notif}.", fg='blue'))
                else:
                    current_app.logger.error(f"Gagal kirim notifikasi penolakan ke {user_phone_for_notif}.")
                    click.echo(click.style(f"  [WhatsApp] ERROR: Gagal kirim notifikasi penolakan ke {user_phone_for_notif}.", fg='red'))
        except Exception as e_wa_reject_cli:
            current_app.logger.error(f"Exception WA penolakan ke {user_phone_for_notif}: {str(e_wa_reject_cli)}", exc_info=True)
            click.echo(click.style(f"  [WhatsApp] ERROR: Exception: {str(e_wa_reject_cli)}", fg='red'))
    elif not user_phone_for_notif:
        current_app.logger.warning("Tidak ada nomor telepon, notifikasi dilewati.")
        click.echo(click.style("  [WhatsApp] INFO: Tidak ada nomor telepon, notifikasi dilewati.", fg='yellow'))
    elif not WHATSAPP_AVAILABLE:
        current_app.logger.warning("Klien WhatsApp tidak tersedia, notifikasi dilewati.")
        click.echo(click.style("  [WhatsApp] INFO: Klien WhatsApp tidak tersedia, notifikasi dilewati.", fg='yellow'))
    elif not NOTIFICATION_SERVICE_AVAILABLE:
        current_app.logger.warning("Notification Service tidak tersedia, notifikasi dilewati.")
        click.echo(click.style("  [WhatsApp] INFO: Notification Service tidak tersedia, notifikasi dilewati.", fg='yellow'))
    elif settings_service.get_setting('ENABLE_WHATSAPP_NOTIFICATIONS', 'False') != 'True':
        current_app.logger.info("Notifikasi WhatsApp dinonaktifkan di pengaturan.")
        click.echo(click.style("  [WhatsApp] INFO: Notifikasi WhatsApp dinonaktifkan di pengaturan, notifikasi dilewati.", fg='yellow'))


    try:
        db.session.delete(user_to_reject)
        db.session.commit()
        admin_log_info = f" oleh Admin ID '{admin_id_for_log}'" if admin_performing_rejection else " System"
        current_app.logger.info(f"User REJECTED and DELETED: ID={user_id_for_log}, Phone={user_phone_for_notif}, Name='{user_full_name_for_log}'. Mikrotik: attempted={mikrotik_status_action}. Admin ID: {admin_id_for_log if admin_performing_rejection else 'System'}.")
        click.echo(click.style(f"\nSUKSES: Pengguna '{user_full_name_for_log}' ({user_phone_for_notif}) DITOLAK & DIHAPUS dari database.", fg='green', bold=True))
        if not notification_sent_reject and WHATSAPP_AVAILABLE and user_phone_for_notif:
            click.echo(click.style("  -> PERINGATAN: Notifikasi WA penolakan GAGAL terkirim.", fg='yellow'))
        click.echo(f"  Status Mikrotik: {mikrotik_status_action}")
    except Exception as e_db_reject:
        db.session.rollback()
        current_app.logger.error(f"Error reject/delete user {user_phone_for_notif} from DB: {str(e_db_reject)}", exc_info=True)
        click.echo(click.style(f"\nERROR DB: Gagal menolak/menghapus pengguna: {str(e_db_reject)}", fg='red'))


# --- Perintah delete ---
@user_cli_bp.command('delete', help="Menghapus pengguna (PERMANEN) dari DB & Mikrotik (jika ada).")
@click.argument('phone_number', type=str)
@click.option('--admin-id', '-a', type=str, default=None, help="UUID Admin yang melakukan aksi (opsional, untuk pencatatan).")
@click.option('--force', '-f', is_flag=True, help="Lewati konfirmasi penghapusan.")
@with_appcontext
def delete_user(phone_number, admin_id, force):
    if not MODELS_AVAILABLE or not hasattr(db, 'session') or not User:
        click.echo(click.style("ERROR: Model User atau database session tidak dapat dimuat.", fg='red')); return
    if not MIKROTIK_CLIENT_AVAILABLE:
        current_app.logger.warning("Klien Mikrotik tidak termuat. Operasi penghapusan Mikrotik akan dilewati.")
        click.echo(click.style("ERROR: Klien Mikrotik tidak termuat. Perintah tidak bisa dijalankan.", fg='red'))
        click.echo(click.style("INFO: Operasi penghapusan Mikrotik akan dilewati.", fg='yellow'))


    admin_performing_deletion = None; admin_id_for_log_del = "Tidak Diketahui"
    if admin_id:
        try:
            admin_uuid_del = uuid.UUID(admin_id)
            fetched_admin = db.session.get(User, admin_uuid_del)
            if fetched_admin and fetched_admin.is_admin_role:
                admin_performing_deletion = fetched_admin
                admin_id_for_log_del = str(admin_performing_deletion.id)
            elif fetched_admin:
                current_app.logger.warning(f"Pengguna '{fetched_admin.full_name}' bukan Admin (Role: {fetched_admin.role.value}).")
                click.echo(click.style(f"WARNING: Pengguna '{fetched_admin.full_name}' bukan Admin (Role: {fetched_admin.role.value}).", fg='yellow'))
            else:
                current_app.logger.warning(f"Admin ID '{admin_id}' tidak ditemukan.")
                click.echo(click.style(f"WARNING: Admin ID '{admin_id}' tidak ditemukan.", fg='yellow'))
        except (ValueError, AttributeError) as e:
            current_app.logger.warning(f"Tidak dapat verifikasi role admin untuk admin_id '{admin_id}': {e}", exc_info=True)
            click.echo(click.style(f"WARNING: Tidak dapat verifikasi role admin untuk admin_id '{admin_id}'.", fg='yellow'))


    try: normalized_phone = normalize_phone_for_cli(phone_number)
    except click.BadParameter as e: click.echo(click.style(f"ERROR: {str(e.message)}", fg='red')); return

    user_to_delete = db.session.execute(db.select(User).filter_by(phone_number=normalized_phone)).scalar_one_or_none()
    if not user_to_delete: click.echo(click.style(f"ERROR: Pengguna '{normalized_phone}' tidak ditemukan.", fg='red')); return

    if not force:
        click.echo(click.style(f"\nDETAIL PENGGUNA AKAN DIHAPUS PERMANEN:", fg='red', bold=True))
        click.echo(f"  ID: {user_to_delete.id}, Nama: {user_to_delete.full_name}, Telp: {user_to_delete.phone_number}")
        click.echo(f"  Role: {user_to_delete.role.value}, Status: {user_to_delete.approval_status.value}, Aktif: {'Ya' if user_to_delete.is_active else 'Tidak'}")
        click.echo(click.style("\nPERINGATAN PENTING:", fg='yellow', bold=True))
        click.echo(click.style("  - Menghapus dari DATABASE aplikasi.", fg='yellow'))
        click.echo(click.style("  - MENCOBA menghapus dari MIKROTIK (jika akun Mikrotik ada).", fg='yellow'))
        click.confirm(click.style("\nAnda YAKIN MENGHAPUS PERMANEN pengguna ini dari DB dan Mikrotik?", fg='red', underline=True, bold=True), abort=True)

    user_id_log = str(user_to_delete.id); user_phone_log = user_to_delete.phone_number; user_name_log = user_to_delete.full_name
    mikrotik_username_to_delete = format_to_local_phone(user_phone_log)

    mikrotik_deletion_attempted = False; mikrotik_deletion_successful = False; mikrotik_deletion_message = "Klien Mikrotik tidak tersedia/username tidak valid."
    if MIKROTIK_CLIENT_AVAILABLE and mikrotik_username_to_delete:
        if user_to_delete.mikrotik_password:
            current_app.logger.info(f"Mencoba hapus '{mikrotik_username_to_delete}' dari Mikrotik...")
            click.echo(click.style(f"\n  [Mikrotik] INFO: Mencoba hapus '{mikrotik_username_to_delete}' dari Mikrotik...", fg='cyan'))
            mikrotik_deletion_attempted = True; mikrotik_conn_pool_del = None
            try:
                with get_mikrotik_connection() as mikrotik_api_conn:
                    if mikrotik_api_conn:
                        mikrotik_deletion_successful, mikrotik_deletion_message = delete_hotspot_user(mikrotik_api_conn, mikrotik_username_to_delete)
                        if mikrotik_deletion_successful:
                            current_app.logger.info(f"Mikrotik hapus SUKSES: {mikrotik_deletion_message}")
                            click.echo(click.style(f"  [Mikrotik] SUKSES: {mikrotik_deletion_message}", fg='green'))
                        else:
                            current_app.logger.warning(f"Mikrotik hapus GAGAL/tidak ditemukan. Pesan: {mikrotik_deletion_message}")
                            click.echo(click.style(f"  [Mikrotik] WARNING: Gagal hapus/tidak ditemukan. Pesan: {mikrotik_deletion_message}", fg='yellow'))
                    else:
                        current_app.logger.error("Gagal koneksi Mikrotik.")
                        click.echo(click.style("  [Mikrotik] ERROR: Gagal koneksi Mikrotik.", fg='red'))
                        mikrotik_deletion_message = "Koneksi Mikrotik gagal."
            except Exception as e_mt_delete_cli:
                current_app.logger.error(f"Exception hapus user '{mikrotik_username_to_delete}' dari Mikrotik: {str(e_mt_delete_cli)}", exc_info=True)
                click.echo(click.style(f"  [Mikrotik] ERROR: Exception: {str(e_mt_delete_cli)}", fg='red'))
                mikrotik_deletion_message = str(e_mt_delete_cli)
        else:
            mikrotik_deletion_message = "Pengguna tidak memiliki password Mikrotik (tidak aktif di Mikrotik), penghapusan dilewati."
            current_app.logger.info(mikrotik_deletion_message)
            click.echo(click.style(f"\n  [Mikrotik] INFO: {mikrotik_deletion_message}", fg='blue'))
    elif not mikrotik_username_to_delete:
        mikrotik_deletion_message = "Username Mikrotik tidak valid, penghapusan Mikrotik dilewati."
        current_app.logger.info(mikrotik_deletion_message)
        click.echo(click.style(f"\n  [Mikrotik] INFO: {mikrotik_deletion_message}", fg='blue'))


    db_deletion_successful = False
    try:
        db.session.delete(user_to_delete)
        db.session.commit()
        db_deletion_successful = True
        admin_log_info = f" oleh Admin ID '{admin_id_for_log_del}'" if admin_performing_deletion else " System/CLI"
        current_app.logger.info(f"User DELETED from DB: ID={user_id_log}, Phone={user_phone_log}, Name='{user_name_log}'. Mikrotik: attempted={mikrotik_deletion_attempted}, success={mikrotik_deletion_successful} ('{mikrotik_deletion_message}'). Admin ID: {admin_id_for_log_del if admin_performing_deletion else 'System/CLI'}.")
        click.echo(click.style(f"\nSUKSES: Pengguna '{user_name_log}' ({user_phone_log}) DIHAPUS dari database.", fg='green', bold=True))
    except Exception as e_db_delete_cli:
        db.session.rollback()
        current_app.logger.error(f"Error delete user {user_phone_log} from DB: {str(e_db_delete_cli)}", exc_info=True)
        click.echo(click.style(f"\nERROR DB: Gagal menghapus pengguna: {str(e_db_delete_cli)}", fg='red'))

    click.echo(click.style("\nRingkasan Proses Penghapusan:", bold=True))
    if db_deletion_successful: click.echo(click.style("  - Database: BERHASIL dihapus.", fg='green'))
    else: click.echo(click.style("  - Database: GAGAL dihapus.", fg='red'))
    if mikrotik_deletion_attempted:
        if mikrotik_deletion_successful: click.echo(click.style("  - Mikrotik: BERHASIL dihapus/tidak ditemukan.", fg='green'))
        else:
            click.echo(click.style(f"  - Mikrotik: GAGAL/TIDAK DIKONFIRMASI. Pesan: {mikrotik_deletion_message}", fg='yellow'))
            click.echo(click.style("    -> PERIKSA MIKROTIK MANUAL.", fg='yellow', bold=True))
    else: click.echo(click.style(f"  - Mikrotik: TIDAK DICOBA. Alasan: {mikrotik_deletion_message}", fg='blue'))


# --- Perintah set-role ---
@user_cli_bp.command('set-role', help="Mengubah role pengguna yang sudah ada.")
@click.argument('phone_number', type=str)
@click.argument('new_role', metavar='ROLE', type=click.Choice([r.value for r in UserRole] if MODELS_AVAILABLE and UserRole else [], case_sensitive=False))
@click.option('--admin-id', '-a', type=str, default=None, help="UUID Admin yang melakukan aksi (opsional, untuk pencatatan).")
@with_appcontext
def set_user_role(phone_number, new_role, admin_id):
    if not MODELS_AVAILABLE or not hasattr(db, 'session') or not User or not UserRole:
        click.echo(click.style("ERROR: Model User/UserRole atau database session tidak dapat dimuat.", fg='red')); return

    admin_performing_set_role = None; admin_id_for_log_sr = "Tidak Diketahui"
    if admin_id:
        try:
            admin_uuid_sr = uuid.UUID(admin_id)
            fetched_admin = db.session.get(User, admin_uuid_sr)
            if fetched_admin and fetched_admin.is_admin_role:
                admin_performing_set_role = fetched_admin
                admin_id_for_log_sr = str(admin_performing_set_role.id)
            elif fetched_admin:
                current_app.logger.warning(f"Pengguna '{fetched_admin.full_name}' bukan Admin (Role: {fetched_admin.role.value}).")
                click.echo(click.style(f"WARNING: Pengguna '{fetched_admin.full_name}' bukan Admin (Role: {fetched_admin.role.value}).", fg='yellow'))
            else:
                current_app.logger.warning(f"Admin ID '{admin_id}' tidak ditemukan.")
                click.echo(click.style(f"WARNING: Admin ID '{admin_id}' tidak ditemukan.", fg='yellow'))
        except (ValueError, AttributeError) as e:
            current_app.logger.warning(f"Tidak dapat verifikasi role admin untuk admin_id '{admin_id}': {e}", exc_info=True)
            click.echo(click.style(f"WARNING: Tidak dapat verifikasi role admin untuk admin_id '{admin_id}'.", fg='yellow'))

    try:
        normalized_phone = normalize_phone_for_cli(phone_number)
        role_enum_to_set = UserRole(new_role.upper())
    except click.BadParameter as e: click.echo(click.style(f"ERROR: {str(e.message)}", fg='red')); return
    except ValueError: click.echo(click.style(f"ERROR: Role '{new_role}' tidak valid.", fg='red')); return

    user_to_update_role = db.session.execute(db.select(User).filter_by(phone_number=normalized_phone)).scalar_one_or_none()
    if not user_to_update_role: click.echo(click.style(f"ERROR: Pengguna '{normalized_phone}' tidak ditemukan.", fg='red')); return

    old_role_val = user_to_update_role.role.value if isinstance(user_to_update_role.role, enum.Enum) else str(user_to_update_role.role)
    new_role_val = role_enum_to_set.value

    if user_to_update_role.role == role_enum_to_set:
        click.echo(click.style(f"INFO: Pengguna '{user_to_update_role.full_name}' sudah role '{old_role_val}'.", fg='yellow')); return

    if old_role_val != UserRole.USER.value and new_role_val == UserRole.USER.value:
        click.echo(click.style(f"INFO: Downgrade dari {old_role_val} ke {new_role_val}. Memerlukan data Blok & Kamar.", fg='blue'))
        if not user_to_update_role.blok or not user_to_update_role.kamar:
            current_app.logger.error(f"Pengguna '{user_to_update_role.full_name}' (role USER) tidak memiliki data Blok atau Kamar yang wajib. Upgrade/downgrade dibatalkan.")
            click.echo(click.style("ERROR: Pengguna tidak memiliki data Blok atau Kamar yang wajib untuk peran USER. Upgrade/downgrade dibatalkan.", fg='red'))
            click.echo(click.style("Harap update pengguna dengan Blok dan Kamar yang valid terlebih dahulu menggunakan 'flask user update'.", fg='yellow'))
            return

    password_for_notification = None
    portal_password_plain_text = None

    if new_role_val == UserRole.ADMIN.value or new_role_val == UserRole.SUPER_ADMIN.value:
        password_for_notification = generate_random_password(length=6, type='numeric')
        user_to_update_role.password_hash = generate_password_hash_func(password_for_notification)
        portal_password_plain_text = password_for_notification
        click.echo(click.style(f"INFO: Password portal BARU (6 digit angka) telah di-generate untuk peran {new_role_val}. Password lama ditimpa.", fg='blue'))

    elif new_role_val == UserRole.USER.value and old_role_val != UserRole.USER.value:
        password_for_notification = generate_random_password(length=8, type='numeric')
        user_to_update_role.mikrotik_password = password_for_notification
        click.echo(click.style(f"INFO: Password Mikrotik baru digenerate (8 digit angka) untuk {new_role_val}.", fg='blue'))

    user_to_update_role.role = role_enum_to_set
    user_to_update_role.updated_at = datetime.now(dt_timezone.utc)

    try:
        db.session.commit()
        db.session.refresh(user_to_update_role)
        
        admin_log_info = f" oleh Admin ID '{admin_id_for_log_sr}'" if admin_performing_set_role else " (System/CLI)"
        current_app.logger.info(f"User role updated: ID={user_to_update_role.id}, Phone={normalized_phone}, Name='{user_to_update_role.full_name}'. Old: {old_role_val}, New: {new_role_val}. Admin ID: {admin_id_for_log_sr if admin_performing_set_role else 'System/CLI'}.")
        click.echo(click.style(f"SUKSES: Role '{user_to_update_role.full_name}' ({normalized_phone}) diubah dari {old_role_val} ke {new_role_val}.", fg='green'))

        whatsapp_notification_sent = False
        if WHATSAPP_AVAILABLE and NOTIFICATION_SERVICE_AVAILABLE and user_to_update_role.phone_number and settings_service.get_setting('ENABLE_WHATSAPP_NOTIFICATIONS', 'False') == 'True':
            phone_display_local = format_to_local_phone(user_to_update_role.phone_number) or user_to_update_role.phone_number
            message_body_role_change = ""
            context_for_notif = {"full_name": user_to_update_role.full_name, "phone_number": phone_display_local}
            
            if new_role_val == UserRole.USER.value and old_role_val != UserRole.USER.value:
                context_for_notif["username"] = phone_display_local
                context_for_notif["password"] = password_for_notification
                message_body_role_change = get_notification_message("user_downgrade_to_user_with_password", context_for_notif)
                
                if MIKROTIK_CLIENT_AVAILABLE:
                    mikrotik_username_mt = format_to_local_phone(user_to_update_role.phone_number)
                    if mikrotik_username_mt:
                        with get_mikrotik_connection() as api_conn:
                            if api_conn:
                                default_profile = current_app.config.get('MIKROTIK_DEFAULT_PROFILE', 'default')
                                activate_success, mikrotik_msg = activate_or_update_hotspot_user(
                                    api_connection=api_conn,
                                    user_mikrotik_username=mikrotik_username_mt,
                                    mikrotik_profile_name=default_profile,
                                    hotspot_password=user_to_update_role.mikrotik_password,
                                    comment=f"Role downgraded to USER for {user_to_update_role.full_name}",
                                    force_update_profile=True
                                )
                                if activate_success:
                                    current_app.logger.info(f"Akun Mikrotik {user_to_update_role.full_name} disinkronkan untuk peran USER.")
                                    click.echo(click.style(f"INFO: Akun Mikrotik {user_to_update_role.full_name} disinkronkan untuk peran USER.", fg='blue'))
                                else:
                                    current_app.logger.warning(f"Gagal sinkronisasi Mikrotik saat downgrade role: {mikrotik_msg}")
                                    click.echo(click.style(f"WARNING: Gagal sinkronisasi Mikrotik saat downgrade role: {mikrotik_msg}", fg='yellow'))
                            else:
                                current_app.logger.warning("Gagal koneksi Mikrotik saat downgrade role.")
                                click.echo(click.style("WARNING: Gagal koneksi Mikrotik saat downgrade role.", fg='yellow'))
                    else:
                        current_app.logger.warning("Nomor telepon tidak dapat diformat ke username Mikrotik saat downgrade role.")
                        click.echo(click.style("WARNING: Nomor telepon tidak dapat diformat ke username Mikrotik saat downgrade role.", fg='yellow'))

            elif new_role_val != UserRole.USER.value and old_role_val == UserRole.USER.value:
                context_for_notif["password"] = portal_password_plain_text
                message_body_role_change = get_notification_message("user_upgrade_to_admin_with_password", context_for_notif)
                
                if MIKROTIK_CLIENT_AVAILABLE and user_to_update_role.mikrotik_password:
                    mikrotik_username = format_to_local_phone(user_to_update_role.phone_number)
                    if mikrotik_username:
                        with get_mikrotik_connection() as api_conn:
                            if api_conn:
                                delete_success, delete_msg = delete_hotspot_user(api_conn, mikrotik_username)
                                if delete_success:
                                    current_app.logger.info(f"Akun Mikrotik {mikrotik_username} dihapus karena diupgrade ke {new_role_val}.")
                                    click.echo(click.style(f"INFO: Akun Mikrotik {mikrotik_username} dihapus karena diupgrade ke {new_role_val}.", fg='blue'))
                                    user_to_update_role.mikrotik_password = None
                                    db.session.commit()
                                else:
                                    current_app.logger.warning(f"Gagal menghapus akun Mikrotik {mikrotik_username} saat upgrade role: {delete_msg}")
                                    click.echo(click.style(f"WARNING: Gagal menghapus akun Mikrotik {mikrotik_username} saat upgrade role: {delete_msg}", fg='yellow'))
                            else:
                                current_app.logger.warning("Gagal koneksi Mikrotik saat upgrade role.")
                                click.echo(click.style("WARNING: Gagal koneksi Mikrotik saat upgrade role.", fg='yellow'))
                    else:
                        current_app.logger.warning("Nomor telepon tidak dapat diformat ke username Mikrotik saat upgrade role.")
                        click.echo(click.style("WARNING: Nomor telepon tidak dapat diformat ke username Mikrotik saat upgrade role.", fg='yellow'))

            if message_body_role_change:
                whatsapp_notification_sent = send_whatsapp_message(user_to_update_role.phone_number, message_body_role_change)
                if whatsapp_notification_sent:
                    click.echo(click.style(f"INFO: Notifikasi WhatsApp perubahan role dikirim ke {user_to_update_role.phone_number}.", fg='blue'))
                else:
                    click.echo(click.style(f"WARNING: Gagal kirim notifikasi WhatsApp perubahan role ke {user_to_update_role.phone_number}.", fg='yellow'))
        
        if not whatsapp_notification_sent and (WHATSAPP_AVAILABLE and NOTIFICATION_SERVICE_AVAILABLE):
            current_app.logger.info("Notifikasi WhatsApp perubahan role tidak dikirim (fitur notifikasi nonaktif/gagal).")
            click.echo(click.style("INFO: Notifikasi WhatsApp perubahan role tidak dikirim (fitur notifikasi nonaktif/gagal).", fg='yellow'))
        elif not (WHATSAPP_AVAILABLE and NOTIFICATION_SERVICE_AVAILABLE):
             current_app.logger.info("Notifikasi WhatsApp perubahan role tidak dikirim (klien WhatsApp/Notif Service tidak tersedia).")
             click.echo(click.style("INFO: Notifikasi WhatsApp perubahan role tidak dikirim (klien WhatsApp/Notif Service tidak tersedia).", fg='yellow'))
        elif settings_service.get_setting('ENABLE_WHATSAPP_NOTIFICATIONS', 'False') != 'True':
            current_app.logger.info("Notifikasi WhatsApp dinonaktifkan di pengaturan.")
            click.echo(click.style("INFO: Notifikasi WhatsApp dinonaktifkan di pengaturan, notifikasi dilewati.", fg='yellow'))


    except Exception as e_db_set_role:
        db.session.rollback()
        current_app.logger.error(f"Error set-role untuk {normalized_phone}: {str(e_db_set_role)}", exc_info=True)
        click.echo(click.style(f"ERROR: Gagal ubah role: {str(e_db_set_role)}", fg='red'))

@user_cli_bp.command('set-password', help="Mengatur atau mereset password portal untuk pengguna.")
@click.argument('phone_number', type=str)
@click.option('--password', '-p', prompt="Masukkan password baru", hide_input=True, confirmation_prompt=True, help="Password baru untuk pengguna. Akan di-hash sebelum disimpan.")
@with_appcontext
def set_user_password(phone_number, password):
    if not MODELS_AVAILABLE or not hasattr(db, 'session') or not User:
        click.echo(click.style("ERROR: Model User atau database session tidak dapat dimuat.", fg='red'))
        return
    if not generate_password_hash_func:
        click.echo(click.style("ERROR: Fungsi hashing password tidak tersedia.", fg='red'))
        return
        
    if not password or len(password) < 6:
        click.echo(click.style("ERROR: Password minimal 6 karakter.", fg='red'))
        return

    try:
        normalized_phone = normalize_phone_for_cli(phone_number)
    except click.BadParameter as e:
        click.echo(click.style(f"ERROR: {str(e.message)}", fg='red'))
        return

    user_to_update = db.session.execute(db.select(User).filter_by(phone_number=normalized_phone)).scalar_one_or_none()
    
    if not user_to_update:
        click.echo(click.style(f"ERROR: Pengguna dengan nomor '{normalized_phone}' tidak ditemukan.", fg='red'))
        return

    try:
        new_password_hash = generate_password_hash_func(password)
        user_to_update.password_hash = new_password_hash
        user_to_update.updated_at = datetime.now(dt_timezone.utc)
        
        db.session.commit()
        
        click.echo(click.style(f"SUKSES: Password untuk pengguna '{user_to_update.full_name}' ({normalized_phone}) telah berhasil diatur ulang.", fg='green'))
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error setting password for {normalized_phone}: {str(e)}", exc_info=True)
        click.echo(click.style(f"ERROR: Gagal menyimpan password baru ke database: {str(e)}", fg='red'))

# --- Perintah seed-usage ---
@user_cli_bp.command('seed-usage', help="Membuat data dummy kuota & pemakaian harian untuk user.")
@click.argument('phone_number', type=str)
@click.option('--quota-purchased', '-q', type=int, default=10240, show_default=True, help="Total kuota dibeli (MB). Default: 10GB.")
@click.option('--days', '-d', type=int, default=7, show_default=True, help="Jumlah hari ke belakang untuk data pemakaian.")
@click.option('--admin-id', '-a', type=str, default=None, help="UUID Admin yang melakukan aksi (opsional, untuk log).")
@with_appcontext
def seed_user_usage(phone_number, quota_purchased, days, admin_id):
    if not MODELS_AVAILABLE or not hasattr(db, 'session') or not User or not DailyUsageLog:
        click.echo(click.style("ERROR: Model User/DailyUsageLog atau database session tidak dapat dimuat.", fg='red')); return
    try:
        db.session.execute(db.select(DailyUsageLog)).first()
    except Exception:
        click.echo(click.style("ERROR: Model DailyUsageLog tidak terdefinisi dengan benar atau tidak dapat diakses.", fg='red')); return

    if quota_purchased <= 0:
        click.echo(click.style("ERROR: --quota-purchased harus lebih besar dari 0.", fg='red')); return
    if days <= 0:
        click.echo(click.style("ERROR: --days harus lebih besar dari 0.", fg='red')); return

    admin_performing_seed = None; admin_id_for_log_seed = "Tidak Diketahui"
    if admin_id:
        try:
            admin_uuid_seed = uuid.UUID(admin_id)
            fetched_admin = db.session.get(User, admin_uuid_seed)
            if fetched_admin and fetched_admin.is_admin_role:
                admin_performing_seed = fetched_admin
                admin_id_for_log_seed = str(admin_performing_seed.id)
            elif fetched_admin:
                current_app.logger.warning(f"Pengguna '{fetched_admin.full_name}' bukan Admin (Role: {fetched_admin.role.value}).")
                click.echo(click.style(f"WARNING: Pengguna '{fetched_admin.full_name}' bukan Admin (Role: {fetched_admin.role.value}).", fg='yellow'))
            else:
                click.echo(click.style(f"WARNING: Admin ID '{admin_id}' tidak ditemukan.", fg='yellow'))
        except (ValueError, AttributeError) as e:
            current_app.logger.warning(f"Error memproses Admin ID: '{admin_id}': {e}", exc_info=True)
            click.echo(click.style(f"WARNING: Error memproses Admin ID: '{admin_id}'.", fg='yellow'))

    try:
        normalized_phone = normalize_phone_for_cli(phone_number)
    except click.BadParameter as e:
        click.echo(click.style(f"ERROR: {str(e.message)}", fg='red')); return

    user_to_seed = db.session.execute(db.select(User).filter_by(phone_number=normalized_phone)).scalar_one_or_none()

    if not user_to_seed:
        click.echo(click.style(f"ERROR: Pengguna '{normalized_phone}' tidak ditemukan.", fg='red')); return

    click.echo(click.style(f"Memulai pembuatan data dummy untuk '{user_to_seed.full_name}' ({normalized_phone})...", fg='cyan'))
    click.echo(f"  Kuota Dibeli: {quota_purchased} MB")
    click.echo(f"  Periode Data: {days} hari terakhir")

    today = date.today()
    start_date = today - timedelta(days=days - 1)
    new_logs = []
    total_generated_usage_mb = 0.0

    try:
        num_deleted = db.session.execute(
            db.delete(DailyUsageLog).where(
                DailyUsageLog.user_id == user_to_seed.id,
                DailyUsageLog.log_date >= start_date,
                DailyUsageLog.log_date <= today
            )
        ).rowcount
        if num_deleted > 0:
             current_app.logger.info(f"Menghapus {num_deleted} log pemakaian lama dalam rentang tanggal.")
             click.echo(click.style(f"  INFO: Menghapus {num_deleted} log pemakaian lama dalam rentang tanggal.", fg='blue'))
    except Exception as e_del_log:
         current_app.logger.warning(f"Gagal menghapus log lama: {e_del_log}", exc_info=True)
         click.echo(click.style(f"  WARNING: Gagal menghapus log lama: {str(e_del_log)}", fg='yellow'))

    for i in range(days):
        log_date = start_date + timedelta(days=i)
        remaining_quota = quota_purchased - total_generated_usage_mb
        if remaining_quota <= 0:
            daily_usage = 0.0
        else:
            max_reasonable_daily = 1500
            remaining_days = days - i
            avg_remaining_per_day = remaining_quota / remaining_days if remaining_days > 0 else remaining_quota
            upper_bound = min(max_reasonable_daily, avg_remaining_per_day * 1.5)
            daily_usage = random.uniform(0, upper_bound)
            daily_usage = max(0.0, min(daily_usage, remaining_quota))

        daily_usage = round(daily_usage, 2)
        log_entry = DailyUsageLog(user_id=user_to_seed.id, log_date=log_date, usage_mb=daily_usage)
        new_logs.append(log_entry)
        total_generated_usage_mb += daily_usage
        click.echo(f"    -> {log_date}: {daily_usage:.2f} MB")

    total_generated_usage_mb = round(total_generated_usage_mb, 2)

    user_to_seed.total_quota_purchased_mb = quota_purchased
    user_to_seed.total_quota_used_mb = total_generated_usage_mb
    user_to_seed.updated_at = datetime.now(dt_timezone.utc)

    try:
        db.session.add_all(new_logs)
        db.session.commit()
        admin_log_info = f" Admin ID: {admin_id_for_log_seed}" if admin_performing_seed else " Admin ID: System/CLI"
        log_msg_seed = f"User usage seeded: ID={user_to_seed.id}, Phone={normalized_phone}. Purchased={quota_purchased}MB, Used={total_generated_usage_mb:.2f}MB over {days} days. {admin_log_info}."
        current_app.logger.info(log_msg_seed)
        click.echo(click.style(f"\nSUKSES: Data dummy dibuat untuk '{user_to_seed.full_name}'.", fg='green'))
        click.echo(f"  Total Kuota Dibeli : {quota_purchased} MB")
        click.echo(f"  Total Kuota Terpakai: {total_generated_usage_mb:.2f} MB")
        click.echo(f"  Sisa Kuota         : {quota_purchased - total_generated_usage_mb:.2f} MB")
        click.echo(f"  Jumlah Log Harian  : {len(new_logs)} hari")

    except Exception as e_db_seed:
        db.session.rollback()
        current_app.logger.error(f"Error seeding usage for {normalized_phone}: {str(e_db_seed)}", exc_info=True)
        click.echo(click.style(f"\nERROR: Gagal menyimpan data dummy: {str(e_db_seed)}", fg='red'))


# --- Perintah Mikrotik Profile ---
@user_cli_bp.command('add-mikrotik-profile', help="Menambahkan profil Mikrotik Hotspot baru.")
@click.option('--name', required=True, prompt="Nama Profil Mikrotik", help="Nama unik untuk profil Mikrotik.")
@click.option('--rate-limit', default=None, help="Batas kecepatan (misal: '1M/1M' untuk 1Mbps upload/download).")
@click.option('--shared-users', type=int, default=None, help="Jumlah pengguna bersama yang diizinkan untuk profil ini.")
@click.option('--description', default=None, help="Deskripsi profil.")
@with_appcontext
def add_mikrotik_profile(name, rate_limit, shared_users, description):
    if not MODELS_AVAILABLE or not hasattr(db, 'session') or not PackageProfile:
        click.echo(click.style("ERROR: Model PackageProfile atau database session tidak dapat dimuat.", fg='red')); return
    if not MIKROTIK_CLIENT_AVAILABLE:
        current_app.logger.error("Klien Mikrotik tidak tersedia. Tidak bisa menambahkan profil di Mikrotik.")
        click.echo(click.style("ERROR: Klien Mikrotik tidak tersedia. Tidak bisa menambahkan profil di Mikrotik.", fg='red')); return

    if db.session.execute(db.select(PackageProfile).filter_by(profile_name=name)).scalar_one_or_none():
        click.echo(click.style(f"ERROR: Profil Mikrotik dengan nama '{name}' sudah ada di database aplikasi.", fg='red')); return

    mikrotik_profile_added_mt = False
    mikrotik_message_mt = "Tidak mencoba karena klien Mikrotik tidak tersedia."

    try:
        with get_mikrotik_connection() as mikrotik_api_conn:
            if mikrotik_api_conn:
                current_app.logger.info(f"Mencoba menambahkan profil '{name}' ke Mikrotik...")
                click.echo(click.style(f"INFO: Mencoba menambahkan profil '{name}' ke Mikrotik...", fg='cyan'))
                mikrotik_profile_added_mt, mikrotik_message_mt = add_mikrotik_hotspot_user_profile(
                    api_connection=mikrotik_api_conn,
                    profile_name=name,
                    rate_limit=rate_limit,
                    shared_users=shared_users,
                    comment=description
                )
                if mikrotik_profile_added_mt:
                    current_app.logger.info(f"Profil '{name}' berhasil ditambahkan di Mikrotik. Pesan: {mikrotik_message_mt}")
                    click.echo(click.style(f"SUKSES: Profil '{name}' berhasil ditambahkan di Mikrotik. Pesan: {mikrotik_message_mt}", fg='green'))
                else:
                    current_app.logger.error(f"Gagal menambahkan profil '{name}' di Mikrotik. Pesan: {mikrotik_message_mt}")
                    click.echo(click.style(f"ERROR: Gagal menambahkan profil '{name}' di Mikrotik. Pesan: {mikrotik_message_mt}", fg='red'))
            else:
                current_app.logger.error("Gagal mendapatkan koneksi Mikrotik.")
                click.echo(click.style("ERROR: Gagal mendapatkan koneksi Mikrotik.", fg='red'))
                mikrotik_message_mt = "Gagal mendapatkan koneksi Mikrotik."
    except Exception as e_mt_add_profile:
        current_app.logger.error(f"Exception saat menambah profil Mikrotik '{name}': {str(e_mt_add_profile)}", exc_info=True)
        click.echo(click.style(f"ERROR: Exception saat menambah profil Mikrotik '{name}': {str(e_mt_add_profile)}", fg='red'))
        mikrotik_message_mt = str(e_mt_add_profile)

    if not mikrotik_profile_added_mt:
        click.echo(click.style("\nPERINGATAN: Profil GAGAL ditambahkan di Mikrotik. Tidak akan disimpan ke database aplikasi.", fg='yellow', bold=True))
        click.echo(f"  Detail Mikrotik: {mikrotik_message_mt}")
        return

    new_profile = PackageProfile(
        profile_name=name,
        description=description
    )

    db.session.add(new_profile)
    try:
        db.session.commit()
        current_app.logger.info(f"Profil Mikrotik '{name}' juga berhasil disimpan ke database aplikasi.")
        click.echo(click.style(f"\nSUKSES: Profil Mikrotik '{name}' juga berhasil disimpan ke database aplikasi.", fg='green'))
    except Exception as e_db_profile:
        db.session.rollback()
        current_app.logger.error(f"Error menyimpan profil Mikrotik '{name}' ke DB setelah sukses di Mikrotik: {str(e_db_profile)}", exc_info=True)
        click.echo(click.style(f"\nERROR DB: Gagal menyimpan profil Mikrotik ke database aplikasi meskipun sudah sukses di Mikrotik: {str(e_db_profile)}", fg='red'))
        click.echo(click.style("  Anda mungkin perlu menghapus profil ini secara manual dari Mikrotik jika tidak ingin ada duplikasi.", fg='yellow'))