import os
import sys
from dotenv import load_dotenv
from routeros_api import RouterOsApiPool
from routeros_api.exceptions import RouterOsApiError

# Muat variabel dari file .env
# Pastikan skrip ini dijalankan dari direktori root proyek Anda
env_path = os.path.join(os.path.dirname(__file__), ".env")
if not os.path.exists(env_path):
    print(f"❌ ERROR: File .env tidak ditemukan di path: {env_path}")
    print("Pastikan Anda menjalankan skrip ini dari direktori root proyek backend.")
    sys.exit(1)

load_dotenv(dotenv_path=env_path)

# Baca Konfigurasi Mikrotik dari .env
MIKROTIK_HOST = os.environ.get("MIKROTIK_HOST")
MIKROTIK_USERNAME = os.environ.get("MIKROTIK_USERNAME") or os.environ.get("MIKROTIK_USER")
MIKROTIK_PASSWORD = os.environ.get("MIKROTIK_PASSWORD")
MIKROTIK_PORT = int(os.environ.get("MIKROTIK_PORT", 8728))

print("--- Tes Koneksi dan Pembuatan User Mikrotik ---")
print("Membaca Konfigurasi dari .env...")
print(f"  - MIKROTIK_HOST: {MIKROTIK_HOST}")
print(f"  - MIKROTIK_USERNAME: {MIKROTIK_USERNAME}")
print(f"  - MIKROTIK_PASSWORD: {'*' * len(MIKROTIK_PASSWORD) if MIKROTIK_PASSWORD else 'None'}")
print(f"  - MIKROTIK_PORT: {MIKROTIK_PORT}")
print("-" * 20)

# Validasi awal
if not all([MIKROTIK_HOST, MIKROTIK_USERNAME, MIKROTIK_PASSWORD]):
    print("❌ GAGAL: Harap pastikan MIKROTIK_HOST, MIKROTIK_USERNAME, dan MIKROTIK_PASSWORD terisi di file .env")
    sys.exit(1)

assert isinstance(MIKROTIK_HOST, str)
assert isinstance(MIKROTIK_USERNAME, str)
assert isinstance(MIKROTIK_PASSWORD, str)

# Inisialisasi pool koneksi
try:
    print("🔄 Mencoba menginisialisasi pool koneksi...")
    connection_pool = RouterOsApiPool(
        MIKROTIK_HOST, username=MIKROTIK_USERNAME, password=MIKROTIK_PASSWORD, port=MIKROTIK_PORT, plaintext_login=True
    )
    print("✅ SUKSES: Pool koneksi berhasil diinisialisasi.")
except Exception as e:
    print(f"❌ GAGAL: Gagal menginisialisasi pool koneksi. Error: {e}")
    sys.exit(1)

# Tes mendapatkan koneksi dari pool
api = None
try:
    print("\n🔄 Mencoba mendapatkan koneksi API dari pool...")
    api = connection_pool.get_api()
    print("✅ SUKSES: Koneksi API berhasil didapatkan.")

    # Tes membuat user baru
    test_username = "test_user_from_script"
    test_password = "testpassword123"
    print(f"\n🔄 Mencoba membuat user hotspot dengan nama: '{test_username}'...")

    hotspot_user_resource = api.get_resource("/ip/hotspot/user")

    # Cek apakah user sudah ada
    existing_users = hotspot_user_resource.get(name=test_username)
    if existing_users:
        print(f"🟡 INFO: User '{test_username}' sudah ada. Menghapus sebelum membuat yang baru...")
        hotspot_user_resource.remove(id=existing_users[0]["id"])

    # Buat user baru
    hotspot_user_resource.add(
        name=test_username,
        password=test_password,
        profile="default",  # Ganti jika Anda punya profil default lain
    )
    print(f"✅ SUKSES: User '{test_username}' berhasil dibuat di Mikrotik.")
    print("🎉 Tes Selesai. Koneksi dan operasi tulis ke Mikrotik BERHASIL.")

except RouterOsApiError as e:
    print(f"❌ GAGAL: Terjadi error API RouterOS. Pesan: {getattr(e, 'original_message', str(e))}")
except Exception as e:
    print(f"❌ GAGAL: Terjadi error tidak terduga. Error: {e}")
finally:
    if api:
        connection_pool.disconnect()
        print("\nℹ️ Koneksi ditutup.")
