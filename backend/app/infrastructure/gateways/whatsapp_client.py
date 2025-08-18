# backend/app/infrastructure/gateways/whatsapp_client.py (Disempurnakan dengan Fungsi PDF)
import requests
import logging
from flask import current_app

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

    current_app.logger.info(f"Attempting to send WhatsApp to {target_number} via Fonnte (URL: {api_url})")
    current_app.logger.debug(f"Fonnte Payload: {payload}, Headers: {{'Authorization': '***'}}")

    try:
        response = requests.post(api_url, headers=headers, data=payload, timeout=20)
        if not (200 <= response.status_code < 300):
             current_app.logger.warning(f"Fonnte API returned non-2xx status: {response.status_code} - {response.text[:200]}")
        try:
            response_json = response.json()
            current_app.logger.info(f"Fonnte API Response for {target_number}: {response_json}")
            if response_json.get('status') is True:
                current_app.logger.info(f"Fonnte reported SUCCESS for sending to {target_number}")
                return True
            else:
                error_reason = response_json.get('reason', 'Unknown reason from Fonnte')
                current_app.logger.error(f"Fonnte reported FAILURE for {target_number}: {error_reason}")
                return False
        except ValueError:
            current_app.logger.error(f"Failed to decode Fonnte JSON response for {target_number}. Status: {response.status_code}, Response text: {response.text[:200]}")
            return False
    except requests.exceptions.Timeout:
        current_app.logger.error(f"Timeout error sending WhatsApp to {target_number} via Fonnte.")
        return False
    except requests.exceptions.RequestException as e:
        current_app.logger.error(f"Error sending WhatsApp to {target_number} via Fonnte: Request Exception - {e}", exc_info=False)
        return False
    except Exception as e:
        current_app.logger.error(f"Unexpected error sending WhatsApp via Fonnte to {target_number}: {e}", exc_info=True)
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

    # Payload untuk mengirim file (document) via Fonnte
    # 'message' digunakan sebagai caption, 'url' sebagai link ke file
    payload = {
        'target': target_number,
        'message': caption,
        'url': pdf_url,
        'filename': filename,
        'countryCode': '0'
    }

    current_app.logger.info(f"Attempting to send WhatsApp with PDF to {target_number} via Fonnte")
    current_app.logger.debug(f"Fonnte File Payload: {payload}, Headers: {{'Authorization': '***'}}")
    
    try:
        # Fonnte tetap menggunakan POST dengan form-data (parameter 'data')
        response = requests.post(api_url, headers=headers, data=payload, timeout=30) # Timeout lebih lama untuk media
        
        # Logika pemrosesan respons sama dengan pengiriman teks
        response_json = response.json()
        current_app.logger.info(f"Fonnte API File Response for {target_number}: {response_json}")
        if response_json.get('status') is True:
            current_app.logger.info(f"Fonnte reported SUCCESS for sending PDF to {target_number}")
            return True
        else:
            error_reason = response_json.get('reason', 'Unknown reason from Fonnte')
            current_app.logger.error(f"Fonnte reported FAILURE for PDF to {target_number}: {error_reason}")
            return False
    except requests.exceptions.RequestException as e:
        current_app.logger.error(f"Error sending WhatsApp with PDF to {target_number}: Request Exception - {e}", exc_info=False)
        return False
    except Exception as e:
        current_app.logger.error(f"Unexpected error sending PDF via Fonnte to {target_number}: {e}", exc_info=True)
        return False

def send_otp_whatsapp(target_number: str, otp: str) -> bool:
    """Helper function untuk mengirim pesan OTP."""
    expire_minutes = current_app.config.get('OTP_EXPIRE_SECONDS', 300) // 60
    # Menggunakan notification_service untuk konsistensi
    from app.services.notification_service import get_notification_message
    message_body = get_notification_message("auth_send_otp", {"otp_code": otp, "otp_expiry_minutes": expire_minutes})
    return send_whatsapp_message(target_number, message_body)