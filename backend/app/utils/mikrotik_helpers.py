# backend/app/utils/mikrotik_helpers.py

from flask import current_app
from datetime import datetime, timezone as dt_tz
from app.infrastructure.db.models import User, UserRole

def get_server_for_user(user: User) -> str:
    """
    Menentukan nama server hotspot MikroTik yang sesuai berdasarkan peran pengguna
    dan konfigurasi, dengan prioritas pada mode testing.
    """
    is_test_mode = current_app.config.get('SYNC_TEST_MODE_ENABLED', False)
    
    # Check test mode first - override all other logic if test mode is enabled 
    # and phone number is in test list
    if is_test_mode:
        # PERBAIKAN: Set log level ke DEBUG untuk informasi ini
        # Print semua informasi debug yang diperlukan
        current_app.logger.info(f"[TEST MODE] Active: {is_test_mode}")
        current_app.logger.info(f"[TEST MODE] User: {getattr(user, 'full_name', None)} (ID: {getattr(user, 'id', None)})")
        current_app.logger.info(f"[TEST MODE] Role: {getattr(user, 'role', None)}")
        current_app.logger.info(f"[TEST MODE] MIKROTIK_SERVER_TESTING: {current_app.config.get('MIKROTIK_SERVER_TESTING', 'not set')}")
        
        user_phone = getattr(user, 'phone_number', None)
        test_phone_numbers = current_app.config.get('SYNC_TEST_PHONE_NUMBERS', [])
        
        # PERBAIKAN: Debugging nilai mentah
        current_app.logger.info(f"[TEST MODE] Raw test phone numbers: {test_phone_numbers!r}, type: {type(test_phone_numbers)}")
        
        # Convert test_phone_numbers to list if it's a string
        if isinstance(test_phone_numbers, str):
            test_phone_numbers = [test_phone_numbers]
        
        # Normalize test_phone_numbers to ensure they are all strings
        test_phone_numbers = [str(num).strip() for num in test_phone_numbers if num]
        
        current_app.logger.info(f"[TEST MODE] Checking if {user_phone} is in test numbers: {test_phone_numbers}")
        
        # FORCE TEST MODE untuk semua user ketika SYNC_TEST_MODE_ENABLED=True
        # Ini untuk debugging dan memastikan semua user mengunakan server testing saat mode test aktif
        current_app.logger.info(f"[TEST MODE] Forcing test server for ALL users because test mode is active")
        return current_app.config.get('MIKROTIK_SERVER_TESTING', 'testing')
        
        # Kode ini tidak akan dieksekusi karena perubahan di atas
        # yang memaksa semua user menggunakan server testing ketika mode test aktif
        pass

    role_server_map = {
        UserRole.USER: current_app.config.get('MIKROTIK_SERVER_USER'),
        UserRole.KOMANDAN: current_app.config.get('MIKROTIK_SERVER_KOMANDAN'),
        UserRole.ADMIN: current_app.config.get('MIKROTIK_SERVER_ADMIN'),
        UserRole.SUPER_ADMIN: current_app.config.get('MIKROTIK_SERVER_SUPER_ADMIN')
    }
    server_name = role_server_map.get(user.role)
    return server_name if server_name else 'all'

def determine_target_profile(user: User) -> str:
    """
    Satu-satunya fungsi yang menentukan profil user di MikroTik berdasarkan semua kondisi.
    Fungsi ini sekarang HANYA berisi logika produksi dengan presisi yang ditingkatkan.
    """
    # Check if test mode is enabled - use standard profile for test mode
    is_test_mode = current_app.config.get('SYNC_TEST_MODE_ENABLED', False)
    if is_test_mode:
        current_app.logger.info(f"[TEST MODE] Determine profile for {getattr(user, 'full_name', None)}")
        # Gunakan profil standard untuk test mode
        return current_app.config['MIKROTIK_PROFILE_AKTIF']
    
    now_utc = datetime.now(dt_tz.utc)
    
    # --- [PERBAIKAN LOGIKA PRIORITAS DI SINI] ---
    # Prioritas 1: Status Blokir adalah yang paling utama. Jika user diblokir,
    # semua kondisi lain diabaikan dan profil blokir yang diterapkan.
    if user.is_blocked:
        return current_app.config['MIKROTIK_PROFILE_BLOKIR']

    # Prioritas 2: Status akun tidak aktif (untuk pengguna lama yang akan dihapus).
    # Ini hanya dievaluasi jika pengguna TIDAK diblokir.
    if not user.is_active:
        return current_app.config['MIKROTIK_PROFILE_INACTIVE']

    # Prioritas 3: Akun unlimited tidak perlu cek kuota
    if user.is_unlimited_user:
        return current_app.config['MIKROTIK_PROFILE_UNLIMITED']

    # Prioritas 4: Cek masa berlaku. Jika sudah expired, langsung habis.
    is_expired = user.quota_expiry_date and user.quota_expiry_date < now_utc
    if is_expired:
        return current_app.config['MIKROTIK_PROFILE_HABIS']

    # Logika baru yang lebih presisi untuk FUP dan Kuota Habis.
    # Hanya berlaku untuk user non-unlimited yang pernah beli kuota.
    if user.total_quota_purchased_mb > 0:
        
        # Hitung sisa kuota dalam MB untuk presisi
        # Menggunakan float untuk menangani nilai desimal dari penggunaan.
        purchased_mb = float(user.total_quota_purchased_mb)
        used_mb = float(user.total_quota_used_mb or 0.0)
        remaining_mb = purchased_mb - used_mb

        # Kondisi 1: Kuota Habis (Out of Quota)
        # Didefinisikan sebagai sisa kuota kurang dari atau sama dengan 0.
        if remaining_mb <= 0:
            return current_app.config['MIKROTIK_PROFILE_HABIS']

        # Kondisi 2: Masuk FUP (Low Quota)
        # Didefinisikan sebagai pemakaian di atas persentase FUP, TAPI kuota belum habis.
        fup_threshold_percent = float(current_app.config.get('FUP_THRESHOLD_PERCENT', 85))
        usage_percent = (used_mb / purchased_mb) * 100
        
        if usage_percent >= fup_threshold_percent:
            return current_app.config['MIKROTIK_PROFILE_FUP']

    # Default: Jika semua kondisi di atas tidak terpenuhi, profilnya aktif.
    return current_app.config['MIKROTIK_PROFILE_AKTIF']

# Menjaga kompatibilitas jika ada bagian lain yang masih memanggil nama lama
get_profile_for_user = determine_target_profile