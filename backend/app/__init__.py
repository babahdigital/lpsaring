# backend/app/__init__.py
# VERSI FINAL: Mengembalikan logika-logika penting yang hilang dan mempertahankan struktur yang robust.

import os
import sys
import logging
import uuid
import json
from typing import Optional
from datetime import datetime, timezone as dt_timezone
from logging.handlers import RotatingFileHandler
from werkzeug.exceptions import HTTPException

import redis
from flask import Flask, current_app, request, jsonify, g
from http import HTTPStatus
from jose import jwt, JWTError, ExpiredSignatureError
from werkzeug.middleware.proxy_fix import ProxyFix

from config import config_options

# Import celery_app dan make_celery_app dari extensions
from .extensions import db, migrate, cors, limiter, make_celery_app
from .infrastructure.db.models import UserRole
from .infrastructure.http.json_provider import CustomJSONProvider
from .services import settings_service
from app.utils.auth_cookie_utils import set_access_cookie, set_refresh_cookie

module_log = logging.getLogger(__name__)


def _ensure_dev_superadmin_if_configured(app: Flask) -> None:
    """Create a SUPER_ADMIN user from env in development mode (idempotent).

    Rules:
    - Development only.
    - Requires SUPERADMIN_PHONE + SUPERADMIN_PASSWORD.
    - If a matching user already exists, do nothing.
    - Safe under multi-worker (handles IntegrityError).
    """

    if app.testing:
        return

    flask_env = (os.getenv("FLASK_ENV") or "").strip().lower()
    if flask_env != "development":
        return

    phone_raw = (os.getenv("SUPERADMIN_PHONE") or "").strip()
    password = os.getenv("SUPERADMIN_PASSWORD")
    name = (os.getenv("SUPERADMIN_NAME") or "Super Admin").strip() or "Super Admin"

    if not phone_raw or not password:
        return

    try:
        from sqlalchemy.exc import IntegrityError, OperationalError, ProgrammingError
        from werkzeug.security import generate_password_hash

        from app.infrastructure.db.models import ApprovalStatus, User, UserRole
        from app.utils.formatters import get_phone_number_variations, normalize_to_e164
    except Exception:
        module_log.exception("Dev superadmin bootstrap skipped: required modules not available")
        return

    with app.app_context():
        variations = [v for v in (get_phone_number_variations(phone_raw) or []) if v]
        if not variations:
            module_log.warning("Dev superadmin bootstrap skipped: invalid SUPERADMIN_PHONE=%r", phone_raw)
            return

        try:
            existing = db.session.query(User).filter(User.phone_number.in_(variations)).first()
            if existing:
                module_log.info(
                    "Dev superadmin already exists (id=%s phone=%s role=%s); skipping",
                    getattr(existing, "id", None),
                    getattr(existing, "phone_number", None),
                    getattr(getattr(existing, "role", None), "value", None),
                )
                return

            phone_e164 = normalize_to_e164(phone_raw)

            # SQLAlchemy declarative models accept kwargs at runtime, but Pylance
            # can't reliably infer the generated __init__ signature.
            # Set attributes explicitly to avoid reportCallIssue.
            new_user = User()
            new_user.phone_number = phone_e164
            new_user.full_name = name
            new_user.role = UserRole.SUPER_ADMIN
            new_user.approval_status = ApprovalStatus.APPROVED
            new_user.is_active = True
            new_user.password_hash = generate_password_hash(password)
            new_user.approved_at = datetime.now(dt_timezone.utc)
            db.session.add(new_user)
            db.session.commit()
            module_log.warning(
                "Dev superadmin created: phone=%s name=%s (role=SUPER_ADMIN)",
                phone_e164,
                name,
            )
        except IntegrityError:
            db.session.rollback()
            module_log.info("Dev superadmin bootstrap: created concurrently by another worker; skipping")
        except (OperationalError, ProgrammingError):
            db.session.rollback()
            module_log.warning("Dev superadmin bootstrap skipped: database not ready")
        except Exception:
            db.session.rollback()
            module_log.exception("Dev superadmin bootstrap failed")


class HotspotFlask(Flask):
    redis_client_otp: Optional[redis.Redis]


