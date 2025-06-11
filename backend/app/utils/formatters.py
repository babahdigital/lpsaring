# backend/app/utils/formatters.py
# Kumpulan fungsi helper untuk pemformatan data.

import re
from datetime import datetime, timezone as dt_timezone
from zoneinfo import ZoneInfo
from typing import Optional, List

def format_datetime_to_wita(dt_utc: Optional[datetime]) -> str:
    """
    Mengonversi objek datetime UTC menjadi string dengan zona waktu WITA (UTC+8).
    Mengembalikan string kosong jika input bukan datetime yang valid.
    """
    if not isinstance(dt_utc, datetime):
        return ""

    if dt_utc.tzinfo is None:
        dt_utc = dt_utc.replace(tzinfo=dt_timezone.utc)

    wita_tz = ZoneInfo("Asia/Makassar")
    dt_wita = dt_utc.astimezone(wita_tz)
    
    return dt_wita.strftime('%d %b %Y, %H:%M:%S %Z')

def normalize_to_e164(phone_number: str) -> str:
    """
    Menormalisasi berbagai format nomor telepon Indonesia ke format E.164 (+62).
    Melemparkan ValueError jika format tidak valid.
    """
    if not phone_number or not isinstance(phone_number, str):
        raise ValueError("Nomor telepon tidak boleh kosong atau bukan string.")
    
    cleaned = re.sub(r'[\s\-()+]', '', phone_number).strip()

    if not cleaned:
        raise ValueError("Nomor telepon tidak boleh kosong setelah dibersihkan.")

    e164_number = ""
    if cleaned.startswith('08'):
        e164_number = '+62' + cleaned[1:]
    elif cleaned.startswith('628'):
        e164_number = '+' + cleaned
    elif cleaned.startswith('+628'):
        e164_number = cleaned
    elif cleaned.startswith('8') and len(cleaned) >= 8: # Asumsi format 8xxxxxxx untuk Indonesia
        e164_number = '+62' + cleaned
    else:
        raise ValueError(f"Format awalan nomor telepon '{phone_number}' tidak valid. Harus 08xx, 628xx, +628xx, atau 8xx.")

    # Validasi panjang dan format akhir E.164
    if not (11 <= len(e164_number) <= 15):
        raise ValueError(f"Panjang nomor telepon tidak valid ({len(e164_number)} digit). Harusnya 11-15 digit termasuk kode negara.")
    
    if not re.match(r'^\+628[1-9][0-9]{7,11}$', e164_number):
        raise ValueError(f"Nomor telepon '{phone_number}' tidak valid untuk format E.164 Indonesia (+628xx).")

    return e164_number

def format_to_local_phone(phone_number: Optional[str]) -> Optional[str]:
    """
    Mengubah format E.164 (+62) menjadi format lokal (08).
    Berguna untuk username Mikrotik atau tampilan lokal.
    """
    if not phone_number:
        return None
        
    if phone_number.startswith('+628'):
        return '0' + phone_number[3:]
    
    return phone_number

def get_phone_number_variations(input_phone_number: str) -> List[str]:
    """
    Menghasilkan berbagai variasi format umum untuk nomor telepon Indonesia untuk membantu pencarian.
    Termasuk: E.164 (+628xxxx), lokal (08xxxx), dan raw (8xxxx).
    """
    variations = []
    if not isinstance(input_phone_number, str) or not input_phone_number.strip():
        return variations

    # Bersihkan input, hapus karakter non-digit
    cleaned_input = re.sub(r'[^\d]+', '', input_phone_number).strip()

    if not cleaned_input:
        return variations

    # Coba normalisasi ke E.164
    try:
        e164 = normalize_to_e164(input_phone_number)
        variations.append(e164)
        
        # Tambahkan format lokal (08xxxx) jika E.164 ada
        if e164.startswith('+62'):
            local_format = '0' + e164[3:]
            if local_format not in variations:
                variations.append(local_format)
        
        # Tambahkan format mentah (8xxxx) jika cocok dengan pola E.164
        if e164.startswith('+628'):
            raw_format = e164[3:]
            if raw_format not in variations:
                variations.append(raw_format)

    except ValueError:
        # Jika normalisasi gagal, coba tambahkan input yang sudah dibersihkan sebagai variasi
        # Ini menangani kasus di mana input mungkin bukan nomor lengkap/valid, tetapi bagian darinya
        if cleaned_input not in variations:
            variations.append(cleaned_input)
    
    # Pastikan input asli yang dibersihkan disertakan jika belum ada
    if cleaned_input not in variations:
        variations.append(cleaned_input)

    # Tambahkan awalan umum jika belum ada
    if not cleaned_input.startswith('+62') and ('+62' + cleaned_input) not in variations:
        variations.append('+62' + cleaned_input)
    if not cleaned_input.startswith('0') and ('0' + cleaned_input) not in variations:
        variations.append('0' + cleaned_input)

    return list(set(variations)) # Kembalikan variasi unik