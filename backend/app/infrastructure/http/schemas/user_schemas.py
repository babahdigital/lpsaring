# backend/app/infrastructure/http/schemas/user_schemas.py
# VERSI: Perbaikan validator nomor telepon standalone dan penyesuaian skema lainnya.

import uuid
import re
import enum
from pydantic import BaseModel, Field, validator, root_validator
from typing import Optional, List, Any
from datetime import datetime

# --- Import Enum (dari models.py jika tersedia, jika tidak gunakan placeholder) ---
try:
    from app.infrastructure.db.models import UserRole, ApprovalStatus, UserBlok, UserKamar
except ImportError:
    print("WARNING: Gagal mengimpor Enum (UserRole, ApprovalStatus, UserBlok, UserKamar) dari models.py di user_schemas.py. Menggunakan placeholder.")
    class UserRole(str, enum.Enum): USER = "USER"; ADMIN = "ADMIN"; SUPER_ADMIN = "SUPER_ADMIN"
    class ApprovalStatus(str, enum.Enum): PENDING_APPROVAL = "PENDING_APPROVAL"; APPROVED = "APPROVED"; REJECTED = "REJECTED"
    class UserBlok(str, enum.Enum): A="A"; B="B"; C="C"; D="D"; E="E"; F="F"
    class UserKamar(str, enum.Enum): Kamar_1 = "1"; Kamar_2 = "2"; Kamar_3 = "3"; Kamar_4 = "4"; Kamar_5 = "5"; Kamar_6 = "6"
# ------------------------------------------------------------------------------------

# --- Fungsi Validasi Nomor Telepon Standalone ---
# Didefinisikan di luar kelas agar bisa digunakan kembali dengan benar oleh validator Pydantic
def validate_indonesian_phone_number(phone_input: Any) -> str:
    """
    Memvalidasi dan memformat input nomor telepon Indonesia ke format +62xxxxxxxx.
    Menerima input string atau None (akan dilewati jika None pada validator).
    """
    # Pastikan input adalah string sebelum diproses
    if not isinstance(phone_input, str):
        # Jika validator dipanggil dengan None (misalnya pada field opsional), kembalikan None
        if phone_input is None:
            return phone_input # type: ignore
        # Jika tipe lain, raise TypeError
        raise TypeError(f"Input nomor telepon harus berupa string, bukan {type(phone_input)}")

    v = phone_input # Sekarang kita tahu v adalah string

    if not v:
        raise ValueError('Nomor telepon tidak boleh kosong.')

    # Hapus karakter non-digit kecuali '+' di awal jika ada
    cleaned_phone = re.sub(r'[^\d+]', '', v).strip()

    # Normalisasi awalan ke format +62
    if cleaned_phone.startswith('08'):
        formatted_phone = '+62' + cleaned_phone[1:]
    elif cleaned_phone.startswith('628'):
        # Tambahkan '+' jika belum ada
        formatted_phone = '+' + cleaned_phone if not cleaned_phone.startswith('+') else cleaned_phone
    elif cleaned_phone.startswith('+628'):
        formatted_phone = cleaned_phone
    elif cleaned_phone.startswith('8') and len(cleaned_phone) >= 8:
        # Kasus jika pengguna memasukkan mulai dari 8...
        formatted_phone = '+62' + cleaned_phone
    else:
        # Format awalan tidak dikenali
        raise ValueError('Format awalan nomor telepon tidak valid (harus 08xx, 628xx, atau +628xx).')

    # Validasi panjang final setelah normalisasi
    if not (11 <= len(formatted_phone) <= 15):
        raise ValueError(f'Panjang nomor telepon tidak valid ({len(formatted_phone)} digit). Seharusnya 11-15 digit termasuk +62.')

    # Validasi akhir format +628[1-9]xxxxxxxx
    if not re.match(r'^\+628[1-9][0-9]{7,11}$', formatted_phone):
        raise ValueError('Format nomor telepon +62 tidak valid (setelah +628 harus diikuti angka 1-9).')

    return formatted_phone
