# backend/app/infrastructure/http/komandan/schemas.py
# PENYEMPURNAAN: Membuat skema lebih konsisten dan tangguh
# sejalan dengan arsitektur aplikasi secara keseluruhan.

from pydantic import BaseModel, Field, model_validator
from typing import Optional
import uuid

# Impor tipe enum dari model database
from app.infrastructure.db.models import RequestType, RequestStatus

class QuotaRequestCreateSchema(BaseModel):
    """
    Skema untuk memvalidasi payload saat Komandan membuat permintaan baru.
    """
    request_type: RequestType
    # Dibuat non-opsional dengan default None agar lebih eksplisit,
    # validasi sebenarnya terjadi di model_validator.
    requested_mb: int | None = Field(None, gt=0, description="Jumlah kuota dalam MB. Wajib jika tipe request adalah QUOTA.")
    requested_duration_days: int | None = Field(None, gt=0, description="Jumlah hari durasi. Wajib jika tipe request adalah QUOTA.")

    @model_validator(mode='after')
    def check_quota_details_are_present_if_needed(self) -> 'QuotaRequestCreateSchema':
        """Memastikan detail kuota diisi jika tipe permintaan adalah QUOTA."""
        if self.request_type == RequestType.QUOTA:
            if self.requested_mb is None or self.requested_duration_days is None:
                raise ValueError("Untuk tipe permintaan QUOTA, requested_mb dan requested_duration_days wajib diisi.")
        return self

class QuotaRequestResponseSchema(BaseModel):
    """
    Skema untuk respons setelah permintaan berhasil dibuat.
    """
    id: uuid.UUID
    status: RequestStatus  # Menggunakan tipe Enum langsung
    request_type: RequestType # Menggunakan tipe Enum langsung
    message: str

    class Config:
        """
        Konfigurasi Pydantic untuk skema ini.
        - from_attributes: Memungkinkan pembuatan skema dari objek model SQLAlchemy.
        - use_enum_values: Memastikan nilai enum (string) yang dikirim dalam JSON, bukan objek enum.
        """
        from_attributes = True
        use_enum_values = True