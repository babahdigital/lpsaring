# backend/config.py - VERSI FINAL DENGAN KONFIGURASI CORS YANG BENAR

import os
import ast
import warnings
from datetime import timedelta
from celery.schedules import crontab

# Function to load environment variables from .env.override
def load_env_override():
    """Manually load .env.override file to ensure it takes precedence"""
    import os
    from pathlib import Path
    
    override_path = Path('.env.override')
    if override_path.exists():
        print(f"Loading environment overrides from .env.override")
        with open(override_path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                    
                if '=' in line:
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip().strip('"\'')
                    if key:  # Skip empty keys
                        os.environ[key] = value
                        print(f"  Set {key}={value}")

# Load .env.override at import time
load_env_override()


# --- Helper untuk Membaca Environment Variable ---
def get_env_bool(var_name, default='False'):
    return os.environ.get(var_name, default).lower() in ('true', '1', 't', 'yes')

def get_env_int(var_name, default):
    try:
        return int(os.environ.get(var_name, str(default)))
    except (ValueError, TypeError):
        warnings.warn(f"PERINGATAN: {var_name} bukan integer, gunakan default {default}.")
        return default

def get_env_list(var_name: str, default: str = '[]') -> list:
    """
    Mendapatkan nilai daftar (list) dari environment variable.
    
    Menerima format:
    1. JSON array string: ["item1", "item2"]
    2. String biasa (dikembalikan sebagai item tunggal): "item1"  
    3. Comma-separated values: "item1,item2,item3"
    """
    value_str = os.environ.get(var_name, default)
    if not value_str:
        return []
    
    # Handle case when value is just a quoted string like "0817701083"
    if value_str.startswith('"') and value_str.endswith('"') and value_str.count('"') == 2:
        # Remove quotes and return single item list
        return [value_str.strip('"')]
        
    try:
        # Try to evaluate as literal (for JSON arrays)
        evaluated = ast.literal_eval(value_str)
        if isinstance(evaluated, list):
            return evaluated
        elif evaluated:  # If it's a single non-empty value
            return [str(evaluated)]
    except (ValueError, SyntaxError):
        if isinstance(value_str, str) and value_str.strip():
            # [PENYEMPURNAAN] Memisahkan string berdasarkan koma
            items = [item.strip() for item in value_str.split(',') if item.strip()]
            if items:
                return items
    
    warnings.warn(f"PERINGATAN: Nilai untuk {var_name} ('{value_str}') tidak dapat di-parse sebagai list. Menggunakan list kosong.")
    return []

class Config:
    """Konfigurasi dasar aplikasi Flask."""

    # --- Konfigurasi Umum Flask & Keamanan ---
    SECRET_KEY = os.environ.get('SECRET_KEY')
    JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY')
    JWT_ALGORITHM = os.environ.get('JWT_ALGORITHM', 'HS256')

    _lax = os.environ.get('ALLOW_LAX_CONFIG_IMPORT') == '1'
    if not SECRET_KEY:
        if _lax:
            SECRET_KEY = 'dev-placeholder-secret'
        else:
            raise ValueError("FATAL: SECRET_KEY tidak ditemukan di environment variables.")
    if not JWT_SECRET_KEY:
        if _lax:
            JWT_SECRET_KEY = 'dev-placeholder-jwt'
        else:
            raise ValueError("FATAL: JWT_SECRET_KEY tidak ditemukan di environment variables.")

    _expires_minutes = get_env_int('JWT_ACCESS_TOKEN_EXPIRES_MINUTES', 15)
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(minutes=_expires_minutes)
    # Refresh token expiry (default 30 hari)
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=get_env_int('JWT_REFRESH_TOKEN_EXPIRES_DAYS', 30))
    # Aktifkan lokasi token di header (Bearer) dan cookies untuk refresh token
    JWT_TOKEN_LOCATION = ["headers", "cookies"]
    # Konfigurasi cookie untuk refresh token
    JWT_REFRESH_COOKIE_NAME = os.environ.get('JWT_REFRESH_COOKIE_NAME', 'refresh_token')
    JWT_COOKIE_SECURE = get_env_bool('JWT_COOKIE_SECURE', 'False')
    JWT_COOKIE_SAMESITE = os.environ.get('JWT_COOKIE_SAMESITE', 'Lax')
    # Matikan CSRF untuk cookie JWT bila hanya dipakai same-site melalui reverse proxy yang sama
    JWT_COOKIE_CSRF_PROTECT = get_env_bool('JWT_COOKIE_CSRF_PROTECT', 'False')

    # --- Konfigurasi Proxy (Nginx) & Logging ---
    PROXYFIX_X_FOR = get_env_int('PROXYFIX_X_FOR', 1)
    PROXYFIX_X_PROTO = get_env_int('PROXYFIX_X_PROTO', 1)
    LOG_TO_FILE = get_env_bool('LOG_TO_FILE', 'False')
    LOG_DIR = os.environ.get('LOG_DIR', 'logs')
    LOG_FILENAME = os.environ.get('LOG_FILENAME', 'app.log')
    LOG_MAX_BYTES = get_env_int('LOG_MAX_BYTES', 10485760)
    LOG_BACKUP_COUNT = get_env_int('LOG_BACKUP_COUNT', 5)
    LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO').upper()

    # --- Konfigurasi Database (SQLAlchemy) ---
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL')
    if not SQLALCHEMY_DATABASE_URI:
        if _lax:
            SQLALCHEMY_DATABASE_URI = 'sqlite:///__lax_config__.db'
        else:
            raise ValueError("ERROR: Konfigurasi database (DATABASE_URL) tidak ditemukan.")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ECHO = get_env_bool('SQLALCHEMY_ECHO', 'False')

    # --- Konfigurasi Redis Terpusat ---
    REDIS_HOST = os.environ.get('REDIS_HOST', 'redis')
    REDIS_PORT = get_env_int('REDIS_PORT', 6379)
    _redis_password = os.environ.get('REDIS_PASSWORD')
    REDIS_PASSWORD = _redis_password if _redis_password and _redis_password.lower() != 'null' else None
    _redis_auth = f":{REDIS_PASSWORD}@" if REDIS_PASSWORD else ""
    
    RATELIMIT_STORAGE_URI = os.environ.get('RATELIMIT_STORAGE_URI', f"redis://{_redis_auth}{REDIS_HOST}:{REDIS_PORT}/0")
    REDIS_URL_OTP = os.environ.get('REDIS_URL_OTP', f"redis://{_redis_auth}{REDIS_HOST}:{REDIS_PORT}/1")

    # --- Konfigurasi Celery ---
    broker_url = os.environ.get('CELERY_BROKER_URL', f"redis://{_redis_auth}{REDIS_HOST}:{REDIS_PORT}/2")
    result_backend = os.environ.get('CELERY_RESULT_BACKEND', f"redis://{_redis_auth}{REDIS_HOST}:{REDIS_PORT}/3")
    beat_schedule = {
        "check-low-quota-hourly": {
            "task": "check_low_quota_task",
            "schedule": timedelta(hours=1),
        },
        "sync-all-users-status-every-5-minutes": {
            "task": "tasks.dispatch_all_users_sync",
            "schedule": timedelta(minutes=5),
        },
        "sync-bypass-address-list-every-30-minutes": {
            "task": "tasks.sync_bypass_address_list",
            "schedule": timedelta(minutes=30),
        },
        "cleanup-stale-devices-daily": {
            "task": "tasks.cleanup_stale_devices",
            "schedule": timedelta(days=1),
        },
        "validate-device-consistency-every-6-hours": {
            "task": "tasks.validate_device_consistency",
            "schedule": timedelta(hours=6),
        },
        "audit-address-list-hourly": {
            "task": "tasks.audit_address_list_consistency",
            "schedule": timedelta(hours=1),
        },
        "cleanup-stale-static-leases-daily": {
            "task": "tasks.cleanup_stale_static_leases",
            "schedule": timedelta(days=1),
        },
        "repair-address-list-mismatch-every-2-hours": {
            "task": "tasks.repair_stale_address_list_entries",
            "schedule": timedelta(hours=2),
        },
        # Dynamic warm MAC cache (interval configurable; applied at runtime override if needed)
        "warm-mac-cache-periodic": {
            "task": "tasks.warm_mac_cache",
            "schedule": timedelta(minutes=get_env_int('WARM_MAC_INTERVAL_MINUTES', 5)),
        },
    }
    
    task_track_started = True
    task_serializer = "json"
    accept_content = ["json"]
    result_serializer = "json"
    timezone = "Asia/Makassar"
    enable_utc = False

    # --- Konfigurasi Layanan Spesifik ---
    OTP_EXPIRE_SECONDS = get_env_int('OTP_EXPIRE_SECONDS', 300)
    RATELIMIT_DEFAULT = os.environ.get('API_RATE_LIMIT', '200 per day;50 per hour;10 per minute')
    RATELIMIT_ENABLED = get_env_bool('RATELIMIT_ENABLED', 'True')
    
    # --- Konfigurasi Pihak Ketiga ---
    MIDTRANS_SERVER_KEY = os.environ.get('MIDTRANS_SERVER_KEY')
    MIDTRANS_CLIENT_KEY = os.environ.get('MIDTRANS_CLIENT_KEY')
    MIDTRANS_IS_PRODUCTION = get_env_bool('MIDTRANS_IS_PRODUCTION', 'False')
    
    WHATSAPP_API_URL = os.environ.get('WHATSAPP_API_URL', 'https://api.fonnte.com/send')
    WHATSAPP_API_KEY = os.environ.get('WHATSAPP_API_KEY')
    ENABLE_WHATSAPP_NOTIFICATIONS = get_env_bool('ENABLE_WHATSAPP_NOTIFICATIONS', 'True')
    
    # --- Konfigurasi MikroTik ---
    MIKROTIK_HOST = os.environ.get('MIKROTIK_HOST')
    MIKROTIK_USERNAME = os.environ.get('MIKROTIK_USERNAME')
    MIKROTIK_PASSWORD = os.environ.get('MIKROTIK_PASSWORD')
    MIKROTIK_PORT = get_env_int('MIKROTIK_PORT', 8728)
    MIKROTIK_USE_SSL = get_env_bool('MIKROTIK_USE_SSL', 'False')
    MIKROTIK_PLAIN_TEXT_LOGIN = get_env_bool('MIKROTIK_PLAIN_TEXT_LOGIN', 'True')

    MIKROTIK_PROFILE_AKTIF = os.environ.get('MIKROTIK_PROFILE_AKTIF', 'profile-aktif')
    MIKROTIK_PROFILE_FUP = os.environ.get('MIKROTIK_PROFILE_FUP', 'profile-fup')
    MIKROTIK_PROFILE_HABIS = os.environ.get('MIKROTIK_PROFILE_HABIS', 'profile-habis')
    MIKROTIK_PROFILE_BLOKIR = os.environ.get('MIKROTIK_PROFILE_BLOKIR', 'profile-blokir')
    MIKROTIK_PROFILE_UNLIMITED = os.environ.get('MIKROTIK_PROFILE_UNLIMITED', 'profile-unlimited')
    MIKROTIK_PROFILE_INACTIVE = os.environ.get('MIKROTIK_PROFILE_INACTIVE', 'inactive')
    FUP_THRESHOLD_PERCENT = get_env_int('FUP_THRESHOLD_PERCENT', 85)
    FUP_HABIS_NOTIF_COOLDOWN_HOURS = get_env_int('FUP_HABIS_NOTIF_COOLDOWN_HOURS', 24)
    MIKROTIK_SERVER_USER = os.environ.get('MIKROTIK_SERVER_USER', 'srv-user')
    MIKROTIK_SERVER_KOMANDAN = os.environ.get('MIKROTIK_SERVER_KOMANDAN', 'srv-komandan')
    MIKROTIK_SERVER_ADMIN = os.environ.get('MIKROTIK_SERVER_ADMIN', 'srv-admin')
    MIKROTIK_SERVER_SUPER_ADMIN = os.environ.get('MIKROTIK_SERVER_SUPER_ADMIN', 'srv-support')
    MIKROTIK_FUP_ADDRESS_LIST = os.environ.get('MIKROTIK_FUP_ADDRESS_LIST', 'klient_fup')
    MIKROTIK_HABIS_ADDRESS_LIST = os.environ.get('MIKROTIK_HABIS_ADDRESS_LIST', 'klient_habis')
    MIKROTIK_BLOKIR_ADDRESS_LIST = os.environ.get('MIKROTIK_BLOKIR_ADDRESS_LIST', 'klient_blokir')
    MIKROTIK_BYPASS_ADDRESS_LIST = os.environ.get('MIKROTIK_BYPASS_ADDRESS_LIST', 'bypass_client')
    # Address list untuk pengguna tidak aktif (tanpa paket/masa aktif habis)
    MIKROTIK_INACTIVE_ADDRESS_LIST = os.environ.get('MIKROTIK_INACTIVE_ADDRESS_LIST', 'inactive_client')
    MIKROTIK_DHCP_SERVER_NAME = os.environ.get('MIKROTIK_DHCP_SERVER_NAME', None)
    ENABLE_IP_BINDING_LEGACY = get_env_bool('ENABLE_IP_BINDING_LEGACY', 'False')
    REQUIRE_EXPLICIT_DEVICE_AUTH = get_env_bool('REQUIRE_EXPLICIT_DEVICE_AUTH', 'True')

    # --- Konfigurasi Aplikasi & Mode Uji Coba ---
    FRONTEND_URL = os.environ.get('FRONTEND_URL', 'http://localhost:3000')
    # [PERBAIKAN] Membaca CORS_ADDITIONAL_ORIGINS menggunakan helper get_env_list
    CORS_ADDITIONAL_ORIGINS = get_env_list('CORS_ADDITIONAL_ORIGINS', '[]')
    APP_PUBLIC_BASE_URL = os.environ.get('APP_PUBLIC_BASE_URL')
    APP_LINK_USER = os.environ.get('APP_LINK_USER', 'http://localhost:3000')
    APP_LINK_ADMIN = os.environ.get('APP_LINK_ADMIN', 'http://localhost:3000/admin')
    APP_LINK_MIKROTIK = os.environ.get('APP_LINK_MIKROTIK', 'http://10.5.50.1/login')
    APP_LINK_ADMIN_CHANGE_PASSWORD = os.environ.get('APP_LINK_ADMIN_CHANGE_PASSWORD', 'http://localhost:3000/akun')
    ENABLE_ADMIN_ROUTES = get_env_bool('ENABLE_ADMIN_ROUTES', 'True')
    SYNC_TEST_MODE_ENABLED = get_env_bool('SYNC_TEST_MODE_ENABLED', 'False')
    SYNC_TEST_PHONE_NUMBERS = get_env_list('SYNC_TEST_PHONE_NUMBERS', "[]")
    MIKROTIK_SERVER_TESTING = os.environ.get('MIKROTIK_SERVER_TESTING', 'all')
    # MIKROTIK_PROFILE_TESTING tidak digunakan lagi, gunakan MIKROTIK_PROFILE_AKTIF untuk profile testing
    
    MIKROTIK_MAC_LOOKUP_ENABLE_HOST = get_env_bool('MIKROTIK_MAC_LOOKUP_ENABLE_HOST', 'True')
    MIKROTIK_MAC_LOOKUP_ENABLE_DHCP_LEASE = get_env_bool('MIKROTIK_MAC_LOOKUP_ENABLE_DHCP_LEASE', 'True')
    
    # --- [NEW] Dynamic Network Configuration for Production ---
    # These replace all hardcore IP values throughout the application
    NETWORK_PROXY_IPS = get_env_list('NETWORK_PROXY_IPS', '["10.0.0.1","172.17.0.1","172.18.0.1"]')
    NETWORK_PRIVATE_RANGES = get_env_list('NETWORK_PRIVATE_RANGES', '["10.","192.168.","172.16.","172.17.","172.18."]')
    NETWORK_ALLOW_LOCALHOST = get_env_bool('NETWORK_ALLOW_LOCALHOST', 'True')
    NETWORK_DETECTION_TIMEOUT = get_env_int('NETWORK_DETECTION_TIMEOUT', 5)
    MAC_LOOKUP_CACHE_TTL = get_env_int('MAC_LOOKUP_CACHE_TTL', 300)
    BACKEND_MAC_LOOKUP_ENABLED = get_env_bool('BACKEND_MAC_LOOKUP_ENABLED', 'True')
    # Simplified MAC detection tuning (added by architecture 2.0 simplification)
    MAC_POSITIVE_GRACE_SECONDS = get_env_int('MAC_POSITIVE_GRACE_SECONDS', 90)  # in-memory grace reuse window
    MAC_NEGATIVE_TTL = get_env_int('MAC_NEGATIVE_TTL', 20)  # redis negative cache seconds (fast retry)
    MAC_ARP_TTL = get_env_int('MAC_ARP_TTL', 180)
    # MikroTik connection & lookup tuning
    MIKROTIK_CONNECT_TIMEOUT_SECONDS = get_env_int('MIKROTIK_CONNECT_TIMEOUT_SECONDS', 3)
    MIKROTIK_READ_TIMEOUT_SECONDS = get_env_int('MIKROTIK_READ_TIMEOUT_SECONDS', 5)
    # Default DHCP server name (optional). If set, static leases will use this when server cannot be inferred.
    MIKROTIK_DEFAULT_DHCP_SERVER = os.environ.get('MIKROTIK_DEFAULT_DHCP_SERVER')
    # Enforce explicit device authorization (no auto-bypass/lease in legacy/no-JWT mode)
    REQUIRE_EXPLICIT_DEVICE_AUTH = get_env_bool('REQUIRE_EXPLICIT_DEVICE_AUTH', 'True')
    # Maximum authorized devices per user
    MAX_DEVICES_PER_USER = get_env_int('MAX_DEVICES_PER_USER', 3)
    MIKROTIK_LOOKUP_PARALLEL = get_env_bool('MIKROTIK_LOOKUP_PARALLEL', 'False')  # enable future parallel host/dhcp/arp
    MIKROTIK_FORCE_REFRESH_CLEAR_GRACE = get_env_bool('MIKROTIK_FORCE_REFRESH_CLEAR_GRACE', 'True')
    # Batas maksimum entry in-memory grace cache (agar hemat memory saat banyak client)
    MIKROTIK_GRACE_MAX_ENTRIES = get_env_int('MIKROTIK_GRACE_MAX_ENTRIES', 1000)
    # Multi-pool size untuk koneksi MikroTik (round-robin). 1 = single pool.
    MIKROTIK_POOL_SIZE = get_env_int('MIKROTIK_POOL_SIZE', 1)
    # Throttling logging koneksi / error repetitif
    LOG_SUPPRESSION_THRESHOLD = get_env_int('LOG_SUPPRESSION_THRESHOLD', 20)
    LOG_SUPPRESSION_WINDOW_SECONDS = get_env_int('LOG_SUPPRESSION_WINDOW_SECONDS', 300)
    # Adaptive grace tuning: minimal grace ketika sering force_refresh
    MAC_GRACE_MIN_SECONDS = get_env_int('MAC_GRACE_MIN_SECONDS', 15)
    MAC_GRACE_ADAPT_DECAY = get_env_int('MAC_GRACE_ADAPT_DECAY', 5)  # pengurangan per X force
    MAC_GRACE_FORCE_WINDOW_SECONDS = get_env_int('MAC_GRACE_FORCE_WINDOW_SECONDS', 300)
    # Metrics toggle
    ENABLE_INTERNAL_METRICS = get_env_bool('ENABLE_INTERNAL_METRICS', 'True')
    METRICS_BASIC_AUTH = os.environ.get('METRICS_BASIC_AUTH')  # format user:pass (opsional)
    # Metrics latency buckets (ms) comma separated, fallback default
    METRICS_LATENCY_BUCKETS = os.environ.get('METRICS_LATENCY_BUCKETS', '5,10,25,50,100,250,500,1000,2000')
    # Warm MAC cache task settings
    WARM_MAC_ENABLED = get_env_bool('WARM_MAC_ENABLED', 'True')
    WARM_MAC_BATCH_SIZE = get_env_int('WARM_MAC_BATCH_SIZE', 50)
    WARM_MAC_INTERVAL_MINUTES = get_env_int('WARM_MAC_INTERVAL_MINUTES', 5)
    # Address list sync batching
    ADDRESS_LIST_BATCH_SIZE = get_env_int('ADDRESS_LIST_BATCH_SIZE', 50)
    ADDRESS_LIST_BATCH_SLEEP_MS = get_env_int('ADDRESS_LIST_BATCH_SLEEP_MS', 30)
    # Redis pipelining
    REDIS_PIPELINE_BATCH_SIZE = get_env_int('REDIS_PIPELINE_BATCH_SIZE', 0)  # 0=disabled
    # Optional pseudo async lookup mode (thread offload)
    MIKROTIK_ASYNC_MODE = get_env_bool('MIKROTIK_ASYNC_MODE', 'False')
    # Suppress noisy API docs skip-route logs (aktifkan dengan TRUE untuk menyembunyikan log skip)
    SUPPRESS_API_DOCS_SKIP_LOG = get_env_bool('SUPPRESS_API_DOCS_SKIP_LOG', 'True')

    # Fast-path optimization: skip MAC lookup entirely for localhost in dev/test
    # This prevents long waits when client_ip is 127.0.0.1/::1 during local development
    SKIP_MAC_LOOKUP_FOR_LOCALHOST = get_env_bool('SKIP_MAC_LOOKUP_FOR_LOCALHOST', 'True')
    
    @staticmethod
    def init_app(app):
        pass

class DevelopmentConfig(Config):
    FLASK_DEBUG = True
    LOG_LEVEL = 'DEBUG'
    RATELIMIT_ENABLED = True

class ProductionConfig(Config):
    FLASK_DEBUG = False
    LOG_LEVEL = 'INFO'
    MIDTRANS_IS_PRODUCTION = True
    # In production, never treat localhost as a valid client IP
    NETWORK_ALLOW_LOCALHOST = False

class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = os.environ.get('TEST_DATABASE_URL', 'sqlite:///:memory:')
    SQLALCHEMY_ECHO = False
    RATELIMIT_ENABLED = True
    SYNC_TEST_MODE_ENABLED = True

config_options = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}