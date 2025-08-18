# backend/app/infrastructure/http/schemas/user_schemas.py
# VERSI FINAL: Penyempurnaan logika is_quota_finished untuk menangani masa aktif.
# pyright: reportCallIssue=false, reportAttributeAccessIssue=false, reportArgumentType=false

import uuid
import re
import enum
from pydantic import (
    BaseModel, Field, field_validator, model_validator, ConfigDict, computed_field
)
from typing import Optional, List, Any
from datetime import datetime, date, time

# Impor Enum dari models.py
from app.infrastructure.db.models import UserRole, ApprovalStatus, UserBlok, UserKamar
# Impor model 'User' untuk digunakan dalam 'isinstance'
from app.infrastructure.db.models import User
# Impor formatter terpusat
from app.utils.formatters import normalize_to_e164, format_to_local_phone

# --- Helper Validator Terpusat ---
def validate_indonesian_phone_number(v: Any) -> str:
    if not isinstance(v, str):
        if v is None:
            raise TypeError("Nomor telepon tidak boleh kosong.")
        raise TypeError(f"Input nomor telepon harus berupa string, bukan {type(v)}")
    
    try:
        return normalize_to_e164(v)
    except ValueError as e:
        raise ValueError(str(e))

# --- Skema Dasar & Umum ---
class UserBaseSchema(BaseModel):
    phone_number: str = Field(...)
    full_name: str = Field(..., min_length=2, max_length=100)
    blok: Optional[str] = Field(None)
    kamar: Optional[str] = Field(None)

    @field_validator('phone_number', mode='before')
    @classmethod
    def validate_phone(cls, v: Any) -> str:
        return validate_indonesian_phone_number(v)

    @field_validator('full_name', mode='before')
    @classmethod
    def validate_full_name(cls, v: Any) -> str:
        if v is None: raise ValueError('Nama Lengkap tidak boleh kosong.')
        if isinstance(v, str):
            stripped_v = v.strip()
            if len(stripped_v) < 2: raise ValueError('Nama Lengkap minimal 2 karakter.')
            return stripped_v
        raise TypeError('Nama Lengkap harus berupa string.')

    @field_validator('blok', mode='before')
    @classmethod
    def validate_blok_input(cls, v: Any) -> Optional[str]:
        if v is None or v == '': return None
        if isinstance(v, enum.Enum): v = v.value
        if isinstance(v, str):
            v_upper = v.upper()
            allowed_values = {b.value for b in UserBlok}
            if v_upper in allowed_values: return v_upper
            raise ValueError(f"Blok '{v}' tidak valid. Pilihan: {list(allowed_values)}")
        raise TypeError('Input untuk Blok harus berupa string atau Enum yang valid.')

    @field_validator('kamar', mode='before')
    @classmethod
    def validate_kamar_input(cls, v: Any) -> Optional[str]:
        if v is None or v == '': return None
        if isinstance(v, enum.Enum): v = v.value
        if isinstance(v, str):
            if v.isdigit() and 1 <= int(v) <= 6: return f"Kamar_{v}"
            allowed_values = {k.value for k in UserKamar}
            if v in allowed_values: return v
            raise ValueError(f"Kamar '{v}' tidak valid. Pilihan: {list(allowed_values)} atau angka 1-6.")
        raise TypeError('Input untuk Kamar harus berupa string atau Enum yang valid.')

# --- Skema untuk Endpoint Admin ---
class UserCreateByAdminSchema(UserBaseSchema):
    role: UserRole = Field(...)

    @model_validator(mode='after')
    def check_blok_kamar_for_user_role(self) -> 'UserCreateByAdminSchema':
        if self.role == UserRole.USER and (self.blok is None or self.kamar is None):
            raise ValueError("Blok dan Kamar wajib diisi untuk pengguna biasa.")
        if self.role == UserRole.SUPER_ADMIN:
            raise ValueError('Peran Super Admin tidak dapat dibuat melalui API ini.')
        return self

class UserUpdateByAdminSchema(BaseModel):
    full_name: Optional[str] = Field(None, min_length=2, max_length=100)
    blok: Optional[UserBlok] = None
    kamar: Optional[UserKamar] = None
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None
    is_unlimited_user: Optional[bool] = None
    add_gb: Optional[float] = Field(None, ge=0.0, description="Kuota yang akan ditambahkan dalam Gigabyte. Akan dikonversi ke MB di backend.")
    add_days: Optional[int] = Field(None, ge=0)

    @field_validator('blok', 'kamar', mode='before')
    @classmethod
    def validate_alamat(cls, v: Any) -> Optional[str]:
        if v is None or v == '': return None
        if isinstance(v, enum.Enum): v = v.value
        if isinstance(v, str): return v
        raise TypeError('Input alamat harus string.')

