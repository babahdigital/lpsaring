# backend/app/infrastructure/gateways/whatsapp_client.py (Disempurnakan dengan Fungsi PDF)
from typing import Optional
import random
import time

import requests
from flask import current_app

from app.utils.circuit_breaker import record_failure, record_success, should_allow_call

def _apply_send_delay() -> None:
    min_ms = int(current_app.config.get('WHATSAPP_SEND_DELAY_MIN_MS', 400))
    max_ms = int(current_app.config.get('WHATSAPP_SEND_DELAY_MAX_MS', 1200))

    if min_ms < 0:
        min_ms = 0
    if max_ms < 0:
        max_ms = 0
    if max_ms < min_ms:
        min_ms, max_ms = max_ms, min_ms

    delay_ms = random.randint(min_ms, max_ms) if max_ms > min_ms else min_ms
    if delay_ms > 0:
        time.sleep(delay_ms / 1000.0)

def validate_whatsapp_provider() -> tuple[bool, str | None]:
    """Validasi status provider WhatsApp (Fonnte) sebelum kirim pesan."""
    validate_url = current_app.config.get('WHATSAPP_VALIDATE_URL')
    api_key = current_app.config.get('WHATSAPP_API_KEY')

    if not validate_url or not isinstance(validate_url, str):
        return False, 'WHATSAPP_VALIDATE_URL belum disetel.'
    if not api_key or not isinstance(api_key, str):
        return False, 'WHATSAPP_API_KEY belum disetel.'

    try:
        timeout_seconds = int(current_app.config.get('WHATSAPP_HTTP_TIMEOUT_SECONDS', 15))
        response = requests.post(
            validate_url,
            headers={'Authorization': api_key},
            timeout=timeout_seconds,
        )
        payload = response.json()
    except requests.exceptions.Timeout:
        return False, 'Timeout saat validasi status provider WhatsApp.'
    except requests.exceptions.RequestException as e:
        return False, f'Gagal menghubungi endpoint validasi WhatsApp: {e}'
    except ValueError:
        return False, 'Respons validasi WhatsApp bukan JSON yang valid.'

    is_ok = payload.get('status') is True
    if is_ok:
        return True, None

    reason = payload.get('reason')
    if isinstance(reason, str) and reason:
        return False, reason
    return False, 'Provider WhatsApp belum siap (device/token belum valid).'
