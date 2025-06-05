# backend/app/commands/user_commands.py
# Versi: Perbaikan SyntaxError di perintah 'update', penambahan seed-usage.
# Versi: Perbaikan input kosong untuk blok/kamar admin
# Versi: Perbaikan re-prompting pada input kosong untuk blok/kamar admin
# Versi: Penyempurnaan format prompt untuk blok/kamar admin
# Versi: Pembaruan input dan prompt untuk opsi --role di create-admin
# Versi: Perbaikan SyntaxError unmatched ')' pada definisi @click.option
# Versi: Perbaikan SyntaxError unterminated string literal pada seed_user_usage

import click
from flask import current_app
from app.extensions import db
import re
import uuid
import enum
import random
import string
from datetime import datetime, timezone as dt_timezone, date, timedelta

# --- Impor Model & Helper ---
try:
    from app.infrastructure.db.models import User, UserRole, ApprovalStatus, UserBlok, UserKamar, DailyUsageLog
    MODELS_AVAILABLE = True
except ImportError:
    print("CRITICAL ERROR: Could not import User/DailyUsageLog models in user_commands.py.")
    MODELS_AVAILABLE = False
    class UserRole(str, enum.Enum): USER = "USER"; ADMIN = "ADMIN"; SUPER_ADMIN = "SUPER_ADMIN"
    class ApprovalStatus(str, enum.Enum): PENDING_APPROVAL = "PENDING_APPROVAL"; APPROVED = "APPROVED"; REJECTED = "REJECTED"
    class UserBlok(str, enum.Enum): A="A"; B="B"; C="C"; D="D"; E="E"; F="F";
    class UserKamar(str, enum.Enum): Kamar_1="1"; Kamar_2="2"; Kamar_3="3"; Kamar_4="4"; Kamar_5="5"; Kamar_6="6"
    class User: pass
    class DailyUsageLog: pass

try:
    from app.infrastructure.http.auth_routes import generate_password_hash as auth_routes_hash
    generate_password_hash_func = auth_routes_hash
except ImportError:
    try:
        from werkzeug.security import generate_password_hash as werkzeug_hash
        generate_password_hash_func = werkzeug_hash
    except ImportError:
        def dummy_hash(password: str) -> str: return f"hashed_{password}"
        generate_password_hash_func = dummy_hash

try:
    from app.infrastructure.gateways.whatsapp_client import send_whatsapp_message
    WHATSAPP_AVAILABLE = True
except ImportError:
    WHATSAPP_AVAILABLE = False
    def send_whatsapp_message(to: str, body: str) -> bool: return False

MIKROTIK_CLIENT_AVAILABLE = False
try:
    from app.infrastructure.gateways.mikrotik_client import (
        get_mikrotik_connection,
        activate_or_update_hotspot_user,
        format_to_local_phone,
        delete_hotspot_user
    )
    MIKROTIK_CLIENT_AVAILABLE = True
except ImportError:
    def get_mikrotik_connection(): return None
    def activate_or_update_hotspot_user(connection_pool, user_db_id: str, mikrotik_profile_name: str, hotspot_password: str, comment:str=""): return False, "Not implemented"
    def format_to_local_phone(phone: str | None) -> str | None: return phone if not (phone and phone.startswith('+62')) else '0' + phone[3:]
    def delete_hotspot_user(connection_pool, username: str): return False, "Not implemented"

# --- Role choice mapping for create-admin ---
# Pastikan UserRole sudah terdefinisi atau diimpor sebelum baris ini
if MODELS_AVAILABLE: # Hanya definisikan jika UserRole (dari model) tersedia
    ROLE_INPUT_MAP_ADMIN_CREATE = {
        '1': UserRole.SUPER_ADMIN,
        '2': UserRole.ADMIN
    }
    ROLE_DESCRIPTIONS_ADMIN_CREATE = [f"{num}: {ROLE_INPUT_MAP_ADMIN_CREATE[num].value}" for num in ROLE_INPUT_MAP_ADMIN_CREATE]
else: # Fallback jika model tidak termuat, agar skrip tidak error saat load awal
    ROLE_INPUT_MAP_ADMIN_CREATE = {'1': "SUPER_ADMIN_FALLBACK", '2': "ADMIN_FALLBACK"} # Fallback values
    ROLE_DESCRIPTIONS_ADMIN_CREATE = ["1: SUPER_ADMIN (fallback)", "2: ADMIN (fallback)"]


# --- Definisi Grup CLI dan Fungsi Helper ---
@click.group(name='user', help="Perintah terkait manajemen pengguna aplikasi hotspot.")
def user_cli_bp():
    if not MODELS_AVAILABLE and current_app:
         click.echo(click.style("PERINGATAN: Model database tidak dapat dimuat.", fg='yellow'), err=True)

def normalize_phone_for_cli(phone_number_input: str) -> str:
    if not phone_number_input:
        raise click.BadParameter("Nomor telepon tidak boleh kosong.")
    cleaned = re.sub(r'[\s\-()+]', '', phone_number_input)
    if cleaned.startswith('08'):
        return '+62' + cleaned[1:]
    elif cleaned.startswith('628'):
        return '+' + cleaned if not cleaned.startswith('+') else cleaned
    elif cleaned.startswith('+628'):
        return cleaned
    elif cleaned.startswith('8') and len(cleaned) >= 8:
        return '+62' + cleaned
    else:
        raise click.BadParameter(
            f"Format nomor telepon '{phone_number_input}' tidak dikenali. "
            "Gunakan format standar Indonesia seperti 08xx, 628xx, atau +628xx."
        )

def generate_random_password(length=6, type='numeric'):
    if type == 'numeric':
        return "".join(random.choices(string.digits, k=length))
    elif type == 'alphanumeric':
        alphabet = string.ascii_letters + string.digits
        return "".join(random.choices(alphabet, k=length))
    else:
        return "".join(random.choices(string.digits, k=length))


# --- Perintah create-admin ---
@user_cli_bp.command('create-admin', help="Membuat pengguna Admin/Super Admin baru (langsung aktif).")
@click.option('--phone', required=True, prompt="Nomor Telepon Admin (format 08... atau +62...)", help="Nomor telepon unik untuk admin.")
@click.option('--name', required=True, prompt="Nama Lengkap Admin", help="Nama lengkap admin.")
@click.option('--blok',
              default="",
              prompt=f"Blok Rumah Admin ({', '.join(b.value for b in UserBlok)})" if MODELS_AVAILABLE else "Blok Rumah Admin (A,B,C,D,E,F)",
              help=f"Blok rumah admin. Pilihan: {', '.join(b.value for b in UserBlok) if MODELS_AVAILABLE else 'A-F'}. Tekan Enter untuk mengosongkan.",
              type=click.Choice([b.value for b in UserBlok] + [""] if MODELS_AVAILABLE else ["A","B","C","D","E","F",""], case_sensitive=False),
              show_default=False,
              show_choices=False)
