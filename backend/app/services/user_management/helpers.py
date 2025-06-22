# backend/app/services/user_management/helpers.py
# Modul ini berisi fungsi-fungsi pendukung umum yang digunakan oleh service lain.
import json
import secrets
import string
from flask import current_app
from typing import Tuple, Optional, Any, Callable
from datetime import datetime, timezone

from app.extensions import db
from app.infrastructure.db.models import User, PromoEvent, PromoEventType, PromoEventStatus, AdminActionLog, AdminActionType

from app.services import settings_service
from app.infrastructure.gateways.mikrotik_client import get_mikrotik_connection

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
    """Menangani operasi Mikrotik dengan koneksi pool dan logging."""
    try:
        with get_mikrotik_connection() as api_conn:
            if api_conn:
                return operation_func(api_connection=api_conn, **kwargs)
            return False, "Gagal mendapatkan koneksi ke Mikrotik."
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