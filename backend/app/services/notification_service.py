# backend/app/services/notification_service.py
# pyright: reportArgumentType=false
import json
import itsdangerous
import os
import logging
from flask import current_app
from typing import Dict, Any, Optional

from app.services.config_service import get_app_links

logger = logging.getLogger(__name__)

_templates_cache = None
_template_file_path = None
_last_modified_time = 0.0

def _get_serializer() -> itsdangerous.URLSafeTimedSerializer:
    """Membuat instance serializer dengan secret key dari konfigurasi aplikasi."""
    secret_key = current_app.config.get('SECRET_KEY')
    if not secret_key:
        raise ValueError("SECRET_KEY tidak diatur di konfigurasi aplikasi.")
    return itsdangerous.URLSafeTimedSerializer(secret_key, salt='temp-invoice-access')

def generate_temp_invoice_token(transaction_id: str) -> str:
    """Menghasilkan token aman berbatas waktu untuk akses invoice sementara."""
    s = _get_serializer()
    return s.dumps(str(transaction_id))

def verify_temp_invoice_token(token: str, max_age_seconds: int = 3600) -> Optional[str]:
    """Memverifikasi token invoice sementara dan mengembalikan ID transaksi jika valid."""
    s = _get_serializer()
    try:
        transaction_id = s.loads(token, max_age=max_age_seconds)
        return str(transaction_id)
    except (itsdangerous.SignatureExpired, itsdangerous.BadTimeSignature, itsdangerous.BadSignature):
        logger.warning(f"Percobaan akses invoice dengan token tidak valid atau kedaluwarsa: {token}")
        return None

def _load_templates() -> Dict[str, str]:
    """
    Memuat atau memuat ulang template dari file JSON
    hanya jika file tersebut telah diubah, bukan setiap kali dalam mode debug.
    """
    global _templates_cache, _template_file_path, _last_modified_time

    if _template_file_path is None:
        # [PERBAIKAN] Menggunakan os.path.dirname dan os.path.abspath untuk mendapatkan
        # direktori file saat ini, lalu naik satu level untuk mencapai 'app'
        # dan masuk ke 'app/notifications'.
        current_dir = os.path.dirname(os.path.abspath(__file__))
        _template_file_path = os.path.join(current_dir, '..', '..', 'notifications', 'templates.json')
        # Alternatif, jika 'app' adalah root aplikasi dan 'notifications' ada di dalamnya:
        # _template_file_path = os.path.join(current_app.root_path, 'notifications', 'templates.json')
        # Namun, berdasarkan `ls -l /app/app/notifications/`, path relatif dari root_path
        # harusnya 'app/notifications'. Jadi, kita akan sesuaikan dengan itu.
        _template_file_path = os.path.join(current_app.root_path, 'app', 'notifications', 'templates.json')


    try:
        current_mod_time = os.path.getmtime(_template_file_path)

        if _templates_cache is None or current_mod_time > _last_modified_time:
            with open(_template_file_path, 'r', encoding='utf-8') as f:
                _templates_cache = json.load(f)
            _last_modified_time = current_mod_time
            logger.info("Template notifikasi berhasil dimuat ulang ke dalam cache.")

    except FileNotFoundError:
        logger.error(f"Kritis: File template notifikasi tidak ditemukan di '{_template_file_path}'", exc_info=True)
        _templates_cache = {}
    except json.JSONDecodeError as e:
        logger.error(f"Kritis: Gagal memuat file template karena format JSON tidak valid: {e}", exc_info=True)
        if _templates_cache is None:
             _templates_cache = {}

    return _templates_cache


def get_notification_message(template_key: str, context: Dict[str, Any] = None) -> str:
    """
    Menghasilkan pesan notifikasi dari template dan konteks yang diberikan.
    """
    if context is None:
        context = {}

    templates = _load_templates()
    template_string = templates.get(template_key)

    if not template_string:
        logger.warning(f"Kunci template notifikasi tidak ditemukan: '{template_key}'")
        return f"Peringatan Sistem: Template '{template_key}' tidak ditemukan."

    app_links = get_app_links()
    final_context = {
        "link_user_app": app_links.get("user_app", ""),
        "link_admin_app": app_links.get("admin_app", ""),
        "link_mikrotik_login": app_links.get("mikrotik_login", ""),
        "link_admin_app_change_password": app_links.get("admin_app_change_password", ""),
        **context
    }

    try:
        return template_string.format(**final_context)
    except KeyError as e:
        logger.error(f"Placeholder {e} hilang di konteks untuk template '{template_key}'.", exc_info=True)

        fallback_template_key = f"{template_key}_fallback"
        fallback_template = templates.get(fallback_template_key)

        if fallback_template:
            logger.warning(f"Menggunakan template fallback '{fallback_template_key}' karena placeholder hilang.")
            try:
                return fallback_template.format(**final_context)
            except KeyError:
                return "Pemberitahuan: Terjadi sedikit kendala saat kami mencoba mengirimkan detail notifikasi untuk Anda."

        return "Pemberitahuan: Terjadi kendala saat kami mencoba mengirimkan notifikasi. Tim kami telah diberitahu."