#!/bin/bash

# Script untuk menghasilkan tipe TypeScript dari spesifikasi OpenAPI/Swagger
# Dapat dijalankan di Linux/macOS atau di Windows dengan Git Bash atau WSL

set -e  # Keluar jika ada error

# Konfigurasi
API_URL="http://localhost:5010/api/docs/swagger.json"
OUTPUT_PATH="./frontend/types/generated/api.ts"

# Deteksi OS untuk menentukan tempat file sementara
if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "cygwin" ]]; then
  # Windows
  TEMP_JSON="$(pwd -W)/temp_swagger.json"
else
  # Linux/macOS
  TEMP_JSON="/tmp/swagger.json"
fi

echo "🚀 Memulai proses generate TypeScript types dari OpenAPI"

# Jalankan script persiapan direktori terlebih dahulu
if [[ -f "./scripts/prepare-output-dirs.sh" ]]; then
  echo "🔧 Mempersiapkan direktori output..."
  bash ./scripts/prepare-output-dirs.sh
fi

# Periksa apakah curl tersedia
if ! command -v curl &> /dev/null; then
  echo "⚠️ WARNING: curl tidak ditemukan. Melewati pengecekan backend."
else
  # Periksa apakah backend sudah berjalan
  echo "📡 Mengecek backend API di localhost:5010..."
  if ! curl -s --head http://localhost:5010/api/ping | head -1 | grep -q "200"; then
    echo "❌ ERROR: Backend tidak dapat diakses di http://localhost:5010"
    echo "   Pastikan backend sudah berjalan dengan menjalankan:"
    echo "   docker-compose up -d backend"
    exit 1
  fi
  echo "✓ Backend tersedia."
fi

# Buat direktori output jika belum ada
mkdir -p $(dirname "$OUTPUT_PATH")

# Cek apakah kita memiliki file swagger.json offline untuk digunakan
OFFLINE_SWAGGER="./backend/.output/swagger.json"

if [[ -f "$OFFLINE_SWAGGER" ]]; then
  echo "📋 Ditemukan file swagger.json offline: $OFFLINE_SWAGGER"
  cp "$OFFLINE_SWAGGER" "$TEMP_JSON"
elif command -v curl &> /dev/null; then
  # Unduh spesifikasi OpenAPI/Swagger
  echo "⬇️  Mengunduh spesifikasi OpenAPI dari $API_URL"
  if ! curl -s "$API_URL" -o "$TEMP_JSON"; then
    echo "❌ ERROR: Gagal mengunduh swagger.json"
    echo "   Cek apakah backend berjalan atau gunakan file offline"
    exit 1
  fi
else
  echo "❌ ERROR: curl tidak tersedia dan tidak ada file swagger.json offline"
  exit 1
fi

# Cek apakah jq tersedia
if ! command -v jq &> /dev/null; then
  echo "⚠️ WARNING: jq tidak ditemukan. Melewati validasi JSON."
else
  # Validasi JSON yang diunduh
  echo "🔍 Memvalidasi JSON yang diunduh..."
  if ! jq empty "$TEMP_JSON" 2>/dev/null; then
    echo "❌ ERROR: File swagger.json tidak valid"
    exit 1
  fi
  echo "✓ JSON valid."
fi

# Cek apakah npx tersedia
if ! command -v npx &> /dev/null; then
  echo "❌ ERROR: npx tidak ditemukan. Pastikan Node.js diinstall."
  exit 1
fi

# Install openapi-typescript jika diperlukan
echo "🔍 Memastikan openapi-typescript terinstall..."
if ! npm list -g openapi-typescript &> /dev/null; then
  echo "📦 Menginstall openapi-typescript secara global..."
  npm install -g openapi-typescript
fi

# Generate TypeScript types
echo "🔧 Menghasilkan tipe TypeScript dari spesifikasi OpenAPI..."
npx openapi-typescript "$TEMP_JSON" --output "$OUTPUT_PATH" --export-type

# Header untuk file output
echo "// File ini dihasilkan secara otomatis oleh generate-api-types.sh" > "$OUTPUT_PATH.tmp"
echo "// JANGAN EDIT FILE INI SECARA MANUAL! Akan tertimpa saat generate ulang." >> "$OUTPUT_PATH.tmp"
echo "// Dibuat pada: $(date)" >> "$OUTPUT_PATH.tmp"
echo "" >> "$OUTPUT_PATH.tmp"

# Gabungkan dengan hasil generate
cat "$OUTPUT_PATH" >> "$OUTPUT_PATH.tmp"
mv "$OUTPUT_PATH.tmp" "$OUTPUT_PATH"

# Tambahkan fallback untuk kompatibilitas jika struktur yang diharapkan tidak ada
echo "" >> "$OUTPUT_PATH"
echo "// Fallback untuk kompatibilitas dengan kode yang ada" >> "$OUTPUT_PATH"
echo "export namespace OpenAPI {" >> "$OUTPUT_PATH"
echo "  // Tempatkan tipe-tipe tambahan di sini jika diperlukan" >> "$OUTPUT_PATH"
echo "}" >> "$OUTPUT_PATH"

# Pastikan namespace components tersedia
echo "" >> "$OUTPUT_PATH"
echo "// Pastikan namespace components tersedia untuk kompatibilitas" >> "$OUTPUT_PATH"
echo "export namespace components {" >> "$OUTPUT_PATH"
echo "  export namespace schemas {" >> "$OUTPUT_PATH"
echo "    // Pastikan components.schemas tersedia untuk kompatibilitas" >> "$OUTPUT_PATH"
echo "  }" >> "$OUTPUT_PATH"
echo "}" >> "$OUTPUT_PATH"

echo "✅ Sukses! File tipe TypeScript dihasilkan di:"
echo "   $OUTPUT_PATH"
echo ""
echo "🔔 CATATAN: Jika Anda ingin menambahkan tipe kustom atau perluasan,"
echo "   buat file terpisah seperti 'types/api-types-custom.ts' yang"
echo "   mengimpor dan memperluas tipe yang dihasilkan secara otomatis."
