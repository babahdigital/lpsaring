# backend/app/infrastructure/http/schemas/package_schemas.py
# VERSI FINAL: Disesuaikan dengan model Package terbaru di database.

from pydantic import BaseModel, Field, ConfigDict
from uuid import UUID
from typing import Optional

# ==============================================================================
# PackagePublic: Skema untuk respons API GET /api/packages
# ==============================================================================
class PackagePublic(BaseModel):
    """Skema untuk menampilkan data paket ke publik via API."""
    id: UUID
    name: str
    price: int
    description: Optional[str] = None
    
    # Field yang sesuai dengan model database
    duration_days: int
    data_quota_gb: float
    
    # [DIHAPUS] Field 'speed_limit_kbps' dihapus karena tidak ada di model DB.
    # Ini mencegah error dan menjaga konsistensi SSoT (Single Source of Truth).
    
    is_active: bool

    # Menggunakan ConfigDict untuk Pydantic v2
    model_config = ConfigDict(from_attributes=True)