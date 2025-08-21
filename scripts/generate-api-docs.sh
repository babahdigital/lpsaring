#!/bin/bash
# Documentation generator for API endpoints
# This script generates Markdown documentation for API endpoints

# Warna untuk output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${YELLOW}=== Generating API Endpoint Documentation ===${NC}"

# Direktori base
BASE_DIR=$(dirname "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)")
FRONTEND_DIR="$BASE_DIR/frontend"
BACKEND_DIR="$BASE_DIR/backend"
DOCS_DIR="$BASE_DIR/docs"

# Make sure docs directory exists
mkdir -p "$DOCS_DIR"

# Output file
OUTPUT_FILE="$DOCS_DIR/API_ENDPOINTS.md"

# File utama yang berisi endpoint
ENDPOINTS_FILE="$FRONTEND_DIR/constants/api-endpoints.ts"

echo -e "\n${YELLOW}Mengekstrak endpoint dari frontend...${NC}"

# Ekstrak endpoint dari constants/api-endpoints.ts dengan kategori
# Hanya ambil baris yang memiliki endpoint dan hindari komentar
SENSITIVE_ENDPOINTS=$(grep -A20 "SENSITIVE_ENDPOINTS" "$ENDPOINTS_FILE" | grep "^[[:space:]]*'/[^']*'" | grep -o "'/[^']*'" | tr -d "'" | grep -v "^/$")
AUTH_ENDPOINTS=$(grep -A10 "AUTH_ENDPOINTS" "$ENDPOINTS_FILE" | grep "^[[:space:]]*'/[^']*'" | grep -o "'/[^']*'" | tr -d "'" | grep -v "^/$")
CIRCUIT_BREAKER_EXCLUDED=$(grep -A10 "CIRCUIT_BREAKER_EXCLUDED" "$ENDPOINTS_FILE" | grep "^[[:space:]]*'/[^']*'" | grep -o "'/[^']*'" | tr -d "'" | grep -v "^/$")

# Get all endpoint categories
ALL_ENDPOINTS=$(cat <<EOF
$SENSITIVE_ENDPOINTS
$AUTH_ENDPOINTS
$CIRCUIT_BREAKER_EXCLUDED
EOF
)

# Sort and uniquify endpoints
UNIQUE_ENDPOINTS=$(echo "$ALL_ENDPOINTS" | sort | uniq)

# Generate documentation header
cat > "$OUTPUT_FILE" <<EOF
# API Endpoints Documentation

This document provides a comprehensive list of API endpoints used in the Hotspot Portal application.
It includes endpoint URLs, their purpose, and implementation details.

> **Generated:** $(date)

## Table of Contents

