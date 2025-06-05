# backend/app/__init__.py
"""File utama untuk inisialisasi aplikasi Flask (Application Factory)."""

import os
import sys
import logging
import locale
from datetime import datetime, date, timezone as dt_timezone
from logging.handlers import RotatingFileHandler
from flask import Flask, current_app, request # Tambahkan request
import redis
from werkzeug.middleware.proxy_fix import ProxyFix
import uuid

from config import config_options, Config
from .extensions import db, migrate, cors, limiter

module_log = logging.getLogger(__name__)

class RequestIdFilter(logging.Filter):
    def filter(self, record):
        try:
            if request and hasattr(request, 'environ'):
                record.request_id = request.environ.get('FLASK_REQUEST_ID', 'N/A_NoReqID')
            else:
                record.request_id = 'N/A_NoRequestCtx'
        except RuntimeError:
             record.request_id = 'N/A_NoRequestCtx_RuntimeError'
        return True

def setup_logging(app: Flask):
    log_level_str = app.config.get('LOG_LEVEL', 'INFO').upper()
    log_level = getattr(logging, log_level_str, logging.INFO)
    
    flask_app_logger = logging.getLogger('flask.app')
    werkzeug_logger = logging.getLogger('werkzeug')

    flask_app_logger.handlers.clear()
    werkzeug_logger.handlers.clear()

    flask_app_logger.setLevel(log_level)
    werkzeug_logger.setLevel(log_level)

    log_formatter = logging.Formatter(
        '%(asctime)s %(levelname)-8s [%(name)s] [%(request_id)s] %(message)s [in %(pathname)s:%(lineno)d]'
    )
    
    request_id_filter = RequestIdFilter()

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(log_formatter)
    stream_handler.setLevel(log_level)
    stream_handler.addFilter(request_id_filter)

    flask_app_logger.addHandler(stream_handler)
    werkzeug_logger.addHandler(stream_handler)

    flask_app_logger.propagate = False
    werkzeug_logger.propagate = False

    if app.config.get('LOG_TO_FILE', False) and not app.testing:
        log_dir = app.config.get('LOG_DIR', 'logs')
        project_root = os.path.abspath(os.path.join(app.root_path, '..'))
        if not os.path.isabs(log_dir):
            log_dir = os.path.join(project_root, log_dir)

        try:
            os.makedirs(log_dir, exist_ok=True)
            log_file_path = os.path.join(log_dir, app.config.get('LOG_FILENAME', 'app.log'))
            file_handler = RotatingFileHandler(
                log_file_path,
                maxBytes=app.config.get('LOG_MAX_BYTES', 10*1024*1024),
                backupCount=app.config.get('LOG_BACKUP_COUNT', 5),
                encoding='utf-8'
            )
            file_handler.setFormatter(log_formatter)
            file_handler.setLevel(app.config.get('LOG_FILE_LEVEL', 'INFO').upper())
            file_handler.addFilter(request_id_filter)

            flask_app_logger.addHandler(file_handler)
            module_log.info(f"File logging enabled: {log_file_path} at level {file_handler.level}")
        except Exception as e:
            module_log.error(f"Failed to initialize file logging to '{log_dir}': {e}", exc_info=True)
            
    module_log.info(f"Logging setup complete. App Log Level: {log_level_str}")

