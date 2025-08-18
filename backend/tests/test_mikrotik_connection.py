# pyright: reportArgumentType=false, reportAttributeAccessIssue=false
import os
import pytest
from dotenv import load_dotenv
from routeros_api import RouterOsApiPool
from routeros_api.exceptions import RouterOsApiError

# Muat variabel dari file .env
# Pastikan skrip ini dijalankan dari direktori root proyek Anda
env_path = os.path.join(os.path.dirname(__file__), '.env')
if os.path.exists(env_path):
    load_dotenv(dotenv_path=env_path)


# Baca Konfigurasi Mikrotik dari .env
MIKROTIK_HOST = os.environ.get('MIKROTIK_HOST')
MIKROTIK_USERNAME = os.environ.get('MIKROTIK_USERNAME')
MIKROTIK_PASSWORD = os.environ.get('MIKROTIK_PASSWORD')
MIKROTIK_PORT = int(os.environ.get('MIKROTIK_PORT', 8728))

def _should_skip():
    return not all([MIKROTIK_HOST, MIKROTIK_USERNAME, MIKROTIK_PASSWORD])

@pytest.mark.integration
def test_mikrotik_connection_and_user_creation():
    if _should_skip():
        pytest.skip("Mikrotik credentials not set; skipping integration test")

    # Logging ringkas untuk debugging
    print("[MikrotikTest] Host=", MIKROTIK_HOST, "User=", MIKROTIK_USERNAME)

    # Inisialisasi pool koneksi
    connection_pool = RouterOsApiPool(
        MIKROTIK_HOST,
        username=MIKROTIK_USERNAME,
        password=MIKROTIK_PASSWORD,
        port=MIKROTIK_PORT,
        plaintext_login=True
    )

# Tes mendapatkan koneksi dari pool
    api = connection_pool.get_api()
    test_username = "test_user_from_script"
    test_password = "testpassword123"
    hotspot_user_resource = api.get_resource('/ip/hotspot/user')
    existing_users = hotspot_user_resource.get(name=test_username)
    if existing_users:
        hotspot_user_resource.remove(id=existing_users[0]['id'])
    hotspot_user_resource.add(name=test_username, password=test_password, profile='default')
    # Assertion sederhana: user harus bisa diambil kembali
    created = hotspot_user_resource.get(name=test_username)
    assert created, "User mikrotik tidak ditemukan setelah dibuat"
    connection_pool.disconnect()