# backend/app/infrastructure/http/schemas/auth_schemas.py

from pydantic import BaseModel, Field, field_validator, model_validator, ConfigDict
from typing import Optional, List, Dict, Any
import uuid

from app.utils.formatters import normalize_to_e164

# Fungsi validator ini sudah bagus, tidak perlu diubah.
def validate_phone_number(v: str) -> str:
    if not v:
        raise ValueError("Nomor telepon tidak boleh kosong.")
    try:
        return normalize_to_e164(v)
    except ValueError as e:
        raise ValueError(str(e))

# Skema ini tidak perlu diubah.
class RequestOtpRequestSchema(BaseModel):
    phone_number: str
    _normalize_phone = field_validator('phone_number', mode='before')(validate_phone_number)

# --- PERBAIKAN UTAMA ---
class VerifyOtpRequestSchema(BaseModel):
    """
    Skema untuk verifikasi OTP.
    Field client_ip dan client_mac telah dihapus karena backend akan mendeteksinya secara otomatis
    untuk memastikan data selalu akurat dan real-time.
    """
    phone_number: str
    otp: str = Field(..., min_length=6, max_length=6)
    
    # DIHAPUS: client_ip tidak lagi diperlukan dari payload.
    # client_ip: Optional[str] = Field(None, description="IP Address lokal pengguna dari captive portal.")
    
    # DIHAPUS: client_mac tidak lagi diperlukan dari payload.
    # client_mac: Optional[str] = Field(None, description="MAC Address lokal pengguna dari captive portal.")
    
    _normalize_phone = field_validator('phone_number', mode='before')(validate_phone_number)

# Skema ini tidak perlu diubah.
class UserRegisterRequestSchema(BaseModel):
    phone_number: str
    full_name: str = Field(..., min_length=2)
    blok: Optional[str] = None
    kamar: Optional[str] = None
    register_as_komandan: bool = Field(False, description="Tandai True untuk mendaftar sebagai Komandan")
    
    _normalize_phone = field_validator('phone_number', mode='before')(validate_phone_number)

    @model_validator(mode='after')
    def check_address_for_user_role(self) -> 'UserRegisterRequestSchema':
        if not self.register_as_komandan and (not self.blok or not self.kamar):
            raise ValueError("Blok dan Kamar wajib diisi untuk pendaftaran pengguna biasa.")
        return self

# --- PENYEMPURNAAN: Skema User untuk Respons API ---
class UserSchema(BaseModel):
    id: uuid.UUID
    phone_number: str
    full_name: str
    role: str
    is_active: bool
    is_blocked: bool
    is_quota_finished: bool
    # Tambahkan field lain yang relevan yang Anda kirim ke frontend
    
    model_config = ConfigDict(from_attributes=True)

# Skema ini tidak perlu diubah.
class RequestOtpResponseSchema(BaseModel):
    message: str = "Kode OTP telah dikirim ke nomor WhatsApp Anda."

# --- PENYEMPURNAAN: Menggunakan UserSchema yang lebih spesifik ---
class VerifyOtpResponseSchema(BaseModel):
    access_token: str
    token_type: str = "bearer"
    token: Optional[str] = None
    user: UserSchema # Menggantikan 'Any' dengan skema yang jelas

# Skema lain di bawah ini sudah bagus.
class AuthErrorResponseSchema(BaseModel):
    error: str
    details: Optional[List[Dict[str, Any]] | str] = None

class UserRegisterResponseSchema(BaseModel):
    message: str
    user_id: uuid.UUID
    phone_number: str

class ChangePasswordRequestSchema(BaseModel):
    current_password: str = Field(..., min_length=6)
    new_password: str = Field(..., min_length=6)