@click.option('--kamar',
              default="",
              prompt=f"Nomor Kamar Admin ({', '.join(k.value for k in UserKamar)})" if MODELS_AVAILABLE else "Nomor Kamar Admin (1,2,3,4,5,6)",
              help=f"Nomor kamar admin. Pilihan: {', '.join(k.value for k in UserKamar) if MODELS_AVAILABLE else '1-6'}. Tekan Enter untuk mengosongkan.",
              type=click.Choice([k.value for k in UserKamar] + [""] if MODELS_AVAILABLE else ["1","2","3","4","5","6",""], case_sensitive=False),
              show_default=False,
              show_choices=False)
@click.option('--password', required=True, prompt="Password Portal Admin", hide_input=True, confirmation_prompt=True, help="Password untuk login admin ke portal. Minimal 6 karakter.")
@click.option('--role',
              type=click.Choice(list(ROLE_INPUT_MAP_ADMIN_CREATE.keys())),
              default='2', # '2' untuk ADMIN
              prompt=f"Pilih Role ({', '.join(ROLE_DESCRIPTIONS_ADMIN_CREATE)})",
              show_default=True, # Akan menampilkan [2] sebagai default
              show_choices=False, # Keterangan pilihan sudah ada di prompt
              help=f"Tentukan role untuk admin. {', '.join(ROLE_DESCRIPTIONS_ADMIN_CREATE)}.")
@click.option('--mikrotik-password', default=None, help="Password Mikrotik khusus untuk admin ini (opsional).")
def create_admin(phone, name, blok, kamar, password, role, mikrotik_password):
    if not MODELS_AVAILABLE:
        click.echo(click.style("ERROR: Model User, UserRole, dll. tidak dapat dimuat. Perintah create-admin tidak bisa dijalankan.", fg='red')); return

    try:
        normalized_phone = normalize_phone_for_cli(phone)
        
        # Konversi input role ('1' atau '2') ke enum UserRole
        try:
            role_enum = ROLE_INPUT_MAP_ADMIN_CREATE[role]
        except KeyError:
            # Seharusnya tidak terjadi karena click.Choice sudah memvalidasi
            click.echo(click.style(f"ERROR: Pilihan role internal '{role}' tidak valid.", fg='red'))
            return
        
        blok_clean = blok.strip().upper() if blok else ""
        blok_enum_val = UserBlok(blok_clean) if MODELS_AVAILABLE and blok_clean in [b.value for b in UserBlok] else None
        
        kamar_clean = kamar.strip() if kamar else ""
        kamar_enum_val = UserKamar(kamar_clean) if MODELS_AVAILABLE and kamar_clean in [k.value for k in UserKamar] else None
                
    except (ValueError, TypeError) as e: # ValueError bisa dari UserBlok/UserKamar jika ada input tak terduga
        click.echo(click.style(f"ERROR: Input tidak valid - {e}", fg='red')); return

    if db.session.execute(db.select(User).filter_by(phone_number=normalized_phone)).scalar_one_or_none():
        click.echo(click.style(f"ERROR: Nomor telepon '{normalized_phone}' sudah terdaftar.", fg='red')); return

    if not password or len(password) < 6:
        click.echo(click.style("ERROR: Password portal admin minimal 6 karakter.", fg='red')); return

    hashed_portal_password = generate_password_hash_func(password)
    final_mikrotik_password_hash_for_db = None
    if mikrotik_password:
        final_mikrotik_password_hash_for_db = generate_password_hash_func(mikrotik_password)
        click.echo(click.style(f"INFO: Password Mikrotik manual untuk admin '{name}' akan di-hash.", fg='blue'))

    new_admin = User(
        phone_number=normalized_phone,
        full_name=name,
        blok=blok_enum_val,
        kamar=kamar_enum_val,
        password_hash=hashed_portal_password,
        mikrotik_password=final_mikrotik_password_hash_for_db,
        role=role_enum, # Menggunakan role_enum yang sudah dikonversi
        approval_status=ApprovalStatus.APPROVED,
        is_active=True,
        approved_at=datetime.now(dt_timezone.utc),
    )

    try:
        db.session.add(new_admin)
        db.session.commit()
        db.session.refresh(new_admin)
        click.echo(click.style(f"SUKSES: Pengguna {role_enum.value} '{new_admin.full_name}' (ID: {new_admin.id}) berhasil dibuat.", fg='green'))
    except Exception as e:
        db.session.rollback()
        if hasattr(current_app, 'logger'):
            current_app.logger.error(f"Error creating admin {normalized_phone} via CLI: {e}", exc_info=True)
        click.echo(click.style(f"ERROR: Gagal menyimpan admin baru: {e}", fg='red'))


