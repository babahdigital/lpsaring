# backend/app/infrastructure/http/admin/schemas.py
# VERSI FINAL: Menggabungkan semua skema untuk Admin API untuk mencegah circular imports.

import uuid
import json
from pydantic import BaseModel, Field, field_validator, ConfigDict, model_validator
from typing import Optional, List
from datetime import datetime
import enum

# Impor model DB dan Enum yang relevan
from app.infrastructure.db.models import (
    RequestStatus,
    RequestType,
    AdminActionType,
    UserRole,
    ApprovalStatus,
    NotificationType,
)

# --- Skema untuk Notifikasi ---


class NotificationRecipientUpdateSchema(BaseModel):
    notification_type: NotificationType
    subscribed_admin_ids: List[uuid.UUID]


# --- Skema untuk Permintaan (Request) ---


class RequestApprovalAction(str, enum.Enum):
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    REJECT_AND_GRANT_QUOTA = "REJECT_AND_GRANT_QUOTA"


# [PERBAIKAN UTAMA] Merombak skema untuk menangani semua aksi, termasuk durasi unlimited
class RequestApprovalSchema(BaseModel):
    action: RequestApprovalAction

    # Field untuk penolakan atau proses sebagian
    rejection_reason: Optional[str] = Field(
        None, min_length=5, description="Alasan penolakan atau proses sebagian. Wajib diisi jika action bukan APPROVE."
    )

    # Field untuk aksi proses sebagian (grant partial quota)
    granted_quota_mb: Optional[int] = Field(
        None, ge=0, description="Kuota dalam MB yang diberikan saat proses sebagian."
    )
    granted_duration_days: Optional[int] = Field(
        None, ge=0, description="Durasi dalam hari yang diberikan saat proses sebagian."
    )

    # [PERBAIKAN] Field baru yang krusial untuk durasi unlimited
    unlimited_duration_days: Optional[int] = Field(
        None,
        ge=1,
        description="Durasi dalam hari untuk akses unlimited. Wajib diisi jika menyetujui request unlimited.",
    )

    @model_validator(mode="after")
    def check_fields_based_on_action(self):
        action = self.action
        rejection_reason = self.rejection_reason
        granted_quota_mb = self.granted_quota_mb
        granted_duration_days = self.granted_duration_days

        # Jika aksi adalah REJECT, alasan wajib diisi
        if action == RequestApprovalAction.REJECT and not rejection_reason:
            raise ValueError("Alasan penolakan wajib diisi saat menolak permintaan.")

        # Jika aksi adalah REJECT_AND_GRANT_QUOTA
        if action == RequestApprovalAction.REJECT_AND_GRANT_QUOTA:
            # Alasan juga wajib diisi
            if not rejection_reason:
                raise ValueError("Alasan wajib diisi saat memproses permintaan sebagian.")

            # Minimal salah satu dari kuota atau durasi harus diisi dan lebih besar dari 0
            has_quota = granted_quota_mb is not None and granted_quota_mb > 0
            has_duration = granted_duration_days is not None and granted_duration_days > 0
            if not has_quota and not has_duration:
                raise ValueError(
                    "Saat memproses sebagian, minimal salah satu dari kuota atau durasi harus diberikan dan lebih besar dari 0."
                )

        # Validasi untuk `unlimited_duration_days` akan ditangani di level route/endpoint
        # karena membutuhkan informasi `request_type` yang tidak ada di dalam payload ini.

        return self


class RequesterInfoSchema(BaseModel):
    id: uuid.UUID
    full_name: str
    phone_number: str
    model_config = ConfigDict(from_attributes=True)


class QuotaRequestListItemSchema(BaseModel):
    id: uuid.UUID
    requester: RequesterInfoSchema
    status: RequestStatus
    request_type: RequestType
    request_details: Optional[dict] = None
    rejection_reason: Optional[str] = None
    created_at: datetime
    processed_at: Optional[datetime] = None

    @field_validator("request_details", mode="before")
    @classmethod
    def parse_json_string(cls, v):
        if isinstance(v, str):
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                return {"error": "Format JSON tidak valid"}
        return v

    model_config = ConfigDict(from_attributes=True, use_enum_values=True)


# --- Skema untuk Pengguna (User) & Log Aktivitas ---


class AdminUserInfo(BaseModel):
    id: uuid.UUID
    full_name: str
    phone_number: str
    model_config = ConfigDict(from_attributes=True)


class UserResponseSchema(BaseModel):
    id: uuid.UUID
    phone_number: str
    full_name: str
    blok: Optional[str] = None
    kamar: Optional[str] = None
    role: UserRole
    is_active: bool
    approval_status: ApprovalStatus
    is_unlimited_user: bool
    mikrotik_user_exists: bool
    total_quota_purchased_mb: int
    total_quota_used_mb: float
    quota_expiry_date: Optional[datetime] = None
    created_at: datetime
    approved_at: Optional[datetime] = None
    mikrotik_server_name: Optional[str] = None
    mikrotik_profile_name: Optional[str] = None
    model_config = ConfigDict(from_attributes=True, use_enum_values=True)


class AdminActionLogResponseSchema(BaseModel):
    id: uuid.UUID
    action_type: AdminActionType
    details: Optional[str] = None
    created_at: datetime
    admin: Optional[AdminUserInfo] = None
    target_user: Optional[AdminUserInfo] = None

    @field_validator("details", mode="before")
    @classmethod
    def parse_details_json(cls, v):
        if isinstance(v, dict):
            return json.dumps(v, default=str)
        return v

    model_config = ConfigDict(from_attributes=True, use_enum_values=True)
