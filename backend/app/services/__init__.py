# backend/app/services/__init__.py
# VERSI FINAL - Disesuaikan dengan modul yang benar-benar ada

# Mengimpor setiap modul layanan yang ada agar bisa diakses dari paket 'services'
from . import config_service
from . import notification_service
from . import settings_service
from . import transaction_service

# __all__ mendefinisikan apa saja yang akan diimpor ketika seseorang
# menggunakan 'from app.services import *'.
# Semua nama yang tidak ada filenya telah dihapus.
__all__ = [
    'config_service',
    'notification_service',
    'settings_service',
    'transaction_service',
]