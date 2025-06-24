# backend/app/tasks.py
import logging
from app.extensions import celery_app # Import celery_app yang sudah diinisialisasi
from app.infrastructure.gateways.whatsapp_client import send_whatsapp_with_pdf

logger = logging.getLogger(__name__)

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
    logger.info(f"Celery Task: Memulai pengiriman WhatsApp dengan PDF ke {recipient_number} untuk URL: {pdf_url}")
    try:
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