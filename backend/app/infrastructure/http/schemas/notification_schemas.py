# backend/app/infrastructure/http/schemas/notification_schemas.py
# FILE BARU: Schema untuk manajemen penerima notifikasi.

import uuid
from pydantic import BaseModel, Field
from typing import List

# --- Import Enum dari models.py ---
try:
    from app.infrastructure.db.models import NotificationType
except ImportError:
    import enum
    print("WARNING: Gagal mengimpor NotificationType dari models.py. Menggunakan placeholder.")
    class NotificationType(str, enum.Enum):
        NEW_USER_REGISTRATION = "NEW_USER_REGISTRATION"
# ------------------------------------

class NotificationRecipientStatusSchema(BaseModel):
    """
    Schema untuk menampilkan status langganan notifikasi seorang admin.
    Digunakan dalam response GET.
    """
    id: uuid.UUID = Field(..., description="ID Pengguna (Admin)")
    full_name: str = Field(..., description="Nama Lengkap Admin")
    phone_number: str = Field(..., description="Nomor Telepon Admin")
    is_subscribed: bool = Field(..., description="Status apakah admin ini berlangganan notifikasi pendaftaran pengguna baru.")

    class Config:
        from_attributes = True

class NotificationRecipientUpdateSchema(BaseModel):
    """
    Schema untuk menerima daftar ID admin yang akan di-subscribe.
    Digunakan dalam request POST/PUT.
    """
    subscribed_admin_ids: List[uuid.UUID] = Field(..., description="Daftar lengkap ID admin yang harus berlangganan notifikasi.")
    notification_type: NotificationType = Field(default=NotificationType.NEW_USER_REGISTRATION, description="Jenis notifikasi yang diatur.")

class NotificationUpdateResponseSchema(BaseModel):
    """
    Schema respons setelah berhasil memperbarui daftar penerima notifikasi.
    """
    success: bool = True
    message: str = "Daftar penerima notifikasi berhasil diperbarui."
    total_recipients: int = Field(..., description="Jumlah total penerima setelah pembaruan.")