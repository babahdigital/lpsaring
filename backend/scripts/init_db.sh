#!/bin/bash
set -eu

# Ambil variabel lingkungan dari .env atau gunakan nilai default.
# DB_HOST defaultnya adalah nama service di docker-compose.yml, yaitu 'db'.
DB_HOST="${DB_HOST:-db}"
DB_PORT="${DB_PORT:-5432}"

echo "Memulai proses inisialisasi database..."
echo "Host Target: ${DB_HOST}, Port Target: ${DB_PORT}"

# Loop tunggu menggunakan Python socket (tidak butuh paket eksternal)
MAX_ATTEMPTS=30
i=1
while [ "$i" -le "$MAX_ATTEMPTS" ]; do
    # Menjalankan skrip python inline untuk memeriksa koneksi socket.
    # Keluar dengan kode 0 jika sukses, 1 jika gagal. Error stderr diabaikan.
    python - <<PY_SCRIPT 2>/dev/null
import os
import socket
import sys

try:
    host = os.environ.get("DB_HOST", "db")
    port = int(os.environ.get("DB_PORT", "5432"))
    with socket.create_connection((host, port), timeout=2):
        pass
    sys.exit(0)
except (socket.timeout, ConnectionRefusedError, OSError):
    sys.exit(1)
PY_SCRIPT

    # Memeriksa exit code dari skrip python
    if [ $? -eq 0 ]; then
        echo "✅ Koneksi ke PostgreSQL berhasil."
        break # Keluar dari loop jika koneksi sukses
    fi

    if [ "$i" -eq "$MAX_ATTEMPTS" ]; then
        echo "Gagal terhubung ke database di ${DB_HOST}:${DB_PORT} setelah ${MAX_ATTEMPTS} percobaan. Membatalkan."
        exit 1
    fi

    echo "Percobaan ${i}/${MAX_ATTEMPTS}: PostgreSQL belum siap. Mencoba lagi dalam 2 detik..."
    i=$((i + 1))
    sleep 2
done

echo "Menjalankan migrasi database..."
# Set verbose mode untuk troubleshooting
export FLASK_ENV=development
export FLASK_DEBUG=0

# Function untuk retry migrasi jika gagal
run_migration() {
    local max_attempts=3
    local attempt=1
    
    while [ $attempt -le $max_attempts ]; do
        echo "🔄 Attempt $attempt/$max_attempts: Running flask db upgrade..."
        
        # Jalankan upgrade dengan timeout per-migration yang lebih panjang
        timeout 300 flask db upgrade
        
        # Check if migration completed successfully
        if [ $? -eq 0 ]; then
            echo "✅ Migrasi database berhasil completed"
            return 0
        else
            echo "❌ Migrasi attempt $attempt gagal atau timeout"
            
            if [ $attempt -lt $max_attempts ]; then
                echo "⏳ Waiting 10 seconds before retry..."
                sleep 10
            fi
        fi
        
        attempt=$((attempt + 1))
    done
    
    echo "❌ All migration attempts failed"
    return 1
}

# Run migration with retry logic
if ! run_migration; then
    echo "💥 Migrasi database gagal setelah semua percobaan"
    exit 1
fi

echo "Memeriksa dan membuat Super Admin jika diperlukan..."

# Ekspor variabel agar bisa dibaca oleh skrip Python
export SUPERADMIN_NAME="Kecek"
export SUPERADMIN_PHONE="0811580039"
export SUPERADMIN_ROLE="SUPER_ADMIN"
export SUPERADMIN_PASSWORD="alhabsyi"

# Menjalankan skrip Python khusus untuk pengecekan.
# Exit code 1 dari skrip menandakan user tidak ada.
if python -m scripts.check_superadmin; then
    echo "Super Admin sudah ada. Melewati pembuatan."
else
    echo "Super Admin belum ada. Membuat user: $SUPERADMIN_NAME..."
    flask user create --name "$SUPERADMIN_NAME" --phone "$SUPERADMIN_PHONE" --role "$SUPERADMIN_ROLE" --password "$SUPERADMIN_PASSWORD"
fi

echo "Inisialisasi pengaturan default..."
python -m scripts.init_settings

echo "Inisialisasi database selesai."

# Create completion marker for healthcheck
echo "Database initialization completed at $(date)" > /tmp/init_complete
echo "✅ All initialization tasks completed successfully!"