# backend/app/utils/formatters.py
# Kumpulan fungsi helper untuk pemformatan data.

import os
import re
from typing import Optional, List, Any
from datetime import datetime, date, timezone as dt_timezone
from decimal import Decimal, ROUND_HALF_UP
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def format_app_date(dt_utc: Optional[datetime] = None) -> str:
    """Format tanggal sesuai zona waktu aplikasi (dd-mm-yyyy)."""
    local_dt = get_app_local_datetime(dt_utc)
    return local_dt.strftime("%d-%m-%Y")


def format_app_time(dt_utc: Optional[datetime] = None) -> str:
    """Format waktu sesuai zona waktu aplikasi (HH:MM:SS)."""
    local_dt = get_app_local_datetime(dt_utc)
    return local_dt.strftime("%H:%M:%S")


def format_app_datetime(dt_utc: Optional[datetime] = None, include_tz: bool = False) -> str:
    """Format tanggal dan waktu sesuai zona waktu aplikasi (dd-mm-yyyy HH:MM:SS)."""
    local_dt = get_app_local_datetime(dt_utc)
    date_str = local_dt.strftime("%d-%m-%Y")
    time_str = local_dt.strftime("%H:%M:%S")
    if include_tz:
        tz_name = local_dt.tzname() or ""
        return f"{date_str} {time_str} {tz_name}".strip()
    return f"{date_str} {time_str}".strip()


def _coerce_dateish_value(value: Any) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return get_app_local_datetime(value).date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        if re.match(r"^\d{2}-\d{2}-\d{4}$", raw):
            try:
                return datetime.strptime(raw, "%d-%m-%Y").date()
            except ValueError:
                return None
        normalized = raw.replace("Z", "+00:00")
        try:
            return get_app_local_datetime(datetime.fromisoformat(normalized)).date()
        except ValueError:
            pass
        for candidate in (raw, raw.split("T", 1)[0], raw.split(" ", 1)[0]):
            try:
                return date.fromisoformat(candidate)
            except ValueError:
                continue
    return None