def send_whatsapp_message(recipient_number: str, message_body: str) -> bool:
    """
    Mengirim pesan WhatsApp ke nomor tujuan menggunakan API Fonnte.
    (Fungsi ini tetap sama, tidak ada perubahan)
    """
    api_url = current_app.config.get('WHATSAPP_API_URL')
    api_key = current_app.config.get('WHATSAPP_API_KEY')

    if not api_url or not isinstance(api_url, str):
        current_app.logger.error("WhatsApp API URL (WHATSAPP_API_URL) is not configured correctly or not a string.")
        return False
    if not api_key or not isinstance(api_key, str):
        current_app.logger.error("WhatsApp API Key (WHATSAPP_API_KEY) is not configured correctly or not a string.")
        return False

    headers = {'Authorization': api_key}
    
    if recipient_number.startswith('+'):
        target_number = recipient_number[1:]
    else:
        if recipient_number.startswith('08'):
             target_number = '62' + recipient_number[1:]
        else:
             target_number = recipient_number
    
    if not target_number.startswith('62'):
         current_app.logger.error(f"Invalid target number format for Fonnte after processing: {target_number}. Expected '62...'")
         return False

    payload = {
        'target': target_number,
        'message': message_body,
        'countryCode': '0'
    }

    if not should_allow_call("whatsapp"):
        current_app.logger.warning("WhatsApp circuit breaker open. Skipping send.")
        return False

    _apply_send_delay()

    current_app.logger.info(f"Attempting to send WhatsApp to {target_number} via Fonnte (URL: {api_url})")
    current_app.logger.debug(f"Fonnte Payload: {payload}, Headers: {{'Authorization': '***'}}")

    try:
        timeout_seconds = int(current_app.config.get('WHATSAPP_HTTP_TIMEOUT_SECONDS', 15))
        response = requests.post(api_url, headers=headers, data=payload, timeout=timeout_seconds)
        if not (200 <= response.status_code < 300):
             current_app.logger.warning(f"Fonnte API returned non-2xx status: {response.status_code} - {response.text[:200]}")
        try:
            response_json = response.json()
            current_app.logger.info(f"Fonnte API Response for {target_number}: {response_json}")
            if response_json.get('status') is True:
                current_app.logger.info(f"Fonnte reported SUCCESS for sending to {target_number}")
                record_success("whatsapp")
                return True
            else:
                error_reason = response_json.get('reason', 'Unknown reason from Fonnte')
                current_app.logger.error(f"Fonnte reported FAILURE for {target_number}: {error_reason}")
                record_failure("whatsapp")
                return False
        except ValueError:
            current_app.logger.error(f"Failed to decode Fonnte JSON response for {target_number}. Status: {response.status_code}, Response text: {response.text[:200]}")
            record_failure("whatsapp")
            return False
    except requests.exceptions.Timeout:
        current_app.logger.error(f"Timeout error sending WhatsApp to {target_number} via Fonnte.")
        record_failure("whatsapp")
        return False
    except requests.exceptions.RequestException as e:
        current_app.logger.error(f"Error sending WhatsApp to {target_number} via Fonnte: Request Exception - {e}", exc_info=False)
        record_failure("whatsapp")
        return False
    except Exception as e:
        current_app.logger.error(f"Unexpected error sending WhatsApp via Fonnte to {target_number}: {e}", exc_info=True)
        record_failure("whatsapp")
        return False