class RequestIdFilter(logging.Filter):
    """Menambahkan request_id ke setiap log record untuk kemudahan tracing."""

    def filter(self, record):
        try:
            if request and hasattr(request, "environ"):
                record.request_id = request.environ.get("FLASK_REQUEST_ID", "N/A_NoReqID")
            else:
                record.request_id = "N/A_NoRequestCtx"
        except RuntimeError:
            record.request_id = "N/A_NoRequestCtx_RuntimeError"
        return True


class JsonLogFormatter(logging.Formatter):
    def format(self, record):
        payload = {
            "timestamp": self.formatTime(record, datefmt="%d-%m-%Y %H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", None),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=True)


def setup_logging(app: Flask):
    """Mengkonfigurasi logging untuk aplikasi dengan konfigurasi yang fleksibel."""
    log_level_str = app.config.get("LOG_LEVEL", "INFO").upper()
    log_level = getattr(logging, log_level_str, logging.INFO)

    root_logger = logging.getLogger()
    app_logger = logging.getLogger("flask.app")
    werkzeug_logger = logging.getLogger("werkzeug")
    gunicorn_error_logger = logging.getLogger("gunicorn.error")
    gunicorn_access_logger = logging.getLogger("gunicorn.access")
    sqlalchemy_engine_logger = logging.getLogger("sqlalchemy.engine")
    sqlalchemy_pool_logger = logging.getLogger("sqlalchemy.pool")

    use_json = app.config.get("LOG_FORMAT_JSON", False)
    if use_json:
        log_formatter = JsonLogFormatter()
    else:
        log_formatter = logging.Formatter(
            "%(asctime)s %(levelname)-8s [%(name)s] [%(request_id)s] %(message)s [in %(pathname)s:%(lineno)d]",
            datefmt="%d-%m-%Y %H:%M:%S",
        )
    request_id_filter = RequestIdFilter()
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(log_formatter)
    stream_handler.addFilter(request_id_filter)
    loggers_to_config = [
        root_logger,
        app_logger,
        werkzeug_logger,
        gunicorn_error_logger,
        gunicorn_access_logger,
        sqlalchemy_engine_logger,
        sqlalchemy_pool_logger,
    ]
    for logger in loggers_to_config:
        logger.handlers.clear()
        logger.setLevel(log_level)
        logger.addHandler(stream_handler)
        if logger is not root_logger:
            logger.propagate = False

    if app.config.get("LOG_TO_FILE", False) and not app.testing:
        log_dir = app.config.get("LOG_DIR", "logs")
        # DIKEMBALIKAN: Logika path absolut yang fleksibel
        project_root = os.path.abspath(os.path.join(app.root_path, ".."))
        if not os.path.isabs(log_dir):
            log_dir = os.path.join(project_root, log_dir)
        # DIKEMBALIKAN: Penanganan error saat membuat direktori log
        try:
            os.makedirs(log_dir, exist_ok=True)
            log_file = os.path.join(log_dir, app.config.get("LOG_FILENAME", "app.log"))
            # DIKEMBALIKAN: Konfigurasi file log yang dinamis dari config
            file_handler = RotatingFileHandler(
                log_file,
                maxBytes=app.config.get("LOG_MAX_BYTES", 10 * 1024 * 1024),
                backupCount=app.config.get("LOG_BACKUP_COUNT", 5),
                encoding="utf-8",
            )
            file_handler.setFormatter(log_formatter)
            file_handler.setLevel(app.config.get("LOG_FILE_LEVEL", "INFO").upper())
            file_handler.addFilter(request_id_filter)
            app_logger.addHandler(file_handler)
            module_log.info(f"File logging diaktifkan: {log_file}")
        except Exception as e:
            module_log.error(f"Gagal menginisialisasi file logging: {e}", exc_info=True)

    module_log.info(f"Setup logging selesai. Log Level: {log_level_str}")


