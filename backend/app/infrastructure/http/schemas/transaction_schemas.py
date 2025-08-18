# backend/app/infrastructure/http/schemas/transaction_schemas.py
from pydantic import BaseModel, Field, ConfigDict
import uuid
from typing import Optional
from datetime import datetime

# --- [PENAMBAHAN] Skema untuk Respons Riwayat Transaksi ---
class PackageInfoInTransaction(BaseModel):
    """Skema sederhana untuk menampilkan info paket dalam transaksi."""
    name: str
    model_config = ConfigDict(from_attributes=True)

class TransactionResponseSchema(BaseModel):
    """Skema untuk menampilkan riwayat transaksi ke pengguna."""
    id: uuid.UUID
    midtrans_order_id: str
    amount: int
    status: str
    payment_method: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    package: Optional[PackageInfoInTransaction] = None
    model_config = ConfigDict(from_attributes=True)

# --- Skema yang sudah ada ---
class InitiateTransactionRequest(BaseModel):
    """Skema validasi untuk request inisiasi transaksi."""
    package_id: uuid.UUID = Field(..., description="ID Paket (UUID) yang dipilih pengguna")

class InitiateTransactionResponse(BaseModel):
    """Skema respons setelah transaksi berhasil diinisiasi."""
    transaction_id: uuid.UUID
    snap_token: str
    redirect_url: str