# --- Perintah update ---
@user_cli_bp.command('update', help="Memperbarui data pengguna yang sudah ada.")
@click.argument('phone_number', type=str)
@click.option('--nama', default=None, help="Nama lengkap baru.")
@click.option('--blok', default=None, help="Blok baru (A/B/C...) atau 'kosong' untuk menghapus.", type=click.Choice([b.value for b in UserBlok] + ["kosong"] if MODELS_AVAILABLE else ["A","B","C","kosong"], case_sensitive=False))
@click.option('--kamar', default=None, help="Kamar baru (1/2/3...) atau 'kosong' untuk menghapus.", type=click.Choice([k.value for k in UserKamar] + ["kosong"] if MODELS_AVAILABLE else ["1","2","3","kosong"], case_sensitive=False))
@click.option('--aktif', default=None, type=click.BOOL, help="Set status aktif (true/false).")
@click.option('--admin-id', '-a', type=str, default=None, help="UUID Admin yang melakukan aksi (opsional, untuk log).")
def update_user(phone_number, nama, blok, kamar, aktif, admin_id):
    if not MODELS_AVAILABLE:
        click.echo(click.style("ERROR: Model User tidak dapat dimuat.", fg='red')); return

    admin_performing_update = None; admin_id_for_log_upd = "Tidak Diketahui"
    if admin_id:
        try:
            admin_uuid_upd = uuid.UUID(admin_id)
            admin_performing_update = db.session.get(User, admin_uuid_upd) # type: ignore
            if not admin_performing_update: click.echo(click.style(f"WARNING: Admin ID '{admin_id}' tidak ditemukan.", fg='yellow'))
            elif not admin_performing_update.role_is_admin(): # type: ignore
                click.echo(click.style(f"WARNING: Pengguna '{admin_performing_update.full_name}' bukan Admin.", fg='yellow')) # type: ignore
                admin_performing_update = None
            else: admin_id_for_log_upd = str(admin_performing_update.id) # type: ignore
        except ValueError: click.echo(click.style(f"WARNING: Format UUID --admin-id salah: '{admin_id}'.", fg='yellow'))
        except AttributeError: click.echo(click.style("WARNING: Tidak dapat verifikasi role admin.", fg='yellow'))

    try:
        normalized_phone = normalize_phone_for_cli(phone_number)
    except click.BadParameter as e:
        click.echo(click.style(f"ERROR: {e.message}", fg='red')); return

    user_to_update = db.session.execute(db.select(User).filter_by(phone_number=normalized_phone)).scalar_one_or_none() # type: ignore

    if not user_to_update:
        click.echo(click.style(f"ERROR: Pengguna '{normalized_phone}' tidak ditemukan.", fg='red')); return

    updated_fields = []
    user_updated = False

    # Update Nama
    if nama is not None:
        if user_to_update.full_name != nama: # type: ignore
            user_to_update.full_name = nama # type: ignore
            updated_fields.append(f"Nama menjadi '{nama}'")
            user_updated = True
        else:
            click.echo(click.style(f"INFO: Nama pengguna sudah '{nama}'.", fg='blue'))

    # Update Blok
    if blok is not None:
        if blok.lower() == "kosong":
            if user_to_update.blok is not None: # type: ignore
                user_to_update.blok = None # type: ignore
                updated_fields.append("Blok dikosongkan")
                user_updated = True
            else:
                click.echo(click.style("INFO: Blok pengguna sudah kosong.", fg='blue'))
        else:
            try: 
                blok_enum_val = UserBlok(blok.upper()) 
                if user_to_update.blok != blok_enum_val: 
                    user_to_update.blok = blok_enum_val 
                    updated_fields.append(f"Blok menjadi '{blok_enum_val.value}'")
                    user_updated = True
                else:
                     click.echo(click.style(f"INFO: Blok pengguna sudah '{blok_enum_val.value}'.", fg='blue')) 
            except ValueError: 
                click.echo(click.style(f"ERROR: Nilai blok '{blok}' tidak valid.", fg='red')); return

    # Update Kamar
    if kamar is not None:
        if kamar.lower() == "kosong":
            if user_to_update.kamar is not None: # type: ignore
                user_to_update.kamar = None # type: ignore
                updated_fields.append("Kamar dikosongkan")
                user_updated = True
            else:
                click.echo(click.style("INFO: Kamar pengguna sudah kosong.", fg='blue'))
        else:
            try: 
                kamar_enum_val = UserKamar(kamar) 
                if user_to_update.kamar != kamar_enum_val: 
                    user_to_update.kamar = kamar_enum_val 
                    updated_fields.append(f"Kamar menjadi '{kamar_enum_val.value}'")
                    user_updated = True
                else:
                     click.echo(click.style(f"INFO: Kamar pengguna sudah '{kamar_enum_val.value}'.", fg='blue')) 
            except ValueError: 
                click.echo(click.style(f"ERROR: Nilai kamar '{kamar}' tidak valid.", fg='red')); return

    # Update Status Aktif
    if aktif is not None: 
        if user_to_update.is_active != aktif: 
            user_to_update.is_active = aktif 
            updated_fields.append(f"Status aktif menjadi '{'Ya' if aktif else 'Tidak'}'")
            user_updated = True
        else:
            click.echo(click.style(f"INFO: Status aktif pengguna sudah '{'Ya' if aktif else 'Tidak'}'.", fg='blue'))

    if not user_updated:
        click.echo(click.style("Tidak ada perubahan data yang dilakukan.", fg='yellow'))
        return

    try:
        user_to_update.updated_at = datetime.now(dt_timezone.utc) 
        db.session.commit()
        log_msg = f"User data updated: ID={user_to_update.id}, Phone={normalized_phone}, Name='{user_to_update.full_name}'. Changes: {'; '.join(updated_fields)}. Admin ID: {admin_id_for_log_upd if admin_performing_update else 'System/CLI'}." 
        if hasattr(current_app, 'logger'):
            current_app.logger.info(log_msg) 
        click.echo(click.style(f"SUKSES: Data pengguna '{user_to_update.full_name}' ({normalized_phone}) berhasil diperbarui.", fg='green')) 
        click.echo(f"  Perubahan: {', '.join(updated_fields)}")
    except Exception as e_db_update:
        db.session.rollback()
        if hasattr(current_app, 'logger'):
            current_app.logger.error(f"Error update user {normalized_phone}: {e_db_update}", exc_info=True) 
        click.echo(click.style(f"ERROR: Gagal memperbarui data pengguna: {e_db_update}", fg='red'))


# --- Perintah list ---
@user_cli_bp.command('list', help="Menampilkan daftar pengguna dengan filter.")
@click.option('--status', '-s', type=click.Choice([s.value for s in ApprovalStatus] if MODELS_AVAILABLE else [], case_sensitive=False), default=None, help="Filter status approval.")
@click.option('--role', '-r', type=click.Choice([r.value for r in UserRole] if MODELS_AVAILABLE else [], case_sensitive=False), default=None, help="Filter role.")
@click.option('--active', '-ac', type=click.BOOL, default=None, help="Filter status aktif (True/False).")
@click.option('--limit', '-l', type=int, default=20, show_default=True, help="Jumlah maksimal pengguna.")
@click.option('--search', '-q', type=str, default=None, help="Cari nama atau nomor telepon.")
def list_users(status, role, active, limit, search):
    if not MODELS_AVAILABLE:
        click.echo(click.style("ERROR: Model User tidak dapat dimuat.", fg='red')); return

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
        search_term = f"%{search}%"
        query = query.filter(db.or_(User.full_name.ilike(search_term), User.phone_number.ilike(search_term))) 

    users_to_list = db.session.execute(query.order_by(User.created_at.desc()).limit(limit)).scalars().all() 

    if not users_to_list:
        click.echo("Tidak ada pengguna ditemukan."); return

    click.echo(click.style("Daftar Pengguna:", fg='cyan', bold=True))
    header = "{:<37} {:<15} {:<20} {:<7} {:<7} {:<18} {:<13} {:<7} {:<15} {:<15}".format(
        "ID Pengguna", "No. Telepon", "Nama", "Blok", "Kamar", "Status Approval", "Role", "Aktif?", "Device Brand", "Device Model"
    )
    click.echo(click.style(header, fg='yellow'))
    line_length_exact = 37 + 1 + 15 + 1 + 20 + 1 + 7 + 1 + 7 + 1 + 18 + 1 + 13 + 1 + 7 + 1 + 15 + 1 + 15
    click.echo(click.style("-" * line_length_exact, fg='cyan'))

    for user_obj in users_to_list:
        blok_display = (user_obj.blok.value if user_obj.blok and hasattr(user_obj.blok, 'value') else "N/A") 
        kamar_display = (user_obj.kamar.value if user_obj.kamar and hasattr(user_obj.kamar, 'value') else "N/A") 
        user_line = "{:<37} {:<15} {:<20} {:<7} {:<7} {:<18} {:<13} {:<7} {:<15} {:<15}".format(
            str(user_obj.id), 
            user_obj.phone_number, 
            (user_obj.full_name or "")[:18] + ('..' if len(user_obj.full_name or "") > 18 else ''), 
            blok_display[:5] + ('..' if len(blok_display) > 5 else ''),
            kamar_display[:5] + ('..' if len(kamar_display) > 5 else ''),
            user_obj.approval_status.value if hasattr(user_obj.approval_status, 'value') else str(user_obj.approval_status), 
            user_obj.role.value if hasattr(user_obj.role, 'value') else str(user_obj.role), 
            "Ya" if user_obj.is_active else "Tidak", 
            (user_obj.device_brand or "N/A")[:13] + ('..' if len(user_obj.device_brand or "") > 13 else ''), 
            (user_obj.device_model or "N/A")[:13] + ('..' if len(user_obj.device_model or "") > 13 else '') 
        )
        click.echo(user_line)
    click.echo(click.style("-" * line_length_exact, fg='cyan'))
    click.echo(f"Menampilkan {len(users_to_list)} pengguna (limit: {limit}).")

