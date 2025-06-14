# backend/app/__init__.py
# VERSI FINAL: Mendaftarkan blueprint-blueprint baru, termasuk untuk Promo.

import os
import sys
import logging
import locale
from datetime import datetime, date, timezone as dt_timezone
from logging.handlers import RotatingFileHandler
from flask import Flask, current_app, request, jsonify
from http import HTTPStatus
import redis
from werkzeug.middleware.proxy_fix import ProxyFix
import uuid

from jose import jwt, JWTError, ExpiredSignatureError
from .infrastructure.db.models import UserRole

from config import config_options, Config
from .extensions import db, migrate, cors, limiter
from .services import settings_service
from .infrastructure.http.json_provider import CustomJSONProvider

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
    migrate.init_app(app, db)
    
    frontend_url = app.config.get('FRONTEND_URL', 'http://localhost:3000')
    additional_origins = app.config.get('CORS_ADDITIONAL_ORIGINS', [])
    allowed_origins = list(set(filter(None, [frontend_url] + additional_origins)))
    cors.init_app(app, resources={r"/api/*": {"origins": allowed_origins}}, supports_credentials=True)
    module_log.info(f"CORS initialized. Allowed origins: {allowed_origins}")

    try:
        if not app.config.get('TESTING', False) and app.config.get('RATELIMIT_ENABLED', True):
            limiter.init_app(app)
            module_log.info("Rate limiter initialized.")
        else:
            module_log.info("Rate limiter is disabled.")
    except Exception as e:
        module_log.error(f"Failed to initialize Rate Limiter: {e}", exc_info=True)
    
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
    except redis.exceptions.ConnectionError as e:
        module_log.critical(f"FAILED to connect to Redis for OTP: {e}. OTP features will be UNAVAILABLE.", exc_info=True)
        app.redis_client_otp = None
    except Exception as e_redis:
        module_log.critical(f"An unexpected error occurred while initializing Redis client for OTP: {e_redis}", exc_info=True)
        app.redis_client_otp = None
        
    module_log.info("Extensions registration finished.")

def register_blueprints(app: Flask):
    module_log.info("Registering blueprints...")
    try:
        # Blueprint yang ada sebelumnya
        from .infrastructure.http.auth_routes import auth_bp
        app.register_blueprint(auth_bp)
        module_log.info(f"Blueprint '{auth_bp.name}' registered.")

        from .infrastructure.http.packages_routes import packages_bp
        app.register_blueprint(packages_bp)
        module_log.info(f"Blueprint '{packages_bp.name}' registered.")
        
        from .infrastructure.http.transactions_routes import transactions_bp
        app.register_blueprint(transactions_bp)
        module_log.info(f"Blueprint '{transactions_bp.name}' registered.")
        
        from .infrastructure.http.public_routes import public_bp
        app.register_blueprint(public_bp)
        module_log.info(f"Blueprint '{public_bp.name}' (Public) registered.")

        # Daftarkan blueprint-blueprint baru dari direktori /user
        from .infrastructure.http.user.profile_routes import profile_bp
        app.register_blueprint(profile_bp)
        module_log.info(f"Blueprint '{profile_bp.name}' (User Profile) registered.")

        from .infrastructure.http.user.data_routes import data_bp
        app.register_blueprint(data_bp)
        module_log.info(f"Blueprint '{data_bp.name}' (User Data & Stats) registered.")

        # Daftarkan blueprint publik baru
        from .infrastructure.http.public_user_routes import public_user_bp
        app.register_blueprint(public_user_bp)
        module_log.info(f"Blueprint '{public_user_bp.name}' (Public User) registered.")

        # Daftarkan blueprint publik untuk promo
        from .infrastructure.http.public_promo_routes import public_promo_bp
        app.register_blueprint(public_promo_bp)
        module_log.info(f"Blueprint '{public_promo_bp.name}' (Public Promo) registered.")

        # Pendaftaran blueprint admin
        if app.config.get('ENABLE_ADMIN_ROUTES', False):
            try:
                # Definisikan prefix admin di satu tempat untuk konsistensi
                ADMIN_API_PREFIX = '/api/admin'
                module_log.info("Registering ALL admin blueprints under prefix: %s", ADMIN_API_PREFIX)

                from .infrastructure.http.admin.user_management_routes import user_management_bp
                app.register_blueprint(user_management_bp, url_prefix=ADMIN_API_PREFIX)
                
                from .infrastructure.http.admin.package_management_routes import package_management_bp
                app.register_blueprint(package_management_bp, url_prefix=ADMIN_API_PREFIX)
                
                from .infrastructure.http.admin.settings_routes import settings_management_bp
                app.register_blueprint(settings_management_bp, url_prefix=ADMIN_API_PREFIX)
                
                from .infrastructure.http.admin.profile_management_routes import profile_management_bp
                app.register_blueprint(profile_management_bp, url_prefix=ADMIN_API_PREFIX)
                
                from .infrastructure.http.admin.promo_management_routes import promo_management_bp
                app.register_blueprint(promo_management_bp, url_prefix=ADMIN_API_PREFIX)
                
                # --- PERUBAHAN DI SINI ---
                # Daftarkan admin_bp DENGAN prefix yang sama, karena prefix di filenya sudah dihapus.
                from .infrastructure.http.admin_routes import admin_bp
                app.register_blueprint(admin_bp, url_prefix=ADMIN_API_PREFIX)
                
                module_log.info("All admin blueprints registered successfully.")
                
            except ImportError as e_admin_bp:
                module_log.error(f"Admin routes enabled, but failed to import or register an admin blueprint: {e_admin_bp}", exc_info=True)
                
    except ImportError as e_bp_import:
        module_log.error(f"Failed to import a blueprint module: {e_bp_import}", exc_info=True)
    module_log.info("Blueprints registration process finished.")