1. [Authentication Endpoints](#authentication-endpoints)
2. [Device Management Endpoints](#device-management-endpoints)
3. [Client Detection Endpoints](#client-detection-endpoints)
4. [Administrative Endpoints](#administrative-endpoints)
5. [Utility Endpoints](#utility-endpoints)

---

EOF

# Analyze backend implementation
echo -e "${YELLOW}Analyzing backend implementation...${NC}"

# Mencari semua session blueprint routes
SESSION_ROUTES=$(grep -n "@session_bp.route" "$BACKEND_DIR/app/infrastructure/http/auth/session_routes.py")
DEVICE_ROUTES=$(grep -n "@device_bp.route" "$BACKEND_DIR/app/infrastructure/http/auth/device_routes.py")
PUBLIC_AUTH_ROUTES=$(grep -n "@public_auth_bp.route" "$BACKEND_DIR/app/infrastructure/http/auth/public_auth_routes.py")
UTILITY_ROUTES=$(grep -n "@utility_bp.route" "$BACKEND_DIR/app/infrastructure/http/auth/utility_routes.py")

# Generate documentation sections
cat >> "$OUTPUT_FILE" <<EOF
## Authentication Endpoints

| Endpoint | Methods | Purpose | Implementation |
|----------|---------|---------|----------------|
EOF

# Process AUTH_ENDPOINTS
for endpoint in $AUTH_ENDPOINTS; do
  # Extract endpoint path without prefix
  endpoint_path=${endpoint#/auth}
  
  # Find implementation details
  if echo "$SESSION_ROUTES" | grep -q "$endpoint_path"; then
    line_number=$(echo "$SESSION_ROUTES" | grep "$endpoint_path" | cut -d ':' -f1)
    implementation_file="session_routes.py:$line_number"
    method=$(echo "$SESSION_ROUTES" | grep "$endpoint_path" | grep -o "methods=\[[^]]*\]" | sed 's/methods=//')
  elif echo "$PUBLIC_AUTH_ROUTES" | grep -q "$endpoint_path"; then
    line_number=$(echo "$PUBLIC_AUTH_ROUTES" | grep "$endpoint_path" | cut -d ':' -f1)
    implementation_file="public_auth_routes.py:$line_number"
    method=$(echo "$PUBLIC_AUTH_ROUTES" | grep "$endpoint_path" | grep -o "methods=\[[^]]*\]" | sed 's/methods=//')
  else
    implementation_file="Unknown"
    method="Unknown"
  fi
  
  # Determine purpose based on endpoint name
  if [[ "$endpoint" == */login ]]; then
    purpose="Authenticates users"
  elif [[ "$endpoint" == */logout ]]; then
    purpose="Logs out users"
  elif [[ "$endpoint" == */refresh ]]; then
    purpose="Refreshes auth tokens"
  elif [[ "$endpoint" == */register ]]; then
    purpose="Registers new users"
  elif [[ "$endpoint" == */verify-otp ]]; then
    purpose="Verifies OTP codes"
  elif [[ "$endpoint" == */verify-role ]]; then
    purpose="Verifies user roles"
  else
    purpose="Authentication operation"
  fi
  
  echo "| \`$endpoint\` | $method | $purpose | \`$implementation_file\` |" >> "$OUTPUT_FILE"
done

# Device Management Endpoints section
cat >> "$OUTPUT_FILE" <<EOF

## Device Management Endpoints

| Endpoint | Methods | Purpose | Implementation |
|----------|---------|---------|----------------|
EOF

# Process Device endpoints
for endpoint in $UNIQUE_ENDPOINTS; do
  if [[ "$endpoint" == */device* ]]; then
    # Extract endpoint path without prefix
    endpoint_path=${endpoint#/auth}
    
    # Find implementation details
    if echo "$DEVICE_ROUTES" | grep -q "$endpoint_path"; then
      line_number=$(echo "$DEVICE_ROUTES" | grep "$endpoint_path" | cut -d ':' -f1)
      implementation_file="device_routes.py:$line_number"
      method=$(echo "$DEVICE_ROUTES" | grep "$endpoint_path" | grep -o "methods=\[[^]]*\]" | sed 's/methods=//')
    else
      implementation_file="Unknown"
      method="Unknown"
    fi
    
    # Determine purpose based on endpoint name
    if [[ "$endpoint" == */authorize-device ]]; then
      purpose="Authorizes a device"
    elif [[ "$endpoint" == */reject-device ]]; then
      purpose="Rejects device authorization"
    elif [[ "$endpoint" == */invalidate-device ]]; then
      purpose="Invalidates device access"
    elif [[ "$endpoint" == */sync-device ]]; then
      purpose="Syncs device information"
    else
      purpose="Device management operation"
    fi
    
    echo "| \`$endpoint\` | $method | $purpose | \`$implementation_file\` |" >> "$OUTPUT_FILE"
  fi
done

# Client Detection Endpoints section
cat >> "$OUTPUT_FILE" <<EOF

## Client Detection Endpoints

| Endpoint | Methods | Purpose | Implementation |
|----------|---------|---------|----------------|
EOF

# Process Client Detection endpoints
for endpoint in $UNIQUE_ENDPOINTS; do
  if [[ "$endpoint" == */detect* ]] || [[ "$endpoint" == */check* ]]; then
    # Extract endpoint path without prefix
    endpoint_path=${endpoint#/auth}
    
    # Find implementation details
    if echo "$DEVICE_ROUTES" | grep -q "$endpoint_path"; then
      line_number=$(echo "$DEVICE_ROUTES" | grep "$endpoint_path" | cut -d ':' -f1)
      implementation_file="device_routes.py:$line_number"
      method=$(echo "$DEVICE_ROUTES" | grep "$endpoint_path" | grep -o "methods=\[[^]]*\]" | sed 's/methods=//')
    else
      implementation_file="Unknown"
      method="Unknown"
    fi
    
    # Determine purpose based on endpoint name
    if [[ "$endpoint" == */detect-client-info ]]; then
      purpose="Detects client IP and MAC"
    elif [[ "$endpoint" == */check-device-status ]]; then
      purpose="Checks device status"
    elif [[ "$endpoint" == */check-token-device ]]; then
      purpose="Validates token and device"
    else
      purpose="Client detection operation"
    fi
    
    echo "| \`$endpoint\` | $method | $purpose | \`$implementation_file\` |" >> "$OUTPUT_FILE"
  fi
done

# Administrative Endpoints section
cat >> "$OUTPUT_FILE" <<EOF

## Administrative Endpoints

| Endpoint | Methods | Purpose | Implementation |
|----------|---------|---------|----------------|
EOF

# Process Admin endpoints
for endpoint in $UNIQUE_ENDPOINTS; do
  if [[ "$endpoint" == */admin* ]]; then
    # Extract endpoint path without prefix
    endpoint_path=${endpoint#/auth}
    
    # Find implementation details
    if echo "$SESSION_ROUTES" | grep -q "$endpoint_path"; then
      line_number=$(echo "$SESSION_ROUTES" | grep "$endpoint_path" | cut -d ':' -f1)
      implementation_file="session_routes.py:$line_number"
      method=$(echo "$SESSION_ROUTES" | grep "$endpoint_path" | grep -o "methods=\[[^]]*\]" | sed 's/methods=//')
    else
      implementation_file="Unknown"
      method="Unknown"
    fi
    
    # Determine purpose based on endpoint name
    if [[ "$endpoint" == */admin/login ]]; then
      purpose="Admin authentication"
    else
      purpose="Administrative operation"
    fi
    
    echo "| \`$endpoint\` | $method | $purpose | \`$implementation_file\` |" >> "$OUTPUT_FILE"
  fi
done

# Utility Endpoints section
cat >> "$OUTPUT_FILE" <<EOF

## Utility Endpoints

| Endpoint | Methods | Purpose | Implementation |
|----------|---------|---------|----------------|
EOF

# Process Utility endpoints
for endpoint in $UNIQUE_ENDPOINTS; do
  if [[ "$endpoint" == */clear* ]] || [[ "$endpoint" == */session-stats* ]]; then
    # Extract endpoint path without prefix
    endpoint_path=${endpoint#/auth}
    
    # Find implementation details
    if echo "$UTILITY_ROUTES" | grep -q "$endpoint_path"; then
      line_number=$(echo "$UTILITY_ROUTES" | grep "$endpoint_path" | cut -d ':' -f1)
      implementation_file="utility_routes.py:$line_number"
      method=$(echo "$UTILITY_ROUTES" | grep "$endpoint_path" | grep -o "methods=\[[^]]*\]" | sed 's/methods=//')
    else
      implementation_file="Unknown"
      method="Unknown"
    fi
    
    # Determine purpose based on endpoint name
    if [[ "$endpoint" == */clear-cache ]]; then
      purpose="Clears API caches"
    elif [[ "$endpoint" == */session-stats ]]; then
      purpose="Provides session statistics"
    else
      purpose="Utility operation"
    fi
    
    echo "| \`$endpoint\` | $method | $purpose | \`$implementation_file\` |" >> "$OUTPUT_FILE"
  fi
done

# Add footnote
cat >> "$OUTPUT_FILE" <<EOF

---

## Notes

* All endpoints under \`/auth/*\` are registered with the \`/api\` prefix in the application
* Blueprint registration is handled in \`backend/app/infrastructure/http/__init__.py\`
* Authentication endpoints use JWT tokens and HttpOnly cookies for refresh tokens
* Some endpoints have rate limiting applied to prevent abuse

*Documentation generated automatically by \`generate-api-docs.sh\`*
EOF

echo -e "${GREEN}API Endpoint documentation generated: ${OUTPUT_FILE#$BASE_DIR/}${NC}"
