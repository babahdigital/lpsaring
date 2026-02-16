# backend/app/tasks.py
import logging
import json
from datetime import datetime, timezone as dt_timezone

from app.infrastructure.gateways.whatsapp_client import send_whatsapp_with_pdf, send_whatsapp_message
from app.services.hotspot_sync_service import sync_hotspot_usage_and_profiles, cleanup_inactive_users
from app.services import settings_service
from app.services.walled_garden_service import sync_walled_garden
# Import create_app dari app/__init__.py
from app import create_app
# Kita akan menggunakan celery_app dari extensions.py sebagai decorator
# Pastikan ini sesuai dengan cara Anda mengimpor celery_app di docker-compose.yml
# `celery -A app.extensions.celery_app worker`
from app.extensions import celery_app

logger = logging.getLogger(__name__)


def _record_task_failure(app, task_name: str, payload: dict, error_message: str) -> None:
    redis_client = getattr(app, "redis_client_otp", None)
    if redis_client is None:
        return
    try:
        dlq_key = app.config.get("TASK_DLQ_REDIS_KEY", "celery:dlq")
        item = {
            "task": task_name,
            "payload": payload,
            "error": error_message,
            "created_at": datetime.now(dt_timezone.utc).isoformat(),
        }
        redis_client.rpush(dlq_key, json.dumps(item))
    except Exception:
        return

@celery_app.task(
    name="send_whatsapp_invoice_task",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": 3},
)
def send_whatsapp_invoice_task(self, recipient_number: str, caption: str, pdf_url: str, filename: str, request_id: str = ''):
    """
    Celery task untuk mengirim pesan WhatsApp dengan lampiran PDF.
    
    Args:
        recipient_number (str): Nomor HP tujuan.
        caption (str): Teks/caption untuk pesan WhatsApp.
        pdf_url (str): URL publik ke file PDF invoice.
        filename (str): Nama file PDF.
    """
    # Penting: Buat instance aplikasi Flask di dalam konteks task
    # Ini memastikan current_app tersedia untuk semua fungsi yang dipanggil dalam task
    # yang membutuhkan konteks aplikasi (misalnya, mengakses app.config)
    # environ.get sekarang akan berfungsi karena 'environ' telah diimpor secara langsung.
    app = create_app()
    
    with app.app_context():
        logger.info(f"Celery Task: Memulai pengiriman WhatsApp dengan PDF ke {recipient_number} untuk URL: {pdf_url}. Request ID: {request_id}")
        try:
            # send_whatsapp_with_pdf sekarang akan memiliki akses ke current_app
            success = send_whatsapp_with_pdf(recipient_number, caption, pdf_url, filename)
            if not success:
                logger.error(f"Celery Task: Gagal mengirim WhatsApp invoice ke {recipient_number} (Fonnte reported failure).")
                # Fallback: kirim pesan teks tanpa PDF
                text_success = send_whatsapp_message(recipient_number, caption)
                if text_success:
                    logger.info(f"Celery Task: Pesan teks berhasil dikirim ke {recipient_number} setelah gagal PDF.")
                else:
                    logger.error(f"Celery Task: Pesan teks juga gagal dikirim ke {recipient_number}.")
                    raise RuntimeError("Fonnte gagal mengirim pesan PDF dan teks.")
            else:
                logger.info(f"Celery Task: Berhasil mengirim WhatsApp invoice ke {recipient_number}.")
        except Exception as e:
            logger.error(f"Celery Task: Exception saat mengirim WhatsApp invoice ke {recipient_number}: {e}", exc_info=True)
            if self.request.retries >= 3:
                _record_task_failure(
                    app,
                    "send_whatsapp_invoice_task",
                    {
                        "recipient_number": recipient_number,
                        "caption": caption,
                        "pdf_url": pdf_url,
                        "filename": filename,
                        "request_id": request_id,
                    },
                    str(e),
                )
            raise


@celery_app.task(
    name="sync_hotspot_usage_task",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": 2},
)
def sync_hotspot_usage_task(self):
    app = create_app()
    with app.app_context():
        logger.info("Celery Task: Memulai sinkronisasi kuota dan profil hotspot.")
        try:
            sync_interval = settings_service.get_setting_as_int('QUOTA_SYNC_INTERVAL_SECONDS', 300)
            redis_client = getattr(app, "redis_client_otp", None)
            if redis_client is not None:
                now_ts = int(datetime.now(dt_timezone.utc).timestamp())
                last_ts_str = redis_client.get("quota_sync:last_run_ts")
                if last_ts_str:
                    last_ts = int(last_ts_str)
                    if now_ts - last_ts < max(sync_interval, 30):
                        logger.info("Celery Task: Skip sinkronisasi (menunggu interval dinamis).")
                        return

            result = sync_hotspot_usage_and_profiles()
            logger.info(f"Celery Task: Sinkronisasi selesai. Result: {result}")
            if redis_client is not None:
                redis_client.set("quota_sync:last_run_ts", int(datetime.now(dt_timezone.utc).timestamp()))
        except Exception as e:
            logger.error(f"Celery Task: Sinkronisasi gagal: {e}", exc_info=True)
            if self.request.retries >= 2:
                _record_task_failure(app, "sync_hotspot_usage_task", {}, str(e))
            raise


@celery_app.task(
    name="cleanup_inactive_users_task",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": 2},
)
def cleanup_inactive_users_task(self):
    app = create_app()
    with app.app_context():
        logger.info("Celery Task: Memulai pembersihan pengguna tidak aktif.")
        try:
            result = cleanup_inactive_users()
            logger.info(f"Celery Task: Pembersihan selesai. Result: {result}")
        except Exception as e:
            logger.error(f"Celery Task: Pembersihan gagal: {e}", exc_info=True)
            if self.request.retries >= 2:
                _record_task_failure(app, "cleanup_inactive_users_task", {}, str(e))
            raise


@celery_app.task(
    name="sync_walled_garden_task",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": 2},
)
def sync_walled_garden_task(self):
    app = create_app()
    with app.app_context():
        logger.info("Celery Task: Memulai sinkronisasi walled-garden.")
        try:
            result = sync_walled_garden()
            logger.info(f"Celery Task: Walled-garden sync selesai. Result: {result}")
        except Exception as e:
            logger.error(f"Celery Task: Walled-garden sync gagal: {e}", exc_info=True)
            if self.request.retries >= 2:
                _record_task_failure(app, "sync_walled_garden_task", {}, str(e))
            raise