# --- Perintah approve ---
@user_cli_bp.command('approve', help="Menyetujui pengguna PENDING atau sinkronisasi ulang pengguna APPROVED ke Mikrotik.")
@click.argument('phone_number', type=str)
@click.option('--admin-id', '-a', type=str, default=None, help="UUID Admin yang melakukan aksi (opsional, untuk pencatatan).")
@click.option('--force-sync', '-fs', is_flag=True, help="Paksa sinkronisasi (generate password Mikrotik baru & update ke Mikrotik) meskipun pengguna sudah APPROVED.")
@click.option('--profile', '-p', type=str, default=None, help="Nama profile Mikrotik yang akan digunakan (override default dari config).")
def approve_user(phone_number, admin_id, force_sync, profile):
    if not MODELS_AVAILABLE or not MIKROTIK_CLIENT_AVAILABLE:
        click.echo(click.style("ERROR: Model User atau Klien Mikrotik tidak termuat.", fg='red'))
        return

    admin_performing_action = None
    admin_id_for_log = "System/CLI" # Default jika tidak ada admin ID
    if admin_id:
        try:
            admin_uuid = uuid.UUID(admin_id)
            admin_performing_action = db.session.get(User, admin_uuid) 
            if not admin_performing_action:
                click.echo(click.style(f"WARNING: Admin ID '{admin_id}' tidak ditemukan.", fg='yellow'))
            elif not admin_performing_action.role_is_admin(): 
                click.echo(click.style(f"WARNING: Pengguna '{admin_performing_action.full_name}' bukan Admin.", fg='yellow')) 
                admin_performing_action = None
            else:
                admin_id_for_log = str(admin_performing_action.id)
        except ValueError:
            click.echo(click.style(f"WARNING: Format UUID --admin-id salah: '{admin_id}'.", fg='yellow'))
        except AttributeError:
             click.echo(click.style("WARNING: Tidak dapat verifikasi role admin (model User tidak lengkap).", fg='yellow'))

    try:
        normalized_phone = normalize_phone_for_cli(phone_number)
    except click.BadParameter as e:
        click.echo(click.style(f"ERROR: {e.message}", fg='red')); return

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
        password_untuk_mikrotik = generate_random_password(length=6) # Selalu generate baru untuk force_sync
        password_generated_for_this_action = True
        click.echo(click.style(f"  [INFO] Force Sync: Password baru '{password_untuk_mikrotik}' akan dibuat.", fg='blue'))
    elif is_initial_approval:
        if user_to_process.mikrotik_password and len(user_to_process.mikrotik_password) == 6 and user_to_process.mikrotik_password.isdigit():
            password_untuk_mikrotik = user_to_process.mikrotik_password
            click.echo(click.style(f"  [INFO] Initial Approval: Menggunakan password yang sudah ada: '{password_untuk_mikrotik}'.", fg='blue'))
        else:
            password_untuk_mikrotik = generate_random_password(length=6)
            password_generated_for_this_action = True
            click.echo(click.style(f"  [INFO] Initial Approval: Password baru '{password_untuk_mikrotik}' dibuat (sebelumnya kosong/tidak valid).", fg='blue'))
    else: # Kasus ini seharusnya tidak terjadi jika logika di atas benar, tapi sebagai fallback
        click.echo(click.style(f"  [WARNING] Kondisi tidak terduga, menggunakan password yang ada atau generate baru jika kosong.", fg='yellow'))
        password_untuk_mikrotik = user_to_process.mikrotik_password if user_to_process.mikrotik_password and len(user_to_process.mikrotik_password) == 6 and user_to_process.mikrotik_password.isdigit() else generate_random_password(length=6)
        if password_untuk_mikrotik != user_to_process.mikrotik_password: password_generated_for_this_action = True


    # Update Database
    try:
        if is_initial_approval:
            if user_to_process.role == UserRole.USER: 
                if not user_to_process.blok: 
                    click.echo(click.style(f"  [DB] ERROR: Pengguna '{user_to_process.full_name}' (role USER) tidak memiliki data Blok. Penyetujuan dibatalkan.", fg='red')) 
                    return
                if not user_to_process.kamar: 
                    click.echo(click.style(f"  [DB] ERROR: Pengguna '{user_to_process.full_name}' (role USER) tidak memiliki data Kamar. Penyetujuan dibatalkan.", fg='red')) 
                    return
            user_to_process.approval_status = ApprovalStatus.APPROVED 
            user_to_process.is_active = True 
            user_to_process.approved_at = datetime.now(dt_timezone.utc) 
            if admin_performing_action: user_to_process.approved_by_id = admin_performing_action.id 
            user_to_process.rejected_at = None 
            user_to_process.rejected_by_id = None 
        
        # Selalu update mikrotik_password di DB dengan yang akan digunakan/digenerate
        user_to_process.mikrotik_password = password_untuk_mikrotik
        user_to_process.updated_at = datetime.now(dt_timezone.utc) 

        db.session.commit()
        db.session.refresh(user_to_process) # Refresh untuk mendapatkan data terbaru
        admin_log_info_db = f" oleh Admin ID '{admin_id_for_log}'" if admin_id_for_log != "System/CLI" and is_initial_approval else ""
        password_log_info_db = f" Password Mikrotik diupdate ke '{password_untuk_mikrotik}'." if password_generated_for_this_action or force_sync else " Password Mikrotik tidak berubah."
        click.echo(click.style(f"  [DB] SUKSES: Status pengguna diperbarui{admin_log_info_db}.{password_log_info_db}", fg='green'))
    except Exception as e_db_approve:
        db.session.rollback()
        if hasattr(current_app, 'logger'):
            current_app.logger.error(f"Error DB {action_description} untuk {normalized_phone}: {e_db_approve}", exc_info=True) 
        click.echo(click.style(f"  [DB] ERROR: {e_db_approve}", fg='red'))
        return

    # Update Mikrotik
    mikrotik_update_success = False
    mikrotik_message_detail = "Klien Mikrotik tidak tersedia."
    if MIKROTIK_CLIENT_AVAILABLE: 
        mikrotik_profile_to_use = profile or current_app.config.get('MIKROTIK_DEFAULT_PROFILE', 'default') 
        mikrotik_username_mt = format_to_local_phone(user_to_process.phone_number) 

        if not mikrotik_username_mt:
            click.echo(click.style(f"  [Mikrotik] WARNING: Tidak dapat konversi nomor ke username Mikrotik. Update Mikrotik dilewati.", fg='yellow'))
            mikrotik_message_detail = "Format username Mikrotik tidak valid."
        else:
            mikrotik_conn_pool = None
            try:
                mikrotik_conn_pool = get_mikrotik_connection() 
                if mikrotik_conn_pool:
                    click.echo(f"  [Mikrotik] INFO: Mencoba update Mikrotik untuk '{mikrotik_username_mt}' (ID DB: {user_to_process.id}) profile: {mikrotik_profile_to_use} dengan password '{password_untuk_mikrotik}'") 
                    kamar_val_for_comment = user_to_process.kamar.value if user_to_process.kamar and hasattr(user_to_process.kamar, 'value') else 'N/A' 
                    blok_val_for_comment = user_to_process.blok.value if user_to_process.blok and hasattr(user_to_process.blok, 'value') else 'N/A' 
                    comment_for_mikrotik = f"{user_to_process.full_name or 'N/A'} | Blk {blok_val_for_comment} Km {kamar_val_for_comment} | ID:{str(user_to_process.id)[:8]}" 

                    mikrotik_update_success, mikrotik_message_detail = activate_or_update_hotspot_user( 
                        connection_pool=mikrotik_conn_pool, user_db_id=str(user_to_process.id), 
                        mikrotik_profile_name=mikrotik_profile_to_use, hotspot_password=password_untuk_mikrotik,
                        comment=comment_for_mikrotik
                    )
                    if mikrotik_update_success: click.echo(click.style(f"  [Mikrotik] SUKSES: {mikrotik_message_detail}", fg='green'))
                    else: click.echo(click.style(f"  [Mikrotik] ERROR: {mikrotik_message_detail}", fg='red'))
                else:
                    click.echo(click.style("  [Mikrotik] ERROR: Gagal koneksi Mikrotik.", fg='red'))
                    mikrotik_message_detail = "Koneksi Mikrotik gagal."
            except Exception as e_mt_approve:
                if hasattr(current_app, 'logger'):
                    current_app.logger.error(f"Exception Mikrotik untuk {mikrotik_username_mt}: {e_mt_approve}", exc_info=True) 
                click.echo(click.style(f"  [Mikrotik] ERROR Exception: {e_mt_approve}", fg='red'))
                mikrotik_message_detail = str(e_mt_approve)

    # Kirim Notifikasi WhatsApp
    whatsapp_notification_success = False
    # Hanya kirim WA jika ini persetujuan awal atau jika force_sync dan password berhasil digenerate/diupdate di MT
    if WHATSAPP_AVAILABLE and user_to_process.phone_number and (is_initial_approval or (force_sync and password_generated_for_this_action and mikrotik_update_success)): 
        try:
            username_display_for_wa = format_to_local_phone(user_to_process.phone_number) or user_to_process.phone_number 
            message_body_wa = ""
            if is_initial_approval:
                message_body_wa = (f"Selamat {user_to_process.full_name},\n\nPendaftaran hotspot Anda telah DISETUJUI!\n\n" 
                                   f"Detail Akun:\nUsername: {username_display_for_wa}\nPassword: {password_untuk_mikrotik}\n\n"
                                   f"Simpan info ini. Terima kasih.")
            elif force_sync and password_generated_for_this_action: # Hanya kirim jika password benar-benar baru karena force_sync
                message_body_wa = (f"Hai {user_to_process.full_name},\n\nAkun hotspot Anda telah disinkronkan ulang.\n" 
                                   f"Password Baru: {password_untuk_mikrotik}\nUsername: {username_display_for_wa}\n\nTerima kasih.")

            if message_body_wa: # Pastikan ada pesan untuk dikirim
                whatsapp_notification_success = send_whatsapp_message(user_to_process.phone_number, message_body_wa) 
                if whatsapp_notification_success: click.echo(click.style(f"  [WhatsApp] SUKSES: Notifikasi & password dikirim ke {user_to_process.phone_number}.", fg='green')) 
                else: click.echo(click.style(f"  [WhatsApp] ERROR: Gagal kirim notifikasi ke {user_to_process.phone_number}.", fg='red')) 
        except Exception as e_wa_approve:
            if hasattr(current_app, 'logger'):
                current_app.logger.error(f"Exception WA untuk {user_to_process.phone_number}: {e_wa_approve}", exc_info=True) 
            click.echo(click.style(f"  [WhatsApp] ERROR Exception: {e_wa_approve}", fg='red'))
    elif not user_to_process.phone_number: click.echo(click.style("  [WhatsApp] INFO: Tidak ada nomor telepon, notifikasi dilewati.", fg='yellow')) 
    elif not WHATSAPP_AVAILABLE:
        click.echo(click.style("  [WhatsApp] INFO: Klien WhatsApp tidak tersedia, notifikasi dilewati.", fg='yellow'))
        if is_initial_approval or (force_sync and password_generated_for_this_action):
            click.echo(click.style(f"    -> Info Admin: Password Mikrotik {user_to_process.full_name}: {password_untuk_mikrotik}", fg='blue')) 

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
def reject_user(phone_number, admin_id, reason, force):
    if not MODELS_AVAILABLE:
        click.echo(click.style("ERROR: Model User tidak dapat dimuat.", fg='red')); return

    admin_performing_rejection = None; admin_id_for_log = "Tidak Diketahui"
    if admin_id:
        try:
            admin_uuid = uuid.UUID(admin_id)
            admin_performing_rejection = db.session.get(User, admin_uuid) 
            if not admin_performing_rejection: click.echo(click.style(f"WARNING: Admin ID '{admin_id}' tidak ditemukan.", fg='yellow'))
            elif not admin_performing_rejection.role_is_admin(): 
                click.echo(click.style(f"WARNING: Pengguna '{admin_performing_rejection.full_name}' bukan Admin.", fg='yellow')) 
                admin_performing_rejection = None
            else: admin_id_for_log = str(admin_performing_rejection.id) 
        except ValueError: click.echo(click.style(f"WARNING: Format UUID --admin-id salah: '{admin_id}'.", fg='yellow'))
        except AttributeError: click.echo(click.style("WARNING: Tidak dapat verifikasi role admin.", fg='yellow'))

    try: normalized_phone = normalize_phone_for_cli(phone_number)
    except click.BadParameter as e: click.echo(click.style(f"ERROR: {e.message}", fg='red')); return

    user_to_reject = db.session.execute(db.select(User).filter_by(phone_number=normalized_phone)).scalar_one_or_none() 

    if not user_to_reject: click.echo(click.style(f"ERROR: Pengguna '{normalized_phone}' tidak ditemukan.", fg='red')); return

    if user_to_reject.approval_status != ApprovalStatus.PENDING_APPROVAL: 
        current_status_val = user_to_reject.approval_status.value if hasattr(user_to_reject.approval_status, 'value') else str(user_to_reject.approval_status) 
        click.echo(click.style(f"INFO: Pengguna '{user_to_reject.full_name}' tidak PENDING (Status: {current_status_val}).", fg='yellow')) 
        click.echo(click.style("Gunakan 'delete' untuk status lain.", fg='yellow')); return

    if not force:
        click.echo(click.style(f"\nDETAIL PENGGUNA AKAN DITOLAK & DIHAPUS:", fg='yellow', bold=True))
        click.echo(f"  Nama: {user_to_reject.full_name}, Telp: {user_to_reject.phone_number}, Status: {user_to_reject.approval_status.value}") 
        click.confirm(click.style("\nAnda YAKIN MENOLAK dan MENGHAPUS PERMANEN pendaftaran ini?", fg='red', bold=True), abort=True)

    user_full_name_for_log = user_to_reject.full_name; user_id_for_log = str(user_to_reject.id); user_phone_for_notif = user_to_reject.phone_number 

    notification_sent_reject = False
    if WHATSAPP_AVAILABLE and user_phone_for_notif: 
        try:
            phone_display_local = format_to_local_phone(user_phone_for_notif) or user_phone_for_notif 
            message_body_reject = (f"Yth. {user_full_name_for_log},\n\nPendaftaran hotspot Anda ({phone_display_local}) tidak dapat kami setujui.\n" 
                                   f"Alasan: {reason}\n\nData pendaftaran Anda akan dihapus. Hubungi admin jika ada pertanyaan.\nTerima kasih.")
            notification_sent_reject = send_whatsapp_message(user_phone_for_notif, message_body_reject) 
            if notification_sent_reject: click.echo(click.style(f"  [WhatsApp] INFO: Notifikasi penolakan dikirim ke {user_phone_for_notif}.", fg='blue'))
            else: click.echo(click.style(f"  [WhatsApp] ERROR: Gagal kirim notifikasi penolakan ke {user_phone_for_notif}.", fg='red'))
        except Exception as e_wa_reject_cli:
            if hasattr(current_app, 'logger'):
                current_app.logger.error(f"Exception WA penolakan ke {user_phone_for_notif}: {e_wa_reject_cli}", exc_info=True) 
            click.echo(click.style(f"  [WhatsApp] ERROR: Exception: {e_wa_reject_cli}", fg='red'))
    elif not user_phone_for_notif: click.echo(click.style("  [WhatsApp] INFO: Tidak ada nomor telepon, notifikasi dilewati.", fg='yellow'))
    elif not WHATSAPP_AVAILABLE: click.echo(click.style("  [WhatsApp] INFO: Klien WhatsApp tidak tersedia, notifikasi dilewati.", fg='yellow'))

    try: 
        db.session.delete(user_to_reject)
        db.session.commit()
        if hasattr(current_app, 'logger'):
            current_app.logger.info(f"User REJECTED and DELETED: ID={user_id_for_log}, Phone={user_phone_for_notif}, Name='{user_full_name_for_log}'. Admin ID: {admin_id_for_log if admin_performing_rejection else 'System'}.") 
        click.echo(click.style(f"\nSUKSES: Pengguna '{user_full_name_for_log}' ({user_phone_for_notif}) DITOLAK & DIHAPUS dari database.", fg='green', bold=True))
        if not notification_sent_reject and WHATSAPP_AVAILABLE and user_phone_for_notif:
            click.echo(click.style("  -> PERINGATAN: Notifikasi WA penolakan GAGAL terkirim.", fg='yellow'))
    except Exception as e_db_reject:
        db.session.rollback()
        if hasattr(current_app, 'logger'):
            current_app.logger.error(f"Error reject/delete user {user_phone_for_notif} from DB: {e_db_reject}", exc_info=True) 
        click.echo(click.style(f"\nERROR DB: Gagal menolak/menghapus pengguna: {e_db_reject}", fg='red'))


