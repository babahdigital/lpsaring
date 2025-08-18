# scripts/check_superadmin.py
import os
import sys

# Menambahkan path root proyek ke sys.path agar bisa mengimpor 'app'
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app
from app.infrastructure.db.models import User, UserRole
from app.utils.formatters import normalize_to_e164

def check_superadmin_exists():
    """
    Skrip untuk memeriksa apakah Super Admin default sudah ada di database.
    - Keluar dengan exit code 0 (sukses) jika user ditemukan.
    - Keluar dengan exit code 1 (gagal) jika user tidak ditemukan.
    """
    # Ambil nomor telepon dari environment variable yang di-set di init_db.sh
    superadmin_phone = os.environ.get('SUPERADMIN_PHONE')
    if not superadmin_phone:
        print("Error: Environment variable SUPERADMIN_PHONE tidak diatur.", file=sys.stderr)
        sys.exit(2)

    app = create_app(os.getenv('FLASK_CONFIG') or 'default')
    with app.app_context():
        try:
            phone_e164 = normalize_to_e164(superadmin_phone)
            user = User.query.filter_by(
                phone_number=phone_e164,
                role=UserRole.SUPER_ADMIN
            ).first()

            if user:
                print(f"Info: Super Admin dengan nomor {superadmin_phone} ditemukan di database.")
                sys.exit(0)  # Sukses, user ada.
            else:
                print(f"Info: Super Admin dengan nomor {superadmin_phone} tidak ditemukan.")
                sys.exit(1)  # Gagal, user tidak ada.

        except Exception as e:
            print(f"Error saat menjalankan pengecekan Super Admin: {e}", file=sys.stderr)
            sys.exit(2) # Kode error untuk kegagalan skrip

if __name__ == "__main__":
    check_superadmin_exists()