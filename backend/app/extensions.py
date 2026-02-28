# backend/app/extensions.py
# VERSI DISEMPURNAKAN DENGAN INTEGRASI CELERY

import json
import logging
import sys
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# Import yang dibutuhkan untuk Celery
from celery import Celery
from celery.schedules import crontab
from celery.signals import after_setup_logger, after_setup_task_logger
import os
from dotenv import load_dotenv

# Hanya buat instance di sini untuk ekstensi Flask yang ada
db = SQLAlchemy()
migrate = Migrate()
cors = CORS()
limiter = Limiter(
    key_func=get_remote_address,
    # Konfigurasi default limits dan storage akan diambil dari app.config saat init_app
)

# --- Inisialisasi Celery ---
# Pemuatan .env di sini agar Celery dapat mengakses konfigurasi saat berdiri sendiri
# (misalnya, saat menjalankan `celery worker` secara langsung)
basedir = os.path.abspath(os.path.dirname(__file__))
dotenv_path = None
current_dir = basedir
# Naik hingga 4 level direktori untuk mencari .env
for _ in range(4):
    potential_path = os.path.join(current_dir, ".env")
    if os.path.exists(potential_path):
        dotenv_path = potential_path
        break
    parent_dir = os.path.dirname(current_dir)
    if parent_dir == current_dir:
        break
    current_dir = parent_dir

if dotenv_path:
    load_dotenv(dotenv_path=dotenv_path)
    print(f"INFO: Berhasil memuat variabel lingkungan untuk Celery dari: {dotenv_path}")
else:
    print(
        f"INFO: File .env tidak ditemukan untuk Celery di {basedir} dan direktori induknya. Menggunakan default atau variabel sistem."
    )


class _JsonLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": self.formatTime(record, datefmt="%d-%m-%Y %H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=True)


def _get_env_log_level() -> int:
    level_str = (os.environ.get("LOG_LEVEL") or "INFO").upper()
    return getattr(logging, level_str, logging.INFO)


def _get_env_log_formatter() -> logging.Formatter:
    use_json = (os.environ.get("LOG_FORMAT_JSON") or "False").lower() == "true"
    if use_json:
        return _JsonLogFormatter()
    return logging.Formatter(
        "%(asctime)s %(levelname)-8s [%(name)s] %(message)s",
        datefmt="%d-%m-%Y %H:%M:%S",
    )


def _ensure_stdout_logging(target_logger: logging.Logger) -> None:
    level = _get_env_log_level()
    formatter = _get_env_log_formatter()

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)
    handler.setFormatter(formatter)

    # Make logging deterministic inside Celery worker/beat.
    target_logger.handlers.clear()
    target_logger.setLevel(level)
    target_logger.addHandler(handler)
    target_logger.propagate = False

    root = logging.getLogger()
    if not root.handlers:
        root.setLevel(level)
        root.addHandler(handler)


@after_setup_logger.connect
def _celery_after_setup_logger(logger: logging.Logger, *args, **kwargs) -> None:  # pragma: no cover
    _ensure_stdout_logging(logger)


@after_setup_task_logger.connect
def _celery_after_setup_task_logger(logger: logging.Logger, *args, **kwargs) -> None:  # pragma: no cover
    _ensure_stdout_logging(logger)


