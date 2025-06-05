# backend/app/infrastructure/http/schemas/auth_schemas.py
# Versi: Penyesuaian 'kamar' menjadi wajib untuk registrasi pengguna biasa.

from pydantic import BaseModel, Field, validator
import re
import uuid
from typing import Optional, List, Dict, Any
import enum

try:
    from app.infrastructure.db.models import UserBlok, UserKamar
except ImportError:
    print("WARNING: Gagal mengimpor UserBlok atau UserKamar dari models.py di auth_schemas.py. Menggunakan placeholder.")
    class UserBlok(str, enum.Enum):
        A="A"; B="B"; C="C"; D="D"; E="E"; F="F"
    class UserKamar(str, enum.Enum):
        Kamar_1 = "1"; Kamar_2 = "2"; Kamar_3 = "3"; Kamar_4 = "4"; Kamar_5 = "5"; Kamar_6 = "6"

def validate_phone_number(phone: str) -> str:
    if not phone: raise ValueError("Nomor telepon tidak boleh kosong.")
    cleaned_phone = re.sub(r"[^\d+]", "", phone).strip()
    
    if cleaned_phone.startswith('08'):
        formatted_phone = '+62' + cleaned_phone[1:]
    elif cleaned_phone.startswith('628'):
        formatted_phone = '+' + cleaned_phone if not cleaned_phone.startswith('+') else cleaned_phone
    elif cleaned_phone.startswith('+628'):
        formatted_phone = cleaned_phone
    elif cleaned_phone.startswith('8') and len(cleaned_phone) >= 8:
        formatted_phone = '+62' + cleaned_phone
    else:
        raise ValueError("Format nomor telepon tidak valid (awalan 08..., 628..., atau +628...).")
    
    if not (11 <= len(formatted_phone) <= 15):
        raise ValueError(f"Panjang nomor telepon tidak valid setelah normalisasi ({len(formatted_phone)} digit). Seharusnya antara 11-15 digit termasuk +62.")
    return formatted_phone

class UserRegisterRequestSchema(BaseModel):
    phone_number: str = Field(..., description="Nomor telepon pengguna (format 08... atau +628...)")
    full_name: str = Field(..., min_length=2, max_length=100, description="Nama Lengkap Pengguna")
    blok: UserBlok = Field(..., description="Blok tempat tinggal pengguna (wajib)") # Tetap wajib
    kamar: UserKamar = Field(..., description="Nomor kamar pengguna (wajib)") # PERUBAHAN: Menjadi wajib

    _validate_phone_number = validator('phone_number', pre=True, allow_reuse=True)(validate_phone_number)

class UserRegisterResponseSchema(BaseModel):
    message: str = Field(..., example="Registrasi berhasil. Akun Anda sedang menunggu persetujuan Admin.")
    user_id: Optional[uuid.UUID] = None
    phone_number: Optional[str] = None

class RequestOtpRequestSchema(BaseModel):
    phone_number: str = Field(..., description="Nomor telepon (format 08... atau +628...)")
    _validate_phone_number = validator('phone_number', pre=True, allow_reuse=True)(validate_phone_number)

class VerifyOtpRequestSchema(BaseModel):
    phone_number: str = Field(..., description="Nomor telepon (format +628...)")
    otp: str = Field(..., min_length=6, max_length=6, description="Kode OTP 6 digit")

    @validator('phone_number', pre=True, always=True)
    def check_and_format_phone_verify(cls, v):
        try:
            formatted = validate_phone_number(v)
            return formatted
        except ValueError as e:
            raise ValueError(str(e)) from e

    @validator('otp')
    def check_otp_format(cls, v):
        if not v.isdigit() or len(v) != 6:
             raise ValueError("Kode OTP harus berupa 6 digit angka.")
        return v

class RequestOtpResponseSchema(BaseModel):
    message: str = "OTP telah dikirim ke nomor telepon Anda."

class VerifyOtpResponseSchema(BaseModel):
    access_token: str = Field(..., description="Token JWT untuk akses")
    token_type: str = "bearer"

class AuthErrorResponseSchema(BaseModel):
    error: str = Field(..., description="Deskripsi error")
    details: Optional[List[Dict[str, Any]]] = None

class UserResponseSchemaPlaceholder(BaseModel):
    id: uuid.UUID
    phone_number: str
    full_name: Optional[str] = None
    is_active: bool
    class Config:
        from_attributes = True
        use_enum_values = True