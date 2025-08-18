#!/bin/sh
# Development startup script

echo "🚀 Starting Nuxt Development Server..."
echo "📂 Working directory: $(pwd)"
echo "👤 Running as user: $(whoami)"
echo "🌐 Host: ${NUXT_HOST:-0.0.0.0}"
echo "🔌 Port: ${NUXT_PORT:-3000}"

# Check if node_modules exists
if [ ! -d "node_modules" ]; then
    echo "📦 Installing dependencies..."
    npm install
fi

# Create necessary directories
mkdir -p .nuxt .output

# Set permissions if needed
if [ "$(whoami)" = "root" ]; then
    chown -R node:node .nuxt .output node_modules 2>/dev/null || true
fi

# Start development server
echo "🏃 Starting npm run dev..."
exec npm run dev
