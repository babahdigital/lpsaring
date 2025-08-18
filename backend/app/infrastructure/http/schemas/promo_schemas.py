# backend/app/infrastructure/http/schemas/promo_schemas.py
# VERSI FINAL: Mengintegrasikan bonus_duration_days ke semua skema yang relevan.

import uuid
import datetime
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict

from app.infrastructure.db.models import PromoEventType, PromoEventStatus

# Skema dasar untuk data yang sama di create dan update
class PromoEventBaseSchema(BaseModel):
    name: str = Field(..., min_length=3, max_length=150, description="Nama event atau promo.")
    description: Optional[str] = Field(None, description="Deskripsi detail dari promo.")
    event_type: PromoEventType = Field(default=PromoEventType.GENERAL_ANNOUNCEMENT, description="Jenis event.")
    status: PromoEventStatus = Field(default=PromoEventStatus.DRAFT, description="Status event saat ini.")
    start_date: datetime.datetime = Field(..., description="Tanggal dan waktu promo dimulai.")
    end_date: Optional[datetime.datetime] = Field(None, description="Tanggal dan waktu promo berakhir (opsional).")
    bonus_value_mb: Optional[int] = Field(None, ge=0, description="Nilai bonus kuota dalam MB (jika ada).")
    # --- FIELD BARU UNTUK DURASI DITAMBAHKAN DI SINI ---
    bonus_duration_days: Optional[int] = Field(None, ge=1, description="Durasi masa aktif bonus dalam hari (jika ada).")

    model_config = ConfigDict(use_enum_values=True, from_attributes=True)

# Skema yang digunakan saat membuat event baru
class PromoEventCreateSchema(PromoEventBaseSchema):
    pass

# Skema yang digunakan saat memperbarui event yang ada
# Semua field dibuat opsional
class PromoEventUpdateSchema(BaseModel):
    name: Optional[str] = Field(None, min_length=3, max_length=150)
    description: Optional[str] = None
    event_type: Optional[PromoEventType] = None
    status: Optional[PromoEventStatus] = None
    start_date: Optional[datetime.datetime] = None
    end_date: Optional[datetime.datetime] = None
    bonus_value_mb: Optional[int] = Field(None, ge=0)
    # --- FIELD BARU DITAMBAHKAN UNTUK UPDATE ---
    bonus_duration_days: Optional[int] = Field(None, ge=1)


# Skema untuk response data user (hanya informasi yang relevan)
class UserInfoSchema(BaseModel):
    id: uuid.UUID
    full_name: str

    model_config = ConfigDict(from_attributes=True)

# Skema untuk response data event, termasuk info admin yang membuat
# Ini akan otomatis mewarisi `bonus_duration_days` dari `PromoEventBaseSchema`
class PromoEventResponseSchema(PromoEventBaseSchema):
    id: uuid.UUID
    created_at: datetime.datetime
    updated_at: datetime.datetime
    created_by: Optional[UserInfoSchema] = None

    model_config = ConfigDict(from_attributes=True)
