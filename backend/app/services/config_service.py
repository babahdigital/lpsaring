# backend/app/services/config_service.py
# Helper untuk mengambil konfigurasi aplikasi secara terpusat.

from flask import current_app
from typing import Dict

def get_app_links() -> Dict[str, str]:
    """
    Mengambil semua URL aplikasi dari konfigurasi .env.
    Mengembalikan dictionary yang berisi link-link tersebut.
    """
    return {
        "user_app": current_app.config.get('APP_LINK_USER', ''),
        "admin_app": current_app.config.get('APP_LINK_ADMIN', ''),
        "mikrotik_login": current_app.config.get('APP_LINK_MIKROTIK', '')
    }