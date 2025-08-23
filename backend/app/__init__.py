# Ensure environment variables are loaded first thing
import os
from pathlib import Path
import logging

# Setup basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("env_loader")

def load_env_override():
    """Manually load .env.override file at app initialization"""
    # Check multiple possible locations for the override file
    paths_to_check = [
        Path('.env.override'),  # In current directory 
        Path('../.env.override'),  # One level up (from app directory)
        Path('/app/.env.override'),  # Absolute path in Docker container
    ]
    
    for override_path in paths_to_check:
        if override_path.exists():
            print(f"Found .env.override at {override_path.absolute()}")
            try:
                with open(override_path) as f:
                    content = f.read()
                    print(f"Contents of .env.override:\n{content}")
                    
                    # Process each line
                    for line in content.splitlines():
                        line = line.strip()
                        if not line or line.startswith('#'):
                            continue
                            
                        if '=' in line:
                            key, value = line.split('=', 1)
                            key = key.strip()
                            value = value.strip().strip('"\'')
                            if key:
                                # Show what's being set
                                print(f"Setting environment variable: {key}={value}")
                                os.environ[key] = value
                                
                print("Successfully loaded environment overrides")
                return True
            except Exception as e:
                print(f"Error loading .env.override: {e}")
                continue
    
    print("Warning: .env.override not found in any expected location")
    return False

# Load environment variables at the earliest possible moment
load_env_override()

# backend/app/__init__.py
# VERSI FINAL: Menambahkan bypass untuk request OPTIONS di hook maintenance.
# pyright: reportAttributeAccessIssue=false

import os
import sys
import logging
import uuid
import time
from datetime import datetime, timezone as dt_timezone, timedelta
from http import HTTPStatus

import redis
from flask import Flask, current_app, request, jsonify
from flask_jwt_extended import JWTManager
from jose import jwt, JWTError, ExpiredSignatureError
from werkzeug.middleware.proxy_fix import ProxyFix
from logging.handlers import RotatingFileHandler

from config import config_options, Config
from .extensions import db, migrate, cors, limiter, celery_app
from .services import settings_service
from .infrastructure.http.json_provider import CustomJSONProvider
from .infrastructure.db.models import User, UserRole
from .infrastructure.gateways.mikrotik_pool import init_mikrotik_pool

# Monitor environment variables
import app.env_monitor  # noqa


module_log = logging.getLogger(__name__)

_maintenance_cache = {'status': 'False', 'message': 'Maintenance.', 'last_checked': datetime.min}

class RequestIdFilter(logging.Filter):
  def filter(self, record):
    try:
      record.request_id = request.environ.get('FLASK_REQUEST_ID', 'N/A_NoReqID')
    except RuntimeError:
      record.request_id = 'N/A_NoRequestCtx'
    return True

def setup_logging(app: Flask):
  log_level_str = app.config.get('LOG_LEVEL', 'INFO').upper()
  log_level = getattr(logging, log_level_str, logging.INFO)

  for name in ('flask.app', 'werkzeug', 'sqlalchemy.engine'):
    logger = logging.getLogger(name)
    logger.handlers.clear()
    logger.setLevel(log_level)

  if not app.config.get('SQLALCHEMY_ECHO', False):
    logging.getLogger('sqlalchemy.engine').setLevel(logging.WARNING)

  fmt = '%(asctime)s %(levelname)-8s [%(name)s] [%(request_id)s] %(message)s [in %(pathname)s:%(lineno)d]'
  formatter = logging.Formatter(fmt)
  filt = RequestIdFilter()

  sh = logging.StreamHandler(sys.stdout)
  sh.setFormatter(formatter)
  sh.setLevel(log_level)
  sh.addFilter(filt)
  logging.getLogger().addHandler(sh)

  if app.config.get('LOG_TO_FILE') and not app.testing:
    log_dir = os.path.join(app.root_path, app.config.get('LOG_DIR', 'logs'))
    os.makedirs(log_dir, exist_ok=True)

    fh = RotatingFileHandler(
      os.path.join(log_dir, app.config.get('LOG_FILENAME', 'app.log')),
      maxBytes=app.config.get('LOG_MAX_BYTES', 10485760),
      backupCount=app.config.get('LOG_BACKUP_COUNT', 5),
      encoding='utf-8',
    )

    fh.setFormatter(formatter)
    fh.setLevel(log_level)
    fh.addFilter(filt)
    logging.getLogger().addHandler(fh)

  module_log.info(f"Logging ready. Level={log_level_str}")

