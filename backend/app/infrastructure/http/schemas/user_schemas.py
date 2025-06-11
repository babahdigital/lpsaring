# backend/app/infrastructure/http/schemas/user_schemas.py
import uuid
import re
import enum
from pydantic import (
    BaseModel, Field, field_validator, model_validator, ConfigDict
)
from typing import Optional, List, Any
from datetime import datetime

# Impor Enum dari models.py
from app.infrastructure.db.models import UserRole, ApprovalStatus, UserBlok, UserKamar

def validate_indonesian_phone_number(v: Any) -> str:
    if not isinstance(v, str):
        if v is None:
            raise TypeError("Nomor telepon tidak boleh kosong.")
        raise TypeError(f"Input nomor telepon harus berupa string, bukan {type(v)}")
    cleaned_phone = re.sub(r'[\s\-()+]', '', v).strip()
    if cleaned_phone.startswith('08'):
        formatted_phone = '+62' + cleaned_phone[1:]
    elif cleaned_phone.startswith('628'):
        formatted_phone = '+' + cleaned_phone
    elif cleaned_phone.startswith('+628'):
        formatted_phone = cleaned_phone
    elif cleaned_phone.startswith('8') and len(cleaned_phone) >= 8:
        formatted_phone = '+62' + cleaned_phone
    else:
        raise ValueError('Format awalan nomor telepon tidak valid (harus 08xx, 628xx, atau +628xx).')
    if not (11 <= len(formatted_phone) <= 15):
        raise ValueError(f'Panjang nomor telepon tidak valid ({len(formatted_phone)} digit). Seharusnya 11-15 digit termasuk +62.')
    if not re.match(r'^\+628[1-9][0-9]{7,11}$', formatted_phone):
        raise ValueError('Format nomor telepon +62 tidak valid.')
    return formatted_phone

class UserBaseSchema(BaseModel):
    phone_number: str = Field(..., example="+6281234567890")
    full_name: str = Field(..., example="Nama Lengkap Pengguna", min_length=2, max_length=100)
    blok: Optional[str] = Field(None, example="A")
    kamar: Optional[str] = Field(None, example="Kamar_1")

    @field_validator('phone_number', mode='before')
    @classmethod
    def validate_phone(cls, v: Any) -> str:
        return validate_indonesian_phone_number(v)

    @field_validator('full_name', mode='before')
    @classmethod
    def validate_full_name(cls, v: Any) -> str:
        if v is None:
            raise ValueError('Nama Lengkap tidak boleh kosong.')
        if isinstance(v, str):
            stripped_v = v.strip()
            if len(stripped_v) < 2:
                raise ValueError('Nama Lengkap minimal 2 karakter.')
            return stripped_v
        raise TypeError('Nama Lengkap harus berupa string.')

    @field_validator('blok', mode='before')
    @classmethod
    def validate_blok_input(cls, v: Any) -> Optional[str]:
        if v is None or v == '':
            return None
        if isinstance(v, str):
            v_upper = v.upper()
            if v_upper in [b.value for b in UserBlok]:
                return v_upper
            raise ValueError(f"Blok '{v}' tidak valid. Pilihan: {[b.value for b in UserBlok]}")
        raise TypeError('Blok harus berupa string.')

    @field_validator('kamar', mode='before')
    @classmethod
    def validate_kamar_input(cls, v: Any) -> Optional[str]:
        if v is None or v == '':
            return None
        if isinstance(v, str):
            if v.isdigit() and 1 <= int(v) <= 6:
                return f"Kamar_{v}"
            if v in [k.value for k in UserKamar]:
                return v
            raise ValueError(f"Kamar '{v}' tidak valid. Pilihan: {[k.value for k in UserKamar]} atau angka 1-6.")
        raise TypeError('Kamar harus berupa string.')