def register_extensions(app: HotspotFlask):
    """Mendaftarkan semua ekstensi Flask."""
    module_log.info("Menginisialisasi ekstensi...")
    db.init_app(app)
    migrate.init_app(app, db)

    frontend_url = (
        app.config.get("FRONTEND_URL") or app.config.get("APP_PUBLIC_BASE_URL") or app.config.get("APP_LINK_USER")
    )
    allowed_origins = list(
        set([origin for origin in [frontend_url, *app.config.get("CORS_ADDITIONAL_ORIGINS", [])] if origin])
    )
    cors.init_app(app, resources={r"/api/*": {"origins": allowed_origins}}, supports_credentials=True)
    module_log.info(f"CORS diinisialisasi untuk origins: {allowed_origins}")

    if app.config.get("RATELIMIT_ENABLED", True) and not app.testing:
        limiter.init_app(app)
        module_log.info("Rate limiter diinisialisasi.")

    if not app.testing:
        try:
            app.redis_client_otp = redis.Redis(
                host=app.config["REDIS_HOST_OTP"],
                port=app.config["REDIS_PORT_OTP"],
                db=app.config["REDIS_DB_OTP"],
                password=app.config.get("REDIS_PASSWORD_OTP"),
                decode_responses=True,
                socket_connect_timeout=5,
            )
            app.redis_client_otp.ping()
            module_log.info(f"Koneksi Redis untuk OTP berhasil (Host: {app.config['REDIS_HOST_OTP']}).")
        except Exception as e:
            module_log.critical(f"Koneksi ke Redis GAGAL: {e}. Fitur OTP tidak akan berfungsi.", exc_info=True)
            app.redis_client_otp = None
    else:
        app.redis_client_otp = None

    # --- INTEGRASI CELERY APP ---
    # Panggil make_celery_app dengan instance aplikasi Flask.
    # Ini akan menginisialisasi Celery dengan konfigurasi Flask Anda
    # dan mengaitkan task dengan app context Flask.
    make_celery_app(app)
    module_log.info("Celery diinisialisasi dan dikaitkan dengan aplikasi Flask.")
    # --- AKHIR INTEGRASI CELERY APP ---

    module_log.info("Pendaftaran ekstensi selesai.")


def register_blueprints(app: Flask):
    """Mendaftarkan semua blueprint API ke aplikasi."""
    module_log.info("Mendaftarkan blueprints...")
    # DIKEMBALIKAN: Penanganan error saat impor blueprint
    try:
        from .infrastructure.http.auth_routes import auth_bp
        from .infrastructure.http.packages_routes import packages_bp
        from .infrastructure.http.transactions_routes import transactions_bp
        from .infrastructure.http.public_routes import public_bp
        from .infrastructure.http.user.profile_routes import profile_bp
        from .infrastructure.http.user.data_routes import data_bp
        from .infrastructure.http.public_user_routes import public_user_bp
        from .infrastructure.http.public_promo_routes import public_promo_bp
        from .infrastructure.http.komandan.komandan_routes import komandan_bp
        from .infrastructure.http.health_routes import health_bp
        from .infrastructure.http.telegram_webhook_routes import telegram_bp

        blueprints = [
            (auth_bp, None),
            (packages_bp, None),
            (transactions_bp, None),
            (public_bp, None),
            (profile_bp, None),
            (data_bp, None),
            (public_user_bp, None),
            (public_promo_bp, None),
            (komandan_bp, None),
            (health_bp, None),
            (telegram_bp, None),
        ]

        for bp, prefix in blueprints:
            app.register_blueprint(bp, url_prefix=prefix)
            module_log.info(f"Blueprint '{bp.name}' berhasil didaftarkan.")

        if app.config.get("ENABLE_ADMIN_ROUTES", True):
            ADMIN_API_PREFIX = "/api/admin"
            from .infrastructure.http.admin.user_management_routes import user_management_bp
            from .infrastructure.http.admin.package_management_routes import package_management_bp
            from .infrastructure.http.admin.settings_routes import settings_management_bp
            from .infrastructure.http.admin.profile_management_routes import profile_management_bp
            from .infrastructure.http.admin.promo_management_routes import promo_management_bp
            from .infrastructure.http.admin_routes import admin_bp
            from .infrastructure.http.admin.request_management_routes import request_mgmt_bp
            from .infrastructure.http.admin.action_log_routes import action_log_bp
            from .infrastructure.http.admin.metrics_routes import metrics_bp

            admin_blueprints = [
                user_management_bp,
                package_management_bp,
                settings_management_bp,
                profile_management_bp,
                promo_management_bp,
                admin_bp,
                request_mgmt_bp,
                action_log_bp,
                metrics_bp,
            ]
            for bp in admin_blueprints:
                app.register_blueprint(bp, url_prefix=ADMIN_API_PREFIX)
                module_log.info(f"Admin blueprint '{bp.name}' didaftarkan di '{ADMIN_API_PREFIX}'.")

    except ImportError as e:
        module_log.error(f"Gagal mengimpor salah satu blueprint: {e}", exc_info=True)

    module_log.info("Pendaftaran blueprints selesai.")


