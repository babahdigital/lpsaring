# backend/tests/test_whatsapp_send.py
# Versi dengan Path Correction untuk lokasi di tests/

import os
import sys
from dotenv import load_dotenv
from datetime import datetime
import logging  # Impor logging standar

# --- Penyesuaian Path Agar Bisa Impor dari 'app' ---
# Dapatkan direktori tempat skrip ini berada (/app/tests)
script_dir = os.path.dirname(os.path.abspath(__file__))
# Dapatkan direktori 'backend' atau 'app' (satu level di atas 'tests')
app_dir = os.path.dirname(script_dir)  # Seharusnya /app
# Tambahkan direktori 'app' (backend_dir) ke sys.path agar bisa 'from app...'
if app_dir not in sys.path:
    sys.path.insert(0, app_dir)
    print(f"INFO: Menambahkan '{app_dir}' ke sys.path")
# --- Akhir Penyesuaian Path ---

# --- Load Environment Variables dari /app/.env ---
# Path ke file .env sekarang relatif terhadap app_dir
dotenv_path = os.path.join(app_dir, ".env")
if not os.path.exists(dotenv_path):
    print(f"CRITICAL ERROR: File .env tidak ditemukan di {dotenv_path}")
    print("Pastikan file .env ada di direktori '/app' (root backend).")
    sys.exit(1)
load_dotenv(dotenv_path=dotenv_path)
print(f"INFO: Berhasil memuat variabel dari {dotenv_path}")
# --- Selesai Load Env ---


# --- Mocking Flask 'current_app' (Tetap Sama) ---
class MockAppConfig:
    """Kelas tiruan untuk Flask config."""

    def __init__(self):
        self._config = {  # Ambil langsung dari os.getenv setelah load_dotenv
            "WHATSAPP_API_URL": os.getenv("WHATSAPP_API_URL"),
            "WHATSAPP_API_KEY": os.getenv("WHATSAPP_API_KEY"),
            "WHATSAPP_PROVIDER": os.getenv("WHATSAPP_PROVIDER", "Fonnte"),
        }
        print("INFO: Mock Config dibuat:")
        print(f"  WHATSAPP_API_URL: {self._config.get('WHATSAPP_API_URL')}")
        api_key = self._config.get("WHATSAPP_API_KEY")  # Ambil key dulu
        api_key_display = (
            "********" + api_key[-4:] if api_key and len(api_key) > 4 else ("Set" if api_key else "Not Set")
        )
        print(f"  WHATSAPP_API_KEY: {api_key_display}")
        print(f"  WHATSAPP_PROVIDER: {self._config.get('WHATSAPP_PROVIDER')}")
        if not self._config["WHATSAPP_API_URL"] or not self._config["WHATSAPP_API_KEY"]:
            print("WARNING: WHATSAPP_API_URL atau WHATSAPP_API_KEY kosong di .env!")

    def get(self, key, default=None):
        return self._config.get(key, default)


class MockFlask:
    """Kelas tiruan untuk Flask app."""

    def __init__(self):
        self.config = MockAppConfig()
        self.logger = logging.getLogger("WhatsAppTestScript")
        if not self.logger.handlers:
            handler = logging.StreamHandler(sys.stdout)
            formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
        self.logger.setLevel(logging.INFO)


mock_app = MockFlask()
# --- Akhir Mocking ---


# --- Monkey Patching & Impor (Tetap Sama) ---
original_current_app = None
try:
    import flask

    original_current_app = flask.current_app
    flask.current_app = mock_app
    print("INFO: Konteks flask.current_app berhasil di-mock.")
except ImportError:
    print("WARNING: Modul Flask tidak ditemukan.")
    pass
except Exception as e:
    print(f"WARNING: Gagal mock flask.current_app: {e}")

# --- Impor Fungsi WA SETELAH Mocking ---
try:
    # Path import sekarang relatif dari /app
    from app.infrastructure.gateways.whatsapp_client import send_whatsapp_message

    print("INFO: Fungsi 'send_whatsapp_message' berhasil diimpor.")
