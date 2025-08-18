# backend/app/services/settings_service.py
# pyright: reportCallIssue=false

import os
from typing import Optional, Dict, Set
from flask import current_app
from cryptography.fernet import Fernet, InvalidToken
import hashlib
import base64

from app.extensions import db
from app.infrastructure.db.models import ApplicationSetting

# [PERBAIKAN] Kunci-kunci ini SANGAT PENTING untuk keamanan dan stabilitas aplikasi.
# Mereka TIDAK BOLEH diambil dari database. Harus selalu dari environment variable.
PROTECTED_KEYS: Set[str] = {
    'SECRET_KEY', 
    'JWT_SECRET_KEY',
    'ENCRYPTION_KEY' # Ditambahkan untuk praktik terbaik di masa depan
}

# Daftar kunci yang nilainya dienkripsi di dalam database.
ENCRYPTED_KEYS: Set[str] = {
    'WHATSAPP_API_KEY', 'MIDTRANS_SERVER_KEY',
    'MIDTRANS_CLIENT_KEY', 'MIKROTIK_PASSWORD'
}
_fernet_instance = None

def _get_fernet() -> Fernet:
    """Mendapatkan instance Fernet untuk enkripsi/dekripsi."""
    global _fernet_instance
    if _fernet_instance is None:
        # Menggunakan SECRET_KEY sebagai basis untuk kunci enkripsi adalah praktik umum,
        # namun pastikan nilainya kuat dan dikelola dengan aman.
        secret_key = current_app.config.get('SECRET_KEY')
        if not secret_key:
            raise ValueError("FATAL: SECRET_KEY tidak disetel di konfigurasi aplikasi.")
        
        # Menggunakan turunan hash dari SECRET_KEY untuk membuat kunci Fernet 32-byte.
        hasher = hashlib.sha256()
        hasher.update(secret_key.encode('utf-8'))
        derived_key = hasher.digest()
        fernet_key = base64.urlsafe_b64encode(derived_key)
        _fernet_instance = Fernet(fernet_key)
    return _fernet_instance

def get_setting(key: str, default: Optional[str] = None) -> Optional[str]:
    """
    Mengambil nilai pengaturan.
    Untuk kunci yang dilindungi (PROTECTED_KEYS), nilai HANYA diambil dari environment.
    Untuk kunci lain, nilai diambil dari database dengan fallback ke environment.
    """
    # [PERBAIKAN UTAMA] Jika kunci termasuk dalam daftar yang dilindungi,
    # langsung ambil dari environment dan hentikan proses.
    if key in PROTECTED_KEYS:
        return os.getenv(key, default)

    try:
        # Untuk kunci lain, coba ambil dari database terlebih dahulu.
        setting = db.session.get(ApplicationSetting, key)
        if setting:
            if setting.is_encrypted:
                if not setting.setting_value: return None
                try:
                    fernet = _get_fernet()
                    return fernet.decrypt(setting.setting_value.encode('utf-8')).decode('utf-8')
                except InvalidToken:
                    current_app.logger.error(f"Gagal mendekripsi pengaturan '{key}'. Token tidak valid atau kunci enkripsi berubah.")
                    return None # Kembalikan None jika dekripsi gagal
            else:
                return setting.setting_value
        else:
            # Jika tidak ada di DB, fallback ke environment.
            return os.getenv(key, default)
    except Exception as e:
        # Jika terjadi error saat akses DB, fallback ke environment.
        current_app.logger.error(f"Error saat mengambil pengaturan '{key}' dari DB: {e}", exc_info=True)
        return os.getenv(key, default)

def get_setting_as_int(key: str, default: int) -> int:
    """Mengambil nilai pengaturan sebagai integer dengan nilai default jika gagal."""
    value_str = get_setting(key, str(default))
    try:
        return int(value_str) if value_str is not None else default
    except (ValueError, TypeError):
        return default

def update_settings(settings_data: Dict[str, str]) -> None:
    """
    Memperbarui beberapa pengaturan dalam satu transaksi database.
    Mencegah pembaruan pada kunci yang dilindungi.
    """
    fernet = _get_fernet()
    for key, value in settings_data.items():
        # [PERBAIKAN] Jangan biarkan kunci yang dilindungi diubah dari aplikasi.
        if key in PROTECTED_KEYS:
            current_app.logger.warning(f"Upaya untuk mengubah pengaturan yang dilindungi '{key}' diabaikan.")
            continue

        setting = db.session.get(ApplicationSetting, key)
        if not setting:
            setting = ApplicationSetting(setting_key=key)
            db.session.add(setting)
        
        if key in ENCRYPTED_KEYS:
            setting.is_encrypted = True
            setting.setting_value = fernet.encrypt(value.encode('utf-8')).decode('utf-8') if value else ''
        else:
            setting.is_encrypted = False
            setting.setting_value = value