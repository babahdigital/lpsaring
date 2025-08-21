#!/bin/bash
# ===================================================================
# DEPRECATED: Please use validate-endpoints-final.sh instead
# This script is kept for compatibility but contains known issues
# ===================================================================
# Skrip ini dapat dijalankan dengan bash di Linux/macOS atau Git Bash di Windows
# Versi: 1.1.0 - Mendukung analisis mendalam blueprint dan routing
# Script untuk memvalidasi konsistensi endpoint antara frontend dan backend
# dengan mempertimbangkan struktur blueprint Flask

# Warna untuk output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${RED}=== DEPRECATED: Please use validate-endpoints-final.sh instead ===${NC}"
echo -e "${YELLOW}=== Validasi Konsistensi Endpoint API ===${NC}"

# Direktori base
BASE_DIR=$(dirname "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)")
FRONTEND_DIR="$BASE_DIR/frontend"
BACKEND_DIR="$BASE_DIR/backend"

# File utama yang berisi endpoint
ENDPOINTS_FILE="$FRONTEND_DIR/constants/api-endpoints.ts"

echo -e "\n${YELLOW}Mengekstrak endpoint dari frontend...${NC}"

# Ekstrak endpoint dari constants/api-endpoints.ts
FRONTEND_ENDPOINTS=$(grep -o "'/[^']*'" "$ENDPOINTS_FILE" | sort | uniq | tr -d "'" | grep -v "^/$")

# Menampilkan endpoint frontend
echo -e "${GREEN}Daftar endpoint frontend yang terdaftar:${NC}"
echo "$FRONTEND_ENDPOINTS" | sed 's/^/  /'

echo -e "\n${YELLOW}Menganalisis blueprint Flask dan struktur routing...${NC}"

# Membuat file temporary untuk menyimpan analisis blueprint
BLUEPRINT_ANALYSIS=$(mktemp)

# Analisis blueprint dan prefiks
find "$BACKEND_DIR" -name "*.py" | xargs grep -l "Blueprint" | while read -r file; do
  blueprint_name=$(grep -o "Blueprint([^)]*)" "$file" | head -1)
  if [ -n "$blueprint_name" ]; then
    bp_var=$(echo "$blueprint_name" | sed -E "s/Blueprint\(['\"]([^'\"]*)['\"],.*/\1/")
    prefix=$(grep -o "url_prefix=['\"][^'\"]*['\"]" "$file" | head -1 | sed -E "s/url_prefix=['\"](.*)['\"].*/\1/")
    echo "$file:$bp_var:$prefix" >> "$BLUEPRINT_ANALYSIS"
    echo -e "${BLUE}🔍 Blueprint di $file: $bp_var dengan prefix: $prefix${NC}"
  fi
done

echo -e "\n${YELLOW}Memeriksa endpoint di backend Flask...${NC}"

# Inisialisasi array untuk menyimpan endpoint yang ditemukan dan tidak ditemukan
declare -A FOUND_ENDPOINTS
declare -A ENDPOINTS_LOCATION
MISSING_ENDPOINTS=()

# Cari semua file route di backend
BACKEND_FILES=$(find "$BACKEND_DIR" -type f -name "*.py")

