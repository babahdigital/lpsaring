# backend/app/services/user_management/__init__.py
# VERSI FINAL: File ini menginisialisasi paket user_management
# dengan cara mengekspos modul-modul service, bukan fungsi individual.

# Impor modul secara keseluruhan agar bisa dipanggil dari routes.
# Ini adalah pendekatan yang lebih bersih dan sesuai dengan struktur routes yang baru.
from . import user_approval as user_approval
from . import user_deletion as user_deletion
from . import user_profile as user_profile
from . import user_quota as user_quota
from . import user_role as user_role

__all__ = [
    "user_approval",
    "user_deletion",
    "user_profile",
    "user_quota",
    "user_role",
]

# Dengan struktur ini, file lain (seperti user_management_routes.py) bisa melakukan:
#
# from app.services.user_management import user_profile as user_profile_service
#
# Dan kemudian memanggil fungsi di dalamnya dengan:
#
# user_profile_service.create_user_by_admin(...)
#
# Ini menyelesaikan error 'ImportError' karena kita tidak lagi mencoba
# mengimpor fungsi yang sudah tidak ada.
