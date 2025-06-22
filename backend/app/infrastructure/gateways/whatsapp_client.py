# backend/app/infrastructure/gateways/whatsapp_client.py (Disempurnakan Sesuai Fonnte Docs)
import requests
from flask import current_app
import logging # Pastikan logging diimport jika belum

# Fungsi inti untuk mengirim pesan via Fonnte
def send_whatsapp_message(recipient_number: str, message_body: str) -> bool:
    """
    Mengirim pesan WhatsApp ke nomor tujuan menggunakan API Fonnte.

    Args:
        recipient_number (str): Nomor HP tujuan (format +62...).
        message_body (str): Isi pesan yang akan dikirim.

    Returns:
        bool: True jika API Fonnte mengindikasikan sukses (`status: true`), False jika gagal.
    """
    # Gunakan nama variabel dari config Anda
    api_url = current_app.config.get('WHATSAPP_API_URL')
    api_key = current_app.config.get('WHATSAPP_API_KEY')

    # Validasi konfigurasi (seperti kode Anda)
    if not api_url or not isinstance(api_url, str):
        current_app.logger.error("WhatsApp API URL (WHATSAPP_API_URL) is not configured correctly or not a string.")
        return False
    if not api_key or not isinstance(api_key, str):
        current_app.logger.error("WhatsApp API Key (WHATSAPP_API_KEY) is not configured correctly or not a string.")
        return False

    # --- Penyesuaian untuk Fonnte API ---
    headers = {
        'Authorization': api_key # Sesuai docs: token langsung di Auth header
    }

    # Persiapan nomor tujuan:
    # 1. Hapus '+' di awal.
    # 2. Kirim dengan '62' di depan.
    # 3. Set 'countryCode' ke '0' agar Fonnte tidak memproses ulang nomornya.
    if recipient_number.startswith('+'):
        target_number = recipient_number[1:] # Hasilnya: 628...
    else:
        # Jika input sudah '08...', konversi dulu (opsional, tergantung input dari frontend)
        if recipient_number.startswith('08'):
             target_number = '62' + recipient_number[1:]
        else:
             target_number = recipient_number # Asumsikan sudah 62...

    # Pastikan nomor dimulai dengan '62' untuk konsistensi
    if not target_number.startswith('62'):
         current_app.logger.error(f"Invalid target number format for Fonnte after processing: {target_number}. Expected '62...'")
         return False

    payload = {
        'target': target_number,
        'message': message_body,
        'countryCode': '0' # Penting: Nonaktifkan filter Fonnte, kirim nomor apa adanya
    }
    # --- Akhir Penyesuaian Fonnte ---

    current_app.logger.info(f"Attempting to send WhatsApp to {target_number} via Fonnte (URL: {api_url})")
    current_app.logger.debug(f"Fonnte Payload: {payload}, Headers: {{'Authorization': '***'}}") # Jangan log API key

    try:
        # Fonnte menggunakan form-data, jadi pakai parameter 'data' di requests
        response = requests.post(api_url, headers=headers, data=payload, timeout=20)

        # Cek status HTTP (opsional, Fonnte mungkin selalu 200 OK)
        if not (200 <= response.status_code < 300):
             current_app.logger.warning(f"Fonnte API returned non-2xx status: {response.status_code} - {response.text[:200]}")
             # Bisa dianggap gagal jika status non-2xx

        # Proses respons JSON dari Fonnte
        try:
            response_json = response.json()
            current_app.logger.info(f"Fonnte API Response for {target_number}: {response_json}")

            # Periksa key 'status' boolean
            if response_json.get('status') is True: # Eksplisit cek True
                current_app.logger.info(f"Fonnte reported SUCCESS for sending to {target_number}")
                return True
            else:
                error_reason = response_json.get('reason', 'Unknown reason from Fonnte')
                current_app.logger.error(f"Fonnte reported FAILURE for {target_number}: {error_reason}")
                return False
        except ValueError: # Jika respons bukan JSON
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

# Fungsi helper khusus untuk mengirim OTP
def send_otp_whatsapp(target_number: str, otp: str) -> bool:
    """Helper function untuk mengirim pesan OTP."""
    expire_minutes = current_app.config.get('OTP_EXPIRE_SECONDS', 300) // 60
    message_body = f"Kode OTP Anda adalah: {otp}\nJangan berikan kode ini kepada siapapun. Kode berlaku selama {expire_minutes} menit."
    # Panggil fungsi utama
    return send_whatsapp_message(target_number, message_body)