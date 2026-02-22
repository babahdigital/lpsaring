# backend/run.py
from app import create_app  # Import factory function create_app dari package app (app/__init__.py)

# Ambil konfigurasi dari environment variable (opsional, bisa juga di handle dalam create_app)
# config_name = os.getenv('FLASK_CONFIG', 'development') # Contoh jika menggunakan config class

# Buat instance aplikasi Flask menggunakan factory
app = create_app()

# Bagian ini biasanya untuk menjalankan server development Flask langsung (flask run)
# Dalam kasus Docker Compose dengan Gunicorn, Gunicorn akan mengimpor 'app' dari file ini.
# Jadi, pastikan variabel 'app' berisi instance Flask yang sudah dibuat.
# Kode if __name__ == '__main__': di bawah ini mungkin tidak akan pernah dieksekusi
# saat dijalankan via Gunicorn, tapi tidak masalah untuk tetap ada jika Anda
# sewaktu-waktu ingin menjalankan `python run.py` langsung di local (di luar docker).

if __name__ == "__main__":
    # Anda bisa menentukan host dan port di sini jika menjalankan langsung,
    # tapi Gunicorn akan mengontrol ini saat via Docker Compose.
    # Gunakan host='0.0.0.0' agar bisa diakses dari luar container (jika port di-expose).
    # Debug mode sebaiknya dikontrol oleh environment variable/config.
    app.run(host="0.0.0.0", port=5010)  # Port 5000 adalah contoh default Flask