# --- [PENAMBAHAN FUNGSI BARU DI SINI] ---
def send_whatsapp_with_pdf(recipient_number: str, caption: str, pdf_url: str, filename: str) -> bool:
    """
    Mengirim pesan WhatsApp dengan lampiran PDF dari URL menggunakan API Fonnte.

    Args:
        recipient_number (str): Nomor HP tujuan (format +62...).
        caption (str): Teks/caption yang akan menyertai file PDF.
        pdf_url (str): URL publik yang dapat diakses dari file PDF.
        filename (str): Nama file yang akan ditampilkan ke penerima.

    Returns:
        bool: True jika API Fonnte mengindikasikan sukses, False jika gagal.
    """
    api_url = current_app.config.get('WHATSAPP_API_URL') # Fonnte biasanya pakai URL yang sama
    api_key = current_app.config.get('WHATSAPP_API_KEY')

    if not api_url or not api_key:
        current_app.logger.error("WhatsApp API configuration is incomplete for media sending.")
        return False

    headers = {'Authorization': api_key}
    
    if recipient_number.startswith('+'):
        target_number = recipient_number[1:]
    else:
        if recipient_number.startswith('08'):
             target_number = '62' + recipient_number[1:]
        else:
             target_number = recipient_number
    
    if not target_number.startswith('62'):
         current_app.logger.error(f"Invalid target number format for Fonnte: {target_number}")
         return False

    def _download_pdf_bytes() -> Optional[bytes]:
        if not pdf_url:
            return None
        try:
            timeout_seconds = int(current_app.config.get('WHATSAPP_PDF_DOWNLOAD_TIMEOUT_SECONDS', 20))
            response = requests.get(pdf_url, timeout=timeout_seconds)
            if not (200 <= response.status_code < 300):
                current_app.logger.warning(
                    f"Gagal mengunduh PDF untuk WA. Status: {response.status_code} URL: {pdf_url}"
                )
                return None
            return response.content
        except requests.exceptions.RequestException as e:
            current_app.logger.error(
                f"Error mengunduh PDF untuk WA (URL: {pdf_url}): {e}", exc_info=False
            )
            return None

    if not should_allow_call("whatsapp"):
        current_app.logger.warning("WhatsApp circuit breaker open. Skipping PDF send.")
        return False

    current_app.logger.info(f"Attempting to send WhatsApp with PDF to {target_number} via Fonnte")

    pdf_bytes = _download_pdf_bytes()
    if pdf_bytes:
        payload = {
            'target': target_number,
            'message': caption,
            'countryCode': '0'
        }
        files = {
            'file': (filename, pdf_bytes, 'application/pdf')
        }
        current_app.logger.debug("Fonnte File Payload: <binary file>, Headers: {'Authorization': '***'}")
        try:
            timeout_seconds = int(current_app.config.get('WHATSAPP_HTTP_TIMEOUT_SECONDS', 15))
            response = requests.post(api_url, headers=headers, data=payload, files=files, timeout=timeout_seconds)
            try:
                response_json = response.json()
            except ValueError:
                current_app.logger.error(
                    f"Gagal decode JSON response Fonnte (file upload). Status: {response.status_code}, Response: {response.text[:200]}"
                )
                record_failure("whatsapp")
                return False
            current_app.logger.info(f"Fonnte API File Response for {target_number}: {response_json}")
            if response_json.get('status') is True:
                current_app.logger.info(f"Fonnte reported SUCCESS for sending PDF to {target_number}")
                record_success("whatsapp")
                return True
            error_reason = response_json.get('reason', 'Unknown reason from Fonnte')
            current_app.logger.error(f"Fonnte reported FAILURE for PDF to {target_number}: {error_reason}")
            record_failure("whatsapp")
        except requests.exceptions.RequestException as e:
            current_app.logger.error(
                f"Error sending WhatsApp with PDF to {target_number}: Request Exception - {e}", exc_info=False
            )
            record_failure("whatsapp")
        except Exception as e:
            current_app.logger.error(
                f"Unexpected error sending PDF via Fonnte to {target_number}: {e}", exc_info=True
            )
            record_failure("whatsapp")

    payload = {
        'target': target_number,
        'message': caption,
        'url': pdf_url,
        'filename': filename,
        'countryCode': '0'
    }
    current_app.logger.info(
        f"Fallback WA PDF via URL. target={target_number}, url={pdf_url}, filename={filename}"
    )
    try:
        timeout_seconds = int(current_app.config.get('WHATSAPP_HTTP_TIMEOUT_SECONDS', 15))
        response = requests.post(api_url, headers=headers, data=payload, timeout=timeout_seconds)
        try:
            response_json = response.json()
        except ValueError:
            current_app.logger.error(
                f"Gagal decode JSON response Fonnte (url). Status: {response.status_code}, Response: {response.text[:200]}"
            )
            record_failure("whatsapp")
            return False
        current_app.logger.info(f"Fonnte API File Response for {target_number}: {response_json}")
        if response_json.get('status') is True:
            current_app.logger.info(f"Fonnte reported SUCCESS for sending PDF URL to {target_number}")
            record_success("whatsapp")
            return True
        error_reason = response_json.get('reason', 'Unknown reason from Fonnte')
        current_app.logger.error(f"Fonnte reported FAILURE for PDF URL to {target_number}: {error_reason}")
        record_failure("whatsapp")
        return False
    except requests.exceptions.RequestException as e:
        current_app.logger.error(f"Error sending WhatsApp with PDF URL to {target_number}: Request Exception - {e}", exc_info=False)
        record_failure("whatsapp")
        return False
    except Exception as e:
        current_app.logger.error(f"Unexpected error sending PDF URL via Fonnte to {target_number}: {e}", exc_info=True)
        record_failure("whatsapp")
        return False

def send_otp_whatsapp(target_number: str, otp: str) -> bool:
    """Helper function untuk mengirim pesan OTP."""
    expire_minutes = current_app.config.get('OTP_EXPIRE_SECONDS', 300) // 60
    # Menggunakan notification_service untuk konsistensi
    from app.services.notification_service import get_notification_message
    message_body = get_notification_message("auth_send_otp", {"otp_code": otp, "otp_expiry_minutes": expire_minutes})
    return send_whatsapp_message(target_number, message_body)