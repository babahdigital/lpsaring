# backend/app/infrastructure/http/schemas/device_schemas.py

from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, Dict, Any
import uuid

class DeviceInfoSchema(BaseModel):
    """Skema untuk informasi perangkat."""
    mac: Optional[str] = Field(None, description="MAC Address perangkat")
    ip: Optional[str] = Field(None, description="IP Address perangkat")
    id: Optional[str] = Field(None, description="ID perangkat jika sudah terdaftar")
    user_agent: Optional[str] = Field(None, description="User agent perangkat")

class AuthorizeDeviceRequestSchema(BaseModel):
    """Skema untuk permintaan otorisasi perangkat."""
    client_ip: Optional[str] = Field(None, description="IP Address perangkat")
    client_mac: Optional[str] = Field(None, description="MAC Address perangkat")
    device_id: Optional[str] = Field(None, description="ID perangkat jika sudah diketahui")
    
    model_config = ConfigDict(extra='allow')

class AuthorizeDeviceResponseSchema(BaseModel):
    """Skema untuk respons otorisasi perangkat."""
    status: str = "SUCCESS"
    message: str = "Perangkat berhasil diotorisasi"
    device_id: str

class RejectDeviceRequestSchema(BaseModel):
    """Skema untuk permintaan penolakan perangkat."""
    client_ip: Optional[str] = Field(None, description="IP Address perangkat")
    client_mac: Optional[str] = Field(None, description="MAC Address perangkat")
    device_id: Optional[str] = Field(None, description="ID perangkat jika sudah diketahui")
    reason: Optional[str] = Field("user_rejected", description="Alasan penolakan")

class SyncDeviceRequestSchema(BaseModel):
    """Skema untuk permintaan sinkronisasi perangkat."""
    ip: Optional[str] = Field(None, description="IP Address perangkat")
    mac: Optional[str] = Field(None, description="MAC Address perangkat")

class SyncDeviceResponseSchema(BaseModel):
    """Skema untuk respons sinkronisasi perangkat."""
    status: str
    message: str
    registered: Optional[bool] = None
    requires_explicit_authorization: Optional[bool] = None
    data: Optional[Dict[str, Any]] = None