def register_models(_app: Flask):
    from .infrastructure.db import models as _models  # noqa: F401

    module_log.debug("Modul DB Models telah diimpor.")


def register_error_handlers(app: Flask) -> None:
    def _is_api_request() -> bool:
        return request.path.startswith("/api")

    @app.errorhandler(HTTPException)
    def handle_http_exception(error: HTTPException):
        if not _is_api_request():
            return error.get_response()
        status_code = int(error.code or HTTPStatus.INTERNAL_SERVER_ERROR)
        message = error.description or error.name
        payload = {
            "error": message,
            "message": message,
            "status_code": status_code,
        }
        return jsonify(payload), status_code

    @app.errorhandler(Exception)
    def handle_unexpected_exception(error: Exception):
        current_app.logger.error("Unhandled exception: %s", error, exc_info=True)
        payload = {
            "error": "Internal server error.",
            "status_code": HTTPStatus.INTERNAL_SERVER_ERROR,
        }
        return jsonify(payload), HTTPStatus.INTERNAL_SERVER_ERROR


# DIKEMBALIKAN: Fungsi untuk mendaftarkan rute tes
def register_test_routes(app: Flask):
    @app.route("/api/ping", methods=["GET"])
    @limiter.limit(app.config.get("PING_RATE_LIMIT", "5 per minute"))
    def ping():
        return {"message": "pong from backend!", "server_time_utc": datetime.now(dt_timezone.utc).isoformat()}

    module_log.info("Rute tes '/api/ping' telah didaftarkan.")


def register_commands(app: Flask):
    from .commands import (
        user_commands,
        seed_commands,
        sync_usage_command,
        sync_mikrotik_comments_command,
        sync_mikrotik_access_command,
        sync_dhcp_leases_command,
    )
    from .commands.manual_debt_command import add_manual_debt_command
    from .commands.sync_unauthorized_hosts_command import sync_unauthorized_hosts_command
    from .commands.bulk_reset_quota_command import bulk_reset_quota_command
    from .commands.cleanup_transactions_command import cleanup_transactions_command

    app.cli.add_command(user_commands.user_cli_bp)
    app.cli.add_command(seed_commands.seed_db_command)
    app.cli.add_command(sync_usage_command.sync_usage_command)
    app.cli.add_command(sync_mikrotik_comments_command.sync_mikrotik_comments_command)
    app.cli.add_command(sync_mikrotik_access_command.sync_mikrotik_access_command)
    app.cli.add_command(sync_dhcp_leases_command.sync_dhcp_leases_command)
    app.cli.add_command(add_manual_debt_command)
    app.cli.add_command(sync_unauthorized_hosts_command)
    app.cli.add_command(bulk_reset_quota_command)
    app.cli.add_command(cleanup_transactions_command)
    module_log.info("Pendaftaran perintah CLI selesai.")


