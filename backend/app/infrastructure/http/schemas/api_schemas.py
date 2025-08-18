# backend/app/infrastructure/http/schemas/api_schemas.py
# VERSI DIPERBARUI: Menambahkan skema untuk PackageProfile.

import uuid
import json
from pydantic import BaseModel, Field, field_validator, ConfigDict, model_validator
from typing import Optional, List
from datetime import datetime
import enum

# Impor model DB dan Enum yang relevan
from app.infrastructure.db.models import (
    RequestStatus, RequestType, AdminActionType,
    UserRole, ApprovalStatus, NotificationType
)

# --- [BARU] Skema untuk Profil Teknis (PackageProfile) ---
class ProfileSchema(BaseModel):
    id: uuid.UUID
    profile_name: str
    description: Optional[str] = None
    
    model_config = ConfigDict(from_attributes=True)

class ProfileCreateUpdateSchema(BaseModel):
    profile_name: str = Field(..., min_length=2, max_length=100)
    description: Optional[str] = Field(None, max_length=500)


# --- Skema untuk Notifikasi ---
class NotificationRecipientStatusSchema(BaseModel):
    id: uuid.UUID
    full_name: str
    phone_number: str
    is_subscribed: bool

class NotificationRecipientUpdateSchema(BaseModel):
    notification_type: NotificationType
    subscribed_admin_ids: Optional[List[uuid.UUID]] = None

class NotificationUpdateResponseSchema(BaseModel):
    total_recipients: int

# --- Skema untuk Permintaan (Request) ---
class RequestApprovalAction(str, enum.Enum):
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    REJECT_AND_GRANT_QUOTA = "REJECT_AND_GRANT_QUOTA"

class RequestApprovalSchema(BaseModel):
    action: RequestApprovalAction
    rejection_reason: Optional[str] = Field(None, min_length=5, description="Alasan penolakan atau proses sebagian. Wajib diisi jika action bukan APPROVE.")
    granted_quota_mb: Optional[int] = Field(None, ge=0, description="Kuota dalam MB yang diberikan saat proses sebagian.")
    granted_duration_days: Optional[int] = Field(None, ge=0, description="Durasi dalam hari yang diberikan saat proses sebagian.")
    unlimited_duration_days: Optional[int] = Field(None, ge=1, description="Durasi dalam hari untuk akses unlimited. Wajib diisi jika menyetujui request unlimited.")

    @model_validator(mode='after')
    def check_fields_based_on_action(self):
        action = self.action
        rejection_reason = self.rejection_reason
        granted_quota_mb = self.granted_quota_mb
        granted_duration_days = self.granted_duration_days
        if action == RequestApprovalAction.REJECT and not rejection_reason:
            raise ValueError("Alasan penolakan wajib diisi saat menolak permintaan.")
        if action == RequestApprovalAction.REJECT_AND_GRANT_QUOTA:
            if not rejection_reason:
                raise ValueError("Alasan wajib diisi saat memproses permintaan sebagian.")
            has_quota = granted_quota_mb is not None and granted_quota_mb > 0
            has_duration = granted_duration_days is not None and granted_duration_days > 0
            if not has_quota and not has_duration:
                raise ValueError("Saat memproses sebagian, minimal salah satu dari kuota atau durasi harus diberikan dan lebih besar dari 0.")
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

    @field_validator('request_details', mode='before')
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

class AdminActionLogResponseSchema(BaseModel):
    id: uuid.UUID
    action_type: AdminActionType
    details: Optional[str] = None
    created_at: datetime
    admin: Optional[AdminUserInfo] = None
    target_user: Optional[AdminUserInfo] = None

    @field_validator('details', mode='before')
    @classmethod
    def parse_details_json(cls, v):
        if isinstance(v, dict):
            return json.dumps(v, default=str)
        return v
    model_config = ConfigDict(from_attributes=True, use_enum_values=True)