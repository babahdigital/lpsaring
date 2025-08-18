# backend/run.py
import os
from dotenv import load_dotenv

def find_and_load_dotenv():
    """
    Mencari dan memuat file .env secara cerdas.
    Prioritas 1: Direktori yang sama dengan run.py (./backend/.env)
    Prioritas 2: Direktori induk (./.env)
    """
    # Path untuk development (di dalam folder backend)
    dev_path = os.path.join(os.path.dirname(__file__), '.env')
    
    # Path untuk produksi (di root folder, satu tingkat di atas backend)
    prod_path = os.path.join(os.path.dirname(__file__), '..', '.env')

    # Tentukan path mana yang akan digunakan
    dotenv_path = None
    if os.path.exists(dev_path):
        dotenv_path = dev_path
    elif os.path.exists(prod_path):
        dotenv_path = prod_path

    # Muat file .env jika path ditemukan
    if dotenv_path:
        print(f"INFO: Memuat variabel lingkungan dari: {dotenv_path}")
        load_dotenv(dotenv_path=dotenv_path)
    else:
        print("PERINGATAN: File .env tidak ditemukan di lokasi development maupun produksi.")

# --------------------------------------------------------------------
# EKSEKUSI UTAMA
# --------------------------------------------------------------------

# Jalankan fungsi pemuat .env sebelum kode aplikasi lainnya diimpor
if os.getenv('SKIP_DOTENV') != '1':
    find_and_load_dotenv()
else:
    print("INFO: SKIP_DOTENV=1 aktif, melewati pemuatan .env")

# Impor factory create_app SETELAH .env dimuat
from app import create_app

# Register SIGTERM handler for graceful shutdown with Docker
import signal
import sys
import logging

logger = logging.getLogger(__name__)

def sigterm_handler(signum, frame):
    """Handle SIGTERM signal for graceful shutdown"""
    logger.info("SIGTERM received! Initiating graceful shutdown...")
    # This triggers proper cleanup via atexit handlers
    sys.exit(0)

# Register signal handler
signal.signal(signal.SIGTERM, sigterm_handler)

# Buat instance aplikasi Flask menggunakan factory.
# Gunicorn akan mencari variabel bernama 'app' di file ini.
app = create_app(os.getenv('FLASK_CONFIG') or 'default')

# Blok ini hanya berguna untuk development jika Anda menjalankan `python run.py` secara manual.
# Gunicorn tidak akan menjalankan blok ini.
if __name__ == '__main__':
    host = os.getenv('FLASK_RUN_HOST', '127.0.0.1')
    port = int(os.getenv('FLASK_RUN_PORT', '5010'))
    app.run(host=host, port=port)