def register_extensions(app: Flask):
    module_log.info("Initializing extensions...")
    db.init_app(app)
    module_log.info("Database (db) initialized.")
    migrate.init_app(app, db)
    module_log.info("Migrate initialized.")

    frontend_url = app.config.get('FRONTEND_URL', 'http://localhost:3000')
    additional_origins = app.config.get('CORS_ADDITIONAL_ORIGINS', [])
    allowed_origins = [frontend_url] + additional_origins
    allowed_origins = list(set(filter(None, allowed_origins)))
    cors.init_app(app, resources={r"/api/*": {"origins": allowed_origins}}, supports_credentials=True)
    module_log.info(f"CORS initialized. Allowed origins: {allowed_origins}")

    # Limiter Init
    try:
        # PERUBAHAN KUNCI: Gunakan RATELIMIT_STORAGE_URI
        storage_uri_for_limiter = app.config.get('RATELIMIT_STORAGE_URI')
        default_rate_limit_str = app.config.get('RATELIMIT_DEFAULT')
        
        module_log.info(f"Flask-Limiter: Configured storage URI: '{storage_uri_for_limiter}'")
        module_log.info(f"Flask-Limiter: Configured default rate limit: '{default_rate_limit_str}'")
        
        # Flask-Limiter akan membaca 'RATELIMIT_STORAGE_URI' dan 'RATELIMIT_DEFAULT' dari app.config
        # Pastikan variabel ini sudah ada di app.config sebelum init_app()
        # (Seharusnya sudah karena dimuat dari objek Config)

        if not app.config.get('TESTING', False):
             if app.config.get('RATELIMIT_ENABLED', True):
                # Pastikan app.config memiliki kunci yang diharapkan oleh Flask-Limiter
                # Jika RATELIMIT_STORAGE_URI sudah ada di app.config, Flask-Limiter akan menggunakannya.
                limiter.init_app(app)
                module_log.info("Rate limiter initialized.")
                
                # Coba log storage yang efektif digunakan
                # Atribut internal bisa berubah antar versi Flask-Limiter, ini hanya upaya terbaik
                effective_storage_uri = "N/A (could not determine)"
                if hasattr(limiter, 'limiter') and hasattr(limiter.limiter, '_storage') and hasattr(limiter.limiter._storage, 'uri'):
                    effective_storage_uri = limiter.limiter._storage.uri
                elif hasattr(limiter, '_storage') and hasattr(limiter._storage, 'uri'): # Versi lebih lama
                    effective_storage_uri = limiter._storage.uri
                
                if effective_storage_uri != "N/A (could not determine)":
                    module_log.info(f"Flask-Limiter: Effective storage URI after init: {effective_storage_uri}")
                    if "memory://" in effective_storage_uri and "redis" in storage_uri_for_limiter:
                        module_log.warning("Flask-Limiter: Fallback to in-memory storage detected despite Redis configuration. Check Redis connectivity and readiness.")
                else:
                    module_log.warning("Flask-Limiter: Could not determine effective storage URI via known attributes. Check if using in-memory storage.")

             else:
                module_log.info("Rate limiter is disabled via RATELIMIT_ENABLED=False config.")
        else:
            module_log.info("Rate limiter is disabled in TESTING environment.")

    except Exception as e:
        module_log.error(f"Failed to initialize Rate Limiter: {e}", exc_info=True)
    
    # Redis Client untuk OTP
    module_log.info("Initializing Redis client for OTP...")
    try:
        if not app.config.get('TESTING'):
            app.redis_client_otp = redis.Redis(
                host=app.config['REDIS_HOST_OTP'],
                port=app.config['REDIS_PORT_OTP'],
                db=app.config['REDIS_DB_OTP'],
                password=app.config.get('REDIS_PASSWORD_OTP'),
                decode_responses=True,
                socket_connect_timeout=app.config.get('REDIS_CONNECT_TIMEOUT', 5),
                socket_timeout=app.config.get('REDIS_SOCKET_TIMEOUT', 5)
            )
            app.redis_client_otp.ping()
            module_log.info(f"Redis client for OTP connected (Host: {app.config['REDIS_HOST_OTP']}, DB: {app.config['REDIS_DB_OTP']}).")
        else:
            app.redis_client_otp = None
            module_log.info("Redis client for OTP skipped in TESTING environment.")
    except redis.exceptions.ConnectionError as e:
        module_log.critical(f"FAILED to connect to Redis for OTP: {e}. OTP features will be UNAVAILABLE.", exc_info=True)
        app.redis_client_otp = None
    except KeyError as e_key:
        module_log.critical(f"Missing Redis OTP configuration key: {e_key}. OTP functionality will be disabled.", exc_info=True)
        app.redis_client_otp = None
    except Exception as e_redis:
        module_log.critical(f"An unexpected error occurred while initializing Redis client for OTP: {e_redis}", exc_info=True)
        app.redis_client_otp = None
        
    module_log.info("Extensions registration finished.")

def register_blueprints(app: Flask):
    module_log.info("Registering blueprints...")
    try:
        from .infrastructure.http.auth_routes import auth_bp
        app.register_blueprint(auth_bp)
        module_log.info(f"Blueprint '{auth_bp.name}' registered at {auth_bp.url_prefix or '/'}.")

        from .infrastructure.http.user_routes import users_bp
        app.register_blueprint(users_bp)
        module_log.info(f"Blueprint '{users_bp.name}' registered at {users_bp.url_prefix or '/'}.")

        from .infrastructure.http.packages_routes import packages_bp
        app.register_blueprint(packages_bp)
        module_log.info(f"Blueprint '{packages_bp.name}' registered at {packages_bp.url_prefix or '/'}.")
        
        from .infrastructure.http.transactions_routes import transactions_bp
        app.register_blueprint(transactions_bp)
        module_log.info(f"Blueprint '{transactions_bp.name}' registered at {transactions_bp.url_prefix or '/'}.")

        if app.config.get('ENABLE_ADMIN_ROUTES', False):
            try:
                from .infrastructure.http.admin_routes import admin_bp
                app.register_blueprint(admin_bp)
                module_log.info(f"Blueprint '{admin_bp.name}' (Admin) registered at {admin_bp.url_prefix or '/'}.")
            except ImportError:
                module_log.warning("Admin routes enabled in config, but 'admin_routes.py' not found or failed to import.")

    except ImportError as e_bp_import:
        module_log.error(f"Failed to import a blueprint module: {e_bp_import}", exc_info=True)
    module_log.info("Blueprints registration process finished.")