except ImportError as e:
    print(
        "CRITICAL ERROR: Gagal impor 'send_whatsapp_message'. Periksa path 'app/infrastructure/gateways/whatsapp_client.py'."
    )
    print(f"Detail Error: {e}")
    sys.exit(1)
except Exception as e:
    print(f"CRITICAL ERROR: Terjadi kesalahan tak terduga saat impor: {e}")
    sys.exit(1)

# --- Data untuk Tes (INGAT GANTI NOMOR) ---
# !!! PENTING: Ganti dengan nomor WhatsApp AKTIF yang bisa Anda cek pesannya !!!
test_recipient_number = "+62811580039"  # <-- GANTI DENGAN NOMOR ANDA! Format +62...
test_message_content = f"Halo! 👋 Ini adalah pesan tes otomatis (dari test script) sistem Portal Hotspot menggunakan Fonnte.\nTes dikirim pada: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
# ---------------------------------------------

# --- Validasi nomor tes (Versi Perbaikan) ---

# Definisikan placeholder asli yang harus diganti pengguna
placeholder_number = "+628xxxxxxxxxx"

# Dapatkan nomor yang diset pengguna di variabel test_recipient_number
current_test_number = test_recipient_number

# Cek apakah nomor masih berupa placeholder ATAU formatnya tidak valid
is_still_placeholder = current_test_number == placeholder_number
is_invalid_format = (
    not current_test_number.startswith("+628") or len(current_test_number) < 11
)  # Cek panjang minimal dasar

if is_still_placeholder or is_invalid_format:
    print("\n!!! PERHATIAN !!!")
    # Tampilkan nomor yang *sebenarnya* ada di variabel saat ini
    print(
        f"Nomor tujuan tes ('{current_test_number}') masih berupa placeholder ('{placeholder_number}') atau formatnya tidak valid."
    )
    print(
        "Mohon edit file tests/test_whatsapp_send.py dan ganti placeholder dengan nomor WhatsApp Anda yang valid (diawali +62)."
    )
    success = False  # Tandai gagal jika nomor belum diganti/valid
else:
    # Nomor sudah diganti dan format tampak benar, LANJUTKAN PENGIRIMAN
    print(f"\nINFO: Mencoba mengirim pesan tes ke: {current_test_number}")
    print(f"INFO: Isi Pesan: {test_message_content}")

    # --- Panggil Fungsi Pengiriman WA ---
    success = send_whatsapp_message(current_test_number, test_message_content)
    # ---------------------------------

# --- Hasil Tes (Kode di bawah ini tetap sama) ---
print("\n--- HASIL TES PENGIRIMAN WHATSAPP ---")
if success:
    # ... (pesan sukses) ...
    print("✅ Fungsi send_whatsapp_message mengembalikan True.")
    print("   Ini mengindikasikan panggilan API ke Fonnte kemungkinan BERHASIL.")
    print("   Silakan periksa aplikasi WhatsApp di nomor tujuan untuk memastikan pesan benar-benar sampai.")
    print("   (Terkadang perlu beberapa saat sampai pesan masuk).")
else:
    # ... (pesan gagal) ...
    print("❌ Fungsi send_whatsapp_message mengembalikan False.")
    print("   Ini mengindikasikan panggilan API ke Fonnte GAGAL atau Fonnte melaporkan kegagalan.")
    print(
        "   Periksa log error di atas (jika ada dari fungsi send_whatsapp_message), pastikan API Key Fonnte di .env sudah benar,"
    )
    print("   dan cek juga dashboard/log di Fonnte jika tersedia.")
print("------------------------------------")

# --- Mengembalikan current_app (Cleanup) ---
if original_current_app is not None:
    try:
        import flask

        flask.current_app = original_current_app
        print("\nINFO: Konteks flask.current_app dikembalikan ke semula.")
    except ImportError:
        pass
# --- Selesai ---
