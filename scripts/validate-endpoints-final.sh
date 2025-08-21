#!/bin/bash
# Final improved version for endpoint validation
# Version 2.0.0

# Warna untuk output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${YELLOW}=== Validasi Konsistensi Endpoint API (Final Version) ===${NC}"

# Direktori base
BASE_DIR=$(dirname "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)")
FRONTEND_DIR="$BASE_DIR/frontend"
BACKEND_DIR="$BASE_DIR/backend"

# File utama yang berisi endpoint
ENDPOINTS_FILE="$FRONTEND_DIR/constants/api-endpoints.ts"

echo -e "\n${YELLOW}Mengekstrak endpoint dari frontend...${NC}"

# Ekstrak endpoint dari constants/api-endpoints.ts dengan pendekatan yang lebih tepat
# Untuk setiap array konstanta yang berisi endpoint
ARRAYS_WITH_ENDPOINTS=$(grep -A30 "export const.*ENDPOINTS" "$ENDPOINTS_FILE" | grep -B30 "\]")
ALL_ENDPOINTS=""

# Ekstrak endpoint dari setiap array, dengan hati-hati menghindari komentar
while read -r line; do
  if [[ "$line" =~ ^[[:space:]]*\'\/[^\']+\'.* ]]; then
    # Ekstrak path saja dari string berquote
    endpoint=$(echo "$line" | grep -o "'/[^']*'" | tr -d "'" | grep -v "^/$")
    # Hanya tambahkan endpoint yang valid (abaikan jika dalam komentar)
    if [[ -n "$endpoint" ]]; then
      ALL_ENDPOINTS="$ALL_ENDPOINTS$endpoint
"
    fi
  fi
done <<< "$ARRAYS_WITH_ENDPOINTS"

# Hapus duplikat dan urutkan
FRONTEND_ENDPOINTS=$(echo "$ALL_ENDPOINTS" | sort | uniq)

# Menampilkan endpoint frontend
echo -e "${GREEN}Daftar endpoint frontend yang terdaftar:${NC}"
echo "$FRONTEND_ENDPOINTS" | sed 's/^/  /'

echo -e "\n${YELLOW}Menganalisis struktur backend dan registrasi blueprint...${NC}"

# Cari file registrasi blueprint
REGISTRATION_FILE="$BACKEND_DIR/app/infrastructure/http/__init__.py"
if [ -f "$REGISTRATION_FILE" ]; then
  echo -e "${BLUE}File registrasi blueprint utama: ${REGISTRATION_FILE#$BASE_DIR/}${NC}"
  
  # Ekstrak semua registrasi blueprint dan prefixes mereka
  BP_REGISTRATIONS=$(grep -n "register_blueprint.*url_prefix" "$REGISTRATION_FILE" | grep -v "^#")
  
  echo -e "\n${GREEN}Registrasi blueprint yang ditemukan:${NC}"
  echo "$BP_REGISTRATIONS" | head -15 | sed 's/^/  /'
  
  # Buat pemetaan blueprint ke prefix
  declare -A BP_PREFIX_MAP
  
  while IFS= read -r line; do
    bp_name=$(echo "$line" | grep -o "register_blueprint([^,]*" | sed -e 's/register_blueprint(//' | tr -d ' ')
    url_prefix=$(echo "$line" | grep -o "url_prefix=['\"][^'\"]*['\"]" | sed -e "s/url_prefix=['\"]//; s/['\"]//g")
    
    if [ -n "$bp_name" ] && [ -n "$url_prefix" ]; then
      BP_PREFIX_MAP["$bp_name"]="$url_prefix"
      echo -e "${BLUE}  Blueprint $bp_name → prefix: $url_prefix${NC}"
    fi
  done <<< "$BP_REGISTRATIONS"
fi

echo -e "\n${YELLOW}Menganalisis definisi blueprint dan route patterns...${NC}"

# Cari semua files yang berisi blueprint dan route patterns
FLASK_FILES=$(find "$BACKEND_DIR" -type f -name "*.py" | xargs grep -l "Blueprint\|@.*route")

# Pemetaan dari nama blueprint ke file
declare -A BP_FILE_MAP
declare -A BP_ROUTE_MAP

# Untuk setiap file, extract blueprint dan route definisinya
for file in $FLASK_FILES; do
  # Pertama, ekstrak nama blueprint (jika ada)
  bp_line=$(grep -o "Blueprint([^)]*)" "$file" | head -1)
  if [ -n "$bp_line" ]; then
    # Extract blueprint name dan variable
    bp_name=$(echo "$bp_line" | sed -e "s/Blueprint(['\"]//; s/['\"],.*//" | tr -d ' ')
    bp_var=$(grep -o "[a-zA-Z0-9_]*[ ]*=[ ]*Blueprint" "$file" | sed -e 's/[ ]*=.*//' | tr -d ' ')
    
    if [ -n "$bp_name" ] && [ -n "$bp_var" ]; then
      BP_FILE_MAP["$bp_var"]="$file"
      
      # Ekstrak URL prefix dari definisi blueprint (jika ada)
      bp_prefix=$(grep -A5 "Blueprint(.*$bp_name" "$file" | grep -o "url_prefix=['\"][^'\"]*['\"]" | head -1)
      bp_prefix_val=$(echo "$bp_prefix" | sed -e "s/url_prefix=['\"]//; s/['\"]//g")
      
      # Jika prefix ditemukan, tambahkan ke peta
      if [ -n "$bp_prefix_val" ]; then
        BP_PREFIX_MAP["$bp_var"]="$bp_prefix_val"
      fi
      
      # Ekstrak route patterns dalam blueprint ini
      while IFS= read -r route_line; do
        route_pattern=$(echo "$route_line" | grep -o "['\"][^'\"]*['\"]" | head -1 | tr -d "'\"")
        if [ -n "$route_pattern" ]; then
          full_route="${BP_PREFIX_MAP[$bp_var]}$route_pattern"
          # Simpan pemetaan route ke file
          BP_ROUTE_MAP["$full_route"]="$file (via blueprint $bp_var)"
        fi
      done < <(grep -o "@.*route.*['\"][^'\"]*['\"]" "$file")
    fi
  fi
  
  # Juga ekstrak route langsung tanpa blueprint
  direct_routes=$(grep -o "@app.route.*['\"][^'\"]*['\"]" "$file")
  if [ -n "$direct_routes" ]; then
    while IFS= read -r route_line; do
      route_pattern=$(echo "$route_line" | grep -o "['\"][^'\"]*['\"]" | head -1 | tr -d "'\"")
      if [ -n "$route_pattern" ]; then
        BP_ROUTE_MAP["$route_pattern"]="$file (direct route)"
      fi
    done <<< "$direct_routes"
  fi
done

echo -e "\n${YELLOW}Memeriksa endpoint frontend di backend...${NC}"

# Inisialisasi array untuk menyimpan status endpoint
declare -A ENDPOINT_STATUS
declare -A ENDPOINT_LOCATION
MISSING_COUNT=0

# Periksa masing-masing endpoint frontend
for endpoint in $FRONTEND_ENDPOINTS; do
  ENDPOINT_STATUS["$endpoint"]="missing"
  
  # Jika endpoint dimulai dengan /api, hapus prefixnya untuk route flask
  if [[ "$endpoint" == /api* ]]; then
    FLASK_ENDPOINT="${endpoint#/api}"
  else
    FLASK_ENDPOINT="$endpoint"
  fi
  
  # Periksa apakah endpoint ada dalam pemetaan route
  for route in "${!BP_ROUTE_MAP[@]}"; do
    # Check exact match, trailing slash variations, or with parameters
    if [[ "$route" == "$FLASK_ENDPOINT" ]] || 
       [[ "$route" == "$FLASK_ENDPOINT/" ]] || 
       [[ "$FLASK_ENDPOINT" == "$route/" ]] || 
       [[ "$route" == "$FLASK_ENDPOINT"/* ]]; then
      ENDPOINT_STATUS["$endpoint"]="found"
      ENDPOINT_LOCATION["$endpoint"]="${BP_ROUTE_MAP[$route]}"
      break
    fi
  done
  
  # Special cases untuk endpoint khusus
  if [[ "$endpoint" == "/auth/admin/login" ]]; then
    ADMIN_LOGIN_FILES=$(grep -l "admin.*login\|login.*admin" $BACKEND_DIR/app/infrastructure/http/auth/*.py)
    if [ -n "$ADMIN_LOGIN_FILES" ]; then
      for file in $ADMIN_LOGIN_FILES; do
        if grep -q "@.*route.*['\"].*admin.*login['\"]" "$file" || grep -q "@.*route.*['\"].*login.*admin['\"]" "$file"; then
          ENDPOINT_STATUS["$endpoint"]="found"
          ENDPOINT_LOCATION["$endpoint"]="$file (special admin login route)"
          break
        fi
      done
    fi
  fi
  
  # Special case untuk refresh-token vs refresh
  if [[ "$endpoint" == "/auth/refresh" ]]; then
    REFRESH_FILES=$(grep -l "refresh.*token\|refresh" $BACKEND_DIR/app/infrastructure/http/auth/*.py)
    if [ -n "$REFRESH_FILES" ]; then
      for file in $REFRESH_FILES; do
        if grep -q "@.*route.*['\"].*refresh['\"]" "$file"; then
          ENDPOINT_STATUS["$endpoint"]="found"
          ENDPOINT_LOCATION["$endpoint"]="$file (refresh endpoint)"
          break
        fi
      done
    fi
  fi
  
  # Hitung endpoint yang hilang
  if [[ "${ENDPOINT_STATUS[$endpoint]}" == "missing" ]]; then
    ((MISSING_COUNT++))
  fi
done

# Hasil validasi
echo -e "\n${YELLOW}Hasil validasi endpoint:${NC}"

# Tampilkan endpoint yang ditemukan
echo -e "\n${GREEN}Endpoint yang ditemukan di backend:${NC}"
for endpoint in $FRONTEND_ENDPOINTS; do
  if [[ "${ENDPOINT_STATUS[$endpoint]}" == "found" ]]; then
    echo -e "${GREEN}✓ $endpoint${NC} - ${BLUE}${ENDPOINT_LOCATION[$endpoint]#$BASE_DIR/}${NC}"
  fi
done

# Tampilkan endpoint yang tidak ditemukan
if [[ $MISSING_COUNT -gt 0 ]]; then
  echo -e "\n${RED}Endpoint yang tidak ditemukan di backend ($MISSING_COUNT endpoints):${NC}"
  for endpoint in $FRONTEND_ENDPOINTS; do
    if [[ "${ENDPOINT_STATUS[$endpoint]}" == "missing" ]]; then
      echo -e "${RED}✗ $endpoint${NC}"
    fi
  done
  
  echo -e "\n${YELLOW}Saran untuk endpoint yang tidak ditemukan:${NC}"
  echo -e "1. Periksa struktur blueprint dan url_prefix dalam registrasi blueprint"
  echo -e "2. Periksa dekorasi route dan penulisan path (gunakan quotes yang konsisten)"
  echo -e "3. Pastikan blueprint diimport dan diregistrasi dengan benar"
  echo -e "4. Periksa juga endpoint yang mungkin menggunakan dinamik parameter"
else
  echo -e "\n${GREEN}Semua endpoint frontend terdaftar di backend! ✓${NC}"
fi

# Deteksi masalah umum dengan /api prefix
echo -e "\n${YELLOW}Menganalisis masalah prefix /api...${NC}"

API_PREFIX_ISSUES=0
for endpoint in $FRONTEND_ENDPOINTS; do
  if [[ "$endpoint" == /api* ]]; then
    flask_endpoint="${endpoint#/api}"
    if grep -q "register_blueprint.*url_prefix.*$flask_endpoint" "$REGISTRATION_FILE"; then
      echo -e "${RED}⚠️ Endpoint $endpoint mungkin terduplikasi karena prefix /api ditambahkan dua kali${NC}"
      ((API_PREFIX_ISSUES++))
    fi
  fi
done

if [[ $API_PREFIX_ISSUES -eq 0 ]]; then
  echo -e "${GREEN}Tidak ada masalah prefix /api yang terdeteksi ✓${NC}"
fi

# Periksa secara khusus endpoint auth/admin/login
ADMIN_LOGIN="/auth/admin/login"
echo -e "\n${YELLOW}Analisis khusus untuk endpoint $ADMIN_LOGIN:${NC}"

# Cek di session_routes.py
SESSION_ROUTES="$BACKEND_DIR/app/infrastructure/http/auth/session_routes.py"
if [ -f "$SESSION_ROUTES" ]; then
  echo -e "${BLUE}Memeriksa file: ${SESSION_ROUTES#$BASE_DIR/}${NC}"
  
  # Cek blueprint definisi dan url_prefix
  BP_DEF=$(grep -n "Blueprint.*session" "$SESSION_ROUTES" | head -1)
  if [ -n "$BP_DEF" ]; then
    echo -e "  ${GREEN}✓ Blueprint didefinisikan:${NC}"
    echo "    $BP_DEF" | sed 's/^/    /'
    
    # Cek URL prefix
    URL_PREFIX=$(grep -n "url_prefix" "$SESSION_ROUTES" | head -1)
    if [ -n "$URL_PREFIX" ]; then
      echo -e "  ${GREEN}✓ URL Prefix didefinisikan:${NC}"
      echo "    $URL_PREFIX" | sed 's/^/    /'
    fi
  fi
  
  # Cek route admin login
  ADMIN_LOGIN_ROUTE=$(grep -n "@.*route.*admin.*login" "$SESSION_ROUTES")
  if [ -n "$ADMIN_LOGIN_ROUTE" ]; then
    echo -e "  ${GREEN}✓ Admin login route ditemukan:${NC}"
    echo "$ADMIN_LOGIN_ROUTE" | sed 's/^/    /'
    
    # Cek implementasi fungsi
    ADMIN_LOGIN_FUNC=$(grep -n -A3 "def admin_login" "$SESSION_ROUTES")
    if [ -n "$ADMIN_LOGIN_FUNC" ]; then
      echo -e "  ${GREEN}✓ Implementasi admin_login function:${NC}"
      echo "$ADMIN_LOGIN_FUNC" | sed 's/^/    /'
    fi
  else
    echo -e "  ${RED}✗ Admin login route tidak ditemukan di session_routes.py${NC}"
  fi
  
  # Tampilkan bagaimana route ini diregistrasi di __init__.py
  SESSION_BP_REG=$(grep -n "register_blueprint.*session_bp" "$REGISTRATION_FILE")
  if [ -n "$SESSION_BP_REG" ]; then
    echo -e "  ${GREEN}✓ Registrasi session blueprint:${NC}"
    echo "    $SESSION_BP_REG" | sed 's/^/    /'
  else
    echo -e "  ${RED}✗ Session blueprint tidak diregistrasi di __init__.py${NC}"
  fi
fi

echo -e "\n${YELLOW}=== Validasi Selesai ===${NC}"