# --- Perintah delete ---
@user_cli_bp.command('delete', help="Menghapus pengguna (PERMANEN) dari DB & Mikrotik (jika ada).")
@click.argument('phone_number', type=str)
@click.option('--admin-id', '-a', type=str, default=None, help="UUID Admin yang melakukan aksi (opsional, untuk pencatatan).")
@click.option('--force', '-f', is_flag=True, help="Lewati konfirmasi penghapusan.")
def delete_user(phone_number, admin_id, force):
    if not MODELS_AVAILABLE: click.echo(click.style("ERROR: Model User tidak dimuat.", fg='red')); return

    admin_performing_deletion = None; admin_id_for_log_del = "Tidak Diketahui"
    if admin_id:
        try:
            admin_uuid_del = uuid.UUID(admin_id)
            admin_performing_deletion = db.session.get(User, admin_uuid_del) 
            if not admin_performing_deletion : click.echo(click.style(f"WARNING: Admin ID '{admin_id}' tidak ditemukan.", fg='yellow'))
            elif not admin_performing_deletion.role_is_admin(): 
                click.echo(click.style(f"WARNING: Pengguna '{admin_performing_deletion.full_name}' bukan Admin.", fg='yellow')) 
                admin_performing_deletion = None
            else: admin_id_for_log_del = str(admin_performing_deletion.id) 
        except ValueError: click.echo(click.style(f"WARNING: Format UUID --admin-id salah: '{admin_id}'.", fg='yellow'))
        except AttributeError: click.echo(click.style("WARNING: Tidak dapat verifikasi role admin.", fg='yellow'))

    try: normalized_phone = normalize_phone_for_cli(phone_number)
    except click.BadParameter as e: click.echo(click.style(f"ERROR: {e.message}", fg='red')); return

    user_to_delete = db.session.execute(db.select(User).filter_by(phone_number=normalized_phone)).scalar_one_or_none() 
    if not user_to_delete: click.echo(click.style(f"ERROR: Pengguna '{normalized_phone}' tidak ditemukan.", fg='red')); return

    if not force:
        click.echo(click.style(f"\nDETAIL PENGGUNA AKAN DIHAPUS PERMANEN:", fg='red', bold=True))
        click.echo(f"  ID: {user_to_delete.id}, Nama: {user_to_delete.full_name}, Telp: {user_to_delete.phone_number}") 
        click.echo(f"  Role: {user_to_delete.role.value}, Status: {user_to_delete.approval_status.value}, Aktif: {'Ya' if user_to_delete.is_active else 'Tidak'}") 
        click.echo(click.style("\nPERINGATAN PENTING:", fg='yellow', bold=True))
        click.echo(click.style("  - Menghapus dari DATABASE aplikasi.", fg='yellow'))
        click.echo(click.style("  - MENCOBA menghapus dari MIKROTIK.", fg='yellow'))
        click.confirm(click.style("\nAnda YAKIN MENGHAPUS PERMANEN pengguna ini dari DB dan Mikrotik?", fg='red', underline=True, bold=True), abort=True)

    user_id_log = str(user_to_delete.id); user_phone_log = user_to_delete.phone_number; user_name_log = user_to_delete.full_name 
    mikrotik_username_to_delete = format_to_local_phone(user_phone_log) 

    mikrotik_deletion_attempted = False; mikrotik_deletion_successful = False; mikrotik_deletion_message = "Klien Mikrotik tidak tersedia/username tidak valid."
    if MIKROTIK_CLIENT_AVAILABLE and mikrotik_username_to_delete: 
        click.echo(click.style(f"\n  [Mikrotik] INFO: Mencoba hapus '{mikrotik_username_to_delete}' dari Mikrotik...", fg='cyan'))
        mikrotik_deletion_attempted = True; mikrotik_conn_pool_del = None
        try:
            mikrotik_conn_pool_del = get_mikrotik_connection() 
            if mikrotik_conn_pool_del:
                mikrotik_deletion_successful, mikrotik_deletion_message = delete_hotspot_user(connection_pool=mikrotik_conn_pool_del, username=mikrotik_username_to_delete) 
                if mikrotik_deletion_successful: click.echo(click.style(f"  [Mikrotik] SUKSES: {mikrotik_deletion_message}", fg='green'))
                else: click.echo(click.style(f"  [Mikrotik] WARNING: Gagal hapus/tidak ditemukan. Pesan: {mikrotik_deletion_message}", fg='yellow'))
            else:
                click.echo(click.style("  [Mikrotik] ERROR: Gagal koneksi Mikrotik.", fg='red'))
                mikrotik_deletion_message = "Koneksi Mikrotik gagal."
        except Exception as e_mt_delete_cli:
            if hasattr(current_app, 'logger'):
                current_app.logger.error(f"Exception hapus user '{mikrotik_username_to_delete}' dari Mikrotik: {e_mt_delete_cli}", exc_info=True) 
            click.echo(click.style(f"  [Mikrotik] ERROR: Exception: {e_mt_delete_cli}", fg='red'))
            mikrotik_deletion_message = str(e_mt_delete_cli)
    elif not mikrotik_username_to_delete: click.echo(click.style("  [Mikrotik] INFO: Username Mikrotik tidak valid, dilewati.", fg='yellow'))

    db_deletion_successful = False
    try: 
        db.session.delete(user_to_delete)
        db.session.commit()
        db_deletion_successful = True
        if hasattr(current_app, 'logger'):
            current_app.logger.info(f"User DELETED from DB: ID={user_id_log}, Phone={user_phone_log}, Name='{user_name_log}'. Mikrotik: attempted={mikrotik_deletion_attempted}, success={mikrotik_deletion_successful} ('{mikrotik_deletion_message}'). Admin ID: {admin_id_for_log_del if admin_performing_deletion else 'System/CLI'}.") 
        click.echo(click.style(f"\nSUKSES: Pengguna '{user_name_log}' ({user_phone_log}) DIHAPUS dari database.", fg='green', bold=True))
    except Exception as e_db_delete_cli:
        db.session.rollback()
        if hasattr(current_app, 'logger'):
            current_app.logger.error(f"Error delete user {user_phone_log} from DB: {e_db_delete_cli}", exc_info=True) 
        click.echo(click.style(f"\nERROR DB: Gagal menghapus pengguna: {e_db_delete_cli}", fg='red'))

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
@click.argument('new_role', metavar='ROLE', type=click.Choice([r.value for r in UserRole] if MODELS_AVAILABLE else [], case_sensitive=False))
@click.option('--admin-id', '-a', type=str, default=None, help="UUID Admin yang melakukan aksi (opsional, untuk pencatatan).")
def set_user_role(phone_number, new_role, admin_id):
    if not MODELS_AVAILABLE: click.echo(click.style("ERROR: Model User/UserRole tidak dimuat.", fg='red')); return

    admin_performing_set_role = None; admin_id_for_log_sr = "Tidak Diketahui"
    if admin_id:
        try:
            admin_uuid_sr = uuid.UUID(admin_id)
            admin_performing_set_role = db.session.get(User, admin_uuid_sr) 
            if not admin_performing_set_role: click.echo(click.style(f"WARNING: Admin ID '{admin_id}' tidak ditemukan.", fg='yellow'))
            elif not admin_performing_set_role.role_is_admin(): 
                click.echo(click.style(f"WARNING: Pengguna '{admin_performing_set_role.full_name}' bukan Admin.", fg='yellow')) 
                admin_performing_set_role = None
            else: admin_id_for_log_sr = str(admin_performing_set_role.id) 
        except ValueError: click.echo(click.style(f"WARNING: Format UUID --admin-id salah: '{admin_id}'.", fg='yellow'))
        except AttributeError: click.echo(click.style("WARNING: Tidak dapat verifikasi role admin.", fg='yellow'))

    try:
        normalized_phone = normalize_phone_for_cli(phone_number)
        role_enum_to_set = UserRole(new_role.upper()) 
    except click.BadParameter as e: click.echo(click.style(f"ERROR: {e.message}", fg='red')); return
    except ValueError: click.echo(click.style(f"ERROR: Role '{new_role}' tidak valid.", fg='red')); return

    user_to_update_role = db.session.execute(db.select(User).filter_by(phone_number=normalized_phone)).scalar_one_or_none() 
    if not user_to_update_role: click.echo(click.style(f"ERROR: Pengguna '{normalized_phone}' tidak ditemukan.", fg='red')); return

    current_role_val = user_to_update_role.role.value if hasattr(user_to_update_role.role, 'value') else str(user_to_update_role.role) 
    if user_to_update_role.role == role_enum_to_set: 
        click.echo(click.style(f"INFO: Pengguna '{user_to_update_role.full_name}' sudah role '{current_role_val}'.", fg='yellow')); return 

    if role_enum_to_set in [UserRole.ADMIN, UserRole.SUPER_ADMIN] and not user_to_update_role.password_hash: 
        click.echo(click.style(f"PERINGATAN: Mengubah ke {role_enum_to_set.value} tapi password portal (hash) belum ada.", fg='yellow', bold=True)) 

    old_role_val = user_to_update_role.role.value 
    user_to_update_role.role = role_enum_to_set 
    user_to_update_role.updated_at = datetime.now(dt_timezone.utc) 

    try:
        db.session.commit()
        if hasattr(current_app, 'logger'):
            current_app.logger.info(f"User role updated: ID={user_to_update_role.id}, Phone={normalized_phone}, Name='{user_to_update_role.full_name}'. Old: {old_role_val}, New: {role_enum_to_set.value}. Admin ID: {admin_id_for_log_sr if admin_performing_set_role else 'System/CLI'}.") 
        click.echo(click.style(f"SUKSES: Role '{user_to_update_role.full_name}' ({normalized_phone}) diubah dari {old_role_val} ke {role_enum_to_set.value}.", fg='green')) 
    except Exception as e_db_set_role:
        db.session.rollback()
        if hasattr(current_app, 'logger'):
            current_app.logger.error(f"Error set-role untuk {normalized_phone}: {e_db_set_role}", exc_info=True) 
        click.echo(click.style(f"ERROR: Gagal ubah role: {e_db_set_role}", fg='red'))


