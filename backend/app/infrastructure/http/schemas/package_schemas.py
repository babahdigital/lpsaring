# backend/app/infrastructure/http/schemas/package_schemas.py
# VERSI: Disesuaikan dengan model Package terbaru.

from pydantic import BaseModel
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
    
    # --- PENYESUAIAN DENGAN MODEL BARU ---
    duration_days: int
    data_quota_gb: float
    # --- AKHIR PENYESUAIAN ---

    speed_limit_kbps: Optional[int] = None
    is_active: bool

    class Config:
        from_attributes = True