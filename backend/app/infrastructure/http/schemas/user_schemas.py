# backend/app/infrastructure/http/schemas/user_schemas.py
import uuid
import enum
from pydantic import (
    BaseModel, Field, field_validator, model_validator, ConfigDict
)
from typing import Optional, List, Any
from datetime import datetime

# Impor Enum dari models.py
from app.infrastructure.db.models import UserRole, ApprovalStatus, UserBlok, UserKamar
# Impor formatter terpusat
from app.utils.formatters import normalize_to_e164
from app.infrastructure.http.schemas.auth_schemas import TAMPING_TYPES


ALLOWED_TAMPING_TYPES = set(TAMPING_TYPES)

def validate_indonesian_phone_number(v: Any) -> str:
    """
    Validator yang memanggil helper terpusat untuk konsistensi.
    """
    if not isinstance(v, str):
        if v is None:
            raise TypeError("Nomor telepon tidak boleh kosong.")
        raise TypeError(f"Input nomor telepon harus berupa string, bukan {type(v)}")
    
    try:
        # Terima berbagai format (08, +628, 628)
        return normalize_to_e164(v)
    except ValueError as e:
        raise ValueError(str(e))

class UserBaseSchema(BaseModel):
    phone_number: str = Field(..., examples=["+6281234567890"])
    full_name: str = Field(..., examples=["Nama Lengkap Pengguna"], min_length=2, max_length=100)
    blok: Optional[str] = Field(None, examples=["A"])
    kamar: Optional[str] = Field(None, examples=["Kamar_1"])
    is_tamping: bool = Field(False, description="True jika pengguna tamping")
    tamping_type: Optional[str] = Field(None, description="Jenis tamping jika pengguna tamping")

    @field_validator('phone_number', mode='before')
    @classmethod
    def validate_phone(cls, v: Any) -> str:
        # Gunakan validator baru yang terpusat
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

    @field_validator('tamping_type', mode='before')
    @classmethod
    def validate_tamping_type(cls, v: Any) -> Optional[str]:
        # Catatan:
        # - Schema ini dipakai untuk response (UserResponseSchema) juga.
        # - Jangan strict di response karena bisa menyebabkan 500 jika DB punya nilai baru/legacy.
        # - Validasi allowed dilakukan di schema request (create/update).
        if v is None:
            return None
        if v == '':
            return None
        if isinstance(v, str):
            stripped_v = v.strip()
            return stripped_v if stripped_v else None
        raise TypeError('Jenis tamping harus berupa string.')

class UserCreateByAdminSchema(UserBaseSchema):
    role: UserRole = Field(..., examples=[UserRole.USER])

    @field_validator('tamping_type', mode='before')
    @classmethod
    def validate_tamping_type_allowed(cls, v: Any) -> Optional[str]:
        if v is None or v == '':
            return None
        if isinstance(v, str):
            stripped_v = v.strip()
            if not stripped_v:
                return None
            if stripped_v in ALLOWED_TAMPING_TYPES:
                return stripped_v
            raise ValueError("Jenis tamping tidak valid.")
        raise TypeError('Jenis tamping harus berupa string.')

    @model_validator(mode='after')
    def check_blok_kamar_for_user_role(self) -> 'UserCreateByAdminSchema':
        if self.role == UserRole.USER:
            if self.is_tamping:
                if not self.tamping_type:
                    raise ValueError("Jenis tamping wajib dipilih untuk pengguna tamping.")
                if self.blok is not None or self.kamar is not None:
                    raise ValueError("Blok dan Kamar tidak boleh diisi untuk pengguna tamping.")
            else:
                if self.blok is None or self.kamar is None:
                    raise ValueError("Blok dan Kamar wajib diisi untuk pengguna biasa.")
        if self.role == UserRole.SUPER_ADMIN:
            raise ValueError('Peran Super Admin tidak dapat dibuat melalui API ini.')
        return self

