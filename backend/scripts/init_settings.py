# backend/app/scripts/init_settings.py
"""This script initializes default application settings."""
# pyright: reportCallIssue=false
import sys
import os
from app import create_app
from app.extensions import db
from app.infrastructure.db.models import ApplicationSetting

# Pengaturan default yang lengkap, termasuk semua untuk tema.
DEFAULT_SETTINGS = {
    # --- Pengaturan Aplikasi Umum ---
    'APP_NAME': 'Sobigidul',
    'MAX_FAILED_LOGIN_ATTEMPTS': '3',
    'LOGIN_LOCKOUT_DURATION': '300',
    'MAINTENANCE_MODE_ACTIVE': 'False',
    'MAINTENANCE_MODE_MESSAGE': 'Aplikasi sedang dalam perbaikan. Silakan coba lagi nanti.',
    'ENABLE_REGISTRATION': 'True',
    'BUSINESS_NAME': 'Sobigidul Hotspot',
    'BUSINESS_PHONE': '+62811580039',
    
    # --- Pengaturan Tema Lengkap untuk Frontend ---
    'THEME': 'dark',
    'SKIN': 'bordered',
    'APP_CONTENT_LAYOUT_NAV': 'horizontal',
    'APP_CONTENT_WIDTH': 'boxed',
    'FOOTER_TYPE': 'static',
    'NAVBAR_TYPE': 'sticky'
}

def init_settings():
    """Initialize default settings. Assumes tables are created."""
    # Gunakan create_app() untuk mendapatkan konteks aplikasi
    app = create_app(os.getenv('FLASK_CONFIG') or 'default')
    with app.app_context():
        try:
            for key, value in DEFAULT_SETTINGS.items():
                # Memeriksa apakah pengaturan dengan kunci 'key' sudah ada.
                setting = db.session.get(ApplicationSetting, key)
                # Jika tidak ada, maka buat baris baru di database.
                if not setting:
                    print(f"Creating setting: {key}")
                    new_setting = ApplicationSetting(setting_key=key, setting_value=value)
                    db.session.add(new_setting)
            
            db.session.commit()
            print("Successfully initialized default settings.")
                
        except Exception as e:
            print(f"FATAL: Error while initializing settings: {e}", file=sys.stderr)
            db.session.rollback()
            sys.exit(1)

if __name__ == '__main__':
    init_settings()