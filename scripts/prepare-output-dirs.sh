#!/bin/bash

# Script untuk mempersiapkan direktori output untuk swagger dan TypeScript

# Buat direktori output backend jika belum ada
mkdir -p ./backend/.output

# Buat direktori output untuk tipe TypeScript yang dihasilkan
mkdir -p ./frontend/types/generated

# Buat contoh file swagger dasar jika belum ada
if [ ! -f "./backend/.output/swagger.json" ]; then
  echo "Membuat file swagger.json contoh..."
  cat > ./backend/.output/swagger.json << EOF
{
  "openapi": "3.0.2",
  "info": {
    "title": "Hotspot Portal API",
    "description": "API documentation for the Hotspot Portal",
    "version": "1.0.0"
  },
  "paths": {
    "/auth/register": {
      "post": {
        "summary": "Mendaftarkan pengguna baru ke sistem",
        "requestBody": {
          "content": {
            "application/json": {
              "schema": {
                "$ref": "#/components/schemas/UserRegisterRequestSchema"
              }
            }
          }
        },
        "responses": {
          "200": {
            "description": "Pendaftaran berhasil"
          }
        }
      }
    }
  },
  "components": {
    "schemas": {
      "UserRegisterRequestSchema": {
        "type": "object",
        "properties": {
          "phone_number": {
            "type": "string"
          },
          "full_name": {
            "type": "string"
          },
          "blok": {
            "type": "string",
            "nullable": true
          },
          "kamar": {
            "type": "string",
            "nullable": true
          },
          "register_as_komandan": {
            "type": "boolean",
            "default": false
          }
        },
        "required": ["phone_number", "full_name"]
      },
      "AuthErrorResponseSchema": {
        "type": "object",
        "properties": {
          "error": {
            "type": "string"
          },
          "details": {
            "type": "string",
            "nullable": true
          }
        },
        "required": ["error"]
      }
    }
  }
}
EOF
  echo "File contoh swagger.json telah dibuat di ./backend/.output/swagger.json"
fi

echo "Persiapan direktori selesai."