# --- Perintah seed-usage ---
@user_cli_bp.command('seed-usage', help="Membuat data dummy kuota & pemakaian harian untuk user.")
@click.argument('phone_number', type=str)
@click.option('--quota-purchased', '-q', type=int, default=10240, show_default=True, help="Total kuota dibeli (MB). Default: 10GB.")
@click.option('--days', '-d', type=int, default=7, show_default=True, help="Jumlah hari ke belakang untuk data pemakaian.")
@click.option('--admin-id', '-a', type=str, default=None, help="UUID Admin yang melakukan aksi (opsional, untuk log).")
def seed_user_usage(phone_number, quota_purchased, days, admin_id):
    if not MODELS_AVAILABLE:
        click.echo(click.style("ERROR: Model User/DailyUsageLog tidak dapat dimuat.", fg='red')); return
    if not hasattr(db.session.query(DailyUsageLog), 'filter'): 
         click.echo(click.style("ERROR: Model DailyUsageLog tidak terdefinisi dengan benar.", fg='red')); return

    if quota_purchased <= 0:
        click.echo(click.style("ERROR: --quota-purchased harus lebih besar dari 0.", fg='red')); return
    if days <= 0:
        click.echo(click.style("ERROR: --days harus lebih besar dari 0.", fg='red')); return

    admin_performing_seed = None; admin_id_for_log_seed = "Tidak Diketahui"
    if admin_id:
        try:
            admin_uuid_seed = uuid.UUID(admin_id)
            admin_performing_seed = db.session.get(User, admin_uuid_seed) 
            if not admin_performing_seed: click.echo(click.style(f"WARNING: Admin ID '{admin_id}' tidak ditemukan.", fg='yellow'))
            elif not admin_performing_seed.role_is_admin(): 
                click.echo(click.style(f"WARNING: Pengguna '{admin_performing_seed.full_name}' bukan Admin.", fg='yellow')) 
                admin_performing_seed = None
            else: admin_id_for_log_seed = str(admin_performing_seed.id) 
        except (ValueError, AttributeError): click.echo(click.style(f"WARNING: Error memproses Admin ID: '{admin_id}'.", fg='yellow'))

    try:
        normalized_phone = normalize_phone_for_cli(phone_number)
    except click.BadParameter as e:
        click.echo(click.style(f"ERROR: {e.message}", fg='red')); return

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
        num_deleted = db.session.query(DailyUsageLog).filter( 
            DailyUsageLog.user_id == user_to_seed.id, 
            DailyUsageLog.log_date >= start_date, 
            DailyUsageLog.log_date <= today 
        ).delete(synchronize_session=False) 
        if num_deleted > 0:
             click.echo(click.style(f"  INFO: Menghapus {num_deleted} log pemakaian lama dalam rentang tanggal.", fg='blue'))
    except Exception as e_del_log:
         click.echo(click.style(f"  WARNING: Gagal menghapus log lama: {e_del_log}", fg='yellow'))

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
        log_msg_seed = f"User usage seeded: ID={user_to_seed.id}, Phone={normalized_phone}. Purchased={quota_purchased}MB, Used={total_generated_usage_mb:.2f}MB over {days} days. Admin ID: {admin_id_for_log_seed if admin_performing_seed else 'System/CLI'}." 
        if hasattr(current_app, 'logger'):
            current_app.logger.info(log_msg_seed) 
        click.echo(click.style(f"\nSUKSES: Data dummy dibuat untuk '{user_to_seed.full_name}'.", fg='green')) 
        click.echo(f"  Total Kuota Dibeli : {quota_purchased} MB")
        click.echo(f"  Total Kuota Terpakai: {total_generated_usage_mb:.2f} MB")
        click.echo(f"  Sisa Kuota         : {quota_purchased - total_generated_usage_mb:.2f} MB")
        click.echo(f"  Jumlah Log Harian  : {len(new_logs)} hari")

    except Exception as e_db_seed:
        db.session.rollback()
        if hasattr(current_app, 'logger'):
            current_app.logger.error(f"Error seeding usage for {normalized_phone}: {e_db_seed}", exc_info=True) 
        click.echo(click.style(f"\nERROR: Gagal menyimpan data dummy: {e_db_seed}", fg='red'))