# ---------------------------------------------

# --- Skema Pengecekan Nomor Telepon Awal ---
class PhoneCheckRequest(BaseModel):
    phone_number: str = Field(..., description="Nomor telepon pengguna (format internasional atau lokal)")
    full_name: Optional[str] = Field(None, min_length=2, max_length=100, description="Nama Lengkap pengguna (opsional)")

    # Gunakan fungsi validasi standalone
    _validate_phone_check = validator('phone_number', pre=True, allow_reuse=True)(validate_indonesian_phone_number)

    @validator('full_name', pre=True, always=True)
    def validate_check_full_name(cls, v):
        if v is None: return None
        if isinstance(v, str):
            stripped_v = v.strip()
            if not stripped_v: raise ValueError('Nama Lengkap tidak boleh hanya spasi jika diisi.')
            if len(stripped_v) < 2: raise ValueError('Nama Lengkap minimal 2 karakter.')
            return stripped_v
        raise TypeError('Nama Lengkap harus berupa string atau None.')

class PhoneCheckResponse(BaseModel):
    success: bool = True
    user_exists: bool
    user_id: Optional[uuid.UUID] = None
    message: str = "Pengecekan nomor telepon berhasil."
# -------------------------------------------

# --- Skema Dasar Pengguna ---
class UserBaseSchema(BaseModel):
    # Di skema dasar, nomor telepon tetap wajib, tapi bisa diformat dari input apa pun
    phone_number: str = Field(..., example="+6281234567890", description="Nomor telepon format +62")
    full_name: str = Field(..., example="Nama Lengkap Pengguna", min_length=2, max_length=100)
    # Blok dan kamar bisa opsional di level dasar (misal untuk Admin)
    blok: Optional[UserBlok] = Field(None, example=UserBlok.A)
    kamar: Optional[UserKamar] = Field(None, example=UserKamar.Kamar_1)

    # PERBAIKAN: Gunakan fungsi validasi standalone yang benar
    _validate_phone_userbase = validator('phone_number', pre=True, allow_reuse=True)(validate_indonesian_phone_number)

    @validator('full_name', pre=True, always=True)
    def validate_base_full_name(cls, v):
        # Validasi dasar untuk nama
        if v is None: return None # Seharusnya tidak terjadi karena field wajib, tapi aman
        if isinstance(v, str):
            stripped_v = v.strip()
            if not stripped_v: raise ValueError('Nama Lengkap tidak boleh kosong atau hanya spasi.')
            if len(stripped_v) < 2: raise ValueError('Nama Lengkap minimal 2 karakter.')
            return stripped_v
        raise TypeError('Nama Lengkap harus berupa string.')
# --------------------------

# --- Skema untuk Pembuatan User Internal (misal via CLI atau registrasi) ---
class UserCreateInternalSchema(UserBaseSchema):
    # Memaksa blok dan kamar wajib untuk skenario pembuatan user standar
    blok: UserBlok # Wajib di sini
    kamar: UserKamar # Wajib di sini
    # Role bisa ditentukan di sini jika perlu, atau default di model/endpoint
    role: Optional[UserRole] = Field(default=UserRole.USER)
    # Status awal biasanya PENDING atau langsung APPROVED tergantung alur
    approval_status: Optional[ApprovalStatus] = Field(default=ApprovalStatus.PENDING_APPROVAL)
    is_active: Optional[bool] = Field(default=False) # Default tidak aktif sebelum approval
    password_hash: Optional[str] = Field(None) # Untuk admin/superadmin
    mikrotik_password: Optional[str] = Field(None) # Untuk user biasa
# --------------------------------------------------------------------

