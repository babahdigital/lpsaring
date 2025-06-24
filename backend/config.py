# backend/config.py
import os
from dotenv import load_dotenv
import warnings
import ast

# --- Pemuatan File .env ---
basedir = os.path.abspath(os.path.dirname(__file__))
dotenv_path = None
current_dir = basedir
for _ in range(4): # Naik hingga 4 level direktori untuk mencari .env
    potential_path = os.path.join(current_dir, '.env')
    if os.path.exists(potential_path):
        dotenv_path = potential_path
        break
    parent_dir = os.path.dirname(current_dir)
    if parent_dir == current_dir:
        break
    current_dir = parent_dir

if dotenv_path:
    load_dotenv(dotenv_path=dotenv_path)
    print(f"INFO: Berhasil memuat variabel lingkungan dari: {dotenv_path}")
else:
    warnings.warn("PERINGATAN: File .env tidak ditemukan. Aplikasi akan menggunakan default atau variabel sistem.")
    print(f"INFO: Mencari .env di {basedir} dan direktori induknya.")

def get_env_bool(var_name, default='False'):
    """Helper untuk mendapatkan boolean dari environment variable."""
    return os.environ.get(var_name, default).lower() in ('true', '1', 't', 'yes')

def get_env_int(var_name, default):
    """Helper untuk mendapatkan integer dari environment variable."""
    try:
        return int(os.environ.get(var_name, str(default)))
    except ValueError:
        warnings.warn(f"PERINGATAN: {var_name} bukan integer, gunakan default {default}.")
        return default

def get_env_list(var_name, default="[]"):
    """Helper untuk mendapatkan list dari environment variable."""
    val_str = os.environ.get(var_name, default)
    try:
        parsed_val = ast.literal_eval(val_str)
        if isinstance(parsed_val, list):
            return parsed_val
    except (ValueError, SyntaxError):
        if isinstance(val_str, str) and val_str.strip():
            return [item.strip() for item in val_str.split(',') if item.strip()]
    
    if isinstance(default, list):
        return default
    if default == "[]":
        return []
        
    warnings.warn(f"PERINGATAN: Tidak dapat mem-parse {var_name} ('{val_str}') sebagai list. Menggunakan default: {default}")
    return [] if default == "[]" else default

