#!/bin/sh

# Script ini berjalan sebagai root.
echo "Entrypoint: Memeriksa dan memperbaiki hak akses volume..."

# Cek dan perbaiki hak akses HANYA jika direktori ada
if [ -d "/app/logs" ]; then
    echo "--> Mengatur kepemilikan untuk /app/logs"
    chown -R appuser:appuser /app/logs
fi

if [ -d "/app/.cache" ]; then
    echo "--> Mengatur kepemilikan untuk /app/.cache"
    chown -R appuser:appuser /app/.cache
fi

if [ -d "/tmp/celery" ]; then
    echo "--> Mengatur kepemilikan untuk /tmp/celery"
    chown -R appuser:appuser /tmp/celery
fi

echo "Entrypoint: Pemeriksaan hak akses selesai. Beralih ke 'appuser' untuk menjalankan aplikasi..."
exec gosu appuser "$@"