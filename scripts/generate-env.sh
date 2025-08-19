#!/bin/bash
# generate-env.sh - Menghasilkan file .env spesifik dari konfigurasi utama

set -e  # Keluar jika ada error

# Memastikan file .env induk ada
if [ ! -f .env ]; then
  echo "❌ ERROR: File .env tidak ditemukan di direktori root."
  echo "Salin .env.example ke .env dan sesuaikan:"
  echo "cp .env.example .env"
  exit 1
fi

# Membaca file .env induk
echo "📝 Membaca file .env induk..."
source ./.env

# Generate backend .env
echo "🔧 Menghasilkan file .env untuk backend..."
cat > ./backend/.env << EOF
# File ini dihasilkan secara otomatis dari .env root pada $(date)
# JANGAN EDIT FILE INI SECARA MANUAL!

# Konfigurasi Database
DB_HOST=${DB_HOST}
DB_PORT=${DB_PORT}
DB_NAME=${DB_NAME}
DB_USER=${DB_USER}
DB_PASSWORD=${DB_PASSWORD}

# Konfigurasi Redis
REDIS_HOST=${REDIS_HOST}
REDIS_PORT=${REDIS_PORT}
REDIS_PASSWORD=${REDIS_PASSWORD}

# Konfigurasi Flask
SECRET_KEY=${SECRET_KEY}
JWT_SECRET_KEY=${JWT_SECRET_KEY}
JWT_ALGORITHM=${JWT_ALGORITHM}
FLASK_ENV=${FLASK_ENV}
FLASK_DEBUG=${FLASK_DEBUG}
CACHE_CLEAR_ON_START=${CACHE_CLEAR_ON_START}

# Konfigurasi Mikrotik
MIKROTIK_DEFAULT_SERVER=${MIKROTIK_DEFAULT_SERVER}
MIKROTIK_SERVERS=${MIKROTIK_SERVERS}
$(env | grep MIKROTIK_ | grep -v MIKROTIK_SERVERS | grep -v MIKROTIK_DEFAULT_SERVER)

# WhatsApp
WHATSAPP_ENABLED=${WHATSAPP_ENABLED}
WHATSAPP_API_URL=${WHATSAPP_API_URL}
WHATSAPP_API_TOKEN=${WHATSAPP_API_TOKEN}

# Midtrans
MIDTRANS_CLIENT_KEY=${MIDTRANS_CLIENT_KEY}
MIDTRANS_SERVER_KEY=${MIDTRANS_SERVER_KEY}
MIDTRANS_PRODUCTION=${MIDTRANS_PRODUCTION}

# Konfigurasi lainnya
APP_URL=${APP_URL}
EOF

# Generate frontend .env
echo "🔧 Menghasilkan file .env untuk frontend..."
cat > ./frontend/.env << EOF
# File ini dihasilkan secara otomatis dari .env root pada $(date)
# JANGAN EDIT FILE INI SECARA MANUAL!

# Konfigurasi API
NUXT_PUBLIC_API_BASE_URL=${NUXT_PUBLIC_API_BASE_URL}

# Hot Module Reload
NODE_ENV=${FLASK_ENV}
NUXT_HMR_HOST=${NUXT_HMR_HOST}
NUXT_HMR_PORT=${NUXT_HMR_PORT}
NUXT_HMR_PROTOCOL=${NUXT_HMR_PROTOCOL}

# Midtrans Client Key (publik)
NUXT_PUBLIC_MIDTRANS_CLIENT_KEY=${MIDTRANS_CLIENT_KEY}
NUXT_PUBLIC_MIDTRANS_PRODUCTION=${MIDTRANS_PRODUCTION}
EOF

echo "✅ Selesai! File .env berhasil dihasilkan untuk backend dan frontend."
