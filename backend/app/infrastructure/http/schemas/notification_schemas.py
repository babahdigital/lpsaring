# ========================================================================
# File: backend/app/infrastructure/http/schemas/notification_schemas.py
# Penyesuaian: Memastikan NotificationType diimpor dengan benar dan skema siap.
# ========================================================================
import uuid
from pydantic import BaseModel, ConfigDict, Field
from typing import List

from app.infrastructure.db.models import NotificationType


class NotificationRecipientStatusSchema(BaseModel):
    id: uuid.UUID = Field(..., description="ID Pengguna (Admin)")
    full_name: str = Field(..., description="Nama Lengkap Admin")
    phone_number: str = Field(..., description="Nomor Telepon Admin")
    is_subscribed: bool = Field(..., description="Status apakah admin ini berlangganan notifikasi.")

    model_config = ConfigDict(from_attributes=True)


class NotificationRecipientUpdateSchema(BaseModel):
    subscribed_admin_ids: List[uuid.UUID] = Field(
        ..., description="Daftar lengkap ID admin yang harus berlangganan notifikasi."
    )
    notification_type: NotificationType = Field(..., description="Jenis notifikasi yang diatur.")


class NotificationUpdateResponseSchema(BaseModel):
    success: bool = True
    message: str = "Daftar penerima notifikasi berhasil diperbarui."
    total_recipients: int = Field(..., description="Jumlah total penerima setelah pembaruan.")
