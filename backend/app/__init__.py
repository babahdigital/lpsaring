# backend/app/__init__.py
# VERSI FINAL: Mengembalikan logika-logika penting yang hilang dan mempertahankan struktur yang robust.

import os
import sys
import logging
import uuid
from datetime import datetime, timezone as dt_timezone
from logging.handlers import RotatingFileHandler

import redis
from flask import Flask, current_app, request, jsonify
from http import HTTPStatus
from jose import jwt, JWTError, ExpiredSignatureError
from werkzeug.middleware.proxy_fix import ProxyFix

from config import config_options, Config
from .extensions import db, migrate, cors, limiter
from .infrastructure.db.models import UserRole
from .infrastructure.http.json_provider import CustomJSONProvider
from .services import settings_service

module_log = logging.getLogger(__name__)

class RequestIdFilter(logging.Filter):
    """Menambahkan request_id ke setiap log record untuk kemudahan tracing."""
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
    """Mengkonfigurasi logging untuk aplikasi dengan konfigurasi yang fleksibel."""
    log_level_str = app.config.get('LOG_LEVEL', 'INFO').upper()
    log_level = getattr(logging, log_level_str, logging.INFO)
    
    app_logger = logging.getLogger('flask.app')
    werkzeug_logger = logging.getLogger('werkzeug')
    app_logger.handlers.clear()
    werkzeug_logger.handlers.clear()
    app_logger.setLevel(log_level)
    werkzeug_logger.setLevel(log_level)

    log_formatter = logging.Formatter(
        '%(asctime)s %(levelname)-8s [%(name)s] [%(request_id)s] %(message)s [in %(pathname)s:%(lineno)d]'
    )
    request_id_filter = RequestIdFilter()
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(log_formatter)
    stream_handler.addFilter(request_id_filter)
    app_logger.addHandler(stream_handler)
    werkzeug_logger.addHandler(stream_handler)
    app_logger.propagate = False
    werkzeug_logger.propagate = False

    if app.config.get('LOG_TO_FILE', False) and not app.testing:
        log_dir = app.config.get('LOG_DIR', 'logs')
        # DIKEMBALIKAN: Logika path absolut yang fleksibel
        project_root = os.path.abspath(os.path.join(app.root_path, '..'))
        if not os.path.isabs(log_dir):
            log_dir = os.path.join(project_root, log_dir)
        # DIKEMBALIKAN: Penanganan error saat membuat direktori log
        try:
            os.makedirs(log_dir, exist_ok=True)
            log_file = os.path.join(log_dir, app.config.get('LOG_FILENAME', 'app.log'))
            # DIKEMBALIKAN: Konfigurasi file log yang dinamis dari config
            file_handler = RotatingFileHandler(
                log_file, 
                maxBytes=app.config.get('LOG_MAX_BYTES', 10*1024*1024), 
                backupCount=app.config.get('LOG_BACKUP_COUNT', 5), 
                encoding='utf-8'
            )
            file_handler.setFormatter(log_formatter)
            file_handler.setLevel(app.config.get('LOG_FILE_LEVEL', 'INFO').upper())
            file_handler.addFilter(request_id_filter)
            app_logger.addHandler(file_handler)
            module_log.info(f"File logging diaktifkan: {log_file}")
        except Exception as e:
            module_log.error(f"Gagal menginisialisasi file logging: {e}", exc_info=True)
            
    module_log.info(f"Setup logging selesai. Log Level: {log_level_str}")

def register_extensions(app: Flask):
    """Mendaftarkan semua ekstensi Flask."""
    module_log.info("Menginisialisasi ekstensi...")
    db.init_app(app)
    migrate.init_app(app, db)
    
    frontend_url = app.config.get('FRONTEND_URL', 'http://localhost:3000')
    allowed_origins = list(set([frontend_url] + app.config.get('CORS_ADDITIONAL_ORIGINS', [])))
    cors.init_app(app, resources={r"/api/*": {"origins": allowed_origins}}, supports_credentials=True)
    module_log.info(f"CORS diinisialisasi untuk origins: {allowed_origins}")

    if app.config.get('RATELIMIT_ENABLED', True) and not app.testing:
        limiter.init_app(app)
        module_log.info("Rate limiter diinisialisasi.")
    
    if not app.testing:
        # DIKEMBALIKAN: Konfigurasi Redis yang lebih aman dengan parameter terpisah
        try:
            app.redis_client_otp = redis.Redis(
                host=app.config['REDIS_HOST_OTP'],
                port=app.config['REDIS_PORT_OTP'],
                db=app.config['REDIS_DB_OTP'],
                password=app.config.get('REDIS_PASSWORD_OTP'),
                decode_responses=True, 
                socket_connect_timeout=5
            )
            app.redis_client_otp.ping()
            module_log.info(f"Koneksi Redis untuk OTP berhasil (Host: {app.config['REDIS_HOST_OTP']}).")
        except Exception as e:
            module_log.critical(f"Koneksi ke Redis GAGAL: {e}. Fitur OTP tidak akan berfungsi.", exc_info=True)
            app.redis_client_otp = None
    else:
        app.redis_client_otp = None
        
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

        blueprints = [
            (auth_bp, None), (packages_bp, None), (transactions_bp, None),
            (public_bp, None), (profile_bp, None), (data_bp, None),
            (public_user_bp, None), (public_promo_bp, None), (komandan_bp, None)
        ]
        
        for bp, prefix in blueprints:
            app.register_blueprint(bp, url_prefix=prefix)
            module_log.info(f"Blueprint '{bp.name}' berhasil didaftarkan.")

        if app.config.get('ENABLE_ADMIN_ROUTES', True):
            ADMIN_API_PREFIX = '/api/admin'
            from .infrastructure.http.admin.user_management_routes import user_management_bp
            from .infrastructure.http.admin.package_management_routes import package_management_bp
            from .infrastructure.http.admin.settings_routes import settings_management_bp
            from .infrastructure.http.admin.profile_management_routes import profile_management_bp
            from .infrastructure.http.admin.promo_management_routes import promo_management_bp
            from .infrastructure.http.admin_routes import admin_bp
            from .infrastructure.http.admin.request_management_routes import request_mgmt_bp
            from .infrastructure.http.admin.action_log_routes import action_log_bp

            admin_blueprints = [
                user_management_bp, package_management_bp, settings_management_bp,
                profile_management_bp, promo_management_bp, admin_bp,
                request_mgmt_bp, action_log_bp
            ]
            for bp in admin_blueprints:
                app.register_blueprint(bp, url_prefix=ADMIN_API_PREFIX)
                module_log.info(f"Admin blueprint '{bp.name}' didaftarkan di '{ADMIN_API_PREFIX}'.")
    
    except ImportError as e:
        module_log.error(f"Gagal mengimpor salah satu blueprint: {e}", exc_info=True)

    module_log.info("Pendaftaran blueprints selesai.")

