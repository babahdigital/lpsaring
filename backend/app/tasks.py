# backend/app/tasks.py
import logging
import os # <-- Baris ini memastikan modul 'os' tersedia

from app.infrastructure.gateways.whatsapp_client import send_whatsapp_with_pdf
# Import create_app dari app/__init__.py
from app import create_app

logger = logging.getLogger(__name__)

# Kita akan menggunakan celery_app dari extensions.py sebagai decorator
# Pastikan ini sesuai dengan cara Anda mengimpor celery_app di docker-compose.yml
# `celery -A app.extensions.celery_app worker`
from app.extensions import celery_app

@celery_app.task(name="send_whatsapp_invoice_task", bind=True)
def send_whatsapp_invoice_task(self, recipient_number: str, caption: str, pdf_url: str, filename: str):
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
    # os.environ.get sekarang akan berfungsi karena 'os' telah diimpor.
    app = create_app(config_name=os.environ.get('FLASK_CONFIG', 'default')) 
    
    with app.app_context():
        logger.info(f"Celery Task: Memulai pengiriman WhatsApp dengan PDF ke {recipient_number} untuk URL: {pdf_url}")
        try:
            # send_whatsapp_with_pdf sekarang akan memiliki akses ke current_app
            success = send_whatsapp_with_pdf(recipient_number, caption, pdf_url, filename)
            if not success:
                logger.error(f"Celery Task: Gagal mengirim WhatsApp invoice ke {recipient_number} (Fonnte reported failure).")
                # Opsional: Jika Anda ingin Celery mencoba lagi task ini jika gagal
                # raise self.retry(countdown=60, max_retries=3, exc=Exception("Fonnte reported failure"))
            else:
                logger.info(f"Celery Task: Berhasil mengirim WhatsApp invoice ke {recipient_number}.")
        except Exception as e:
            logger.error(f"Celery Task: Exception saat mengirim WhatsApp invoice ke {recipient_number}: {e}", exc_info=True)
            # Opsional: Jika Anda ingin Celery mencoba lagi task ini jika terjadi exception
            # raise self.retry(countdown=60, max_retries=3, exc=e)