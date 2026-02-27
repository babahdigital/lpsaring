# backend/app/infrastructure/http/schemas/auth_schemas.py
from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Optional, List, Dict, Any
import uuid

# Impor fungsi normalisasi dari helper terpusat
from app.utils.formatters import normalize_to_e164

TAMPING_TYPES = [
    "Tamping luar",
    "Tamping AO",
    "Tamping Pembinaan",
    "Tamping kunjungan",
    "Tamping kamtib",
    "Tamping kunci",
    "Tamping klinik",
    "Tamping dapur",
    "Tamping mesjid",
    "Tamping p2u",
    "Tamping BLK",
    "Tamping kebersihan",
    "Tamping Humas",
    "Tamping kebun",
]


# Validator yang sekarang memanggil helper
def validate_phone_number(v: str) -> str:
    """Fungsi validator yang dipanggil oleh Pydantic."""
    if not v:
        raise ValueError("Nomor telepon tidak boleh kosong.")
    try:
        # Normalisasi ke format E.164 (mendukung +<kodeNegara>...)
        return normalize_to_e164(v)
    except ValueError as e:
        # Teruskan pesan error dari normalizer
        raise ValueError(str(e))


class RequestOtpRequestSchema(BaseModel):
    """Skema untuk permintaan OTP."""

    phone_number: str
    _normalize_phone = field_validator("phone_number", mode="before")(validate_phone_number)


class VerifyOtpRequestSchema(BaseModel):
    """Skema untuk verifikasi OTP."""

    phone_number: str
    otp: str = Field(..., min_length=6, max_length=6)
    client_ip: Optional[str] = None
    client_mac: Optional[str] = None
    hotspot_login_context: Optional[bool] = None
    confirm_device_takeover: Optional[bool] = None
    _normalize_phone = field_validator("phone_number", mode="before")(validate_phone_number)


class UserRegisterRequestSchema(BaseModel):
    """Skema untuk registrasi pengguna baru, sekarang mendukung Komandan."""

    phone_number: str
    full_name: str = Field(..., min_length=2)
    blok: Optional[str] = None  # Dijadikan opsional
    kamar: Optional[str] = None  # Dijadikan opsional
    is_tamping: bool = Field(False, description="True jika pengguna tamping")
    tamping_type: Optional[str] = Field(None, description="Jenis tamping jika is_tamping True")
    register_as_komandan: bool = Field(False, description="Tandai True untuk mendaftar sebagai Komandan")

    _normalize_phone = field_validator("phone_number", mode="before")(validate_phone_number)

    @model_validator(mode="after")
    def check_address_for_user_role(self) -> "UserRegisterRequestSchema":
        """
        Validator untuk memastikan 'blok' dan 'kamar' wajib diisi
        HANYA jika pengguna mendaftar sebagai USER biasa.
        """
        if not self.register_as_komandan:
            if self.is_tamping:
                if not self.tamping_type:
                    raise ValueError("Jenis tamping wajib dipilih untuk pengguna tamping.")
                if self.tamping_type not in TAMPING_TYPES:
                    raise ValueError("Jenis tamping tidak valid.")
                if self.blok or self.kamar:
                    raise ValueError("Blok dan Kamar tidak boleh diisi untuk pengguna tamping.")
            else:
                if not self.blok or not self.kamar:
                    raise ValueError("Blok dan Kamar wajib diisi untuk pendaftaran pengguna biasa.")
        return self


class RequestOtpResponseSchema(BaseModel):
    """Skema respons setelah OTP berhasil dikirim."""

    message: str = "Kode OTP telah dikirim ke nomor WhatsApp Anda."


class VerifyOtpResponseSchema(BaseModel):
    """Skema respons setelah login berhasil."""

    access_token: str
    token_type: str = "bearer"
    hotspot_username: Optional[str] = None
    hotspot_password: Optional[str] = None
    session_token: Optional[str] = None
    session_url: Optional[str] = None
    hotspot_login_required: Optional[bool] = None
    hotspot_session_active: Optional[bool] = None


class SessionTokenRequestSchema(BaseModel):
    """Skema untuk pertukaran one-time session token."""

    token: str = Field(..., min_length=16)


class AuthErrorResponseSchema(BaseModel):
    """Skema standar untuk respons error."""

    error: str
    details: Optional[List[Dict[str, Any]] | str] = None
    status: Optional[str] = None
    status_token: Optional[str] = None


class StatusTokenVerifyRequestSchema(BaseModel):
    """Skema untuk memverifikasi token halaman status."""

    status: str
    token: str


class UserRegisterResponseSchema(BaseModel):
    """Skema respons setelah registrasi berhasil."""

    message: str
    user_id: uuid.UUID
    phone_number: str


class ChangePasswordRequestSchema(BaseModel):
    """Skema untuk permintaan perubahan password."""

    current_password: str = Field(..., min_length=6)
    new_password: str = Field(..., min_length=6)
