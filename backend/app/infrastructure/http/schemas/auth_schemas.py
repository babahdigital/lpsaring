# backend/app/infrastructure/http/schemas/auth_schemas.py
from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Optional, List, Dict, Any
import uuid

# Impor fungsi normalisasi dari helper terpusat
from app.utils.formatters import normalize_to_e164

# Validator yang sekarang memanggil helper
def validate_phone_number(v: str) -> str:
    """Fungsi validator yang dipanggil oleh Pydantic."""
    if not v:
        raise ValueError("Nomor telepon tidak boleh kosong.")
    try:
        # PANGGIL FUNGSI DENGAN NAMA YANG BENAR: normalize_to_e164
        return normalize_to_e164(v)
    except ValueError as e:
        # Teruskan pesan error dari normalizer
        raise ValueError(str(e))

class RequestOtpRequestSchema(BaseModel):
    """Skema untuk permintaan OTP."""
    phone_number: str
    _normalize_phone = field_validator('phone_number', mode='before')(validate_phone_number)

class VerifyOtpRequestSchema(BaseModel):
    """Skema untuk verifikasi OTP."""
    phone_number: str
    otp: str = Field(..., min_length=6, max_length=6)
    _normalize_phone = field_validator('phone_number', mode='before')(validate_phone_number)

class UserRegisterRequestSchema(BaseModel):
    """Skema untuk registrasi pengguna baru, sekarang mendukung Komandan."""
    phone_number: str
    full_name: str = Field(..., min_length=2)
    blok: Optional[str] = None  # Dijadikan opsional
    kamar: Optional[str] = None # Dijadikan opsional
    register_as_komandan: bool = Field(False, description="Tandai True untuk mendaftar sebagai Komandan")
    
    _normalize_phone = field_validator('phone_number', mode='before')(validate_phone_number)

    @model_validator(mode='after')
    def check_address_for_user_role(self) -> 'UserRegisterRequestSchema':
        """
        Validator untuk memastikan 'blok' dan 'kamar' wajib diisi
        HANYA jika pengguna mendaftar sebagai USER biasa.
        """
        if not self.register_as_komandan and (not self.blok or not self.kamar):
            raise ValueError("Blok dan Kamar wajib diisi untuk pendaftaran pengguna biasa.")
        return self

class RequestOtpResponseSchema(BaseModel):
    """Skema respons setelah OTP berhasil dikirim."""
    message: str = "Kode OTP telah dikirim ke nomor WhatsApp Anda."

class VerifyOtpResponseSchema(BaseModel):
    """Skema respons setelah login berhasil."""
    access_token: str
    token_type: str = "bearer"

class AuthErrorResponseSchema(BaseModel):
    """Skema standar untuk respons error."""
    error: str
    details: Optional[List[Dict[str, Any]] | str] = None

class UserRegisterResponseSchema(BaseModel):
    """Skema respons setelah registrasi berhasil."""
    message: str
    user_id: uuid.UUID
    phone_number: str

class ChangePasswordRequestSchema(BaseModel):
    """Skema untuk permintaan perubahan password."""
    current_password: str = Field(..., min_length=6)
    new_password: str = Field(..., min_length=6)