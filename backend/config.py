# backend/config.py
import os
import sys
from dotenv import dotenv_values
import warnings
import ast

# --- Pemuatan File .env (multi-file overlay) ---
# Tujuan:
# - DEV: boleh overlay backend/.env.public -> backend/.env.local (local override public)
# - PROD: pakai env produksi saja (biasanya di root .env.prod atau dimount jadi /app/.env)
# - Jangan menimpa env yang sudah diset oleh Docker/OS (Docker env wins)

basedir = os.path.abspath(os.path.dirname(__file__))


def _iter_parent_dirs(start_dir: str, max_levels: int = 4):
    current_dir = start_dir
    for _ in range(max_levels + 1):
        yield current_dir
        parent_dir = os.path.dirname(current_dir)
        if parent_dir == current_dir:
            break
        current_dir = parent_dir


def _is_production_like() -> bool:
    flask_env = (os.environ.get("FLASK_ENV") or "").strip().lower()
    if flask_env == "production":
        return True
    # APP_ENV kadang dipakai sebagai profile compose (mis. public.prod)
    app_env_raw = (os.environ.get("APP_ENV") or "").strip().lower()
    return app_env_raw in {"prod", "production", "public.prod", "public_prod", "publicprod"}


def _discover_dotenv_paths() -> list[str]:
    app_env = os.environ.get("APP_ENV") or os.environ.get("FLASK_ENV")
    app_env = (app_env or "").strip()

    is_prod = _is_production_like()

    # Global (semua mode): hanya muat .env base. Ini juga yang dipakai docker volume mount di produksi (/app/.env).
    global_names: list[str] = [".env"]

    # Prod: izinkan fallback file khusus prod (terutama untuk run non-container).
    # Catatan: pada deploy normal, .env.prod dimount menjadi /app/.env.
    if is_prod:
        global_names.extend([".env.prod", ".env.production"])

    # Dev: overlay hanya dari direktori backend (berdasarkan basedir) agar root .env.public tidak ikut terbaca.
    backend_overlay_names: list[str] = []
    if not is_prod:
        # Public dulu, lalu local override.
        backend_overlay_names.extend([".env.public", ".env.local"])
        # Jika ada profile tambahan, muat paling akhir (override).
        if app_env and app_env not in {"public", "local"}:
            backend_overlay_names.append(f".env.{app_env}")

    # Precedence antar direktori:
    # - Root lebih "base", backend/ lebih "override".
    # Jadi kita load dari parent -> child.
    dirs = list(_iter_parent_dirs(basedir, max_levels=4))
    dirs.reverse()

    paths: list[str] = []
    seen: set[str] = set()
    for d in dirs:
        for name in global_names:
            p = os.path.join(d, name)
            if os.path.exists(p) and p not in seen:
                paths.append(p)
                seen.add(p)

        if not is_prod and d == basedir:
            for name in backend_overlay_names:
                p = os.path.join(d, name)
                if os.path.exists(p) and p not in seen:
                    paths.append(p)
                    seen.add(p)
    return paths


def _load_dotenv_chain(paths: list[str]) -> None:
    if not paths:
        # Dalam Docker, env biasanya disuplai via `env_file`/`environment` sehingga file `.env` memang
        # tidak tersedia di filesystem container. Jangan jadikan ini warning.
        print(f"INFO: Tidak menemukan file dotenv; menggunakan environment OS/Docker (basedir={basedir}).")
        return

    merged: dict[str, str] = {}
    loaded: list[str] = []
    for p in paths:
        try:
            values = dotenv_values(p)
        except Exception:
            continue
        # dotenv_values mengembalikan dict[str, Optional[str]]
        for k, v in values.items():
            if k is None or v is None:
                continue
            merged[str(k)] = str(v)
        loaded.append(p)

    # Set hanya jika belum ada di OS env (Docker env wins)
    for k, v in merged.items():
        if k not in os.environ:
            os.environ[k] = v

    print("INFO: Memuat env chain:")
    for p in loaded:
        print(f" - {p}")


_load_dotenv_chain(_discover_dotenv_paths())


def get_env_bool(var_name, default="False"):
    """Helper untuk mendapatkan boolean dari environment variable."""
    return os.environ.get(var_name, default).lower() in ("true", "1", "t", "yes")


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
            return [item.strip() for item in val_str.split(",") if item.strip()]

    if isinstance(default, list):
        return default
    if default == "[]":
        return []

    warnings.warn(
        f"PERINGATAN: Tidak dapat mem-parse {var_name} ('{val_str}') sebagai list. Menggunakan default: {default}"
    )
    return [] if default == "[]" else default


