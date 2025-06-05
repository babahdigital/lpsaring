# backend/app/infrastructure/http/schemas/transaction_schemas.py
from pydantic import BaseModel, Field
import uuid # Pastikan uuid diimpor jika belum

# Skema untuk data yang dikirim frontend saat memulai transaksi
class InitiateTransactionRequest(BaseModel):
    """Skema validasi untuk request inisiasi transaksi."""
    package_id: uuid.UUID = Field(..., description="ID Paket (UUID) yang dipilih pengguna")
    user_id: uuid.UUID = Field(..., description="ID User (UUID) yang melakukan transaksi (dari check/register)")

    # Anda bisa tambahkan field lain di sini jika diperlukan dari frontend
    # misalnya detail user jika tidak login:
    # customer_name: str | None = Field(None, min_length=2)
    # customer_email: EmailStr | None = None # Gunakan EmailStr dari Pydantic

# Skema untuk data yang dikirim backend sebagai respons inisiasi transaksi
class InitiateTransactionResponse(BaseModel):
    """Skema respons setelah transaksi berhasil diinisiasi."""
    snap_token: str = Field(..., description="Token Midtrans Snap UI untuk ditampilkan di frontend")
    transaction_id: uuid.UUID = Field(..., description="ID Transaksi internal (UUID) yang baru dibuat di database")

    # Aktifkan model_config jika Anda perlu validasi dari atribut objek lain (di sini tidak)
    # model_config = {
    #     "from_attributes": True
    # }