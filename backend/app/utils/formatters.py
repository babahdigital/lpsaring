# backend/app/utils/formatters.py
# Kumpulan fungsi helper untuk pemformatan data.

import os
import re
from typing import Optional, List
from datetime import datetime, timezone as dt_timezone
from decimal import Decimal, ROUND_HALF_UP
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

def format_app_date(dt_utc: Optional[datetime] = None) -> str:
    """Format tanggal sesuai zona waktu aplikasi (dd-mm-yyyy)."""
    local_dt = get_app_local_datetime(dt_utc)
    return local_dt.strftime('%d-%m-%Y')


def format_app_time(dt_utc: Optional[datetime] = None) -> str:
    """Format waktu sesuai zona waktu aplikasi (HH:MM:SS)."""
    local_dt = get_app_local_datetime(dt_utc)
    return local_dt.strftime('%H:%M:%S')


def format_app_datetime(dt_utc: Optional[datetime] = None, include_tz: bool = False) -> str:
    """Format tanggal dan waktu sesuai zona waktu aplikasi (dd-mm-yyyy HH:MM:SS)."""
    local_dt = get_app_local_datetime(dt_utc)
    date_str = local_dt.strftime('%d-%m-%Y')
    time_str = local_dt.strftime('%H:%M:%S')
    if include_tz:
        tz_name = local_dt.tzname() or ""
        return f"{date_str} {time_str} {tz_name}".strip()
    return f"{date_str} {time_str}".strip()


def format_datetime_to_wita(dt_utc: Optional[datetime]) -> str:
    """Mengonversi datetime UTC menjadi string WITA dengan format dd-mm-yyyy."""
    if not isinstance(dt_utc, datetime):
        return ""
    if dt_utc.tzinfo is None:
        dt_utc = dt_utc.replace(tzinfo=dt_timezone.utc)
    wita_tz = ZoneInfo("Asia/Makassar")
    dt_wita = dt_utc.astimezone(wita_tz)
    return format_app_datetime(dt_wita, include_tz=True)

def get_app_timezone_name() -> str:
    return os.environ.get('APP_TIMEZONE', 'Asia/Makassar')

def get_app_local_datetime(dt_utc: Optional[datetime] = None) -> datetime:
    if dt_utc is None:
        dt_utc = datetime.now(dt_timezone.utc)
    if dt_utc.tzinfo is None:
        dt_utc = dt_utc.replace(tzinfo=dt_timezone.utc)
    tz_name = get_app_timezone_name()
    try:
        tz = ZoneInfo(tz_name)
    except ZoneInfoNotFoundError:
        tz = dt_timezone.utc
    return dt_utc.astimezone(tz)

def get_app_date_time_strings(dt_utc: Optional[datetime] = None) -> tuple[str, str]:
    local_dt = get_app_local_datetime(dt_utc)
    return format_app_date(local_dt), format_app_time(local_dt)


def round_mb(value: float, precision: str = "0.01") -> float:
    try:
        return float(Decimal(str(value)).quantize(Decimal(precision), rounding=ROUND_HALF_UP))
    except Exception:
        return float(value)

def normalize_to_e164(phone_number: str) -> str:
    """
    Menormalisasi berbagai format nomor telepon Indonesia ke format E.164 (+62).
    Menerima format: 08xxx, +628xxx, 628xxx, 8xxx
    Aturan validasi: 
    - Panjang total 10-12 digit untuk format lokal (08xx)
    - Digit setelah +62 harus 8-10 digit
    """
    if not phone_number or not isinstance(phone_number, str):
        raise ValueError("Nomor telepon tidak boleh kosong.")
    
    # Bersihkan semua karakter non-digit
    cleaned = re.sub(r'[^\d]', '', phone_number)
    if not cleaned:
        raise ValueError("Nomor telepon tidak boleh kosong.")
    
    # Terima berbagai format awal
    if cleaned.startswith('0'):
        # Format 08xxx -> +628xxx
        e164_number = '+62' + cleaned[1:]
    elif cleaned.startswith('62'):
        # Format 628xxx -> +628xxx
        e164_number = '+' + cleaned
    elif cleaned.startswith('8'):
        # Format 8xxx -> +628xxx
        e164_number = '+62' + cleaned
    else:
        raise ValueError(f"Format awalan nomor telepon '{phone_number}' tidak valid. Gunakan awalan 08, 628, atau +628.")

    # Validasi panjang: 12-14 digit untuk format E.164
    if not (12 <= len(e164_number) <= 14):
        raise ValueError("Panjang nomor telepon tidak valid. Harus antara 10-12 digit untuk format lokal (misal: 08xx).")
    
    # Validasi pola: setelah +628, harus ada 8-10 digit angka
    # [1-9] (digit pertama harus 1-9) + [0-9]{7,9} (7-9 digit berikutnya)
    if not re.match(r'^\+628[1-9][0-9]{7,9}$', e164_number):
        raise ValueError(f"Nomor telepon '{phone_number}' memiliki format yang tidak valid.")
        
    return e164_number

def normalize_to_local(phone_number: str) -> str:
    """
    Menormalisasi berbagai format nomor telepon Indonesia ke format lokal (08xxx).
    Menggunakan validasi dari normalize_to_e164 agar format selalu konsisten.
    """
    e164_number = normalize_to_e164(phone_number)
    return '0' + e164_number[3:]

def format_to_local_phone(phone_number: Optional[str]) -> Optional[str]:
    """Mengubah format E.164 (+62) atau format lain menjadi format lokal (08)."""
    if not phone_number: 
        return None
        
    try:
        # Bersihkan nomor dan pertahankan hanya digit
        cleaned = re.sub(r'[^\d]', '', str(phone_number))
        
        # Konversi berbagai format ke 08xxx
        if cleaned.startswith('62'):
            return '0' + cleaned[2:]
        elif cleaned.startswith('8'):
            return '0' + cleaned
        elif cleaned.startswith('0'):
            return cleaned
        else:
            # Untuk nomor asing, kembalikan tanpa modifikasi
            return cleaned
    except Exception:
        return None

def get_phone_number_variations(query: str) -> List[str]:
    """Menghasilkan variasi format nomor telepon untuk pencarian di database."""
    if not query or not query.isdigit(): 
        return [query] # Kembalikan query jika bukan digit (untuk pencarian nama)
    
    variations = {query}
    try:
        normalized_query = normalize_to_e164(query)
        local_part = normalized_query[3:]  # Hilangkan '+62'
        
        # Tambahkan variasi format
        variations.add(normalized_query)      # +628xxx
        variations.add('62' + local_part)     # 628xxx
        variations.add('0' + local_part)      # 08xxx
        variations.add(local_part)            # 8xxx
    except ValueError:
        # Jika normalisasi gagal, tetap gunakan query asli
        pass
        
    return list(variations)