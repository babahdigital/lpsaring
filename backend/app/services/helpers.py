# backend/app/services/helpers.py
# Modul untuk fungsi pembantu yang dapat digunakan kembali di seluruh aplikasi.

import re

# PENTING: Fungsi normalize_phone_number di sini mungkin duplikat
# dengan app.utils.formatters.normalize_to_e164.
# Disarankan untuk secara bertahap memigrasikan semua penggunaan
# ke app.utils.formatters.normalize_to_e164
# dan menghapus fungsi ini di masa mendatang untuk konsistensi.

def normalize_phone_number(phone_number: str) -> str:
    """
    Membersihkan dan menormalkan nomor telepon ke format internasional (misal: 628xxxxxxxx).
    - Menghilangkan semua karakter non-digit.
    - Jika diawali dengan '0', ganti dengan '62'.
    - Jika tidak diawali dengan '62' atau '0', tambahkan '62' di depan.
    """
    if not phone_number or not isinstance(phone_number, str):
        return ""

    # Hilangkan semua kecuali angka
    cleaned_number = re.sub(r'\D', '', phone_number)

    # Jika nomor dimulai dengan '0', ganti dengan '62'
    if cleaned_number.startswith('0'):
        return '62' + cleaned_number[1:]

    # Jika nomor sudah dimulai dengan '62', biarkan
    if cleaned_number.startswith('62'):
        return cleaned_number

    # Untuk kasus lain (misal: 812...), tambahkan '62'
    if cleaned_number:
        return '62' + cleaned_number

    return ""