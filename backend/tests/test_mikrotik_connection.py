import os
from dotenv import load_dotenv
import routeros_api

# Load environment variables dari backend/.env
dotenv_path = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(dotenv_path=dotenv_path)

MIKROTIK_HOST = os.getenv("MIKROTIK_HOST")
MIKROTIK_USER = os.getenv("MIKROTIK_USER")
MIKROTIK_PASSWORD = os.getenv("MIKROTIK_PASSWORD")
MIKROTIK_PORT = int(os.getenv("MIKROTIK_PORT", 8728))  # Default port jika tidak ada
MIKROTIK_USE_SSL = os.getenv("MIKROTIK_USE_SSL", "false").lower() == "true"

print(f"Attempting to connect to {MIKROTIK_HOST}:{MIKROTIK_PORT} as user '{MIKROTIK_USER}' (SSL: {MIKROTIK_USE_SSL})")

try:
    # Gunakan parameter persis seperti di config/client Anda
    connection = routeros_api.RouterOsApiPool(
        MIKROTIK_HOST,
        username=MIKROTIK_USER,
        password=MIKROTIK_PASSWORD,
        port=MIKROTIK_PORT,
        use_ssl=MIKROTIK_USE_SSL,
        ssl_verify=False,  # Set True jika punya sertifikat valid & terpercaya, False untuk self-signed/testing
        plaintext_login=True,  # Coba True jika SSL=False, atau False jika SSL=True atau tidak yakin
    )
    # Coba dapatkan resource sederhana untuk memastikan koneksi & login berhasil
    api = connection.get_api()
    print("API object retrieved, attempting to get system resource...")
    system_resource = api.get_resource("/system/resource").get()
    print("Successfully connected and retrieved system resource:")
    print(system_resource)
    connection.disconnect()
    print("Connection closed.")

except routeros_api.exceptions.RouterOsApiCommunicationError as e:
    print(f"!!! Communication Error: {e}")  # Ini error yang kita hadapi
    print("!!! Double check username, password, policies, and allowed addresses in MikroTik and .env")
except routeros_api.exceptions.RouterOsApiConnectionError as e:
    print(f"!!! Connection Error: {e}")
    print("!!! Double check host IP, port, API service status in MikroTik, and network connectivity/firewalls")
except Exception as e:
    print(f"!!! An unexpected error occurred: {e}")