class Config:
    """Konfigurasi dasar aplikasi Flask."""

    # --- Konfigurasi Umum Flask ---
    SECRET_KEY = os.environ.get('SECRET_KEY')
    if not SECRET_KEY:
        warnings.warn("PERINGATAN: SECRET_KEY tidak disetel! Gunakan nilai default yang TIDAK AMAN untuk development.")
        SECRET_KEY = 'dev-secret-key-ganti-ini-di-produksi'

    FLASK_DEBUG = get_env_bool('FLASK_DEBUG', 'False')
    FLASK_ENV = os.environ.get('FLASK_ENV', 'production' if not FLASK_DEBUG else 'development')
    FLASK_APP = os.environ.get('FLASK_APP', 'run:app')

    # --- Konfigurasi Database (SQLAlchemy) ---
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL')
    if not SQLALCHEMY_DATABASE_URI:
        db_user = os.environ.get('DB_USER')
        db_password = os.environ.get('DB_PASSWORD')
        db_host = os.environ.get('DB_HOST')
        db_port = os.environ.get('DB_PORT', '5432')
        db_name = os.environ.get('DB_NAME')
        if db_user and db_password and db_host and db_name:
            SQLALCHEMY_DATABASE_URI = f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
            warnings.warn("PERINGATAN: Menggunakan fallback konstruksi DATABASE_URL. Lebih baik set DATABASE_URL langsung.")
        else:
            raise ValueError("ERROR: Konfigurasi database (DATABASE_URL atau DB_USER/PASS/HOST/NAME) tidak ditemukan.")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ECHO = get_env_bool('SQLALCHEMY_ECHO', 'False')

    # --- Konfigurasi Autentikasi (JWT) ---
    JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY')
    if not JWT_SECRET_KEY:
        warnings.warn("PERINGATAN: JWT_SECRET_KEY tidak disetel! Gunakan nilai default yang TIDAK AMAN untuk development.")
        JWT_SECRET_KEY = 'dev-jwt-secret-key-ganti-ini-di-produksi'
    JWT_ALGORITHM = os.environ.get('JWT_ALGORITHM', 'HS256')
    JWT_ACCESS_TOKEN_EXPIRES_MINUTES = get_env_int('JWT_ACCESS_TOKEN_EXPIRES_MINUTES', 30)

    # --- Konfigurasi Redis ---
    REDIS_HOST_OTP = os.environ.get('REDIS_HOST_OTP', 'redis')
    REDIS_PORT_OTP = get_env_int('REDIS_PORT_OTP', 6379)
    REDIS_DB_OTP = get_env_int('REDIS_DB_OTP', 0)
    _redis_password_otp = os.environ.get('REDIS_PASSWORD_OTP')
    REDIS_PASSWORD_OTP = _redis_password_otp if _redis_password_otp and _redis_password_otp.lower() != 'null' else None
    _redis_auth_otp = f":{REDIS_PASSWORD_OTP}@" if REDIS_PASSWORD_OTP else ""
    REDIS_URL_OTP = f"redis://{_redis_auth_otp}{REDIS_HOST_OTP}:{REDIS_PORT_OTP}/{REDIS_DB_OTP}"
    OTP_EXPIRE_SECONDS = get_env_int('OTP_EXPIRE_SECONDS', 300)

    REDIS_HOST_CELERY_BROKER = os.environ.get('REDIS_HOST_CELERY_BROKER', REDIS_HOST_OTP)
    REDIS_PORT_CELERY_BROKER = get_env_int('REDIS_PORT_CELERY_BROKER', REDIS_PORT_OTP)
    REDIS_DB_CELERY_BROKER = get_env_int('REDIS_DB_CELERY_BROKER', 1)
    _redis_password_celery_broker = os.environ.get('REDIS_PASSWORD_CELERY_BROKER', REDIS_PASSWORD_OTP)
    REDIS_PASSWORD_CELERY_BROKER = _redis_password_celery_broker if _redis_password_celery_broker and _redis_password_celery_broker.lower() != 'null' else None
    _redis_auth_celery_broker = f":{REDIS_PASSWORD_CELERY_BROKER}@" if REDIS_PASSWORD_CELERY_BROKER else ""
    CELERY_BROKER_URL = os.environ.get('CELERY_BROKER_URL', f"redis://{_redis_auth_celery_broker}{REDIS_HOST_CELERY_BROKER}:{REDIS_PORT_CELERY_BROKER}/{REDIS_DB_CELERY_BROKER}")

    REDIS_HOST_CELERY_BACKEND = os.environ.get('REDIS_HOST_CELERY_BACKEND', REDIS_HOST_CELERY_BROKER)
    REDIS_PORT_CELERY_BACKEND = get_env_int('REDIS_PORT_CELERY_BACKEND', REDIS_PORT_CELERY_BROKER)
    REDIS_DB_CELERY_BACKEND = get_env_int('REDIS_DB_CELERY_BACKEND', 2)
    _redis_password_celery_backend = os.environ.get('REDIS_PASSWORD_CELERY_BACKEND', REDIS_PASSWORD_CELERY_BROKER)
    REDIS_PASSWORD_CELERY_BACKEND = _redis_password_celery_backend if _redis_password_celery_backend and _redis_password_celery_backend.lower() != 'null' else None
    _redis_auth_celery_backend = f":{REDIS_PASSWORD_CELERY_BACKEND}@" if REDIS_PASSWORD_CELERY_BACKEND else ""
    CELERY_RESULT_BACKEND = os.environ.get('CELERY_RESULT_BACKEND', f"redis://{_redis_auth_celery_backend}{REDIS_HOST_CELERY_BACKEND}:{REDIS_PORT_CELERY_BACKEND}/{REDIS_DB_CELERY_BACKEND}")

    REDIS_HOST_RATELIMIT = os.environ.get('REDIS_HOST_RATELIMIT', REDIS_HOST_OTP)
    REDIS_PORT_RATELIMIT = get_env_int('REDIS_PORT_RATELIMIT', REDIS_PORT_OTP)
    REDIS_DB_RATELIMIT = get_env_int('REDIS_DB_RATELIMIT', REDIS_DB_OTP)
    _redis_password_ratelimit = os.environ.get('REDIS_PASSWORD_RATELIMIT', REDIS_PASSWORD_OTP)
    REDIS_PASSWORD_RATELIMIT = _redis_password_ratelimit if _redis_password_ratelimit and _redis_password_ratelimit.lower() != 'null' else None
    _redis_auth_ratelimit = f":{REDIS_PASSWORD_RATELIMIT}@" if REDIS_PASSWORD_RATELIMIT else ""
    RATELIMIT_STORAGE_URI = os.environ.get('RATELIMIT_STORAGE_URI', f"redis://{_redis_auth_ratelimit}{REDIS_HOST_RATELIMIT}:{REDIS_PORT_RATELIMIT}/{REDIS_DB_RATELIMIT}")
    
    REDIS_CONNECT_TIMEOUT = get_env_int('REDIS_CONNECT_TIMEOUT', 5)
    REDIS_SOCKET_TIMEOUT = get_env_int('REDIS_SOCKET_TIMEOUT', 5)

    # --- Konfigurasi Rate Limiting (Flask-Limiter) ---
    RATELIMIT_DEFAULT = os.environ.get('API_RATE_LIMIT', '200 per day;50 per hour;10 per minute')
    RATELIMIT_STRATEGY = os.environ.get('RATELIMIT_STRATEGY', 'fixed-window')
    PING_RATE_LIMIT = os.environ.get('PING_RATE_LIMIT', '10 per minute')
    RATELIMIT_ENABLED = get_env_bool('RATELIMIT_ENABLED', 'True')

    # --- Konfigurasi Midtrans ---
    MIDTRANS_SERVER_KEY = os.environ.get('MIDTRANS_SERVER_KEY')
    MIDTRANS_CLIENT_KEY = os.environ.get('MIDTRANS_CLIENT_KEY')
    MIDTRANS_IS_PRODUCTION = get_env_bool('MIDTRANS_IS_PRODUCTION', 'False')

    # --- Konfigurasi WhatsApp API ---
    WHATSAPP_API_URL = os.environ.get('WHATSAPP_API_URL')
    WHATSAPP_API_KEY = os.environ.get('WHATSAPP_API_KEY')
    ENABLE_WHATSAPP_NOTIFICATIONS = get_env_bool('ENABLE_WHATSAPP_NOTIFICATIONS', 'True')

    # --- Konfigurasi MikroTik API ---
    MIKROTIK_HOST = os.environ.get('MIKROTIK_HOST')
    MIKROTIK_USERNAME = os.environ.get('MIKROTIK_USERNAME')
    MIKROTIK_PASSWORD = os.environ.get('MIKROTIK_PASSWORD')
    MIKROTIK_PORT = get_env_int('MIKROTIK_PORT', 8728)
    MIKROTIK_USE_SSL = get_env_bool('MIKROTIK_USE_SSL', 'False')
    MIKROTIK_DEFAULT_PROFILE = os.environ.get('MIKROTIK_DEFAULT_PROFILE', 'default')
    MIKROTIK_EXPIRED_PROFILE = os.environ.get('MIKROTIK_EXPIRED_PROFILE', 'expired')
    MIKROTIK_KOMANDAN_PROFILE = os.environ.get('MIKROTIK_KOMANDAN_PROFILE', 'komandan')
    MIKROTIK_SEND_LIMIT_BYTES_TOTAL = get_env_bool('MIKROTIK_SEND_LIMIT_BYTES_TOTAL', 'False')
    MIKROTIK_SEND_SESSION_TIMEOUT = get_env_bool('MIKROTIK_SEND_SESSION_TIMEOUT', 'False')
    # --- Akhir Konfigurasi MikroTik API ---

    # --- Konfigurasi Logging ---
    LOG_TO_FILE = get_env_bool('LOG_TO_FILE', 'False')
    LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO' if FLASK_ENV == 'production' else 'DEBUG').upper()
    LOG_DIR = os.environ.get('LOG_DIR', 'logs')
    LOG_FILENAME = os.environ.get('LOG_FILENAME', 'hotspot_portal.log')
    LOG_MAX_BYTES = get_env_int('LOG_MAX_BYTES', 10*1024*1024)
    LOG_BACKUP_COUNT = get_env_int('LOG_BACKUP_COUNT', 5)
    LOG_FILE_LEVEL = os.environ.get('LOG_FILE_LEVEL', 'INFO').upper()

    # --- Konfigurasi ProxyFix ---
    PROXYFIX_X_FOR = get_env_int('PROXYFIX_X_FOR', 1)
    PROXYFIX_X_PROTO = get_env_int('PROXYFIX_X_PROTO', 1)
    PROXYFIX_X_HOST = get_env_int('PROXYFIX_X_HOST', 0)
    PROXYFIX_X_PORT = get_env_int('PROXYFIX_X_PORT', 0)
    PROXYFIX_X_PREFIX = get_env_int('PROXYFIX_X_PREFIX', 0)

    # --- Konfigurasi Lainnya ---
    FRONTEND_URL = os.environ.get('FRONTEND_URL', 'http://localhost:3010')
    # --- PENAMBAHAN VARIABEL BARU ---
    APP_PUBLIC_BASE_URL = os.environ.get('APP_PUBLIC_BASE_URL')
    # -------------------------------
    CORS_ADDITIONAL_ORIGINS = get_env_list('CORS_ADDITIONAL_ORIGINS', "[]")
    APP_LOCALE = os.environ.get('APP_LOCALE', 'id_ID.UTF-8')
    CURRENCY_SYMBOL = os.environ.get('CURRENCY_SYMBOL', 'Rp ')
    JINJA_DATETIME_FORMAT = os.environ.get('JINJA_DATETIME_FORMAT', '%d/%m/%y %H:%M')
    JINJA_DATETIME_SHORT_FORMAT = os.environ.get('JINJA_DATETIME_SHORT_FORMAT', '%b %d, %Y')
    ENABLE_ADMIN_ROUTES = get_env_bool('ENABLE_ADMIN_ROUTES', 'False')
    APP_LINK_USER = os.environ.get('APP_LINK_USER', 'http://localhost:3010')
    APP_LINK_ADMIN = os.environ.get('APP_LINK_ADMIN', 'http://localhost:3010/admin')
    APP_LINK_MIKROTIK = os.environ.get('APP_LINK_MIKROTIK', 'http://172.16.0.1/login')
    APP_LINK_ADMIN_CHANGE_PASSWORD = os.environ.get('APP_LINK_ADMIN_CHANGE_PASSWORD', f"{APP_LINK_ADMIN}/account-settings")


    @classmethod
    def validate_production_config(cls):
        if cls.FLASK_ENV == 'production':
            if not cls.SECRET_KEY or cls.SECRET_KEY == 'dev-secret-key-ganti-ini-di-produksi':
                raise ValueError("ERROR: SECRET_KEY harus disetel dengan nilai yang kuat di environment production!")
            if not cls.JWT_SECRET_KEY or cls.JWT_SECRET_KEY == 'dev-jwt-secret-key-ganti-ini-di-produksi':
                raise ValueError("ERROR: JWT_SECRET_KEY harus disetel dengan nilai yang kuat di environment production!")
            if not cls.SQLALCHEMY_DATABASE_URI:
                 raise ValueError("ERROR: DATABASE_URL harus disetel di environment production!")
            
            # --- PENAMBAHAN VALIDASI UNTUK URL PUBLIK ---
            if not cls.APP_PUBLIC_BASE_URL:
                 raise ValueError("ERROR: APP_PUBLIC_BASE_URL harus disetel di environment production! Ini dibutuhkan untuk callback dan URL eksternal.")
            # ---------------------------------------------

            if not cls.MIDTRANS_SERVER_KEY or not cls.MIDTRANS_CLIENT_KEY:
                 warnings.warn("PERINGATAN PRODUKSI: Kunci Midtrans (SERVER/CLIENT) tidak disetel. Fitur pembayaran tidak akan berfungsi.")
            if cls.ENABLE_WHATSAPP_NOTIFICATIONS and (not cls.WHATSAPP_API_URL or not cls.WHATSAPP_API_KEY):
                 warnings.warn("PERINGATAN PRODUKSI: Notifikasi WhatsApp diaktifkan tetapi URL/Kunci API WhatsApp tidak disetel.")
            if not cls.MIKROTIK_HOST or not cls.MIKROTIK_USERNAME or not cls.MIKROTIK_PASSWORD:
                 warnings.warn("PERINGATAN PRODUKSI: Konfigurasi MikroTik tidak lengkap. Fitur hotspot mungkin tidak berfungsi.")
            if not cls.RATELIMIT_STORAGE_URI or 'memory://' in cls.RATELIMIT_STORAGE_URI:
                 warnings.warn("PERINGATAN PRODUKSI: RATELIMIT_STORAGE_URI tidak disetel ke backend Redis yang valid. Rate limiting tidak akan persisten.")

