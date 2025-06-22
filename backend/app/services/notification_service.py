# backend/app/services/notification_service.py
# VERSI FINAL: Integrasi otomatis link aplikasi ke dalam konteks notifikasi.

import json
from flask import current_app
from typing import Dict, Any

# Impor service baru kita
from app.services.config_service import get_app_links

TEMPLATE_FILE_PATH = "app/notifications/templates.json"
_templates_cache = None

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

def get_notification_message(template_key: str, context: Dict[str, Any] = None) -> str:
    if context is None:
        context = {}
        
    templates = _load_templates()
    template_string = templates.get(template_key)

    if not template_string:
        current_app.logger.warning(f"Kunci template notifikasi tidak ditemukan: '{template_key}'")
        return f"Peringatan: Template '{template_key}' tidak ditemukan."

    # --- PENYEMPURNAAN DI SINI ---
    # Ambil semua link dari config service
    app_links = get_app_links()
    
    # Buat konteks final dengan menggabungkan data spesifik dan link aplikasi
    # Gunakan nama placeholder yang lebih jelas: link_user_app, link_admin_app, dll.
    final_context = {
        "link_user_app": app_links.get("user_app", ""),
        "link_admin_app": app_links.get("admin_app", ""),
        "link_mikrotik_login": app_links.get("mikrotik_login", ""),
        "link_admin_app_change_password": app_links.get("admin_app_change_password", ""), # Tambahkan ini
        **context  # Gabungkan dengan konteks spesifik dari pemanggil
    }
    
    try:
        # Gunakan konteks final untuk memformat pesan
        return template_string.format(**final_context)
    except KeyError as e:
        current_app.logger.error(f"Placeholder hilang di konteks untuk template '{template_key}': {e}", exc_info=True)
        return f"Peringatan: Data untuk placeholder {e} pada template '{template_key}' tidak disediakan."