def register_extensions(app: Flask):
  module_log.debug('Registering Flask extensions...')
  
  # Clear cache IP/MAC saat startup untuk data fresh
  clear_startup_cache = os.environ.get('CACHE_CLEAR_ON_START', '').lower() == 'true'
  if clear_startup_cache:
    module_log.info('🧹 STARTUP: Clearing IP/MAC cache for fresh data...')
    try:
      # Import dan clear cache manager dengan retry untuk startup stability
      from app.utils.cache_manager import cache_manager
      import time
      
      # --- OPTIMASI STARTUP CACHE CLEAR (VERSI FINAL) ---
      max_retries = 3
      retry_delays = [2, 5, 10] # Jeda dalam detik untuk setiap percobaan
      
      module_log.info("🧹 STARTUP: Preparing to clear IP/MAC cache...")
      for attempt in range(max_retries):
        try:
          # Perbaikan Kritis: Bungkus dalam app.app_context()
          with app.app_context():
            # Ping Redis terlebih dahulu untuk memastikan koneksi tersedia
            redis_client = getattr(current_app, 'redis_client_otp', None)
            if redis_client:
              try:
                redis_client.ping()
                module_log.debug('✅ Redis connection verified before cache clear')
              except Exception as ping_e:
                module_log.warning(f'⚠️ Redis ping failed, may not be ready: {ping_e}')
            
            # Attempt to clear cache
            cache_manager.clear_ip_mac_cache()
          
          module_log.info('✅ STARTUP: IP/MAC cache cleared successfully.')
          break # Jika berhasil, keluar dari loop
        except Exception as retry_e:
          # Log error yang lebih detail
          error_msg = str(retry_e).strip().split('\n')[0] # Ambil baris pertama dari error
          delay = retry_delays[attempt]
          module_log.warning(
              f"🔄 STARTUP: Cache clear attempt {attempt + 1}/{max_retries} failed, retrying in {delay}s: {error_msg}"
          )
          if attempt < max_retries - 1:
              time.sleep(delay)
          else:
              final_error_msg = str(retry_e).strip().split('\n')[0]
              module_log.error(
                  f"⚠️ STARTUP: All cache clear attempts failed. Continuing without initial clear: {final_error_msg}"
              )
            # No need to raise, just continue with app startup
    except Exception as e:
      module_log.warning(f'⚠️ STARTUP: Failed to clear IP/MAC cache after retries: {e}')

  db.init_app(app)
  migrate.init_app(app, db)
  cors.init_app(app)
  limiter.init_app(app)

  # Initialize Celery
  from .tasks import init_celery
  init_celery(app, celery_app)

  try:
    redis_url_otp = app.config['REDIS_URL_OTP']
    app.redis_client_otp = redis.from_url(redis_url_otp, decode_responses=True)
    app.redis_client_otp.ping()
    module_log.info(f"Redis OTP connected via URL: {redis_url_otp}")
  except redis.exceptions.ConnectionError as e:
    module_log.critical(f'Redis OTP FAILED: {e}')
  except Exception as e:
    module_log.critical(f'Unexpected Redis OTP error: {e}', exc_info=True)

def register_models(_app: Flask):
  from .infrastructure.db import models
  module_log.debug('DB models imported.')

