# backend/app/services/notification_service.py (Disempurnakan dengan Tokenizer)
import json
import itsdangerous # [PENAMBAHAN] Impor library untuk token
from flask import current_app
from typing import Dict, Any, Optional

from app.services.config_service import get_app_links

TEMPLATE_FILE_PATH = "app/notifications/templates.json"
_templates_cache = None


def _format_quota_human_readable(remaining_mb: Any) -> str:
    try:
        value_mb = float(remaining_mb)
    except (TypeError, ValueError):
        return str(remaining_mb)

    if value_mb < 1024:
        if value_mb.is_integer():
            return f"{int(value_mb)} MB"
        return f"{value_mb:.2f} MB"

    value_gb = value_mb / 1024.0
    if value_gb.is_integer():
        return f"{int(value_gb)} GB"
    return f"{value_gb:.2f} GB"


def _normalize_link_value(value: Any, fallback: str = "") -> str:
    if value is None:
        return fallback
    value_str = str(value).strip()
    if not value_str or value_str.lower() == "none":
        return fallback
    return value_str

# --- [PENAMBAHAN BLOK BARU] ---
def _get_serializer() -> itsdangerous.URLSafeTimedSerializer:
    """Membuat instance serializer dengan secret key dari konfigurasi aplikasi."""
    secret_key = current_app.config.get('SECRET_KEY')
    if not secret_key:
        raise ValueError("SECRET_KEY tidak diatur di konfigurasi aplikasi.")
    # Salt digunakan untuk memastikan token ini hanya untuk invoice
    return itsdangerous.URLSafeTimedSerializer(secret_key, salt='temp-invoice-access')

def generate_temp_invoice_token(transaction_id: str) -> str:
    """Menghasilkan token aman berbatas waktu untuk akses invoice sementara."""
    s = _get_serializer()
    return s.dumps(str(transaction_id))

def verify_temp_invoice_token(token: str, max_age_seconds: int = 3600) -> Optional[str]:
    """Memverifikasi token invoice sementara dan mengembalikan ID transaksi jika valid."""
    s = _get_serializer()
    try:
        # Verifikasi token dengan masa berlaku (contoh: 1 jam)
        transaction_id = s.loads(token, max_age=max_age_seconds)
        return str(transaction_id)
    except (itsdangerous.SignatureExpired, itsdangerous.BadTimeSignature, itsdangerous.BadSignature):
        current_app.logger.warning(f"Percobaan akses invoice dengan token tidak valid atau kedaluwarsa: {token}")
        return None
# --- [AKHIR BLOK BARU] ---


def _load_templates() -> Dict[str, str]:
    global _templates_cache
    if _templates_cache is None or current_app.debug:
        try:
            with open(TEMPLATE_FILE_PATH, 'r', encoding='utf-8') as f:
                _templates_cache = json.load(f)
            if not current_app.debug:
                 current_app.logger.info("Template notifikasi berhasil dimuat ke cache.")
        except (FileNotFoundError, json.JSONDecodeError) as e:
            current_app.logger.error(f"Kritis: Gagal memuat file template notifikasi: {e}", exc_info=True)
            _templates_cache = {}
    return _templates_cache

def get_notification_message(template_key: str, context: Optional[Dict[str, Any]] = None) -> str:
    if context is None:
        context = {}
        
    templates = _load_templates()
    template_string = templates.get(template_key)

    if not template_string:
        current_app.logger.warning(f"Kunci template notifikasi tidak ditemukan: '{template_key}'")
        return f"Peringatan: Template '{template_key}' tidak ditemukan."

    app_links = get_app_links()
    
    link_user_app = _normalize_link_value(app_links.get("user_app", ""), "")
    link_admin_app = _normalize_link_value(app_links.get("admin_app", ""), "")
    link_mikrotik_login = _normalize_link_value(app_links.get("mikrotik_login", ""), link_user_app)
    link_admin_change = _normalize_link_value(app_links.get("admin_app_change_password", ""), link_admin_app)

    final_context = {
        "link_user_app": link_user_app,
        "link_admin_app": link_admin_app,
        "link_mikrotik_login": link_mikrotik_login,
        "link_admin_app_change_password": link_admin_change,
        **context
    }

    for key in ("link_user_app", "link_admin_app", "link_mikrotik_login", "link_admin_app_change_password"):
        final_context[key] = _normalize_link_value(final_context.get(key), final_context.get("link_user_app", ""))

    if "remaining_quota" not in final_context and "remaining_mb" in final_context:
        final_context["remaining_quota"] = _format_quota_human_readable(final_context.get("remaining_mb"))
    
    try:
        return template_string.format(**final_context)
    except KeyError as e:
        current_app.logger.error(f"Placeholder hilang di konteks untuk template '{template_key}': {e}", exc_info=True)
        return f"Peringatan: Data untuk placeholder {e} pada template '{template_key}' tidak disediakan."