# --- Skema untuk Update User oleh Admin (via CLI atau API Admin) ---
class UserUpdateByAdminSchema(BaseModel):
    full_name: Optional[str] = Field(None, min_length=2, max_length=100, example="Nama Baru Pengguna")
    # Admin boleh mengosongkan blok/kamar atau mengubahnya
    blok: Optional[UserBlok] = Field(None, example=UserBlok.B)
    kamar: Optional[UserKamar] = Field(None, example=UserKamar.Kamar_1)
    role: Optional[UserRole] = Field(None, example=UserRole.ADMIN)
    approval_status: Optional[ApprovalStatus] = Field(None, example=ApprovalStatus.APPROVED)
    is_active: Optional[bool] = Field(None)
    # Password tidak di-hash di sini, hashing terjadi di command/endpoint
    mikrotik_password: Optional[str] = Field(None, min_length=4, example="newpass123", description="Password BARU untuk Mikrotik (plain text).")
    password_hash: Optional[str] = Field(None, description="Password BARU Portal Admin (plain text).") # Untuk admin login
    phone_number: Optional[str] = Field(None, description="Nomor telepon baru (perlu perhatian khusus).")

    # Validasi nomor telepon jika diubah
    _validate_update_phone = validator('phone_number', pre=True, allow_reuse=True)(validate_indonesian_phone_number)

    # Validasi nama jika diubah
    @validator('full_name', pre=True, always=True)
    def validate_update_by_admin_full_name(cls, v):
        if v is None: return None
        return UserBaseSchema.validate_base_full_name(cls, v) # Reuse validasi nama
# ---------------------------------------------------------------------

# --- Skema Respons Umum Pengguna (untuk list, dll) ---
class UserResponseSchema(UserBaseSchema):
    id: uuid.UUID
    role: UserRole
    approval_status: ApprovalStatus
    is_active: bool
    # blok dan kamar diwarisi dari UserBaseSchema (akan berisi nilai jika ada di DB)

    total_quota_purchased_mb: int = Field(0, description="Total kuota yang pernah dibeli dalam MB")
    total_quota_used_mb: int = Field(0, description="Total kuota yang telah digunakan dalam MB")

    device_brand: Optional[str] = Field(None, example="Samsung")
    device_model: Optional[str] = Field(None, example="Galaxy S21")

    created_at: datetime
    updated_at: datetime

    approved_at: Optional[datetime] = None
    rejected_at: Optional[datetime] = None
    last_login_at: Optional[datetime] = None

    class Config:
        from_attributes = True # Membaca dari atribut objek SQLAlchemy
        use_enum_values = True # Mengirim nilai Enum ('USER', 'A', '1') bukan objek Enum
# ------------------------------------------------------

# --- Skema Respons untuk Endpoint /me ---
class UserMeResponseSchema(UserResponseSchema):
    # Saat ini tidak ada field tambahan khusus untuk /me
    # Mewarisi semua field dari UserResponseSchema
    pass
# -------------------------------------

# --- Skema Respons untuk List Pengguna ---
class UserListResponseSchema(BaseModel):
    items: List[UserResponseSchema]
    total: int
    page: Optional[int] = None
    per_page: Optional[int] = None
    total_pages: Optional[int] = None
# ---------------------------------------

# --- Skema Respons Kuota Pengguna ---
class UserQuotaResponse(BaseModel):
    total_quota_purchased_mb: int = Field(..., description="Total kuota yang pernah dibeli dalam MB")
    total_quota_used_mb: int = Field(..., description="Total kuota yang telah digunakan dalam MB")
    remaining_mb: int = Field(..., description="Sisa kuota yang tersedia dalam MB")
    hotspot_username: Optional[str] = Field(None, description="Username hotspot pengguna (biasanya nomor telepon)")
    last_sync_time: Optional[datetime] = Field(None, description="Waktu sinkronisasi terakhir data kuota")
    class Config: from_attributes = True
# ------------------------------------

