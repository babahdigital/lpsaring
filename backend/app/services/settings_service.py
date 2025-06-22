# backend/app/services/settings_service.py
import os
from typing import Optional, Dict, Set
from flask import current_app
from cryptography.fernet import Fernet, InvalidToken
import hashlib
import base64

from app.extensions import db
from app.infrastructure.db.models import ApplicationSetting

ENCRYPTED_KEYS: Set[str] = {
    'WHATSAPP_API_KEY', 'MIDTRANS_SERVER_KEY',
    'MIDTRANS_CLIENT_KEY', 'MIKROTIK_PASSWORD'
}
_fernet_instance = None

def _get_fernet() -> Fernet:
    global _fernet_instance
    if _fernet_instance is None:
        secret_key = current_app.config.get('SECRET_KEY')
        if not secret_key:
            raise ValueError("SECRET_KEY tidak disetel di konfigurasi aplikasi.")
        
        hasher = hashlib.sha256()
        hasher.update(secret_key.encode('utf-8'))
        derived_key = hasher.digest()
        fernet_key = base64.urlsafe_b64encode(derived_key)
        _fernet_instance = Fernet(fernet_key)
    return _fernet_instance

def get_setting(key: str, default: Optional[str] = None) -> Optional[str]:
    try:
        setting = db.session.get(ApplicationSetting, key)
        if setting:
            if setting.is_encrypted:
                if not setting.setting_value: return None
                try:
                    fernet = _get_fernet()
                    return fernet.decrypt(setting.setting_value.encode('utf-8')).decode('utf-8')
                except InvalidToken:
                    current_app.logger.error(f"Gagal mendekripsi pengaturan '{key}'. Token tidak valid.")
                    return None
            else:
                return setting.setting_value
        else:
            return os.getenv(key, default)
    except Exception as e:
        current_app.logger.error(f"Error saat mengambil pengaturan '{key}': {e}", exc_info=True)
        return os.getenv(key, default)

# [PENAMBAHAN] Fungsi yang sebelumnya hilang, untuk mengatasi AttributeError
def get_setting_as_int(key: str, default: int) -> int:
    """Mengambil nilai pengaturan sebagai integer dengan nilai default jika gagal."""
    value_str = get_setting(key, str(default))
    try:
        return int(value_str) if value_str is not None else default
    except (ValueError, TypeError):
        return default

def update_settings(settings_data: Dict[str, str]) -> None:
    """Mempersiapkan pembaruan pengaturan di dalam sesi TANPA commit."""
    fernet = _get_fernet()
    for key, value in settings_data.items():
        setting = db.session.get(ApplicationSetting, key)
        if not setting:
            setting = ApplicationSetting(setting_key=key)
            db.session.add(setting)
        if key in ENCRYPTED_KEYS:
            setting.is_encrypted = True
            setting.setting_value = fernet.encrypt(value.encode('utf-8')).decode('utf-8')
        else:
            setting.is_encrypted = False
            setting.setting_value = value