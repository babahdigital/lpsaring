# backend/app/utils/formatters.py
# Kumpulan fungsi helper untuk pemformatan data.

import re
from typing import Optional, List
from datetime import datetime, timezone as dt_timezone
from zoneinfo import ZoneInfo

def format_datetime_to_wita(dt_utc: Optional[datetime]) -> str:
    """Mengonversi objek datetime UTC menjadi string dengan zona waktu WITA (UTC+8)."""
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
    Aturan validasi: Nomor lokal (08xx) harus 10-12 digit.
    """
    if not phone_number or not isinstance(phone_number, str):
        raise ValueError("Nomor telepon tidak boleh kosong.")
    cleaned = re.sub(r'[\s\-()+]', '', phone_number).strip()
    if not cleaned:
        raise ValueError("Nomor telepon tidak boleh kosong.")
    
    e164_number = ""
    if cleaned.startswith('08'):
        e164_number = '+62' + cleaned[1:]
    elif cleaned.startswith('628'):
        e164_number = '+' + cleaned
    elif cleaned.startswith('+628'):
        e164_number = cleaned
    elif cleaned.startswith('8') and len(cleaned) >= 9: # Minimal 8 diikuti 9 digit
        e164_number = '+62' + cleaned
    else:
        raise ValueError(f"Format awalan nomor telepon '{phone_number}' tidak valid. Gunakan awalan 08, 628, atau +628.")

    # Aturan baru: panjang total nomor lokal 10-12 digit, berarti E.164 adalah 12-14 digit.
    if not (12 <= len(e164_number) <= 14):
        raise ValueError(f"Panjang nomor telepon tidak valid. Harus antara 10-12 digit untuk format lokal (misal: 08xx).")
    
    # Regex baru: setelah +628, harus ada 8-10 digit lagi.
    # [1-9] (1 digit) + [0-9]{7,9} (7-9 digit) = total 8-10 digit.
    if not re.match(r'^\+628[1-9][0-9]{7,9}$', e164_number):
        raise ValueError(f"Nomor telepon '{phone_number}' memiliki format yang tidak valid.")
        
    return e164_number

def format_to_local_phone(phone_number: Optional[str]) -> Optional[str]:
    """Mengubah format E.164 (+62) atau format lain menjadi format lokal (08)."""
    if not phone_number: return None
    try:
        cleaned = re.sub(r'[^\d+]', '', str(phone_number)).strip()
        if cleaned.startswith('+628'): return '0' + cleaned[3:]
        if cleaned.startswith('628'): return '0' + cleaned[2:]
        if cleaned.startswith('08'): return cleaned
        if cleaned.startswith('8'): return '0' + cleaned
        return re.sub(r'\D', '', cleaned)
    except Exception:
        return None

def get_phone_number_variations(query: str) -> List[str]:
    """Menghasilkan variasi format nomor telepon untuk pencarian di database."""
    if not query or not query.isdigit(): return [query] # Kembalikan query jika bukan digit (untuk pencarian nama)
    variations = {query}
    try:
        normalized_query = normalize_to_e164(query)
        local_part = normalized_query[3:]
        variations.add(normalized_query)
        variations.add('628' + local_part)
        variations.add('08' + local_part)
    except ValueError:
        pass # Abaikan jika query tidak bisa dinormalisasi, tetap gunakan query asli
    return list(variations)