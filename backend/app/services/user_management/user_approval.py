# backend/app/services/user_management/user_approval.py
# VERSI FINAL: Dengan pemanggilan notifikasi yang sudah diperbaiki dan lengkap.

from flask import current_app
from sqlalchemy.exc import SQLAlchemyError
from datetime import datetime, timezone as dt_timezone

from app.extensions import db
from app.infrastructure.db.models import User, ApprovalStatus, AdminActionType
from app.services.notification_service import get_notification_message
from app.infrastructure.gateways.whatsapp_client import send_whatsapp_message
from app.infrastructure.gateways.mikrotik_client import get_mikrotik_connection, activate_or_update_hotspot_user
from app.utils.formatters import format_to_local_phone
from .common import log_admin_action, generate_and_hash_password, get_default_mikrotik_profile, get_default_mikrotik_server

def approve_user_account(user: User, admin: User) -> tuple[bool, str]:
    """
    Menyetujui akun pengguna, mengaktifkannya, membuat/memperbarui user di Mikrotik,
    dan mengirim notifikasi dengan detail login.
    """
    if user.approval_status == ApprovalStatus.APPROVED:
        return False, "Pengguna sudah dalam status disetujui."

    original_status = user.approval_status
    user.approval_status = ApprovalStatus.APPROVED
    user.is_active = True
    user.approved_at = datetime.now(dt_timezone.utc)
    user.approved_by_id = admin.id

    # Hasilkan password hotspot jika belum ada
    if not user.mikrotik_password:
        user.mikrotik_password = generate_and_hash_password(is_for_admin=False)

    hotspot_username = format_to_local_phone(user.phone_number)
    if not hotspot_username:
        return False, "Format nomor telepon pengguna tidak valid untuk Mikrotik."

    # Sinkronisasi ke Mikrotik
    try:
        with get_mikrotik_connection() as mikrotik_api:
            if not mikrotik_api:
                return False, "Gagal terhubung ke sistem hotspot. Persetujuan dibatalkan."

            mikrotik_profile = user.mikrotik_profile_name or get_default_mikrotik_profile()
            mikrotik_server = user.mikrotik_server_name or get_default_mikrotik_server()

            success_mt, msg_mt = activate_or_update_hotspot_user(
                api_connection=mikrotik_api,
                user_mikrotik_username=hotspot_username,
                mikrotik_profile_name=mikrotik_profile,
                hotspot_password=user.mikrotik_password,
                comment=f"Approved by {admin.full_name}",
                server=mikrotik_server
            )
            if success_mt:
                user.mikrotik_user_exists = True
            else:
                # Jika gagal di Mikrotik, batalkan seluruh proses persetujuan
                return False, f"Gagal sinkronisasi ke Mikrotik: {msg_mt}"
    except Exception as e:
        return False, f"Terjadi kesalahan saat koneksi ke Mikrotik: {str(e)}"

    # Pencatatan log aksi admin
    log_admin_action(
        admin_id=admin.id,
        target_user_id=user.id,
        action_type=AdminActionType.APPROVE_USER,
        details={"from_status": original_status.value, "to_status": "APPROVED"}
    )
    
    db.session.add(user)

    # --- [PERBAIKAN UTAMA DI SINI] ---
    # Mengirim notifikasi dengan template dan konteks yang benar
    try:
        # 1. Gunakan kunci template yang sudah distandardisasi
        template_key = 'user_approve_success'

        # 2. Siapkan dictionary 'context' dengan SEMUA placeholder yang dibutuhkan oleh template
        context_data = {
            'full_name': user.full_name,
            'hotspot_username': format_to_local_phone(user.phone_number),
            'hotspot_password': user.mikrotik_password  # Pastikan ini password plain text
        }
        
        # 3. Panggil service notifikasi dengan context yang lengkap
        message_body = get_notification_message(template_key, context_data)
        
        # 4. Kirim pesan WhatsApp
        send_whatsapp_message(user.phone_number, message_body)

    except Exception as e:
        current_app.logger.error(f"Gagal mengirim notifikasi persetujuan untuk user {user.id}: {e}", exc_info=True)
        # Jangan gagalkan seluruh proses jika hanya notifikasi yang gagal, cukup catat log
        pass
    # --- [AKHIR PERBAIKAN] ---

    return True, "Pengguna berhasil disetujui, diaktifkan, dan disinkronkan ke Mikrotik."


def reject_user_account(user: User, admin: User) -> tuple[bool, str]:
    """
    Menolak akun pengguna dan mengirim notifikasi penolakan.
    """
    if user.approval_status == ApprovalStatus.REJECTED:
        return False, "Pengguna sudah dalam status ditolak."

    original_status = user.approval_status
    user.approval_status = ApprovalStatus.REJECTED
    user.is_active = False
    user.rejected_at = datetime.now(dt_timezone.utc)
    user.rejected_by_id = admin.id
    
    log_admin_action(
        admin_id=admin.id,
        target_user_id=user.id,
        action_type=AdminActionType.REJECT_USER,
        details={"from_status": original_status.value, "to_status": "REJECTED"}
    )
    
    db.session.add(user)

    try:
        message_body = get_notification_message('user_reject_notification', {"full_name": user.full_name})
        send_whatsapp_message(user.phone_number, message_body)
    except Exception as e:
        current_app.logger.error(f"Gagal mengirim notifikasi penolakan untuk user {user.id}: {e}", exc_info=True)
        pass

    return True, "Pengguna berhasil ditolak."