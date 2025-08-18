# backend/app/utils/security.py

from werkzeug.security import generate_password_hash as werkzeug_generate_password_hash
from werkzeug.security import check_password_hash as werkzeug_check_password_hash

# Metode hashing yang digunakan, scrypt adalah pilihan yang kuat dan direkomendasikan.
# format: scrypt:salt_length:n:r:p
HASH_METHOD = 'scrypt:32768:8:1'

def generate_password_hash(password: str) -> str:
    """
    Membuat hash dari password menggunakan metode yang ditentukan.
    
    :param password: Password dalam bentuk teks biasa.
    :return: String hash dari password.
    """
    return werkzeug_generate_password_hash(password, method=HASH_METHOD)

def check_password_hash(pwhash: str, password: str) -> bool:
    """
    Memeriksa apakah password yang diberikan cocok dengan hash yang tersimpan.
    
    :param pwhash: Hash password yang tersimpan di database.
    :param password: Password dalam bentuk teks biasa yang akan diperiksa.
    :return: True jika cocok, False jika tidak.
    """
    if not pwhash:
        return False
    return werkzeug_check_password_hash(pwhash, password)