# Cari endpoint dengan mempertimbangkan struktur blueprint
for endpoint in $FRONTEND_ENDPOINTS; do
  # Strip /api prefix jika ada
  if [[ $endpoint == /api* ]]; then
    FLASK_ENDPOINT=${endpoint#/api}
  else
    FLASK_ENDPOINT=$endpoint
  fi
  
  # Ekstrak bagian pertama dari path untuk mencari blueprint yang sesuai
  FIRST_PART=$(echo "$FLASK_ENDPOINT" | cut -d/ -f2)
  
  # Tandai awalnya sebagai tidak ditemukan
  FOUND_ENDPOINTS["$endpoint"]=false
  
  # Coba cari endpoint secara langsung
  for file in $BACKEND_FILES; do
    # Periksa berbagai bentuk definisi route
    if grep -q "@.*route.*[\"']$FLASK_ENDPOINT[\"']" "$file" || \
       grep -q "@.*route.*[\"']$FLASK_ENDPOINT/[\"']" "$file" || \
       grep -q "@.*route.*[\"']${FLASK_ENDPOINT%/}[\"']" "$file"; then
      FOUND_ENDPOINTS["$endpoint"]=true
      ENDPOINTS_LOCATION["$endpoint"]="$file (direct match)"
      break
    fi
    
    # Cek juga kemungkinan endpoint dengan prefix blueprint yang berbeda
    while read -r blueprint_info; do
      bp_file=$(echo "$blueprint_info" | cut -d: -f1)
      bp_prefix=$(echo "$blueprint_info" | cut -d: -f3)
      
      if [ -n "$bp_prefix" ] && [[ "$FLASK_ENDPOINT" == "$bp_prefix"* ]]; then
        # Extract path setelah prefix blueprint
        subpath="${FLASK_ENDPOINT#$bp_prefix}"
        # Cek apakah subpath ada di file ini
        if grep -q "@.*route.*[\"']$subpath[\"']" "$file" || \
           grep -q "@.*route.*[\"']$subpath/[\"']" "$file" || \
           grep -q "@.*route.*[\"']${subpath%/}[\"']" "$file"; then
          FOUND_ENDPOINTS["$endpoint"]=true
          ENDPOINTS_LOCATION["$endpoint"]="$file (blueprint path: $subpath)"
          break
        fi
      fi
    done < "$BLUEPRINT_ANALYSIS"
    
    # Jika sudah ditemukan, lanjut ke endpoint berikutnya
    if [ "${FOUND_ENDPOINTS["$endpoint"]}" = true ]; then
      break
    fi
  done
done

# Kompilasi endpoint yang tidak ditemukan
for endpoint in $FRONTEND_ENDPOINTS; do
  if [ "${FOUND_ENDPOINTS["$endpoint"]}" = false ]; then
    MISSING_ENDPOINTS+=("$endpoint")
  fi
done

# Laporan hasil
echo -e "\n${YELLOW}Hasil validasi endpoint:${NC}"

# Tampilkan endpoint yang ditemukan
echo -e "\n${GREEN}Endpoint yang ditemukan:${NC}"
for endpoint in $FRONTEND_ENDPOINTS; do
  if [ "${FOUND_ENDPOINTS["$endpoint"]}" = true ]; then
    location="${ENDPOINTS_LOCATION["$endpoint"]}"
    echo -e "${GREEN}✓ $endpoint${NC} - ${BLUE}${location#$BASE_DIR/}${NC}"
  fi
done

# Laporan endpoint yang tidak ditemukan
if [ ${#MISSING_ENDPOINTS[@]} -gt 0 ]; then
  echo -e "\n${RED}Endpoint yang tidak ditemukan di backend:${NC}"
  for missing in "${MISSING_ENDPOINTS[@]}"; do
    echo -e "${RED}✗ $missing${NC}"
  done
  
  echo -e "\n${YELLOW}Saran untuk endpoint yang tidak ditemukan:${NC}"
  echo -e "1. Periksa penamaan endpoint di frontend dan backend"
  echo -e "2. Periksa struktur blueprint dan url_prefix di flask"
  echo -e "3. Endpoint mungkin didefinisikan di tempat lain atau dengan metode lain"
  echo -e "4. Tambahkan endpoint yang hilang ke backend jika memang diperlukan"
else
  echo -e "\n${GREEN}Semua endpoint frontend terdapat di backend! ✓${NC}"
fi

# Cari panggilan API di frontend
echo -e "\n${YELLOW}Mencari panggilan API di kode frontend:${NC}"

# Mencari string yang mengandung API call patterns
FRONTEND_API_CALLS=$(grep -r "await.*\$api\|await.*\$fetch\|\$api(" --include="*.ts" --include="*.vue" "$FRONTEND_DIR" | grep -v "node_modules")

# Cari dan tampilkan 10 hasil teratas
if [ -n "$FRONTEND_API_CALLS" ]; then
  echo -e "${BLUE}Contoh panggilan API di frontend (10 hasil teratas):${NC}"
  echo "$FRONTEND_API_CALLS" | head -10 | sed 's/^/    /'
fi

# Cari OpenAPI/Swagger spec jika ada
echo -e "\n${YELLOW}Memeriksa OpenAPI/Swagger spec:${NC}"

SWAGGER_PATH="$BACKEND_DIR/.output/swagger.json"
if [ -f "$SWAGGER_PATH" ]; then
  echo -e "${GREEN}File OpenAPI spec ditemukan: ${SWAGGER_PATH#$BASE_DIR/}${NC}"
  
  # Coba ekstrak endpoint dari swagger.json jika jq tersedia
  if command -v jq &> /dev/null; then
    echo -e "${BLUE}Mengekstrak endpoint dari OpenAPI spec...${NC}"
    OPENAPI_ENDPOINTS=$(jq -r '.paths | keys[]' "$SWAGGER_PATH" | sort)
    
    echo -e "${GREEN}Endpoint terdaftar di OpenAPI spec:${NC}"
    echo "$OPENAPI_ENDPOINTS" | head -10 | sed 's/^/    /'
    if [ $(echo "$OPENAPI_ENDPOINTS" | wc -l) -gt 10 ]; then
      echo -e "    ... (dan $(echo "$OPENAPI_ENDPOINTS" | wc -l | xargs) endpoint lainnya)"
    fi
    
    # Periksa kecocokan dengan endpoint frontend
    echo -e "\n${BLUE}Memeriksa kecocokan dengan endpoint frontend...${NC}"
    for endpoint in $FRONTEND_ENDPOINTS; do
      # Strip /api prefix jika ada untuk mencocokkan dengan format OpenAPI
      if [[ $endpoint == /api* ]]; then
        API_PATH=${endpoint#/api}
      else
        API_PATH=$endpoint
      fi
      
      if echo "$OPENAPI_ENDPOINTS" | grep -q "^$API_PATH$"; then
        echo -e "${GREEN}✓ $endpoint terdokumentasi di OpenAPI${NC}"
      fi
    done
  else
    echo -e "${YELLOW}jq tidak ditemukan. Tidak dapat mengekstrak endpoint dari OpenAPI spec.${NC}"
  fi
else
  echo -e "${YELLOW}File OpenAPI spec tidak ditemukan.${NC}"
fi

# Analisis mendalam untuk endpoint yang penting
echo -e "\n${YELLOW}Analisis mendalam untuk endpoint penting:${NC}"

# Periksa secara khusus endpoint login admin
ADMIN_LOGIN_ENDPOINT="/auth/admin/login"
echo -e "\n${BLUE}Mencari endpoint ${ADMIN_LOGIN_ENDPOINT}...${NC}"

ADMIN_FILES=$(grep -l "admin.*login\|login.*admin" "$BACKEND_DIR/app/infrastructure/http"/*.py "$BACKEND_DIR/app/infrastructure/http"/**/*.py 2>/dev/null)

if [ -n "$ADMIN_FILES" ]; then
  echo -e "${GREEN}File yang mungkin terkait admin login:${NC}"
  for file in $ADMIN_FILES; do
    echo -e "${BLUE}🔍 $file:${NC}"
    grep -n "route.*login\|login.*route\|Blueprint\|url_prefix\|@.*route" "$file" | grep -v "^#" | head -10 | sed 's/^/    /'
  done
fi

# Periksa struktur registrasi blueprint secara keseluruhan
echo -e "\n${BLUE}Struktur registrasi blueprint:${NC}"
BLUEPRINT_REGISTRATION=$(grep -l "register_blueprint" "$BACKEND_DIR/app"/**/*.py)

if [ -n "$BLUEPRINT_REGISTRATION" ]; then
  for file in $BLUEPRINT_REGISTRATION; do
    echo -e "${BLUE}🔍 $file:${NC}"
    grep -n "register_blueprint\|Blueprint\|url_prefix" "$file" | grep -v "^#" | head -15 | sed 's/^/    /'
  done
fi

# Bersihkan file sementara
rm -f "$BLUEPRINT_ANALYSIS"

echo -e "\n${YELLOW}=== Validasi Selesai ===${NC}"