def make_celery_app(app=None):
    """
    Fungsi factory untuk membuat instance Celery.
    Jika `app` diberikan, Celery akan dikonfigurasi dengan `app.config`
    dan akan otomatis masuk ke Flask app context.
    """
    # Dapatkan URL Redis dari environment variable yang sudah dimuat
    redis_password_broker = os.environ.get("REDIS_PASSWORD_CELERY_BROKER")
    redis_auth_broker = (
        f":{redis_password_broker}@" if redis_password_broker and redis_password_broker.lower() != "null" else ""
    )
    redis_host_broker = os.environ.get("REDIS_HOST_CELERY_BROKER", "redis")
    redis_port_broker = os.environ.get("REDIS_PORT_CELERY_BROKER", "6379")
    redis_db_broker = os.environ.get("REDIS_DB_CELERY_BROKER", "1")
    broker_url = os.environ.get(
        "CELERY_BROKER_URL", f"redis://{redis_auth_broker}{redis_host_broker}:{redis_port_broker}/{redis_db_broker}"
    )

    redis_password_backend = os.environ.get("REDIS_PASSWORD_CELERY_BACKEND")
    redis_auth_backend = (
        f":{redis_password_backend}@" if redis_password_backend and redis_password_backend.lower() != "null" else ""
    )
    redis_host_backend = os.environ.get("REDIS_HOST_CELERY_BACKEND", "redis")
    redis_port_backend = os.environ.get("REDIS_PORT_CELERY_BACKEND", "6379")
    redis_db_backend = os.environ.get("REDIS_DB_CELERY_BACKEND", "2")
    result_backend = os.environ.get(
        "CELERY_RESULT_BACKEND",
        f"redis://{redis_auth_backend}{redis_host_backend}:{redis_port_backend}/{redis_db_backend}",
    )

    celery_instance = Celery(
        "hotspot_portal",  # Nama aplikasi Celery Anda
        broker=broker_url,
        backend=result_backend,
        include=["app.tasks"],  # Pastikan ini menunjuk ke file tasks Anda
    )

    # Pastikan log Celery + task log muncul di stdout container dan tidak “menimpa” logging app.
    celery_instance.conf.update(
        worker_hijack_root_logger=False,
        worker_redirect_stdouts=False,
    )

    # Jadwal Celery Beat (dikonfigurasi via env untuk sinkronisasi kuota dan cleanup)
    try:
        sync_interval = int(os.environ.get("QUOTA_SYNC_INTERVAL_SECONDS", "300"))
    except ValueError:
        sync_interval = 300
    schedule_seconds = min(sync_interval, 60)

    celery_instance.conf.beat_schedule = {
        "sync-hotspot-usage": {
            "task": "sync_hotspot_usage_task",
            "schedule": schedule_seconds,
        },
        "enforce-end-of-month-debt-block": {
            "task": "enforce_end_of_month_debt_block_task",
            "schedule": 3600,
        },
        "expire-stale-transactions": {
            "task": "expire_stale_transactions_task",
            "schedule": 60,
        },
        "cleanup-inactive-users": {
            "task": "cleanup_inactive_users_task",
            "schedule": crontab(hour=3, minute=0),
        },
    }

    if os.environ.get("WALLED_GARDEN_ENABLED", "False").lower() == "true":
        try:
            wg_interval = int(os.environ.get("WALLED_GARDEN_SYNC_INTERVAL_MINUTES", "30"))
        except ValueError:
            wg_interval = 30
        celery_instance.conf.beat_schedule["sync-walled-garden"] = {
            "task": "sync_walled_garden_task",
            "schedule": crontab(minute=f"*/{max(wg_interval, 1)}"),
        }

    if os.environ.get("ENABLE_MIKROTIK_OPERATIONS", "True").lower() == "true":
        try:
            unauthorized_interval = int(os.environ.get("UNAUTHORIZED_SYNC_INTERVAL_SECONDS", "120"))
        except ValueError:
            unauthorized_interval = 120
        celery_instance.conf.beat_schedule["sync-unauthorized-hosts"] = {
            "task": "sync_unauthorized_hosts_task",
            "schedule": max(30, unauthorized_interval),
        }

        if os.environ.get("AUTO_CLEANUP_WAITING_DHCP_ARP_ENABLED", "False").lower() == "true":
            try:
                cleanup_waiting_interval = int(os.environ.get("AUTO_CLEANUP_WAITING_DHCP_ARP_INTERVAL_SECONDS", "300"))
            except ValueError:
                cleanup_waiting_interval = 300
            celery_instance.conf.beat_schedule["cleanup-waiting-dhcp-arp"] = {
                "task": "cleanup_waiting_dhcp_arp_task",
                "schedule": max(60, cleanup_waiting_interval),
            }

        try:
            parity_guard_interval = int(os.environ.get("POLICY_PARITY_GUARD_INTERVAL_SECONDS", "600"))
        except ValueError:
            parity_guard_interval = 600
        if os.environ.get("ENABLE_POLICY_PARITY_GUARD", "True").lower() == "true":
            celery_instance.conf.beat_schedule["policy-parity-guard"] = {
                "task": "policy_parity_guard_task",
                "schedule": max(60, parity_guard_interval),
            }

        if os.environ.get("ENABLE_MIKROTIK_AUDIT_RECONCILIATION", "True").lower() == "true":
            try:
                audit_hour = int(os.environ.get("MIKROTIK_AUDIT_CRON_HOUR", "4"))
            except ValueError:
                audit_hour = 4
            try:
                audit_minute = int(os.environ.get("MIKROTIK_AUDIT_CRON_MINUTE", "15"))
            except ValueError:
                audit_minute = 15
            celery_instance.conf.beat_schedule["audit-mikrotik-reconciliation"] = {
                "task": "audit_mikrotik_reconciliation_task",
                "schedule": crontab(hour=max(0, min(audit_hour, 23)), minute=max(0, min(audit_minute, 59))),
            }

    if app:
        # Konfigurasi Celery dari konfigurasi Flask app
        # Ini penting agar Celery memiliki akses ke konfigurasi Flask
        celery_instance.conf.update(app.config)

        # Buat kelas Task dasar yang secara otomatis masuk ke Flask app context
        class ContextTask(celery_instance.Task):
            def __call__(self, *args, **kwargs):
                with app.app_context():
                    return self.run(*args, **kwargs)

        celery_instance.Task = ContextTask

    return celery_instance


# Inisialisasi Celery global
celery_app = make_celery_app()
celery = celery_app
