#!/bin/bash

# Script untuk optimasi development di local network hotspot
echo "🚀 Optimizing Nuxt 4 SPA for Local Network Hotspot..."

# Clear Nuxt cache
echo "🧹 Clearing Nuxt cache..."
rm -rf .nuxt
rm -rf .output
rm -rf node_modules/.vite
rm -rf node_modules/.cache

# Clear npm cache untuk memastikan dependencies fresh
echo "🧹 Clearing npm cache..."
npm cache clean --force

# Reinstall dependencies dengan optimizations
echo "📦 Reinstalling dependencies..."
npm ci

# Pre-build dependencies yang sering bermasalah
echo "🔨 Pre-optimizing dependencies..."
npx vite optimize

echo "✅ Optimization complete!"
echo ""
echo "💡 Tips untuk development di local network:"
echo "   1. Pastikan firewall tidak block port 3000"
echo "   2. Gunakan IP address lokal daripada domain"
echo "   3. Disable antivirus real-time scanning untuk folder project"
echo "   4. Tutup aplikasi lain yang menggunakan bandwidth"
echo ""
echo "🌐 Ready to run: npm run dev"