def register_test_routes(app: Flask):
  @app.get('/api/ping')
  @limiter.limit("50 per minute")
  def ping():
    key = current_app.config.get('JWT_SECRET_KEY', 'KUNCI_TIDAK_DITEMUKAN')
    worker_pid = os.getpid()
    return {
      'message': 'pong',
      'server_time': datetime.now(dt_timezone.utc).isoformat(),
      'diagnostics': {
        'worker_pid': worker_pid,
        'key_check': f"JWT_SECRET_KEY (PID: {worker_pid}) starts with: '{key[:4]}...'",
      },
    }

  if app.config.get('ENABLE_INTERNAL_METRICS', True):
    @app.get('/metrics')
    def metrics():
      auth_cfg = app.config.get('METRICS_BASIC_AUTH')
      if auth_cfg:
        from base64 import b64decode
        expected = auth_cfg
        header = request.headers.get('Authorization', '')
        if not header.startswith('Basic '):
            return ('Unauthorized', 401, {'WWW-Authenticate': 'Basic realm="metrics"'})
        try:
            enc = header.split(' ',1)[1]
            userpass = b64decode(enc).decode('utf-8')
        except Exception:
            return ('Unauthorized', 401, {'WWW-Authenticate': 'Basic realm="metrics"'})
        if userpass != expected:
            return ('Forbidden', 403)
      # Build metrics text (Prometheus plain)
      from app.infrastructure.gateways import mikrotik_client_impl as _mimpl  # type: ignore
      snap = getattr(_mimpl, 'get_internal_metrics_snapshot', lambda: {})()
      lines = []
      lines.append('# HELP mac_lookup_total Total MAC lookup attempts')
      lines.append('# TYPE mac_lookup_total counter')
      lines.append(f"mac_lookup_total {snap.get('mac_lookup_total',0)}")
      lines.append('# HELP mac_lookup_cache_hits Total cache hit (Redis)')
      lines.append('# TYPE mac_lookup_cache_hits counter')
      lines.append(f"mac_lookup_cache_hits {snap.get('mac_lookup_cache_hits',0)}")
      lines.append('# HELP mac_lookup_cache_grace_hits Total grace in-memory hits')
      lines.append('# TYPE mac_lookup_cache_grace_hits counter')
      lines.append(f"mac_lookup_cache_grace_hits {snap.get('mac_lookup_cache_grace_hits',0)}")
      lines.append('# HELP mac_lookup_fail Total lookup failures (exceptions)')
      lines.append('# TYPE mac_lookup_fail counter')
      lines.append(f"mac_lookup_fail {snap.get('mac_lookup_fail',0)}")
      lines.append('# HELP mac_lookup_duration_ms_sum Cumulative duration of MAC lookups (ms)')
      lines.append('# TYPE mac_lookup_duration_ms_sum counter')
      lines.append(f"mac_lookup_duration_ms_sum {snap.get('mac_lookup_duration_ms_sum',0.0)}")
      # Histogram buckets
      for k,v in snap.items():
        if k.startswith('mac_lookup_duration_bucket_'):
          le = k.split('_')[-1]
          lines.append(f"mac_lookup_duration_bucket{{le=\"{le}\"}} {v}")
      # Gauges
      if 'mac_grace_cache_size' in snap:
        lines.append('# HELP mac_grace_cache_size Current size of in-memory MAC grace cache')
        lines.append('# TYPE mac_grace_cache_size gauge')
        lines.append(f"mac_grace_cache_size {snap.get('mac_grace_cache_size',0)}")
      if 'mac_lookup_failure_ratio' in snap:
        lines.append('# HELP mac_lookup_failure_ratio Ratio of failed MAC lookups (fail/total)')
        lines.append('# TYPE mac_lookup_failure_ratio gauge')
        lines.append(f"mac_lookup_failure_ratio {snap.get('mac_lookup_failure_ratio',0.0)}")
      # Prometheus classic histogram (_seconds_*) aliases
      if 'mac_lookup_duration_seconds_sum' in snap:
        lines.append('# HELP mac_lookup_duration_seconds_sum Cumulative duration of MAC lookups (s)')
        lines.append('# TYPE mac_lookup_duration_seconds_sum counter')
        lines.append(f"mac_lookup_duration_seconds_sum {snap.get('mac_lookup_duration_seconds_sum',0.0)}")
      if 'mac_lookup_duration_seconds_count' in snap:
        lines.append('# HELP mac_lookup_duration_seconds_count Total MAC lookup observations')
        lines.append('# TYPE mac_lookup_duration_seconds_count counter')
        lines.append(f"mac_lookup_duration_seconds_count {snap.get('mac_lookup_duration_seconds_count',0)}")
      for k,v in snap.items():
        if k.startswith('mac_lookup_duration_seconds_bucket_'):
          le = k.split('_')[-1]
          lines.append(f"mac_lookup_duration_seconds_bucket{{le=\"{le}\"}} {v}")
      body = '\n'.join(lines) + '\n'
      return (body, 200, {'Content-Type': 'text/plain; version=0.0.4'})

    @app.get('/api/metrics/brief')
    def metrics_brief():
      """Ringkasan metrics ringan untuk UI (failure_ratio, grace_cache_size, total)."""
      from app.infrastructure.gateways import mikrotik_client_impl as _mimpl  # type: ignore
      snap = getattr(_mimpl, 'get_internal_metrics_snapshot', lambda: {})()
      data = {
        'mac_lookup_total': snap.get('mac_lookup_total', 0),
        'failure_ratio': snap.get('mac_lookup_failure_ratio', 0.0),
        'grace_cache_size': snap.get('mac_grace_cache_size', 0),
        'duration_ms_sum': snap.get('mac_lookup_duration_ms_sum', 0.0),
        'supports_seconds_histogram': True,
      }
      return jsonify(data)

  @app.get('/api/version')
  def api_version():
    """Info versi build + feature flags aktif untuk frontend harmonization."""
    build_hash = os.getenv('APP_BUILD_HASH') or 'dev'
    features = {
      'metrics_seconds_histogram': True,
      'metrics_gauges': True,
      'redis_pipelining': True,
      'async_lookup': True,
    }
    return {'version': build_hash, 'features': features}

  # Lightweight debug endpoint to echo detected client IP and source
  @app.get('/api/debug/ip-source')
  @limiter.exempt  # Exempt from global/default rate limits: used by frontend polling
  def debug_ip_source():
    try:
      from app.utils.request_utils import get_client_ip
      ip = get_client_ip()
      src = request.environ.get('CLIENT_IP_SOURCE', 'unknown')
      hdrs = {
        'xff': request.headers.get('X-Forwarded-For'),
        'xri': request.headers.get('X-Real-IP'),
        'xfinal': request.headers.get('X-Final-Client-IP'),
        'xclient': request.headers.get('X-Client-IP'),
        'xfe_ip': request.headers.get('X-Frontend-Detected-IP'),
      }
      return jsonify({'ip': ip, 'source': src, 'headers': hdrs}), 200
    except Exception as e:  # pragma: no cover
      return jsonify({'error': str(e)}), 500

  @app.get('/api/users/<int:user_id>/devices/summary')
  def user_devices_summary(user_id: int):
    """Ringkas perangkat user: daftar MAC/IP + last_seen terbaru."""
    from app.infrastructure.db import models  # type: ignore
    from app.extensions import db  # type: ignore
    user = db.session.get(models.User, user_id)
    if not user:
      return {'error': 'not_found'}, 404
    devices = []
    last_seen = None
    for d in getattr(user, 'devices', []) or []:  # type: ignore
      devices.append({
        'mac_address': d.mac_address,
        'ip_address': getattr(d, 'ip_address', None),
        'last_seen_at': getattr(d, 'last_seen_at', None),
      })
      ls = getattr(d, 'last_seen_at', None)
      if ls and (last_seen is None or ls > last_seen):
        last_seen = ls
    return {'user_id': user_id, 'devices': devices, 'last_seen_at': last_seen}

  # Dev-only: list registered routes to verify blueprint registration
  try:
    if app.config.get('ENV', '').lower() != 'production':
      @app.get('/api/_routes')
      @limiter.exempt
      def list_routes():
        routes = []
        for rule in app.url_map.iter_rules():
          safe_methods = [m for m in (rule.methods or []) if m not in ('HEAD', 'OPTIONS')]
          routes.append({
            'rule': str(rule),
            'methods': sorted(safe_methods),
            'endpoint': rule.endpoint,
          })
        return jsonify({'routes': routes}), 200
  except Exception:
    pass

