# backend/app/services/user_management/helpers.py
# Modul ini berisi fungsi-fungsi pendukung umum yang digunakan oleh service lain.
import json
import secrets
import string
from flask import current_app
from typing import Tuple, Optional, Any, Callable
from datetime import datetime, timezone
import inspect # Import modul inspect untuk memeriksa signature fungsi

from app.extensions import db
from app.infrastructure.db.models import User, PromoEvent, PromoEventType, PromoEventStatus, AdminActionLog, AdminActionType

from app.services import settings_service
from app.infrastructure.gateways.mikrotik_client import get_mikrotik_connection
# Import juga activate_or_update_hotspot_user jika dipanggil langsung di sini
# from app.infrastructure.gateways.mikrotik_client import activate_or_update_hotspot_user # Contoh import

def _send_whatsapp_notification(user_phone: str, template_key: str, context: dict) -> bool:
    """Mengirim notifikasi WhatsApp jika diaktifkan."""
    try:
        from app.services.notification_service import get_notification_message
        from app.infrastructure.gateways.whatsapp_client import send_whatsapp_message
        
        if settings_service.get_setting('ENABLE_WHATSAPP_NOTIFICATIONS', 'False') == 'True':
            message_body = get_notification_message(template_key, context)
            if message_body:
                return send_whatsapp_message(user_phone, message_body)
    except Exception as e:
        current_app.logger.error(f"Failed to send WhatsApp notification for template {template_key}: {e}")
    return False

def _log_admin_action(admin: User, target_user: User, action_type: AdminActionType, details: dict):
    """Mencatat aksi admin ke log, tidak mencatat jika pelakunya adalah Superadmin."""
    if admin.is_super_admin_role:
        return
    db.session.add(AdminActionLog(admin_id=admin.id, target_user_id=target_user.id, action_type=action_type, details=json.dumps(details, default=str)))

def _generate_password(length=6, numeric_only=True) -> str:
    """Menghasilkan password acak."""
    characters = string.digits if numeric_only else string.ascii_letters + string.digits
    return "".join(secrets.choice(characters) for _ in range(length))

def _handle_mikrotik_operation(operation_func: Callable, **kwargs: Any) -> Tuple[bool, str]:
    """
    Menangani operasi Mikrotik dengan koneksi pool dan logging.
    Memetakan nama argumen kwargs yang mungkin berbeda dari parameter fungsi target.
    """
    try:
        with get_mikrotik_connection() as api_conn:
            if not api_conn:
                return False, "Gagal mendapatkan koneksi ke Mikrotik."
            
            # --- [START PERBAIKAN] ---
            # Dapatkan signature dari operation_func untuk mengetahui parameter yang diterimanya
            sig = inspect.signature(operation_func)
            
            # Buat dictionary baru untuk argumen yang akan diteruskan
            processed_kwargs = {}
            
            # Loop melalui parameter yang diharapkan oleh operation_func
            for param_name, param in sig.parameters.items():
                if param_name == 'api_connection':
                    continue # api_connection ditangani secara terpisah
                
                # Cek apakah parameter adalah **kwargs (VAR_KEYWORD)
                if param.kind == inspect.Parameter.VAR_KEYWORD:
                    # Jika fungsi menerima **kwargs, teruskan semua kwargs yang belum diproses
                    processed_kwargs.update(kwargs)
                    break
                
                # Penanganan khusus untuk nama argumen yang mungkin berbeda
                if param_name == 'session_timeout_seconds' and 'session_timeout' in kwargs:
                    # Jika fungsi mengharapkan 'session_timeout_seconds' tapi kwargs punya 'session_timeout'
                    processed_kwargs['session_timeout_seconds'] = kwargs['session_timeout']
                    # Hapus 'session_timeout' dari kwargs asli agar tidak diproses lagi jika ada **kwargs
                    if 'session_timeout' in kwargs:
                         del kwargs['session_timeout']
                elif param_name in kwargs:
                    # Jika nama parameter cocok langsung dengan kunci di kwargs
                    processed_kwargs[param_name] = kwargs[param_name]
                    # Hapus kunci dari kwargs asli setelah diproses
                    if param_name in kwargs:
                         del kwargs[param_name]
            
            # Jika operation_func tidak memiliki **kwargs tapi ada sisa di kwargs asli,
            # itu berarti ada argumen yang tidak diharapkan oleh fungsi target.
            # Ini adalah tempat yang baik untuk log peringatan.
            if not any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()) and kwargs:
                 current_app.logger.warning(f"Argumen tidak dikenal yang diteruskan ke {operation_func.__name__}: {kwargs.keys()}")

            return operation_func(api_connection=api_conn, **processed_kwargs)
            # --- [END PERBAIKAN] ---
    except Exception as e:
        current_app.logger.error(f"Mikrotik Error in {operation_func.__name__}: {e}", exc_info=True)
        return False, f"Error Mikrotik: {str(e)}"

def _get_active_bonus_registration_promo() -> Optional[PromoEvent]:
    """Mencari event promo BONUS_REGISTRATION yang aktif."""
    now = datetime.now(timezone.utc)
    return db.session.scalar(db.select(PromoEvent).where(
        PromoEvent.status == PromoEventStatus.ACTIVE,
        PromoEvent.event_type == PromoEventType.BONUS_REGISTRATION,
        PromoEvent.start_date <= now,
        db.or_(
            PromoEvent.end_date.is_(None),
            PromoEvent.end_date >= now
        )
    ).order_by(PromoEvent.created_at.desc()))