class DevelopmentConfig(Config):
    FLASK_DEBUG = True
    FLASK_ENV = 'development'
    SQLALCHEMY_ECHO = get_env_bool('SQLALCHEMY_ECHO', 'True')
    LOG_LEVEL = os.environ.get('LOG_LEVEL', 'DEBUG').upper()
    RATELIMIT_DEFAULT = os.environ.get('API_RATE_LIMIT', '500 per minute')
    ENABLE_WHATSAPP_NOTIFICATIONS = get_env_bool('ENABLE_WHATSAPP_NOTIFICATIONS', 'True')
    RATELIMIT_ENABLED = get_env_bool('RATELIMIT_ENABLED', 'False')
    
    MIKROTIK_SEND_LIMIT_BYTES_TOTAL = get_env_bool('MIKROTIK_SEND_LIMIT_BYTES_TOTAL', 'False')
    MIKROTIK_SEND_SESSION_TIMEOUT = get_env_bool('MIKROTIK_SEND_SESSION_TIMEOUT', 'False')


class ProductionConfig(Config):
    FLASK_DEBUG = False
    FLASK_ENV = 'production'
    SQLALCHEMY_ECHO = False
    LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO').upper()
    MIDTRANS_IS_PRODUCTION = get_env_bool('MIDTRANS_IS_PRODUCTION', 'True')
    ENABLE_WHATSAPP_NOTIFICATIONS = get_env_bool('ENABLE_WHATSAPP_NOTIFICATIONS', 'True')
    RATELIMIT_ENABLED = get_env_bool('RATELIMIT_ENABLED', 'True')
    
    MIKROTIK_SEND_LIMIT_BYTES_TOTAL = get_env_bool('MIKROTIK_SEND_LIMIT_BYTES_TOTAL', 'True')
    MIKROTIK_SEND_SESSION_TIMEOUT = get_env_bool('MIKROTIK_SEND_SESSION_TIMEOUT', 'True')

    def __init__(self):
        super().validate_production_config()


class TestingConfig(Config):
    TESTING = True
    FLASK_DEBUG = True
    FLASK_ENV = 'testing'
    SQLALCHEMY_DATABASE_URI = os.environ.get('TEST_DATABASE_URL') or 'sqlite:///:memory:'
    SQLALCHEMY_ECHO = get_env_bool('SQLALCHEMY_ECHO', 'False')
    JWT_SECRET_KEY = 'test-jwt-secret-key'
    SECRET_KEY = 'test-secret-key'
    ENABLE_WHATSAPP_NOTIFICATIONS = False
    MIDTRANS_SERVER_KEY = 'test-midtrans-server-key'
    MIDTRANS_CLIENT_KEY = 'test-midtrans-client-key'
    MIDTRANS_IS_PRODUCTION = False
    RATELIMIT_ENABLED = False
    LOG_LEVEL = 'DEBUG'
    LOG_TO_FILE = False
    APP_PUBLIC_BASE_URL = 'http://testserver' # Tambahkan untuk testing


config_options = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}

if Config.FLASK_ENV == 'production' and os.environ.get('FLASK_CONFIG') is None:
    Config.validate_production_config()