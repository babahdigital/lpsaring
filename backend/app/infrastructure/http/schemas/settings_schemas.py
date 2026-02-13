# backend/app/infrastructure/http/schemas/settings_schemas.py
# --- FILE BARU ---

from pydantic import BaseModel
from typing import Optional, Dict

class SettingSchema(BaseModel):
    """Schema untuk menampilkan satu item pengaturan."""
    setting_key: str
    setting_value: Optional[str]
    description: Optional[str]
    is_encrypted: bool

    class Config:
        from_attributes = True

class SettingsUpdateSchema(BaseModel):
    """
    Schema untuk menerima data pembaruan pengaturan.
    Strukturnya adalah dictionary key-value.
    """
    settings: Dict[str, str]