# backend/app/infrastructure/http/schemas/package_schemas.py

from pydantic import BaseModel, Field
from uuid import UUID
from typing import Optional
# Hapus import Decimal jika tidak digunakan lagi di skema publik
# from decimal import Decimal
# Hapus import datetime, model_validator jika tidak dipakai di skema ini
# from datetime import datetime
# from pydantic import model_validator

# ==============================================================================
# Skema Pydantic untuk Model Package
# ==============================================================================

# -----------------------------------------------------
# PackageBase: (Tetap sama seperti sebelumnya, pastikan 'price' menggunakan Decimal
#              jika Anda membutuhkannya untuk validasi input Create/Update)
# -----------------------------------------------------
# class PackageBase(BaseModel):
#     name: str = Field(..., min_length=3, max_length=100)
#     price: Decimal = Field(..., gt=Decimal(0)) # Gunakan Decimal untuk input jika perlu presisi
#     description: Optional[str] = None
#     data_quota_mb: int = Field(..., ge=0)
#     speed_limit_kbps: Optional[int] = Field(None, ge=0)
#     mikrotik_profile_name: str = Field(..., max_length=50)
#     is_active: bool = Field(True)

# -----------------------------------------------------
# PackagePublic: Skema untuk respons API GET /api/packages (Disempurnakan)
# Memilih field mana yang ditampilkan ke frontend
# -----------------------------------------------------
class PackagePublic(BaseModel):
    """Skema untuk menampilkan data paket ke publik via API."""
    id: UUID
    name: str
    # --- PERUBAHAN TIPE: Gunakan 'int' karena DB Numeric(10,0) ---
    # Ini memastikan frontend menerima tipe number, bukan string dari Decimal JSON serialization
    price: int
    # ------------------------------------------------------------
    description: Optional[str] = None
    data_quota_mb: int
    speed_limit_kbps: Optional[int] = None
    is_active: bool

    # --- Konfigurasi Pydantic V2 (Sebelumnya 'model_config') ---
    # Pastikan ini ada di dalam class PackagePublic
    class Config:
        from_attributes = True # Menggantikan orm_mode=True di Pydantic v1
    # ----------------------------------------------------------