#!/bin/bash
# Script untuk clear cache dan optimasi startup backend
# File: backend/scripts/clear-startup-cache.sh

echo "🧹 Clearing all caches on startup..."

# Clear Python bytecode cache
find /app -name "*.pyc" -type f -delete
find /app -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true

# Clear Flask cache jika ada
rm -rf /app/.cache/* 2>/dev/null || true
rm -rf /app/instance/cache/* 2>/dev/null || true

# Clear font cache
rm -rf /app/.cache/fontconfig/* 2>/dev/null || true

echo "✅ Startup cache clearing completed"

# Set environment untuk clear cache saat runtime
export CACHE_CLEAR_ON_START=true
export FLASK_CLEAR_CACHE=true

echo "🚀 Backend startup optimization completed"