def create_app(config_name: Optional[str] = None) -> HotspotFlask:
    """Factory function untuk membuat dan mengkonfigurasi aplikasi Flask."""

    def _resolve_config_name(explicit_name: Optional[str]) -> str:
        if explicit_name:
            return explicit_name
        env_name = os.getenv("FLASK_CONFIG")
        if env_name:
            return env_name

        flask_env = (os.getenv("FLASK_ENV") or "").strip().lower()
        if flask_env == "production":
            return "production"
        if flask_env == "testing":
            return "testing"
        if flask_env == "development":
            return "development"
        return "default"

    config_name_str: str = _resolve_config_name(config_name)
    app = HotspotFlask("hotspot_app")
    app.json = CustomJSONProvider(app)

    config_cls = config_options[config_name_str]
    app.config.from_object(config_cls)

    # Pastikan validasi produksi selalu berjalan saat config production dipakai.
    # (Flask `from_object` membaca atribut class tanpa memanggil `__init__`.)
    if config_name_str == "production" and hasattr(config_cls, "validate_production_config"):
        config_cls.validate_production_config()

    # DIKEMBALIKAN: Konfigurasi ProxyFix yang lebih fleksibel
    if any(
        [
            app.config.get("PROXYFIX_X_FOR", 0) > 0,
            app.config.get("PROXYFIX_X_PROTO", 0) > 0,
            app.config.get("PROXYFIX_X_HOST", 0) > 0,
            app.config.get("PROXYFIX_X_PORT", 0) > 0,
            app.config.get("PROXYFIX_X_PREFIX", 0) > 0,
        ]
    ):
        proxy_fix_config = {
            "x_for": app.config.get("PROXYFIX_X_FOR", 1),
            "x_proto": app.config.get("PROXYFIX_X_PROTO", 1),
            "x_host": app.config.get("PROXYFIX_X_HOST", 0),
            "x_port": app.config.get("PROXYFIX_X_PORT", 0),
            "x_prefix": app.config.get("PROXYFIX_X_PREFIX", 0),
        }
        app.wsgi_app = ProxyFix(app.wsgi_app, **proxy_fix_config)

    # --- Register Hooks ---
    @app.before_request
    def ensure_request_id_hook():
        # DIKEMBALIKAN: Fallback ke X-Request-ID dari header
        if "FLASK_REQUEST_ID" not in request.environ:
            request.environ["FLASK_REQUEST_ID"] = request.headers.get("X-Request-ID") or str(uuid.uuid4())

    @app.before_request
    def check_maintenance_mode_hook():
        # DIKEMBALIKAN: Logika maintenance mode yang lebih komprehensif
        is_maintenance = settings_service.get_setting("MAINTENANCE_MODE_ACTIVE", "False") == "True"
        if not is_maintenance:
            return

        # Izinkan akses ke endpoint public tertentu
        allowed_paths = ["/api/admin", "/api/auth", "/api/settings/public"]
        if any(request.path.startswith(p) for p in allowed_paths):
            return

        # Izinkan admin yang sudah login untuk bypass
        token = None
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]

        if not token:
            cookie_name = current_app.config.get("AUTH_COOKIE_NAME", "auth_token")
            token = request.cookies.get(cookie_name)

        if token:
            try:
                payload = jwt.decode(
                    token, current_app.config["JWT_SECRET_KEY"], algorithms=[current_app.config["JWT_ALGORITHM"]]
                )
                if payload.get("rl") in [UserRole.ADMIN.value, UserRole.SUPER_ADMIN.value]:
                    return
            except (JWTError, ExpiredSignatureError):
                pass

        message = settings_service.get_setting("MAINTENANCE_MODE_MESSAGE", "Aplikasi sedang dalam perbaikan.")
        return jsonify({"message": message}), HTTPStatus.SERVICE_UNAVAILABLE

    @app.after_request
    def apply_refreshed_auth_cookies_hook(response):
        # token_required dapat melakukan auto-refresh access token dari refresh cookie.
        # Token baru disimpan di flask.g agar bisa dipasang ke response apa pun.
        try:
            new_access = getattr(g, "new_access_token", None)
            if isinstance(new_access, str) and new_access:
                set_access_cookie(response, new_access)

            new_refresh = getattr(g, "new_refresh_token", None)
            if isinstance(new_refresh, str) and new_refresh:
                set_refresh_cookie(response, new_refresh)
        except Exception:
            pass
        return response

    # --- Inisialisasi Komponen Aplikasi ---
    setup_logging(app)
    register_extensions(app)  # Ini akan menginisialisasi semua ekstensi, termasuk Celery
    register_models(app)
    register_blueprints(app)
    register_error_handlers(app)
    register_test_routes(app)  # Memanggil kembali fungsi pendaftaran rute tes
    register_commands(app)

    _ensure_dev_superadmin_if_configured(app)

    module_log.info(f"Inisialisasi aplikasi '{app.name}' selesai untuk environment '{config_name}'.")
    return app