class Config:
    """Konfigurasi dasar aplikasi Flask."""

    # --- Konfigurasi Umum Flask ---
    SECRET_KEY = os.environ.get("SECRET_KEY")
    if not SECRET_KEY:
        warnings.warn("PERINGATAN: SECRET_KEY tidak disetel! Gunakan nilai default yang TIDAK AMAN untuk development.")
        SECRET_KEY = "dev-secret-key-ganti-ini-di-produksi"

    FLASK_DEBUG = get_env_bool("FLASK_DEBUG", "False")
    FLASK_ENV = os.environ.get("FLASK_ENV", "production" if not FLASK_DEBUG else "development")
    FLASK_APP = os.environ.get("FLASK_APP", "run:app")

    # --- Konfigurasi Database (SQLAlchemy) ---
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL")
    if not SQLALCHEMY_DATABASE_URI:
        db_user = os.environ.get("DB_USER")
        db_password = os.environ.get("DB_PASSWORD")
        db_host = os.environ.get("DB_HOST")
        db_port = os.environ.get("DB_PORT", "5432")
        db_name = os.environ.get("DB_NAME")
        if db_user and db_password and db_host and db_name:
            SQLALCHEMY_DATABASE_URI = f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
            warnings.warn(
                "PERINGATAN: Menggunakan fallback konstruksi DATABASE_URL. Lebih baik set DATABASE_URL langsung."
            )
        else:
            is_testing = os.environ.get("FLASK_ENV") == "testing" or "pytest" in sys.modules
            if is_testing:
                SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
                warnings.warn(
                    "PERINGATAN: DATABASE_URL tidak ditemukan. Menggunakan fallback sqlite in-memory untuk testing."
                )
            else:
                raise ValueError(
                    "ERROR: Konfigurasi database (DATABASE_URL atau DB_USER/PASS/HOST/NAME) tidak ditemukan."
                )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ECHO = get_env_bool("SQLALCHEMY_ECHO", "False")

    # --- Konfigurasi Backup ---
    BACKUP_DIR = os.environ.get("BACKUP_DIR", "/app/backups")

    # --- Konfigurasi Autentikasi (JWT) ---
    JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY")
    if not JWT_SECRET_KEY:
        warnings.warn(
            "PERINGATAN: JWT_SECRET_KEY tidak disetel! Gunakan nilai default yang TIDAK AMAN untuk development."
        )
        JWT_SECRET_KEY = "dev-jwt-secret-key-ganti-ini-di-produksi"
    JWT_ALGORITHM = os.environ.get("JWT_ALGORITHM", "HS256")
    JWT_ACCESS_TOKEN_EXPIRES_MINUTES = get_env_int("JWT_ACCESS_TOKEN_EXPIRES_MINUTES", 30)

    # --- Konfigurasi Cookie Auth ---
    AUTH_COOKIE_NAME = os.environ.get("AUTH_COOKIE_NAME", "auth_token")
    AUTH_COOKIE_HTTPONLY = get_env_bool("AUTH_COOKIE_HTTPONLY", "True")
    AUTH_COOKIE_SECURE = get_env_bool("AUTH_COOKIE_SECURE", "True" if FLASK_ENV == "production" else "False")
    AUTH_COOKIE_SAMESITE = os.environ.get("AUTH_COOKIE_SAMESITE", "Lax")
    AUTH_COOKIE_PATH = os.environ.get("AUTH_COOKIE_PATH", "/")
    AUTH_COOKIE_DOMAIN = os.environ.get("AUTH_COOKIE_DOMAIN")
    AUTH_COOKIE_MAX_AGE_SECONDS = get_env_int("AUTH_COOKIE_MAX_AGE_SECONDS", JWT_ACCESS_TOKEN_EXPIRES_MINUTES * 60)

    # --- Konfigurasi Refresh Token (Rotating Refresh Token via Cookie HttpOnly) ---
    # Access token tetap pendek; refresh token yang panjang untuk UX "ingat saya".
    REFRESH_TOKEN_EXPIRES_DAYS = get_env_int("REFRESH_TOKEN_EXPIRES_DAYS", 30)

    # --- Konfigurasi OTP / Device Authorization ---
    # Default: OTP sukses dianggap self-authorization, jadi device/MAC yang dipakai boleh langsung authorized.
    # Set False jika ingin kembali ke mode "device pertama saja" (atau murni admin authorization).
    OTP_AUTO_AUTHORIZE_DEVICE = get_env_bool("OTP_AUTO_AUTHORIZE_DEVICE", "True")

    REFRESH_COOKIE_NAME = os.environ.get("REFRESH_COOKIE_NAME", "refresh_token")
    REFRESH_COOKIE_HTTPONLY = get_env_bool("REFRESH_COOKIE_HTTPONLY", "True")
    REFRESH_COOKIE_SECURE = get_env_bool("REFRESH_COOKIE_SECURE", "True" if FLASK_ENV == "production" else "False")
    REFRESH_COOKIE_SAMESITE = os.environ.get("REFRESH_COOKIE_SAMESITE", AUTH_COOKIE_SAMESITE)
    REFRESH_COOKIE_PATH = os.environ.get("REFRESH_COOKIE_PATH", AUTH_COOKIE_PATH)
    REFRESH_COOKIE_DOMAIN = os.environ.get("REFRESH_COOKIE_DOMAIN", AUTH_COOKIE_DOMAIN)
    REFRESH_COOKIE_MAX_AGE_SECONDS = get_env_int(
        "REFRESH_COOKIE_MAX_AGE_SECONDS",
        max(1, REFRESH_TOKEN_EXPIRES_DAYS) * 24 * 60 * 60,
    )

    # --- Konfigurasi CSRF (Cookie Auth) ---
    CSRF_PROTECT_ENABLED = get_env_bool("CSRF_PROTECT_ENABLED", "True")
    CSRF_TRUSTED_ORIGINS = get_env_list("CSRF_TRUSTED_ORIGINS", "[]")
    CSRF_STRICT_NO_ORIGIN = get_env_bool("CSRF_STRICT_NO_ORIGIN", "False")
    CSRF_NO_ORIGIN_ALLOWED_IPS = get_env_list("CSRF_NO_ORIGIN_ALLOWED_IPS", "[]")

    # --- Konfigurasi Redis ---
    REDIS_HOST_OTP = os.environ.get("REDIS_HOST_OTP", "redis")
    REDIS_PORT_OTP = get_env_int("REDIS_PORT_OTP", 6379)
    REDIS_DB_OTP = get_env_int("REDIS_DB_OTP", 0)
    _redis_password_otp = os.environ.get("REDIS_PASSWORD_OTP")
    REDIS_PASSWORD_OTP = _redis_password_otp if _redis_password_otp and _redis_password_otp.lower() != "null" else None
    _redis_auth_otp = f":{REDIS_PASSWORD_OTP}@" if REDIS_PASSWORD_OTP else ""
    REDIS_URL_OTP = f"redis://{_redis_auth_otp}{REDIS_HOST_OTP}:{REDIS_PORT_OTP}/{REDIS_DB_OTP}"
    OTP_EXPIRE_SECONDS = get_env_int("OTP_EXPIRE_SECONDS", 300)
    OTP_REQUEST_COOLDOWN_SECONDS = get_env_int("OTP_REQUEST_COOLDOWN_SECONDS", 60)
    OTP_VERIFY_MAX_ATTEMPTS = get_env_int("OTP_VERIFY_MAX_ATTEMPTS", 5)
    OTP_VERIFY_WINDOW_SECONDS = get_env_int("OTP_VERIFY_WINDOW_SECONDS", 300)
    OTP_FINGERPRINT_ENABLED = get_env_bool("OTP_FINGERPRINT_ENABLED", "True")

    REDIS_HOST_CELERY_BROKER = os.environ.get("REDIS_HOST_CELERY_BROKER", REDIS_HOST_OTP)
    REDIS_PORT_CELERY_BROKER = get_env_int("REDIS_PORT_CELERY_BROKER", REDIS_PORT_OTP)
    REDIS_DB_CELERY_BROKER = get_env_int("REDIS_DB_CELERY_BROKER", 1)
    _redis_password_celery_broker = os.environ.get("REDIS_PASSWORD_CELERY_BROKER", REDIS_PASSWORD_OTP)
    REDIS_PASSWORD_CELERY_BROKER = (
        _redis_password_celery_broker
        if _redis_password_celery_broker and _redis_password_celery_broker.lower() != "null"
        else None
    )
    _redis_auth_celery_broker = f":{REDIS_PASSWORD_CELERY_BROKER}@" if REDIS_PASSWORD_CELERY_BROKER else ""
    CELERY_BROKER_URL = os.environ.get(
        "CELERY_BROKER_URL",
        f"redis://{_redis_auth_celery_broker}{REDIS_HOST_CELERY_BROKER}:{REDIS_PORT_CELERY_BROKER}/{REDIS_DB_CELERY_BROKER}",
    )

    REDIS_HOST_CELERY_BACKEND = os.environ.get("REDIS_HOST_CELERY_BACKEND", REDIS_HOST_CELERY_BROKER)
    REDIS_PORT_CELERY_BACKEND = get_env_int("REDIS_PORT_CELERY_BACKEND", REDIS_PORT_CELERY_BROKER)
    REDIS_DB_CELERY_BACKEND = get_env_int("REDIS_DB_CELERY_BACKEND", 2)
    _redis_password_celery_backend = os.environ.get("REDIS_PASSWORD_CELERY_BACKEND", REDIS_PASSWORD_CELERY_BROKER)
    REDIS_PASSWORD_CELERY_BACKEND = (
        _redis_password_celery_backend
        if _redis_password_celery_backend and _redis_password_celery_backend.lower() != "null"
        else None
    )
    _redis_auth_celery_backend = f":{REDIS_PASSWORD_CELERY_BACKEND}@" if REDIS_PASSWORD_CELERY_BACKEND else ""
    CELERY_RESULT_BACKEND = os.environ.get(
        "CELERY_RESULT_BACKEND",
        f"redis://{_redis_auth_celery_backend}{REDIS_HOST_CELERY_BACKEND}:{REDIS_PORT_CELERY_BACKEND}/{REDIS_DB_CELERY_BACKEND}",
    )

    REDIS_HOST_RATELIMIT = os.environ.get("REDIS_HOST_RATELIMIT", REDIS_HOST_OTP)
    REDIS_PORT_RATELIMIT = get_env_int("REDIS_PORT_RATELIMIT", REDIS_PORT_OTP)
    REDIS_DB_RATELIMIT = get_env_int("REDIS_DB_RATELIMIT", REDIS_DB_OTP)
    _redis_password_ratelimit = os.environ.get("REDIS_PASSWORD_RATELIMIT", REDIS_PASSWORD_OTP)
    REDIS_PASSWORD_RATELIMIT = (
        _redis_password_ratelimit if _redis_password_ratelimit and _redis_password_ratelimit.lower() != "null" else None
    )
    _redis_auth_ratelimit = f":{REDIS_PASSWORD_RATELIMIT}@" if REDIS_PASSWORD_RATELIMIT else ""
    RATELIMIT_STORAGE_URI = os.environ.get(
        "RATELIMIT_STORAGE_URI",
        f"redis://{_redis_auth_ratelimit}{REDIS_HOST_RATELIMIT}:{REDIS_PORT_RATELIMIT}/{REDIS_DB_RATELIMIT}",
    )

    REDIS_CONNECT_TIMEOUT = get_env_int("REDIS_CONNECT_TIMEOUT", 5)
    REDIS_SOCKET_TIMEOUT = get_env_int("REDIS_SOCKET_TIMEOUT", 5)

    # --- Konfigurasi Rate Limiting (Flask-Limiter) ---
    RATELIMIT_DEFAULT = os.environ.get("API_RATE_LIMIT", "200 per day;50 per hour;10 per minute")
    RATELIMIT_STRATEGY = os.environ.get("RATELIMIT_STRATEGY", "fixed-window")
    PING_RATE_LIMIT = os.environ.get("PING_RATE_LIMIT", "10 per minute")
    RATELIMIT_ENABLED = get_env_bool("RATELIMIT_ENABLED", "True")

    OTP_REQUEST_RATE_LIMIT = os.environ.get("OTP_REQUEST_RATE_LIMIT", "5 per minute;20 per hour")
    OTP_VERIFY_RATE_LIMIT = os.environ.get("OTP_VERIFY_RATE_LIMIT", "10 per minute;60 per hour")
    ADMIN_LOGIN_RATE_LIMIT = os.environ.get("ADMIN_LOGIN_RATE_LIMIT", "10 per minute;60 per hour")
    REGISTER_RATE_LIMIT = os.environ.get("REGISTER_RATE_LIMIT", "5 per minute;20 per hour")
    SESSION_CONSUME_RATE_LIMIT = os.environ.get("SESSION_CONSUME_RATE_LIMIT", "30 per minute")
    AUTO_LOGIN_RATE_LIMIT = os.environ.get("AUTO_LOGIN_RATE_LIMIT", "60 per minute")
    REFRESH_TOKEN_RATE_LIMIT = os.environ.get("REFRESH_TOKEN_RATE_LIMIT", "60 per minute")
    STATUS_PAGE_TOKEN_MAX_AGE_SECONDS = get_env_int("STATUS_PAGE_TOKEN_MAX_AGE_SECONDS", 300)

    # Signed token for public transaction status links (shareable via WhatsApp).
    TRANSACTION_STATUS_TOKEN_MAX_AGE_SECONDS = get_env_int(
        "TRANSACTION_STATUS_TOKEN_MAX_AGE_SECONDS",
        7 * 24 * 3600,
    )

    # Rate-limit public transaction endpoints protected by `t`.
    PUBLIC_TRANSACTION_STATUS_RATE_LIMIT = os.environ.get("PUBLIC_TRANSACTION_STATUS_RATE_LIMIT", "60 per minute")
    PUBLIC_TRANSACTION_QR_RATE_LIMIT = os.environ.get("PUBLIC_TRANSACTION_QR_RATE_LIMIT", "30 per minute")
    PUBLIC_TRANSACTION_CANCEL_RATE_LIMIT = os.environ.get("PUBLIC_TRANSACTION_CANCEL_RATE_LIMIT", "20 per minute")

    # --- Konfigurasi Midtrans ---
    MIDTRANS_SERVER_KEY = os.environ.get("MIDTRANS_SERVER_KEY")
    MIDTRANS_CLIENT_KEY = os.environ.get("MIDTRANS_CLIENT_KEY")
    MIDTRANS_IS_PRODUCTION = get_env_bool("MIDTRANS_IS_PRODUCTION", "False")
    MIDTRANS_REQUIRE_SIGNATURE_VALIDATION = get_env_bool(
        "MIDTRANS_REQUIRE_SIGNATURE_VALIDATION",
        "True" if FLASK_ENV == "production" else "False",
    )
    MIDTRANS_HTTP_TIMEOUT_SECONDS = get_env_int("MIDTRANS_HTTP_TIMEOUT_SECONDS", 15)
    MIDTRANS_WEBHOOK_IDEMPOTENCY_TTL_SECONDS = get_env_int("MIDTRANS_WEBHOOK_IDEMPOTENCY_TTL_SECONDS", 86400)

    # Prefix untuk order_id transaksi user (endpoint /api/transactions/initiate).
    # Contoh: BD-LPSR -> hasil: BD-LPSR-1A2B3C4D5E6F
    MIDTRANS_ORDER_ID_PREFIX = os.environ.get("MIDTRANS_ORDER_ID_PREFIX", "BD-LPSR")

    # Prefix untuk order_id tagihan admin (Midtrans Core API).
    # Contoh: BD-LPSR -> hasil: BD-LPSR-1A2B3C4D5E6F
    ADMIN_BILL_ORDER_ID_PREFIX = os.environ.get("ADMIN_BILL_ORDER_ID_PREFIX", "BD-LPSR")

    # Prefix untuk order_id pelunasan tunggakan/hutang kuota (debt settlement).
    # Default: DEBT -> hasil:
    # - Total tunggakan: DEBT-40BF16F55C2B
    # - Hutang manual: DEBT-<uuid>~<suffix>
    # Catatan: untuk kompatibilitas, sistem tetap mengenali prefix legacy 'DEBT-' walaupun env ini diubah.
    DEBT_ORDER_ID_PREFIX = os.environ.get("DEBT_ORDER_ID_PREFIX", "DEBT")

    # --- Konfigurasi WhatsApp API ---
    WHATSAPP_API_URL = os.environ.get("WHATSAPP_API_URL")
    WHATSAPP_VALIDATE_URL = os.environ.get("WHATSAPP_VALIDATE_URL")
    WHATSAPP_API_KEY = os.environ.get("WHATSAPP_API_KEY")
    ENABLE_WHATSAPP_NOTIFICATIONS = get_env_bool("ENABLE_WHATSAPP_NOTIFICATIONS", "True")
    WHATSAPP_HTTP_TIMEOUT_SECONDS = get_env_int("WHATSAPP_HTTP_TIMEOUT_SECONDS", 15)
    WHATSAPP_PDF_DOWNLOAD_TIMEOUT_SECONDS = get_env_int("WHATSAPP_PDF_DOWNLOAD_TIMEOUT_SECONDS", 20)
    WHATSAPP_SEND_DELAY_MIN_MS = get_env_int("WHATSAPP_SEND_DELAY_MIN_MS", 400)
    WHATSAPP_SEND_DELAY_MAX_MS = get_env_int("WHATSAPP_SEND_DELAY_MAX_MS", 1200)

    # --- Rate limit WhatsApp (best-effort via Redis) ---
    WHATSAPP_RATE_LIMIT_ENABLED = get_env_bool("WHATSAPP_RATE_LIMIT_ENABLED", "True")
    WHATSAPP_RATE_LIMIT_WINDOW_SECONDS = get_env_int("WHATSAPP_RATE_LIMIT_WINDOW_SECONDS", 60)
    # Maks pesan per nomor per window (default: 3/menit)
    WHATSAPP_RATE_LIMIT_PER_TARGET = get_env_int("WHATSAPP_RATE_LIMIT_PER_TARGET", 3)
    # Maks pesan total seluruh sistem per window (default: 120/menit)
    WHATSAPP_RATE_LIMIT_GLOBAL = get_env_int("WHATSAPP_RATE_LIMIT_GLOBAL", 120)

    # --- Konfigurasi MikroTik API ---
    MIKROTIK_HOST = os.environ.get("MIKROTIK_HOST")
    MIKROTIK_USERNAME = os.environ.get("MIKROTIK_USERNAME") or os.environ.get("MIKROTIK_USER")
    MIKROTIK_PASSWORD = os.environ.get("MIKROTIK_PASSWORD")
    MIKROTIK_PORT = get_env_int("MIKROTIK_PORT", 8728)
    MIKROTIK_USE_SSL = get_env_bool("MIKROTIK_USE_SSL", "False")
    MIKROTIK_SSL_VERIFY = get_env_bool("MIKROTIK_SSL_VERIFY", "False")
    MIKROTIK_PLAIN_TEXT_LOGIN = get_env_bool("MIKROTIK_PLAIN_TEXT_LOGIN", "True")
    MIKROTIK_DEFAULT_PROFILE = os.environ.get("MIKROTIK_DEFAULT_PROFILE", "default")
    MIKROTIK_ACTIVE_PROFILE = os.environ.get("MIKROTIK_ACTIVE_PROFILE", MIKROTIK_DEFAULT_PROFILE)
    MIKROTIK_FUP_PROFILE = os.environ.get("MIKROTIK_FUP_PROFILE", "fup")
    MIKROTIK_HABIS_PROFILE = os.environ.get("MIKROTIK_HABIS_PROFILE", "habis")
    MIKROTIK_UNLIMITED_PROFILE = os.environ.get("MIKROTIK_UNLIMITED_PROFILE", "unlimited")
    MIKROTIK_EXPIRED_PROFILE = os.environ.get("MIKROTIK_EXPIRED_PROFILE", "expired")
    MIKROTIK_BLOCKED_PROFILE = os.environ.get("MIKROTIK_BLOCKED_PROFILE", "inactive")
    MIKROTIK_KOMANDAN_PROFILE = os.environ.get("MIKROTIK_KOMANDAN_PROFILE", "komandan")
    MIKROTIK_DEFAULT_SERVER_USER = os.environ.get("MIKROTIK_DEFAULT_SERVER_USER", "srv-user")
    MIKROTIK_DEFAULT_SERVER_KOMANDAN = os.environ.get("MIKROTIK_DEFAULT_SERVER_KOMANDAN", "srv-komandan")
    MIKROTIK_SEND_LIMIT_BYTES_TOTAL = get_env_bool("MIKROTIK_SEND_LIMIT_BYTES_TOTAL", "False")
    MIKROTIK_SEND_SESSION_TIMEOUT = get_env_bool("MIKROTIK_SEND_SESSION_TIMEOUT", "False")
    MIKROTIK_ADDRESS_LIST_ACTIVE = os.environ.get("MIKROTIK_ADDRESS_LIST_ACTIVE", "active")
    MIKROTIK_ADDRESS_LIST_FUP = os.environ.get("MIKROTIK_ADDRESS_LIST_FUP", "fup")
    MIKROTIK_ADDRESS_LIST_INACTIVE = os.environ.get("MIKROTIK_ADDRESS_LIST_INACTIVE", "inactive")
    MIKROTIK_ADDRESS_LIST_EXPIRED = os.environ.get("MIKROTIK_ADDRESS_LIST_EXPIRED", "expired")
    MIKROTIK_ADDRESS_LIST_HABIS = os.environ.get("MIKROTIK_ADDRESS_LIST_HABIS", "habis")
    MIKROTIK_ADDRESS_LIST_BLOCKED = os.environ.get("MIKROTIK_ADDRESS_LIST_BLOCKED", "blocked")
    IP_BINDING_ENABLED = get_env_bool("IP_BINDING_ENABLED", "True")
    IP_BINDING_TYPE_ALLOWED = os.environ.get("IP_BINDING_TYPE_ALLOWED", "regular")
    IP_BINDING_TYPE_BLOCKED = os.environ.get("IP_BINDING_TYPE_BLOCKED", "blocked")
    HOTSPOT_BYPASS_STATUSES = get_env_list("HOTSPOT_BYPASS_STATUSES", "['active','fup','unlimited']")
    IP_BINDING_FAIL_OPEN = get_env_bool("IP_BINDING_FAIL_OPEN", "False")
    MAX_DEVICES_PER_USER = get_env_int("MAX_DEVICES_PER_USER", 3)
    REQUIRE_EXPLICIT_DEVICE_AUTH = get_env_bool("REQUIRE_EXPLICIT_DEVICE_AUTH", "False")
    DEVICE_STALE_DAYS = get_env_int("DEVICE_STALE_DAYS", 30)
    WALLED_GARDEN_ENABLED = get_env_bool("WALLED_GARDEN_ENABLED", "False")
    WALLED_GARDEN_ALLOWED_HOSTS = get_env_list("WALLED_GARDEN_ALLOWED_HOSTS", "[]")
    WALLED_GARDEN_ALLOWED_IPS = get_env_list("WALLED_GARDEN_ALLOWED_IPS", "[]")
    WALLED_GARDEN_AUTO_INCLUDE_EXTERNAL_HOSTS = get_env_bool("WALLED_GARDEN_AUTO_INCLUDE_EXTERNAL_HOSTS", "True")
    WALLED_GARDEN_AUTO_INCLUDE_PORTAL_HOSTS = get_env_bool("WALLED_GARDEN_AUTO_INCLUDE_PORTAL_HOSTS", "True")
    WALLED_GARDEN_INCLUDE_MIDTRANS_HOSTS = get_env_bool("WALLED_GARDEN_INCLUDE_MIDTRANS_HOSTS", "True")
    WALLED_GARDEN_INCLUDE_MESSAGING_HOSTS = get_env_bool("WALLED_GARDEN_INCLUDE_MESSAGING_HOSTS", "True")
    WALLED_GARDEN_EXTRA_EXTERNAL_URLS = get_env_list("WALLED_GARDEN_EXTRA_EXTERNAL_URLS", "[]")
    WALLED_GARDEN_MANAGED_COMMENT_PREFIX = os.environ.get("WALLED_GARDEN_MANAGED_COMMENT_PREFIX", "lpsaring")
    WALLED_GARDEN_SYNC_INTERVAL_MINUTES = get_env_int("WALLED_GARDEN_SYNC_INTERVAL_MINUTES", 30)
    # --- Akhir Konfigurasi MikroTik API ---

    # --- Konfigurasi Sinkronisasi Kuota & Notifikasi ---
    QUOTA_SYNC_INTERVAL_SECONDS = get_env_int("QUOTA_SYNC_INTERVAL_SECONDS", 300)
    QUOTA_FUP_THRESHOLD_MB = get_env_int("QUOTA_FUP_THRESHOLD_MB", 3072)
    QUOTA_NOTIFY_REMAINING_MB = get_env_list("QUOTA_NOTIFY_REMAINING_MB", "[500]")
    QUOTA_EXPIRY_NOTIFY_DAYS = get_env_list("QUOTA_EXPIRY_NOTIFY_DAYS", "[7, 3, 1]")
    INACTIVE_DEACTIVATE_DAYS = get_env_int("INACTIVE_DEACTIVATE_DAYS", 45)
    INACTIVE_DELETE_DAYS = get_env_int("INACTIVE_DELETE_DAYS", 90)
    # --- Kebijakan Permintaan Komandan ---
    KOMANDAN_REQUEST_WINDOW_HOURS = get_env_int("KOMANDAN_REQUEST_WINDOW_HOURS", 24)
    KOMANDAN_REQUEST_MAX_PER_WINDOW = get_env_int("KOMANDAN_REQUEST_MAX_PER_WINDOW", 1)
    KOMANDAN_REQUEST_COOLDOWN_HOURS = get_env_int("KOMANDAN_REQUEST_COOLDOWN_HOURS", 6)
    KOMANDAN_ALLOW_UNLIMITED_REQUEST = get_env_bool("KOMANDAN_ALLOW_UNLIMITED_REQUEST", "True")
    KOMANDAN_MAX_QUOTA_MB = get_env_int("KOMANDAN_MAX_QUOTA_MB", 51200)
    KOMANDAN_MAX_QUOTA_DAYS = get_env_int("KOMANDAN_MAX_QUOTA_DAYS", 30)
    KOMANDAN_MAX_UNLIMITED_DAYS = get_env_int("KOMANDAN_MAX_UNLIMITED_DAYS", 30)
    # --- Akhir Konfigurasi Sinkronisasi Kuota & Notifikasi ---

    # --- Konfigurasi Logging ---
    LOG_TO_FILE = get_env_bool("LOG_TO_FILE", "False")
    LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO" if FLASK_ENV == "production" else "DEBUG").upper()
    LOG_DIR = os.environ.get("LOG_DIR", "logs")
    LOG_FILENAME = os.environ.get("LOG_FILENAME", "hotspot_portal.log")
    LOG_MAX_BYTES = get_env_int("LOG_MAX_BYTES", 10 * 1024 * 1024)
    LOG_BACKUP_COUNT = get_env_int("LOG_BACKUP_COUNT", 5)
    LOG_FILE_LEVEL = os.environ.get("LOG_FILE_LEVEL", "INFO").upper()
    LOG_FORMAT_JSON = get_env_bool("LOG_FORMAT_JSON", "False")
    LOG_IP_HEADER_DEBUG = get_env_bool("LOG_IP_HEADER_DEBUG", "False")
    LOG_BINDING_DEBUG = get_env_bool("LOG_BINDING_DEBUG", "False")

    # --- Konfigurasi ProxyFix ---
    PROXYFIX_X_FOR = get_env_int("PROXYFIX_X_FOR", 1)
    PROXYFIX_X_PROTO = get_env_int("PROXYFIX_X_PROTO", 1)
    PROXYFIX_X_HOST = get_env_int("PROXYFIX_X_HOST", 0)
    PROXYFIX_X_PORT = get_env_int("PROXYFIX_X_PORT", 0)
    PROXYFIX_X_PREFIX = get_env_int("PROXYFIX_X_PREFIX", 0)
    TRUST_CF_CONNECTING_IP = get_env_bool("TRUST_CF_CONNECTING_IP", "False")
    TRUSTED_PROXY_CIDRS = get_env_list(
        "TRUSTED_PROXY_CIDRS", "['127.0.0.1/32','10.0.0.0/8','172.16.0.0/12','192.168.0.0/16']"
    )
    HOTSPOT_CLIENT_IP_CIDRS = get_env_list("HOTSPOT_CLIENT_IP_CIDRS", "['10.0.0.0/8','172.16.0.0/12','192.168.0.0/16']")

    # Unauthorized host blocking (optional; used by `flask sync-unauthorized-hosts`)
    # Default diarahkan hanya VLAN Klien.
    MIKROTIK_UNAUTHORIZED_CIDRS = get_env_list("MIKROTIK_UNAUTHORIZED_CIDRS", "['172.16.2.0/23']")

    # Optional: lock managed static DHCP leases to specific client CIDRs.
    # If empty, runtime logic will fall back to MIKROTIK_UNAUTHORIZED_CIDRS.
    MIKROTIK_DHCP_STATIC_LEASE_CIDRS = get_env_list("MIKROTIK_DHCP_STATIC_LEASE_CIDRS", "[]")
    # IP/range yang dikecualikan untuk maintenance. Contoh: ['172.16.2.3-7']
    MIKROTIK_UNAUTHORIZED_EXEMPT_IPS = get_env_list("MIKROTIK_UNAUTHORIZED_EXEMPT_IPS", "['172.16.2.3-7']")

    OTP_ALLOW_BYPASS = get_env_bool("OTP_ALLOW_BYPASS", "False")
    OTP_BYPASS_CODE = os.environ.get("OTP_BYPASS_CODE", "000000")
    DEMO_MODE_ENABLED = get_env_bool("DEMO_MODE_ENABLED", "False")
    DEMO_ALLOWED_PHONES = get_env_list("DEMO_ALLOWED_PHONES", "[]")
    DEMO_BYPASS_OTP_CODE = os.environ.get("DEMO_BYPASS_OTP_CODE", "000000")
    DEMO_SHOW_TEST_PACKAGE = get_env_bool("DEMO_SHOW_TEST_PACKAGE", "False")
    DEMO_PACKAGE_IDS = get_env_list("DEMO_PACKAGE_IDS", "[]")
    SYNC_ADDRESS_LIST_ON_LOGIN = get_env_bool("SYNC_ADDRESS_LIST_ON_LOGIN", "True")
    SESSION_TOKEN_EXPIRE_SECONDS = get_env_int("SESSION_TOKEN_EXPIRE_SECONDS", 120)

    DEV_BYPASS_USER_ENDPOINTS = get_env_bool("DEV_BYPASS_USER_ENDPOINTS", "False")
    DEV_BYPASS_USER_PHONE = os.environ.get("DEV_BYPASS_USER_PHONE")
    DEV_BYPASS_USER_ID = os.environ.get("DEV_BYPASS_USER_ID")
    DEV_BYPASS_TOKEN = os.environ.get("DEV_BYPASS_TOKEN")

    # --- Konfigurasi Lainnya ---
    FRONTEND_URL = os.environ.get("FRONTEND_URL")
    # --- PENAMBAHAN VARIABEL BARU ---
    APP_PUBLIC_BASE_URL = os.environ.get("APP_PUBLIC_BASE_URL")
    # -------------------------------
    CORS_ADDITIONAL_ORIGINS = get_env_list("CORS_ADDITIONAL_ORIGINS", "[]")
    APP_LOCALE = os.environ.get("APP_LOCALE", "id_ID.UTF-8")
    APP_TIMEZONE = os.environ.get("APP_TIMEZONE", "Asia/Makassar")
    CURRENCY_SYMBOL = os.environ.get("CURRENCY_SYMBOL", "Rp ")
    JINJA_DATETIME_FORMAT = os.environ.get("JINJA_DATETIME_FORMAT", "%d/%m/%y %H:%M")
    JINJA_DATETIME_SHORT_FORMAT = os.environ.get("JINJA_DATETIME_SHORT_FORMAT", "%b %d, %Y")
    ENABLE_ADMIN_ROUTES = get_env_bool("ENABLE_ADMIN_ROUTES", "False")
    APP_LINK_USER = os.environ.get("APP_LINK_USER") or APP_PUBLIC_BASE_URL or FRONTEND_URL
    APP_LINK_ADMIN = os.environ.get("APP_LINK_ADMIN") or (
        f"{APP_LINK_USER.rstrip('/')}/admin" if APP_LINK_USER else None
    )
    APP_LINK_MIKROTIK = os.environ.get("APP_LINK_MIKROTIK")
    APP_LINK_ADMIN_CHANGE_PASSWORD = os.environ.get("APP_LINK_ADMIN_CHANGE_PASSWORD") or (
        f"{APP_LINK_ADMIN.rstrip('/')}/account-settings" if APP_LINK_ADMIN else None
    )

    PUBLIC_SETTINGS_CACHE_TTL_SECONDS = get_env_int("PUBLIC_SETTINGS_CACHE_TTL_SECONDS", 300)
    METRICS_TTL_SECONDS = get_env_int("METRICS_TTL_SECONDS", 86400)
    TASK_DLQ_REDIS_KEY = os.environ.get("TASK_DLQ_REDIS_KEY", "celery:dlq")

    CIRCUIT_BREAKER_FAILURE_THRESHOLD = get_env_int("CIRCUIT_BREAKER_FAILURE_THRESHOLD", 5)
    CIRCUIT_BREAKER_RESET_SECONDS = get_env_int("CIRCUIT_BREAKER_RESET_SECONDS", 60)
    CIRCUIT_BREAKER_HALF_OPEN_SUCCESS = get_env_int("CIRCUIT_BREAKER_HALF_OPEN_SUCCESS", 2)

    @classmethod
    def validate_production_config(cls):
        if cls.FLASK_ENV == "production":
            if not cls.SECRET_KEY or cls.SECRET_KEY == "dev-secret-key-ganti-ini-di-produksi":
                raise ValueError("ERROR: SECRET_KEY harus disetel dengan nilai yang kuat di environment production!")
            if not cls.JWT_SECRET_KEY or cls.JWT_SECRET_KEY == "dev-jwt-secret-key-ganti-ini-di-produksi":
                raise ValueError(
                    "ERROR: JWT_SECRET_KEY harus disetel dengan nilai yang kuat di environment production!"
                )
            if not cls.SQLALCHEMY_DATABASE_URI:
                raise ValueError("ERROR: DATABASE_URL harus disetel di environment production!")

            # --- PENAMBAHAN VALIDASI UNTUK URL PUBLIK ---
            if not cls.APP_PUBLIC_BASE_URL:
                raise ValueError(
                    "ERROR: APP_PUBLIC_BASE_URL harus disetel di environment production! Ini dibutuhkan untuk callback dan URL eksternal."
                )
            # ---------------------------------------------

            if not cls.MIDTRANS_SERVER_KEY or not cls.MIDTRANS_CLIENT_KEY:
                warnings.warn(
                    "PERINGATAN PRODUKSI: Kunci Midtrans (SERVER/CLIENT) tidak disetel. Fitur pembayaran tidak akan berfungsi."
                )
            if not cls.MIDTRANS_REQUIRE_SIGNATURE_VALIDATION:
                warnings.warn(
                    "PERINGATAN PRODUKSI: MIDTRANS_REQUIRE_SIGNATURE_VALIDATION=False. Webhook Midtrans tidak aman."
                )
            if cls.ENABLE_WHATSAPP_NOTIFICATIONS and (not cls.WHATSAPP_API_URL or not cls.WHATSAPP_API_KEY):
                warnings.warn(
                    "PERINGATAN PRODUKSI: Notifikasi WhatsApp diaktifkan tetapi URL/Kunci API WhatsApp tidak disetel."
                )
            if cls.ENABLE_WHATSAPP_NOTIFICATIONS and not cls.WHATSAPP_VALIDATE_URL:
                warnings.warn(
                    "PERINGATAN PRODUKSI: WHATSAPP_VALIDATE_URL tidak disetel. Validasi nomor WhatsApp akan gagal."
                )
            if not cls.MIKROTIK_HOST or not cls.MIKROTIK_USERNAME or not cls.MIKROTIK_PASSWORD:
                warnings.warn(
                    "PERINGATAN PRODUKSI: Konfigurasi MikroTik tidak lengkap. Fitur hotspot mungkin tidak berfungsi."
                )
            if not cls.RATELIMIT_STORAGE_URI or "memory://" in cls.RATELIMIT_STORAGE_URI:
                warnings.warn(
                    "PERINGATAN PRODUKSI: RATELIMIT_STORAGE_URI tidak disetel ke backend Redis yang valid. Rate limiting tidak akan persisten."
                )
            if not cls.AUTH_COOKIE_SECURE:
                warnings.warn("PERINGATAN PRODUKSI: AUTH_COOKIE_SECURE sebaiknya True untuk HTTPS.")
            if not cls.AUTH_COOKIE_HTTPONLY:
                warnings.warn("PERINGATAN PRODUKSI: AUTH_COOKIE_HTTPONLY sebaiknya True untuk keamanan.")


