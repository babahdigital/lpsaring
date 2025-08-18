# backend/app/infrastructure/http/decorators.py
# PENYEMPURNAAN: Menghapus decorator kustom dan menulis ulang decorator otorisasi
# agar menggunakan flask_jwt_extended sebagai basis.

from functools import wraps
from flask import jsonify
from http import HTTPStatus
# [PENYEMPURNAAN] Import dari flask_jwt_extended
from flask_jwt_extended import jwt_required, get_current_user

from app.infrastructure.db.models import User

# [DIHAPUS] Decorator token_required tidak lagi diperlukan.
# Fungsinya untuk autentikasi kini ditangani sepenuhnya oleh @jwt_required().


def admin_required(f):
    """
    Autorisasi Admin / Super Admin.
    Decorator ini harus digunakan *setelah* @jwt_required, atau bisa digunakan sendiri
    karena sudah menyertakan @jwt_required di dalamnya.
    """
    @wraps(f)
    @jwt_required() # 1. Lakukan autentikasi JWT terlebih dahulu.
    def decorated_function(*args, **kwargs):
        # 2. Ambil user yang sudah diautentikasi.
        current_user: User = get_current_user()
        if not current_user:
            return jsonify({"message": "Pengguna tidak ditemukan setelah autentikasi."}), HTTPStatus.UNAUTHORIZED

        # 3. Lakukan pengecekan peran (otorisasi).
        if not current_user.is_admin_role:
            return jsonify({"message": "Akses ditolak. Memerlukan hak akses Admin."}), HTTPStatus.FORBIDDEN
        
        # 4. Jika lolos, teruskan ke fungsi asli dengan objek user.
        return f(current_user, *args, **kwargs)

    return decorated_function


def super_admin_required(f):
    """
    Autorisasi Super Admin.
    Decorator ini harus digunakan *setelah* @jwt_required, atau bisa digunakan sendiri
    karena sudah menyertakan @jwt_required di dalamnya.
    """
    @wraps(f)
    @jwt_required() # 1. Lakukan autentikasi JWT terlebih dahulu.
    def decorated_function(*args, **kwargs):
        # 2. Ambil user yang sudah diautentikasi.
        current_user: User = get_current_user()
        if not current_user:
            return jsonify({"message": "Pengguna tidak ditemukan setelah autentikasi."}), HTTPStatus.UNAUTHORIZED

        # 3. Lakukan pengecekan peran (otorisasi).
        if not current_user.is_super_admin_role:
            return jsonify({"message": "Akses ditolak. Memerlukan hak akses Super Admin."}), HTTPStatus.FORBIDDEN

        # 4. Jika lolos, teruskan ke fungsi asli dengan objek user.
        return f(current_user, *args, **kwargs)

    return decorated_function