def register_models(_app: Flask):
    from .infrastructure.db import models # noqa: F401,W0611
    module_log.debug("DB Models module (app.infrastructure.db.models) imported for SQLAlchemy detection.")

def register_test_routes(app: Flask):
    @app.route('/api/ping', methods=['GET'])
    @limiter.limit(app.config.get('PING_RATE_LIMIT', "5 per minute"))
    def ping():
        current_app.logger.debug(f"Ping endpoint accessed by IP: {request.remote_addr} (X-Fwd: {request.headers.get('X-Forwarded-For')})")
        now = datetime.now(dt_timezone.utc)
        hour = now.hour
        greeting = "Malam"
        if 5 <= hour < 12: greeting = "Pagi"
        elif 12 <= hour < 15: greeting = "Siang"
        elif 15 <= hour < 18: greeting = "Sore"
        return {"message": f"pong from backend! Selamat {greeting}!", "server_time_utc": now.isoformat()}
    module_log.info("Test route '/api/ping' registered.")

def register_commands(app: Flask):
    module_log.info("Registering CLI commands...")
    try:
        from .commands.seed_commands import seed_db_command
        app.cli.add_command(seed_db_command)
        module_log.info("Registered 'seed-db' command.")

        from .commands.user_commands import user_cli_bp
        app.cli.add_command(user_cli_bp)
        module_log.info("Registered 'user' command group.")

        from .commands.sync_usage_command import sync_usage_command
        app.cli.add_command(sync_usage_command)
        module_log.info("Registered 'sync-usage' command.")

    except ImportError as e_cmd_import:
        module_log.warning(f"Could not import some CLI commands: {e_cmd_import}")
    except Exception as e_cmd_reg:
        module_log.error(f"Error during CLI command registration: {e_cmd_reg}", exc_info=True)
    module_log.info("CLI commands registration process finished.")

def _ensure_request_id():
    if not hasattr(request, 'environ') or 'FLASK_REQUEST_ID' not in request.environ:
        req_id = request.headers.get('X-Request-ID') or str(uuid.uuid4())
        if hasattr(request, 'environ'):
            request.environ['FLASK_REQUEST_ID'] = req_id