def register_models(_app: Flask):
    from .infrastructure.db import models
    module_log.debug("DB Models module imported.")

def register_test_routes(app: Flask):
    @app.route('/api/ping', methods=['GET'])
    @limiter.limit(app.config.get('PING_RATE_LIMIT', "5 per minute"))
    def ping():
        return {"message": "pong from backend!", "server_time_utc": datetime.now(dt_timezone.utc).isoformat()}
    module_log.info("Test route '/api/ping' registered.")

def register_commands(app: Flask):
    module_log.info("Registering CLI commands...")
    try:
        from .commands.seed_commands import seed_db_command
        app.cli.add_command(seed_db_command)
        from .commands.user_commands import user_cli_bp
        app.cli.add_command(user_cli_bp)
        from .commands.sync_usage_command import sync_usage_command
        app.cli.add_command(sync_usage_command)
        module_log.info("All CLI commands registered.")
    except Exception as e_cmd_reg:
        module_log.error(f"Error during CLI command registration: {e_cmd_reg}", exc_info=True)

def create_app(config_name: str = None) -> Flask:
    if config_name is None:
        config_name = os.getenv('FLASK_CONFIG', 'default')
    app = Flask('hotspot_app')
    app.json = CustomJSONProvider(app)

    try:
        app.config.from_object(config_options[config_name])
    except (ImportError, KeyError):
        app.config.from_object(Config())

    if app.config.get('PROXYFIX_X_FOR', 0) > 0:
        proxy_fix_config = {'x_for': app.config.get('PROXYFIX_X_FOR', 1), 'x_proto': app.config.get('PROXYFIX_X_PROTO', 1)}
        app.wsgi_app = ProxyFix(app.wsgi_app, **proxy_fix_config)
    
    @app.before_request
    def check_maintenance_mode():
        is_maintenance = settings_service.get_setting('MAINTENANCE_MODE_ACTIVE', 'False') == 'True'
        if not is_maintenance: return
        
        # PENAMBAHAN: Izinkan akses ke API publik
        allowed_paths = ['/api/admin', '/api/auth', '/api/settings/public', '/api/public', '/admin']
        if any(request.path.startswith(p) for p in allowed_paths): return
        
        auth_header = request.headers.get('Authorization')
        if auth_header and auth_header.startswith('Bearer '):
            try:
                token = auth_header.split(" ")[1]
                payload = jwt.decode(token, current_app.config['JWT_SECRET_KEY'], algorithms=[current_app.config['JWT_ALGORITHM']])
                if payload.get('rl') in [UserRole.ADMIN.value, UserRole.SUPER_ADMIN.value]: return
            except (JWTError, ExpiredSignatureError): pass
        
        message = settings_service.get_setting('MAINTENANCE_MODE_MESSAGE', 'Aplikasi sedang dalam perbaikan.')
        return jsonify({"message": message}), HTTPStatus.SERVICE_UNAVAILABLE
    
    @app.before_request
    def ensure_request_id_hook():
        if 'FLASK_REQUEST_ID' not in request.environ:
            request.environ['FLASK_REQUEST_ID'] = request.headers.get('X-Request-ID') or str(uuid.uuid4())

    setup_logging(app)
    register_extensions(app)
    register_models(app)
    register_blueprints(app)
    register_test_routes(app)
    register_commands(app)

    module_log.info(f"Flask app '{app.name}' initialization complete.")
    return app