def register_models(_app: Flask):
    from .infrastructure.db import models
    module_log.debug("Modul DB Models telah diimpor.")

# DIKEMBALIKAN: Fungsi untuk mendaftarkan rute tes
def register_test_routes(app: Flask):
    @app.route('/api/ping', methods=['GET'])
    @limiter.limit(app.config.get('PING_RATE_LIMIT', "5 per minute"))
    def ping():
        return {"message": "pong from backend!", "server_time_utc": datetime.now(dt_timezone.utc).isoformat()}
    module_log.info("Rute tes '/api/ping' telah didaftarkan.")

def register_commands(app: Flask):
    from .commands import user_commands, seed_commands, sync_usage_command
    app.cli.add_command(user_commands.user_cli_bp)
    app.cli.add_command(seed_commands.seed_db_command)
    app.cli.add_command(sync_usage_command.sync_usage_command)
    module_log.info("Pendaftaran perintah CLI selesai.")

def create_app(config_name: str = None) -> Flask:
    """Factory function untuk membuat dan mengkonfigurasi aplikasi Flask."""
    config_name = config_name or os.getenv('FLASK_CONFIG', 'default')
    app = Flask('hotspot_app')
    app.json = CustomJSONProvider(app)
    app.config.from_object(config_options[config_name])

    # DIKEMBALIKAN: Konfigurasi ProxyFix yang lebih fleksibel
    if app.config.get('PROXYFIX_X_FOR', 0) > 0:
        proxy_fix_config = {
            'x_for': app.config.get('PROXYFIX_X_FOR', 1),
            'x_proto': app.config.get('PROXYFIX_X_PROTO', 1)
        }
        app.wsgi_app = ProxyFix(app.wsgi_app, **proxy_fix_config)
    
    # --- Register Hooks ---
    @app.before_request
    def ensure_request_id_hook():
        # DIKEMBALIKAN: Fallback ke X-Request-ID dari header
        if 'FLASK_REQUEST_ID' not in request.environ:
            request.environ['FLASK_REQUEST_ID'] = request.headers.get('X-Request-ID') or str(uuid.uuid4())

    @app.before_request
    def check_maintenance_mode_hook():
        # DIKEMBALIKAN: Logika maintenance mode yang lebih komprehensif
        is_maintenance = settings_service.get_setting('MAINTENANCE_MODE_ACTIVE', 'False') == 'True'
        if not is_maintenance: return

        # Izinkan akses ke endpoint public tertentu
        allowed_paths = ['/api/admin', '/api/auth', '/api/settings/public']
        if any(request.path.startswith(p) for p in allowed_paths):
            return

        # Izinkan admin yang sudah login untuk bypass
        auth_header = request.headers.get('Authorization')
        if auth_header and auth_header.startswith('Bearer '):
            try:
                token = auth_header.split(" ")[1]
                payload = jwt.decode(token, current_app.config['JWT_SECRET_KEY'], algorithms=[current_app.config['JWT_ALGORITHM']])
                if payload.get('rl') in [UserRole.ADMIN.value, UserRole.SUPER_ADMIN.value]:
                    return
            except (JWTError, ExpiredSignatureError): pass
        
        message = settings_service.get_setting('MAINTENANCE_MODE_MESSAGE', 'Aplikasi sedang dalam perbaikan.')
        return jsonify({"message": message}), HTTPStatus.SERVICE_UNAVAILABLE

    # --- Inisialisasi Komponen Aplikasi ---
    setup_logging(app)
    register_extensions(app)
    register_models(app)
    register_blueprints(app)
    register_test_routes(app) # Memanggil kembali fungsi pendaftaran rute tes
    register_commands(app)

    module_log.info(f"Inisialisasi aplikasi '{app.name}' selesai untuk environment '{config_name}'.")
    return app