class UserCreateByAdminSchema(UserBaseSchema):
    role: UserRole = Field(..., example=UserRole.USER)

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

    @field_validator('blok', mode='before')
    @classmethod
    def validate_blok_input(cls, v: Any) -> Optional[str]:
        if v is None or v == '':
            return None
        if isinstance(v, str):
            v_upper = v.upper()
            if v_upper in [b.value for b in UserBlok]:
                return v_upper
            raise ValueError(f"Blok '{v}' tidak valid. Pilihan: {[b.value for b in UserBlok]}")
        raise TypeError('Blok harus berupa string.')

    @field_validator('kamar', mode='before')
    @classmethod
    def validate_kamar_input(cls, v: Any) -> Optional[str]:
        if v is None or v == '':
            return None
        if isinstance(v, str):
            if v.isdigit() and 1 <= int(v) <= 6:
                return f"Kamar_{v}"
            if v in [k.value for k in UserKamar]:
                return v
            raise ValueError(f"Kamar '{v}' tidak valid. Pilihan: {[k.value for k in UserKamar]} atau angka 1-6.")
        raise TypeError('Kamar harus berupa string.')

class UserResponseSchema(UserBaseSchema):
    id: uuid.UUID
    role: UserRole
    approval_status: ApprovalStatus
    is_active: bool
    total_quota_purchased_mb: int
    total_quota_used_mb: float
    device_brand: Optional[str]
    device_model: Optional[str]
    created_at: datetime
    updated_at: datetime
    approved_at: Optional[datetime]
    last_login_at: Optional[datetime]
    is_unlimited_user: bool
    quota_expiry_date: Optional[datetime]

    # --- PERBAIKAN NORMALISASI OUTPUT KAMAR ---
    @field_validator('kamar', mode='before')
    @classmethod
    def serialize_kamar_to_plain_string(cls, v: Any) -> Optional[str]:
        """
        Validator ini memastikan output 'kamar' selalu berupa angka jika memungkinkan.
        Contoh: 'Kamar_1' menjadi '1'.
        """
        if isinstance(v, enum.Enum):
            v = v.value
        
        if isinstance(v, str) and v.startswith("Kamar_") and v[6:].isdigit():
            return v[6:]
        return v

    model_config = ConfigDict(from_attributes=True)

class UserMeResponseSchema(UserResponseSchema):
    pass

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

class PhoneCheckRequest(BaseModel):
    phone_number: str
    full_name: Optional[str] = None

    @field_validator('phone_number', mode='before')
    @classmethod
    def validate_phone(cls, v: Any) -> str:
        return validate_indonesian_phone_number(v)

class PhoneCheckResponse(BaseModel):
    user_exists: bool
    user_id: Optional[uuid.UUID] = None
    message: Optional[str] = None

class UserQuotaResponse(BaseModel):
    total_quota_purchased_mb: int
    total_quota_used_mb: int
    remaining_mb: int
    hotspot_username: str
    last_sync_time: datetime
    is_unlimited_user: bool
    quota_expiry_date: Optional[datetime]
    model_config = ConfigDict(from_attributes=True)

class WeeklyUsageResponse(BaseModel):
    weekly_data: List[float]

class MonthlyUsageData(BaseModel):
    month_year: str
    usage_mb: float

class MonthlyUsageResponse(BaseModel):
    monthly_data: List[MonthlyUsageData]

class UserProfileResponseSchema(BaseModel):
    id: uuid.UUID
    phone_number: str
    full_name: str
    blok: Optional[str]
    kamar: Optional[str]
    is_active: bool
    role: UserRole
    approval_status: ApprovalStatus
    total_quota_purchased_mb: int
    total_quota_used_mb: float
    quota_expiry_date: Optional[datetime]
    is_unlimited_user: bool
    device_brand: Optional[str]
    device_model: Optional[str]
    created_at: datetime
    updated_at: datetime
    last_login_at: Optional[datetime]

    @field_validator('blok', mode='plain')
    @classmethod
    def serialize_blok_to_plain_string(cls, v: Any) -> Optional[str]:
        if isinstance(v, enum.Enum): return v.value
        if isinstance(v, str) and v in [b.value for b in UserBlok]: return v
        return v

    @field_validator('kamar', mode='plain')
    @classmethod
    def serialize_kamar_to_plain_string(cls, v: Any) -> Optional[str]:
        if isinstance(v, enum.Enum): return v.value
        if isinstance(v, str) and v in [k.value for k in UserKamar]: return v
        if isinstance(v, str) and v.startswith("Kamar_") and v[6:].isdigit(): return v[6:]
        return v

    model_config = ConfigDict(from_attributes=True)