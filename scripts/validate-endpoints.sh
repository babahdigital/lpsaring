#!/usr/bin/env bash
# Script untuk memvalidasi konsistensi endpoint antara frontend dan backend

# Warna untuk output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${YELLOW}=== Validasi Konsistensi Endpoint API ===${NC}"

# Direktori base
BASE_DIR=$(dirname "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)")
FRONTEND_DIR="$BASE_DIR/frontend"
BACKEND_DIR="$BASE_DIR/backend"

# File utama yang berisi endpoint
ENDPOINTS_FILE="$FRONTEND_DIR/constants/api-endpoints.ts"

echo -e "\n${YELLOW}Mengekstrak endpoint dari frontend...${NC}"

# Ekstrak endpoint dari constants/api-endpoints.ts
FRONTEND_ENDPOINTS=$(grep -o "'/[^']*'" "$ENDPOINTS_FILE" | sort | uniq | tr -d "'")

# Menampilkan endpoint frontend
echo -e "${GREEN}Daftar endpoint frontend yang terdaftar:${NC}"
echo "$FRONTEND_ENDPOINTS" | sed 's/^/  /'

echo -e "\n${YELLOW}Memeriksa endpoint di backend Flask...${NC}"

# Cari semua file route di backend
BACKEND_FILES=$(find "$BACKEND_DIR/app/infrastructure/http" -type f -name "*.py")

# Inisialisasi array untuk menyimpan endpoint yang tidak ditemukan
MISSING_ENDPOINTS=()

# Periksa setiap endpoint frontend di backend
for endpoint in $FRONTEND_ENDPOINTS; do
  # Potong '/api' dari awal endpoint jika ada
  if [[ $endpoint == /api/* ]]; then
    FLASK_ENDPOINT=${endpoint#/api}
  else
    FLASK_ENDPOINT=$endpoint
  fi

  # Cari endpoint di file backend
  FOUND=false
  for file in $BACKEND_FILES; do
    if grep -q "@.*route.*[\"']$FLASK_ENDPOINT[\"']" "$file" || \
       grep -q "@.*route.*[\"']$FLASK_ENDPOINT/[\"']" "$file" || \
       grep -q "@.*route.*[\"']$endpoint[\"']" "$file" || \
       grep -q "@.*route.*[\"']$endpoint/[\"']" "$file"; then
      echo -e "${GREEN}✓ Endpoint ${endpoint} ditemukan di ${file#$BASE_DIR/}${NC}"
      FOUND=true
      break
    fi
  done

  # Tambahkan ke array jika tidak ditemukan
  if [ "$FOUND" = false ]; then
    MISSING_ENDPOINTS+=("$endpoint")
  fi
done

# Laporan endpoint yang tidak ditemukan
if [ ${#MISSING_ENDPOINTS[@]} -gt 0 ]; then
  echo -e "\n${RED}Endpoint yang tidak ditemukan di backend:${NC}"
  for missing in "${MISSING_ENDPOINTS[@]}"; do
    echo -e "${RED}✗ $missing${NC}"
  done
  echo -e "\n${YELLOW}Saran: Periksa penamaan endpoint atau tambahkan endpoint yang hilang ke backend${NC}"
else
  echo -e "\n${GREEN}Semua endpoint frontend terdapat di backend! ✓${NC}"
fi

echo -e "\n${YELLOW}=== Validasi Selesai ===${NC}"