# --- Skema untuk Endpoint Publik & User ---
class PhoneCheckRequest(BaseModel):
    phone_number: str
    full_name: Optional[str] = None
    _validate_phone = field_validator('phone_number', mode='before')(validate_indonesian_phone_number)

class PhoneCheckResponse(BaseModel):
    user_exists: bool
    user_id: Optional[uuid.UUID] = None
    message: Optional[str] = None

class WhatsappValidationRequest(BaseModel):
    phone_number: str
    _validate_phone = field_validator('phone_number', mode='before')(validate_indonesian_phone_number)

class UserProfileUpdateRequestSchema(BaseModel):
    full_name: str = Field(..., min_length=2)
    blok: str
    kamar: str

    @field_validator('blok', 'kamar', mode='before')
    @classmethod
    def check_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Field tidak boleh kosong.")
        return v

# --- Skema untuk Respons API ---
class UserResponseSchema(UserBaseSchema):
    id: uuid.UUID
    role: UserRole
    approval_status: ApprovalStatus
    is_active: bool
    is_blocked: bool
    total_quota_purchased_mb: int
    total_quota_used_mb: float
    is_unlimited_user: bool
    quota_expiry_date: Optional[datetime]
    device_brand: Optional[str]
    device_model: Optional[str]
    created_at: datetime
    updated_at: datetime
    approved_at: Optional[datetime]
    last_login_at: Optional[datetime]

    @computed_field
    @property
    def is_quota_finished(self) -> bool:
        """
        Menentukan apakah kuota pengguna habis atau masa aktifnya berakhir.
        Dihitung setiap kali data pengguna diserialisasi.
        """
        if self.is_unlimited_user:
            return False

        # 1. Cek berdasarkan penggunaan kuota
        purchased = float(self.total_quota_purchased_mb or 0)
        used = float(self.total_quota_used_mb or 0)
        is_out_of_quota = (purchased > 0) and (used >= purchased)

        # 2. Cek berdasarkan tanggal kedaluwarsa
        is_expired = False
        if self.quota_expiry_date:
            # [PENYEMPURNAAN] Bandingkan tanggal saja, abaikan waktu, untuk konsistensi.
            # Jika masa aktif habis hari ini, maka besok baru dianggap expired.
            if self.quota_expiry_date.date() < date.today():
                is_expired = True
            
        return is_out_of_quota or is_expired

    model_config = ConfigDict(from_attributes=True, json_schema_extra={
        "examples": [{
            "id": "00000000-0000-0000-0000-000000000000",
            "phone_number": "+6281234567890",
            "full_name": "Nama Lengkap Pengguna",
            "blok": "A",
            "kamar": "Kamar_1"
        }]
    })

class UserQuotaResponse(BaseModel):
    total_quota_purchased_mb: int
    total_quota_used_mb: int
    remaining_mb: int
    hotspot_username: str
    last_sync_time: datetime
    is_unlimited_user: bool
    quota_expiry_date: Optional[datetime]

    @model_validator(mode='before')
    @classmethod
    def calculate_and_format(cls, data):
        if isinstance(data, User):
            purchased = int(data.total_quota_purchased_mb or 0)
            used = int(data.total_quota_used_mb or 0)
            new_data = {
                'total_quota_purchased_mb': purchased,
                'total_quota_used_mb': used,
                'remaining_mb': max(0, purchased - used),
                'hotspot_username': format_to_local_phone(data.phone_number),
                'is_unlimited_user': data.is_unlimited_user,
                'quota_expiry_date': data.quota_expiry_date,
                'last_sync_time': data.updated_at
            }
            return new_data
        return data

    model_config = ConfigDict(from_attributes=True)

class WeeklyUsageResponse(BaseModel):
    weekly_data: List[float]

class MonthlyUsageData(BaseModel):
    month_year: str
    usage_mb: float

class MonthlyUsageResponse(BaseModel):
    monthly_data: List[MonthlyUsageData]

# Alias untuk kompatibilitas mundur
UserMeResponseSchema = UserResponseSchema
UserProfileResponseSchema = UserResponseSchema