def register_commands(app: Flask):
  from .commands.user_cli import user_cli_bp
  from .commands.sync_usage_command import sync_usage_command
  from .commands.simulation_commands import simulate_sync_device_command, simulate_low_quota_command, simulate_authorize_device_command, simulate_cli
  app.cli.add_command(user_cli_bp)
  app.cli.add_command(sync_usage_command)
  app.cli.add_command(simulate_sync_device_command)
  app.cli.add_command(simulate_authorize_device_command)
  app.cli.add_command(simulate_low_quota_command)
  # Grup baru: simulate
  app.cli.add_command(simulate_cli)

def create_app(config_name: str | None = None) -> Flask:
  config_name = config_name or os.getenv('FLASK_CONFIG', 'default')
  app = Flask('hotspot_app', template_folder='app/templates')
  app.json = CustomJSONProvider(app)
  app.config.from_object(config_options.get(config_name, Config()))

  setup_logging(app)

  jwt_manager = JWTManager(app)

  # Optional: Token blocklist (denylist) support
  @jwt_manager.token_in_blocklist_loader
  def check_if_token_revoked(jwt_header, jwt_payload: dict) -> bool:
    try:
      jti = jwt_payload.get('jti')
      if not jti:
        return False
      # Use Redis if available for shared state; else fallback to in-memory flag
      r = getattr(app, 'redis_client_otp', None)
      if r:
        return r.get(f"jwt:block:{jti}") == '1'
      # No redis: minimal fallback (non-shared) flag container
      bl = getattr(app, '_jwt_blocklist', set())
      return jti in bl
    except Exception:
      return False

  @jwt_manager.user_lookup_loader
  def user_lookup_callback(_jwt_header, jwt_data):
    identity = jwt_data.get('sub')
    if not identity:
      return None
    try:
      user_id = uuid.UUID(identity)
      return db.session.get(User, user_id)
    except (ValueError, TypeError):
      return None
      
  # ✅ Tambahkan token verification callback untuk cek perubahan perangkat
  @jwt_manager.token_verification_loader
  def verify_token_not_device_change(jwt_header, jwt_data):
    """
    Verifikasi tambahan untuk token JWT.
    Memeriksa apakah perangkat (IP/MAC) berubah sejak token diterbitkan.
    
    Tidak memblokir token, hanya menyimpan info perubahan di request untuk
    digunakan oleh endpoint yang memerlukan pemeriksaan perubahan perangkat.
    """
    try:
      # Skip untuk endpoint yang tidak memerlukan pemeriksaan perubahan
      skip_paths = ['/api/auth/check-device-status', '/api/auth/detect-client-info']
      if any(request.path.startswith(path) for path in skip_paths):
        return True
        
      # Dapatkan data IP dan MAC saat ini
      from app.utils.request_utils import get_client_ip, get_client_mac
      current_ip = get_client_ip()
      current_mac = get_client_mac()
      
      # Periksa apakah perangkat berubah
      if not current_ip or not current_mac:
        return True  # Tidak bisa menentukan perubahan
        
      # Simpan informasi IP/MAC di request untuk digunakan endpoint lain
      request.device_changed = False
      request.client_ip = current_ip
      request.client_mac = current_mac
      
      # Selalu return True karena ini hanya untuk pengecekan, bukan pemblokiran
      return True
    except Exception:
      # Jangan gagalkan autentikasi jika terjadi kesalahan
      return True

  @app.errorhandler(HTTPStatus.TOO_MANY_REQUESTS)
  def ratelimit_handler(e):
      if request.path == '/api/auth/request-otp':
          error_message = "Anda baru saja meminta OTP. Silakan tunggu 2 menit sebelum mencoba lagi."
      elif request.path == '/api/auth/verify-otp':
          error_message = f"Terlalu banyak percobaan OTP yang salah. {e.description}"
      else:
          error_message = "Terlalu banyak percobaan, silakan coba lagi nanti."
      
      return jsonify(error=error_message), HTTPStatus.TOO_MANY_REQUESTS

  # Enhanced ProxyFix configuration untuk handle multiple proxy layers
  if app.config.get('PROXYFIX_X_FOR', 0) > 0 or app.config.get('PROXYFIX_X_PROTO', 0) > 0:
    app.wsgi_app = ProxyFix(
      app.wsgi_app, 
      x_for=app.config.get('PROXYFIX_X_FOR', 2),  # Increase to handle nginx + docker
      x_proto=app.config.get('PROXYFIX_X_PROTO', 2),
      x_host=1,  # Enable host header forwarding
      x_port=1,  # Enable port header forwarding
      x_prefix=1  # Enable prefix header forwarding
    )

  @app.before_request
  def _req_id():
    request.environ.setdefault('FLASK_REQUEST_ID', request.headers.get('X-Request-ID') or str(uuid.uuid4()))

  @app.before_request
  def _log_captive_requests():
    # Optimized logging - reduce noise untuk health checks dan static requests
    if request.path.startswith('/api/'):
      # Suppress OPTIONS and common health endpoints
      if request.method == 'OPTIONS':
        return
      # Skip logging untuk health check dan frequent endpoints
      skip_endpoints = ['/api/ping', '/api/metrics', '/api/metrics/brief', '/api/auth/detect-client-info', '/api/public/promos/active']
      if any(request.path.startswith(skip) for skip in skip_endpoints):
        return
      
      from app.utils.request_utils import get_client_ip
      client_ip = get_client_ip()
      referer = request.headers.get('Referer', '')
      
      # Tentukan tipe akses berdasarkan referer dan parameter  
      access_type = "WEB-DIRECT"
      if 'captive' in referer.lower() or request.args.get('client_ip') or request.args.get('client_mac'):
        access_type = "CAPTIVE"
      elif 'login' in referer.lower():
        access_type = "WEB-LOGIN"
      
      # Enhanced log throttling untuk mengurangi spam
      log_key = f"{access_type}:{request.path}:{client_ip}:{request.method}"
      current_time = time.time()
      
      # Cache untuk throttling log (global variable)
      if not hasattr(app, '_log_cache'):
        app._log_cache = {}
        
      # Log hanya jika belum ada atau sudah lebih dari 60 detik (increase interval)
      should_log = (log_key not in app._log_cache or 
                   current_time - app._log_cache[log_key] > 60)
      
      # Hanya log untuk request yang penting dan critical operations
      critical_paths = ['/auth/sync-device', '/auth/verify-otp', '/auth/request-otp', '/auth/authorize-device']
      is_critical = any(path in request.path for path in critical_paths)
      
      if (is_critical or access_type in ["CAPTIVE", "WEB-LOGIN"] or request.method in ["POST", "PUT", "DELETE"]) and should_log:
        captive_header = request.headers.get('X-Captive-Portal', 'N/A')
        truncated_referer = referer[:30] + '...' if len(referer) > 30 else referer
        ip_src = request.environ.get('CLIENT_IP_SOURCE', 'unknown')
        app.logger.info(f"[{access_type}] {request.method} {request.path} - IP: {client_ip} (src={ip_src}), Referer: {truncated_referer}")
        app._log_cache[log_key] = current_time
        
        # Cleanup cache lama lebih aggressively
        if len(app._log_cache) > 100:  # Reduce cache size
          old_keys = [k for k, v in app._log_cache.items() if current_time - v > 120]  # 2 minute cleanup
          for old_key in old_keys:
            app._log_cache.pop(old_key, None)
      # Skip logging untuk ping, health checks, dan static requests

  @app.before_request
  def _maintenance():
    # --- [PERBAIKAN] ---
    # Selalu izinkan request OPTIONS (CORS preflight) untuk lewat.
    # Ini harus menjadi baris pertama dalam hook ini.
    if request.method == 'OPTIONS':
        return

    global _maintenance_cache
    if datetime.now() - _maintenance_cache['last_checked'] < timedelta(minutes=1):
      status, msg = _maintenance_cache['status'], _maintenance_cache['message']
    else:
      status = settings_service.get_setting('MAINTENANCE_MODE_ACTIVE', 'False')
      msg = settings_service.get_setting('MAINTENANCE_MODE_MESSAGE', 'Maintenance.')
      _maintenance_cache = {'status': status, 'message': msg, 'last_checked': datetime.now()}

    if status != 'True': return

    allowed = ('/api/admin', '/api/auth/admin/login', '/api/settings/public', '/api/ping')
    if request.path.startswith(allowed): return

    tok = request.headers.get('Authorization', '').removeprefix('Bearer ').strip()
    if tok:
      try:
        secret_key = current_app.config['JWT_SECRET_KEY']
        algorithm = current_app.config['JWT_ALGORITHM']
        payload = jwt.decode(tok, secret_key, algorithms=[algorithm])
        if payload.get('rl') in (UserRole.ADMIN.value, UserRole.SUPER_ADMIN.value): return
      except (JWTError, ExpiredSignatureError): pass
    return jsonify({'message': msg}), HTTPStatus.SERVICE_UNAVAILABLE

  register_extensions(app)
  init_mikrotik_pool(app)
  register_models(app)

  from .infrastructure.http import register_blueprints as register_all_blueprints
  register_all_blueprints(app)
  module_log.info('Blueprint registration complete.')
  
  # Initialize WebSockets and other components from bootstrap
  try:
    from .bootstrap import init_app_components
    init_app_components(app)
    module_log.info('Application components initialized via bootstrap')
  except Exception as e:
    module_log.warning(f'Failed to initialize some app components: {e}')
  
  # Register API documentation
  try:
    from .infrastructure.api_docs import create_api_docs
    create_api_docs(app)
    module_log.info('API Documentation setup complete. Available at /api/swagger')
  except ImportError as e:
    module_log.warning(f'API Documentation setup failed: {e}. Make sure to install required packages.')
  except Exception as e:
    # Log the error but continue - this shouldn't prevent the app from starting
    module_log.warning(f'Error setting up API Documentation: {e}. Documentation may be incomplete.')

  register_test_routes(app)
  register_commands(app)
  
  # Register shutdown handler to ensure resources are properly cleaned up
  try:
    import atexit
    
    @atexit.register
    def cleanup_app_resources():
      module_log.info("Application shutdown detected, cleaning up resources...")
      
      # Clean up MikroTik resources (will be handled by the atexit handler in mikrotik_client_impl.py)
      try:
        # Try to clean up the Flask app's MikroTik pool if it exists
        mikrotik_pool = getattr(app, "mikrotik_api_pool", None)
        if mikrotik_pool and hasattr(mikrotik_pool, "close") and callable(mikrotik_pool.close):
          module_log.info("Closing app's MikroTik connection pool...")
          mikrotik_pool.close()
          module_log.info("App's MikroTik connection pool closed")
      except Exception as e:
        module_log.error(f"Error cleaning up app's MikroTik resources: {e}")
      
      module_log.info("Application resources cleanup completed")
      
    module_log.info("Resource cleanup handlers registered")
  except Exception as e:
    module_log.warning(f"Failed to register resource cleanup handlers: {e}")

  module_log.info('Flask application initialized successfully.')
  return app