def _coerce_datetimeish_value(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return get_app_local_datetime(value)
    if isinstance(value, date):
        return get_app_local_datetime(datetime(value.year, value.month, value.day, tzinfo=dt_timezone.utc))
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        if re.match(r"^\d{2}-\d{2}-\d{4}( \d{2}:\d{2}(:\d{2})?)?$", raw):
            try:
                local_tz = ZoneInfo(get_app_timezone_name())
            except ZoneInfoNotFoundError:
                local_tz = dt_timezone.utc
            for fmt in ("%d-%m-%Y %H:%M:%S", "%d-%m-%Y %H:%M", "%d-%m-%Y"):
                try:
                    parsed = datetime.strptime(raw, fmt)
                    return parsed.replace(tzinfo=local_tz)
                except ValueError:
                    continue
        normalized = raw.replace("Z", "+00:00")
        try:
            return get_app_local_datetime(datetime.fromisoformat(normalized))
        except ValueError:
            pass
        for fmt in (
            "%Y-%m-%d %H:%M:%S.%f",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d",
        ):
            try:
                parsed = datetime.strptime(raw, fmt)
                return get_app_local_datetime(parsed.replace(tzinfo=dt_timezone.utc))
            except ValueError:
                continue
    return None


def format_app_date_display(value: Any, fallback: str = "") -> str:
    coerced = _coerce_dateish_value(value)
    if coerced is None:
        return fallback
    return coerced.strftime("%d-%m-%Y")


def format_app_datetime_display(value: Any, fallback: str = "", include_seconds: bool = True) -> str:
    coerced = _coerce_datetimeish_value(value)
    if coerced is None:
        return fallback
    time_fmt = "%H:%M:%S" if include_seconds else "%H:%M"
    return coerced.strftime(f"%d-%m-%Y {time_fmt}")


def format_datetime_to_wita(dt_utc: Optional[datetime]) -> str:
    """Alias kompatibilitas untuk format datetime di zona waktu aplikasi."""
    if not isinstance(dt_utc, datetime):
        return ""
    if dt_utc.tzinfo is None:
        dt_utc = dt_utc.replace(tzinfo=dt_timezone.utc)
    return format_app_datetime(get_app_local_datetime(dt_utc), include_tz=True)


def get_app_timezone_name() -> str:
    return os.environ.get("APP_TIMEZONE", "Asia/Makassar")


def get_app_timezone() -> ZoneInfo | dt_timezone:
    tz_name = get_app_timezone_name()
    try:
        return ZoneInfo(tz_name)
    except ZoneInfoNotFoundError:
        return dt_timezone.utc


def get_app_timezone_offset_hours(dt_utc: Optional[datetime] = None) -> int:
    if dt_utc is None:
        dt_utc = datetime.now(dt_timezone.utc)
    if dt_utc.tzinfo is None:
        dt_utc = dt_utc.replace(tzinfo=dt_timezone.utc)
    offset = dt_utc.astimezone(get_app_timezone()).utcoffset()
    if offset is None:
        return 0
    return int(offset.total_seconds() // 3600)


def get_app_timezone_label(dt_utc: Optional[datetime] = None) -> str:
    explicit_label = (os.environ.get("APP_TIMEZONE_LABEL") or "").strip()
    if explicit_label:
        return explicit_label

    tz_name = get_app_timezone_name()
    common_labels = {
        "Asia/Jakarta": "WIB",
        "Asia/Makassar": "WITA",
        "Asia/Jayapura": "WIT",
    }
    if tz_name in common_labels:
        return common_labels[tz_name]

    if dt_utc is None:
        dt_utc = datetime.now(dt_timezone.utc)
    if dt_utc.tzinfo is None:
        dt_utc = dt_utc.replace(tzinfo=dt_timezone.utc)
    label = dt_utc.astimezone(get_app_timezone()).tzname()
    return str(label or tz_name)


def get_app_local_datetime(dt_utc: Optional[datetime] = None) -> datetime:
    if dt_utc is None:
        dt_utc = datetime.now(dt_timezone.utc)
    if dt_utc.tzinfo is None:
        dt_utc = dt_utc.replace(tzinfo=dt_timezone.utc)
    return dt_utc.astimezone(get_app_timezone())


def get_app_date_time_strings(dt_utc: Optional[datetime] = None) -> tuple[str, str]:
    local_dt = get_app_local_datetime(dt_utc)
    return format_app_date(local_dt), format_app_time(local_dt)


def round_mb(value: float, precision: str = "0.01") -> float:
    try:
        return float(Decimal(str(value)).quantize(Decimal(precision), rounding=ROUND_HALF_UP))
    except Exception:
        return float(value)


def format_mb_to_gb(value_mb: float, decimals: int = 2) -> str:
    """Convert MB to GB format dengan 2 decimal places (e.g., '10.50 GB')."""
    try:
        value_mb = float(value_mb)
        gb_value = value_mb / 1024.0
        # Round to specified decimals
        format_str = f"{{:.{decimals}f}}"
        return f"{format_str.format(gb_value)} GB"
    except Exception:
        return "0.00 GB"


def normalize_to_e164(phone_number: str) -> str:
    """
    Menormalisasi nomor telepon menjadi format E.164.

    Dukungan:
    - Indonesia (legacy): 08xxx, +628xxx, 628xxx, 8xxx -> +628xxx
    - Internasional: +<digits> (mis. +675...) -> dipertahankan

    Batasan panjang:
    - E.164 generic: 8-14 digit (tanpa tanda '+')
    - Indonesia: tetap divalidasi agar konsisten untuk pola +628...
    """
    if not phone_number or not isinstance(phone_number, str):
        raise ValueError("Nomor telepon tidak boleh kosong.")

    raw = phone_number.strip()
    if raw == "":
        raise ValueError("Nomor telepon tidak boleh kosong.")

    # Jika user sudah memberikan E.164 (+...), dukung untuk semua country code.
    # Simpan hanya digit dan pertahankan prefix '+'
    if raw.startswith("+"):
        digits = re.sub(r"[^\d]", "", raw)
        if not digits:
            raise ValueError("Nomor telepon tidak boleh kosong.")
        e164_number = "+" + digits
        # Generic E.164: +[1-9]\d{7,14} -> 8-15 digit total (E.164 max 15 digits)
        if not re.match(r"^\+[1-9]\d{7,14}$", e164_number):
            raise ValueError("Format nomor telepon internasional tidak valid. Gunakan format +<kodeNegara><nomor>.")
        return e164_number

    # Bersihkan semua karakter non-digit
    cleaned = re.sub(r"[^\d]", "", raw)
    if not cleaned:
        raise ValueError("Nomor telepon tidak boleh kosong.")

    # Dukungan prefix internasional umum: 00<cc><number> -> +<cc><number>
    if cleaned.startswith("00") and len(cleaned) > 2:
        cleaned = cleaned[2:]
        if re.match(r"^[1-9]\d{7,14}$", cleaned):
            return "+" + cleaned
        raise ValueError("Format nomor telepon internasional tidak valid. Gunakan format +<kodeNegara><nomor>.")

    # Terima berbagai format awal
    if cleaned.startswith("0"):
        # Untuk dukungan internasional: awalan 0 itu ambigu (tiap negara beda).
        # Kita hanya dukung format lokal Indonesia untuk nomor seluler 08xxx.
        if not cleaned.startswith("08"):
            raise ValueError(
                "Nomor telepon dengan awalan '0' hanya didukung untuk format Indonesia (08xxx). "
                "Untuk nomor internasional gunakan format +<kodeNegara><nomor> atau 00<kodeNegara><nomor>."
            )
        # Format 08xxx -> +628xxx
        e164_number = "+62" + cleaned[1:]
    elif cleaned.startswith("62"):
        # Format 628xxx -> +628xxx
        e164_number = "+" + cleaned
    elif cleaned.startswith("8"):
        # Format 8xxx -> +628xxx
        e164_number = "+62" + cleaned
    else:
        # Jika bukan pola Indonesia, anggap input sudah mengandung country code tanpa '+' (mis. 675..., 44..., dll)
        if re.match(r"^[1-9]\d{7,14}$", cleaned):
            return "+" + cleaned
        raise ValueError(
            f"Format awalan nomor telepon '{phone_number}' tidak valid. Gunakan awalan 08, 628, +628, atau format internasional +<kodeNegara>..."
        )

    # Validasi panjang: untuk Indonesia (hasil normalisasi selalu +62...)
    # Panjang total string (termasuk '+') biasanya 12-14 untuk nomor Indonesia yang umum.
    # Namun tetap batasi agar tidak kebablasan.
    if not (12 <= len(e164_number) <= 16):
        raise ValueError("Panjang nomor telepon tidak valid.")

    # Validasi pola: setelah +628, harus ada 8-10 digit angka
    # [1-9] (digit pertama harus 1-9) + [0-9]{7,9} (7-9 digit berikutnya)
    if not re.match(r"^\+628[1-9][0-9]{7,11}$", e164_number):
        raise ValueError(f"Nomor telepon '{phone_number}' memiliki format yang tidak valid.")

    return e164_number


def normalize_to_local(phone_number: str) -> str:
    """
    Menormalisasi berbagai format nomor telepon Indonesia ke format lokal (08xxx).
    Menggunakan validasi dari normalize_to_e164 agar format selalu konsisten.
    """
    e164_number = normalize_to_e164(phone_number)
    if e164_number.startswith("+62"):
        return "0" + e164_number[3:]
    # Untuk non-Indonesia, tidak ada padanan "lokal" 08xx. Kembalikan E.164.
    return e164_number


def format_to_local_phone(phone_number: Optional[str]) -> Optional[str]:
    """Mengubah format E.164 (+62) atau format lain menjadi format lokal (08)."""
    if not phone_number:
        return None

    try:
        # Bersihkan nomor dan pertahankan hanya digit
        cleaned = re.sub(r"[^\d]", "", str(phone_number))

        # Konversi berbagai format ke 08xxx
        if cleaned.startswith("62"):
            return "0" + cleaned[2:]
        elif cleaned.startswith("8"):
            return "0" + cleaned
        elif cleaned.startswith("0"):
            return cleaned
        else:
            # Untuk nomor asing, kembalikan tanpa modifikasi
            return cleaned
    except Exception:
        return None


def get_phone_number_variations(query: str) -> List[str]:
    """Menghasilkan variasi format nomor telepon untuk pencarian di database."""
    if not query:
        return [query]

    raw = str(query).strip()
    if raw == "":
        return [raw]

    # Untuk pencarian, kita terima input dengan '+' dan karakter non-digit.
    # Jika hasilnya bukan digit sama sekali, fallback ke raw (mis. nama).
    digits_only = re.sub(r"[^\d]", "", raw)
    if digits_only == "":
        return [raw]

    variations = {raw, digits_only}
    try:
        normalized_query = normalize_to_e164(raw)
        variations.add(normalized_query)
        variations.add(normalized_query.lstrip("+"))

        # Jika Indonesia, tambahkan variasi lokal.
        if normalized_query.startswith("+62"):
            local_part = normalized_query[3:]  # hilangkan '+62'
            variations.add("62" + local_part)  # 628xxx
            variations.add("0" + local_part)  # 08xxx
            variations.add(local_part)  # 8xxx
    except ValueError:
        # Jika normalisasi gagal, tetap gunakan query asli
        pass

    return list(variations)


def build_ip_binding_comment(
    *,
    binding_type: str,
    phone_number: Optional[str],
    user_id: str,
    role: str,
    source: Optional[str] = None,
) -> str:
    """Buat comment ip-binding yang akurat berdasarkan binding_type.

    - bypassed  → "authorized|..." (user mendapat akses penuh)
    - regular   → "managed|..."   (user dikenali tapi hotspot gate masih aktif)
    - blocked   → "blocked|..."   (user diblokir dari jaringan)
    """
    username_08 = format_to_local_phone(phone_number) or ""
    date_str, time_str = get_app_date_time_strings()

    bt = str(binding_type or "regular").strip().lower()
    if bt == "bypassed":
        prefix = "authorized"
    elif bt == "blocked":
        prefix = "blocked"
    else:
        prefix = "managed"

    parts = [f"{prefix}|user={username_08}|uid={user_id}|role={role}"]
    if source:
        parts.append(f"|source={source}")
    parts.append(f"|date={date_str}|time={time_str}")
    return "".join(parts)