# --- Skema Respons Penggunaan Mingguan ---
class WeeklyUsageResponse(BaseModel):
    success: bool = True
    # List berisi 7 angka (float), mewakili penggunaan MB per hari, 7 hari terakhir
    # Urutan: [Hari ke-7 lalu, ..., Hari ke-2 lalu, Kemarin, Hari ini]
    weekly_data: List[float] = Field(..., description="List penggunaan MB per hari selama 7 hari terakhir, diurutkan dari terlama ke terbaru.")
    class Config: from_attributes = False # Tidak perlu baca dari model DB langsung
# ---------------------------------------

# --- Skema Data Penggunaan Bulanan ---
class MonthlyUsageData(BaseModel):
    month_year: str = Field(..., description="Bulan dan tahun (format YYYY-MM)")
    usage_mb: float = Field(..., description="Total penggunaan dalam bulan tersebut (MB)")
# -------------------------------------

# --- Skema Respons Penggunaan Bulanan ---
class MonthlyUsageResponse(BaseModel):
    success: bool = True
    # List berisi data penggunaan per bulan, diurutkan dari bulan terlama ke terbaru
    monthly_data: List[MonthlyUsageData] = Field(..., description="List data penggunaan bulanan, diurutkan dari terlama ke terbaru.")
    class Config: from_attributes = False
# --------------------------------------

# --- Skema Respons Update Profil Pengguna (oleh diri sendiri) ---
class UserProfileResponseSchema(BaseModel):
    success: bool = True
    # Menampilkan data kunci yang mungkin berubah atau relevan setelah update
    phone_number: str
    full_name: str
    blok: Optional[UserBlok] # Bisa None jika admin mengosongkan sebelumnya
    kamar: Optional[UserKamar] # Bisa None jika admin mengosongkan sebelumnya
    updated_at: datetime # Konfirmasi waktu update
    class Config:
        from_attributes = True
        use_enum_values = True
# --------------------------------------------------------------

# --- Skema Request Update Profil Pengguna (oleh diri sendiri) ---
class UserProfileUpdateRequestSchema(BaseModel):
    full_name: Optional[str] = Field(None, min_length=2, max_length=100, description="Nama Lengkap baru pengguna (opsional jika tidak ingin diubah)")
    
    # PERUBAHAN: Jadikan blok dan kamar opsional untuk menerima null
    blok: Optional[UserBlok] = Field(None, description="Blok pengguna. Kirim null jika tidak tinggal di asrama.")
    kamar: Optional[UserKamar] = Field(None, description="Nomor kamar pengguna. Kirim null jika tidak tinggal di asrama.")

    # Validasi nama jika field ada dan tidak None
    @validator('full_name', pre=True, always=True)
    def validate_update_profile_full_name(cls, v):
        if v is None:
            return None # Izinkan None jika tidak ingin mengubah nama
        if isinstance(v, str):
            stripped_v = v.strip()
            if not stripped_v: return None # Anggap string kosong sebagai tidak ada perubahan
            if len(stripped_v) < 2: raise ValueError('Nama Lengkap minimal 2 karakter.')
            return stripped_v
        raise TypeError('Nama Lengkap harus berupa string atau None.')
    
    @root_validator(pre=False, skip_on_failure=True)
    def check_blok_kamar_consistency(cls, values):
        blok, kamar = values.get('blok'), values.get('kamar')
        if (blok is not None and kamar is None) or (blok is None and kamar is not None):
            raise ValueError('Blok dan Kamar harus diisi keduanya atau dikosongkan keduanya.')
        return values

    # Catatan: Validasi bahwa 'blok' dan 'kamar' *harus* diisi oleh peran USER
    # sebaiknya dilakukan di logika endpoint (`user_routes.py`), karena skema ini
    # mungkin saja digunakan dalam konteks lain di masa depan. Namun,
    # membuatnya `Field(...)` tanpa default sudah menyiratkan kewajiban input.
# -------------------------------------------------------------