class UserUpdateByAdminSchema(BaseModel):
    phone_number: Optional[str] = None
    full_name: Optional[str] = Field(None, min_length=2, max_length=100)
    blok: Optional[UserBlok] = None
    kamar: Optional[UserKamar] = None
    is_tamping: Optional[bool] = None
    tamping_type: Optional[str] = None
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None
    is_unlimited_user: Optional[bool] = None
    is_blocked: Optional[bool] = None
    blocked_reason: Optional[str] = None
    add_mb: Optional[int] = Field(None, ge=0)
    add_gb: Optional[float] = Field(None, ge=0.0, description="Kuota yang akan ditambahkan dalam Gigabyte. Akan dikonversi ke MB di backend.")
    add_days: Optional[int] = Field(None, ge=0)

    @field_validator('phone_number', mode='before')
    @classmethod
    def validate_phone(cls, v: Any) -> Optional[str]:
        if v is None or v == '':
            return None
        return validate_indonesian_phone_number(v)


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

    @field_validator('tamping_type', mode='before')
    @classmethod
    def validate_tamping_type(cls, v: Any) -> Optional[str]:
        if v is None or v == '':
            return None
        if isinstance(v, str):
            stripped_v = v.strip()
            if not stripped_v:
                return None
            if stripped_v in ALLOWED_TAMPING_TYPES:
                return stripped_v
            raise ValueError("Jenis tamping tidak valid.")
        raise TypeError('Jenis tamping harus berupa string.')

    @model_validator(mode='after')
    def check_tamping_rules(self) -> 'UserUpdateByAdminSchema':
        if self.is_tamping is True:
            if not self.tamping_type:
                raise ValueError("Jenis tamping wajib dipilih untuk pengguna tamping.")
        return self

class UserChangeRoleSchema(BaseModel):
    """Skema untuk memvalidasi payload saat mengubah peran pengguna."""
    role: UserRole

    @field_validator('role')
    @classmethod
    def role_cannot_be_admin(cls, v: UserRole):
        if v in [UserRole.ADMIN, UserRole.SUPER_ADMIN]:
            raise ValueError("Peran tidak bisa diubah menjadi ADMIN atau SUPER_ADMIN melalui endpoint ini.")
        return v

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
    is_blocked: bool
    blocked_reason: Optional[str] = None
    blocked_at: Optional[datetime] = None

    @field_validator('kamar', mode='before')
    @classmethod
    def serialize_kamar_to_plain_string(cls, v: Any) -> Optional[str]:
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
    blok: Optional[str] = None
    kamar: Optional[str] = None
    is_tamping: Optional[bool] = None
    tamping_type: Optional[str] = None

    @field_validator('tamping_type', mode='before')
    @classmethod
    def validate_tamping_type_allowed(cls, v: Any) -> Optional[str]:
        if v is None or v == '':
            return None
        if isinstance(v, str):
            stripped_v = v.strip()
            if not stripped_v:
                return None
            if stripped_v in ALLOWED_TAMPING_TYPES:
                return stripped_v
            raise ValueError("Jenis tamping tidak valid.")
        raise TypeError('Jenis tamping harus berupa string.')

    @field_validator('blok', 'kamar', mode='before')
    @classmethod
    def check_not_empty(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        if not v or not v.strip():
            raise ValueError("Field tidak boleh kosong.")
        return v

    @model_validator(mode='after')
    def check_tamping_or_address(self) -> 'UserProfileUpdateRequestSchema':
        has_address_fields = any([self.blok is not None, self.kamar is not None, self.is_tamping is not None, self.tamping_type is not None])
        if not has_address_fields:
            return self

        if self.is_tamping is True:
            if not self.tamping_type:
                raise ValueError("Jenis tamping wajib dipilih untuk pengguna tamping.")
            if self.blok or self.kamar:
                raise ValueError("Blok dan Kamar tidak boleh diisi untuk pengguna tamping.")
        else:
            if not self.blok or not self.kamar:
                raise ValueError("Blok dan Kamar wajib diisi untuk pengguna biasa.")
        return self

class AdminSelfProfileUpdateRequestSchema(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=100)
    phone_number: Optional[str] = None

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

    @field_validator('phone_number', mode='before')
    @classmethod
    def validate_phone(cls, v: Any) -> Optional[str]:
        if v is None or v == '':
            return None
        return validate_indonesian_phone_number(v)

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

class WhatsappValidationRequest(BaseModel):
    """Skema untuk memvalidasi permintaan pengecekan nomor WhatsApp."""
    phone_number: str

    @field_validator('phone_number', mode='before')
    @classmethod
    def validate_phone(cls, v: Any) -> str:
        # Menggunakan kembali validator yang sudah ada untuk konsistensi
        return validate_indonesian_phone_number(v)

class UserQuotaResponse(BaseModel):
    total_quota_purchased_mb: float
    total_quota_used_mb: float
    remaining_mb: float
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
    is_tamping: bool
    tamping_type: Optional[str]
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
        if isinstance(v, enum.Enum):
            return v.value
        if isinstance(v, str) and v in [b.value for b in UserBlok]:
            return v
        return v

    @field_validator('kamar', mode='plain')
    @classmethod
    def serialize_kamar_to_plain_string(cls, v: Any) -> Optional[str]:
        if isinstance(v, enum.Enum):
            return v.value
        if isinstance(v, str) and v in [k.value for k in UserKamar]:
            return v
        if isinstance(v, str) and v.startswith("Kamar_") and v[6:].isdigit():
            return v[6:]
        return v

    model_config = ConfigDict(from_attributes=True)