def create_app(config_name: str = None) -> Flask:
    if config_name is None:
        config_name = os.getenv('FLASK_CONFIG', 'default')
    app = Flask('hotspot_app')

    try:
        app.config.from_object(config_options[config_name])
        module_log.info(f"Flask app configured with '{config_name}' settings from config.py.")
    except (ImportError, KeyError) as e:
        module_log.warning(f"Could not load config '{config_name}' from config.py ({e}). Falling back to default Config object.")
        app.config.from_object(Config())

    if app.config.get('PROXYFIX_X_FOR', 0) > 0 or app.config.get('PROXYFIX_X_PROTO', 0) > 0:
        proxy_fix_config = {
            'x_for': app.config.get('PROXYFIX_X_FOR', 1),
            'x_proto': app.config.get('PROXYFIX_X_PROTO', 1),
            'x_host': app.config.get('PROXYFIX_X_HOST', 0),
            'x_port': app.config.get('PROXYFIX_X_PORT', 0),
            'x_prefix': app.config.get('PROXYFIX_X_PREFIX', 0)
        }
        app.wsgi_app = ProxyFix(app.wsgi_app, **proxy_fix_config)
        module_log.info(f"ProxyFix middleware applied with config: {proxy_fix_config}")
    else:
        module_log.info("ProxyFix middleware not applied (PROXYFIX_X_FOR/PROXYFIX_X_PROTO is 0 or not set).")

    app.before_request(_ensure_request_id)
    setup_logging(app)
    module_log.info(f"Flask app '{app.name}' (instance path: {app.instance_path}) created with effective config: '{config_name}'.")

    register_extensions(app)
    register_models(app)
    register_blueprints(app)
    register_test_routes(app)

    module_log.info("Registering custom Jinja2 filters...")
    try:
        primary_locale = app.config.get('APP_LOCALE', 'id_ID.UTF-8')
        fallback_locale_win = 'Indonesian_Indonesia.1252'
        system_locale = ''
        locales_to_try = [primary_locale, fallback_locale_win, system_locale]
        locale_set = False
        for loc in locales_to_try:
            try:
                locale.setlocale(locale.LC_ALL, loc)
                module_log.info(f"Locale set to: {locale.getlocale(locale.LC_ALL)}")
                locale_set = True
                break
            except locale.Error:
                module_log.debug(f"Failed to set locale to '{loc}'.")
        if not locale_set:
            module_log.error("Failed to set any locale. Locale-dependent formatting might fail or use system default.")
    except Exception as e_locale:
        module_log.error(f"Error setting locale: {e_locale}", exc_info=True)

    def format_datetime_filter(value, fmt=None):
        if not isinstance(value, datetime): return value
        fmt = fmt or app.config.get('JINJA_DATETIME_FORMAT', '%d/%m/%y %H:%M')
        try: return value.strftime(fmt)
        except Exception as e_fmt:
            current_app.logger.error(f"Error formatting datetime {value} with format '{fmt}': {e_fmt}")
            return str(value)

    def format_currency_filter(value, currency_symbol=None):
        currency_symbol = currency_symbol or app.config.get('CURRENCY_SYMBOL', 'Rp ')
        try:
            amount = float(value or 0)
            return f"{currency_symbol}{amount:,.0f}".replace(",", "#TEMP#").replace(".", ",").replace("#TEMP#", ".")
        except (ValueError, TypeError) as e_curr:
            current_app.logger.error(f"Error formatting currency {value}: {e_curr}")
            return f"{currency_symbol}0"
            
    def format_datetime_short_filter(value, fmt=None):
        if not isinstance(value, datetime): return value
        fmt = fmt or app.config.get('JINJA_DATETIME_SHORT_FORMAT', '%b %d, %Y')
        try: return value.strftime(fmt)
        except Exception as e_fmt:
            current_app.logger.error(f"Error formatting short datetime {value} with format '{fmt}': {e_fmt}")
            return str(value)

    def format_number_only_filter(value):
        try:
            amount = float(value or 0)
            return f"{int(amount):,}".replace(",", ".")
        except (ValueError, TypeError) as e_num:
            current_app.logger.error(f"Error formatting number only {value}: {e_num}")
            return "0"

    def format_status_filter(value):
        status_map = app.config.get('STATUS_DISPLAY_MAP', {
            'PENDING': 'Menunggu Pembayaran', 'PAID': 'Dibayar', 'SETTLEMENT': 'Selesai',
            'SUCCESS': 'Sukses', 'EXPIRED': 'Kedaluwarsa', 'CANCELLED': 'Dibatalkan',
            'FAILED': 'Gagal', 'UNKNOWN': 'Tidak Diketahui'
        })
        return status_map.get(str(value).upper(), str(value))

    def date_format_filter(value, fmt='%Y-%m-%d'):
        if not isinstance(value, (datetime, date)): return value
        try: return value.strftime(fmt)
        except Exception as e_dfmt:
            current_app.logger.error(f"Error formatting date {value} with format '{fmt}': {e_dfmt}")
            return str(value)

    app.jinja_env.filters['format_datetime'] = format_datetime_filter
    app.jinja_env.filters['format_datetime_short'] = format_datetime_short_filter
    app.jinja_env.filters['format_currency'] = format_currency_filter
    app.jinja_env.filters['format_number_only'] = format_number_only_filter
    app.jinja_env.filters['format_status'] = format_status_filter
    app.jinja_env.filters['date_format'] = date_format_filter

    try: from pytz import timezone as pytz_timezone; PYTZ_AVAILABLE_JINJA = True
    except ImportError: PYTZ_AVAILABLE_JINJA = False; pytz_timezone = None

    def get_current_time_jinja(tz_name=None):
        if tz_name and PYTZ_AVAILABLE_JINJA and pytz_timezone:
            try:
                return datetime.now(pytz_timezone(tz_name))
            except Exception:
                return datetime.now(dt_timezone.utc)
        return datetime.now(dt_timezone.utc)

    app.jinja_env.globals['now'] = get_current_time_jinja
    module_log.info("Custom Jinja2 filters and globals registered.")

    register_commands(app)

    module_log.info(f"Flask app '{app.name}' initialization complete.")
    return app