class DevelopmentConfig(Config):
    FLASK_DEBUG = True
    FLASK_ENV = "development"
    SQLALCHEMY_ECHO = get_env_bool("SQLALCHEMY_ECHO", "True")
    LOG_LEVEL = os.environ.get("LOG_LEVEL", "DEBUG").upper()
    RATELIMIT_DEFAULT = os.environ.get("API_RATE_LIMIT", "500 per minute")
    ENABLE_WHATSAPP_NOTIFICATIONS = get_env_bool("ENABLE_WHATSAPP_NOTIFICATIONS", "True")
    RATELIMIT_ENABLED = get_env_bool("RATELIMIT_ENABLED", "False")

    MIKROTIK_SEND_LIMIT_BYTES_TOTAL = get_env_bool("MIKROTIK_SEND_LIMIT_BYTES_TOTAL", "False")
    MIKROTIK_SEND_SESSION_TIMEOUT = get_env_bool("MIKROTIK_SEND_SESSION_TIMEOUT", "False")


class ProductionConfig(Config):
    FLASK_DEBUG = False
    FLASK_ENV = "production"
    SQLALCHEMY_ECHO = False
    LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
    MIDTRANS_IS_PRODUCTION = get_env_bool("MIDTRANS_IS_PRODUCTION", "True")
    ENABLE_WHATSAPP_NOTIFICATIONS = get_env_bool("ENABLE_WHATSAPP_NOTIFICATIONS", "True")
    RATELIMIT_ENABLED = get_env_bool("RATELIMIT_ENABLED", "True")

    MIKROTIK_SEND_LIMIT_BYTES_TOTAL = get_env_bool("MIKROTIK_SEND_LIMIT_BYTES_TOTAL", "True")
    MIKROTIK_SEND_SESSION_TIMEOUT = get_env_bool("MIKROTIK_SEND_SESSION_TIMEOUT", "True")


class TestingConfig(Config):
    TESTING = True
    FLASK_DEBUG = True
    FLASK_ENV = "testing"
    SQLALCHEMY_DATABASE_URI = os.environ.get("TEST_DATABASE_URL") or "sqlite:///:memory:"
    SQLALCHEMY_ECHO = get_env_bool("SQLALCHEMY_ECHO", "False")
    JWT_SECRET_KEY = "test-jwt-secret-key"
    SECRET_KEY = "test-secret-key"
    ENABLE_WHATSAPP_NOTIFICATIONS = False
    MIDTRANS_SERVER_KEY = "test-midtrans-server-key"
    MIDTRANS_CLIENT_KEY = "test-midtrans-client-key"
    MIDTRANS_IS_PRODUCTION = False
    RATELIMIT_ENABLED = False
    LOG_LEVEL = "DEBUG"
    LOG_TO_FILE = False
    APP_PUBLIC_BASE_URL = os.environ.get("APP_PUBLIC_BASE_URL", "http://testserver")  # Tambahkan untuk testing


config_options = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
    "default": DevelopmentConfig,
}
