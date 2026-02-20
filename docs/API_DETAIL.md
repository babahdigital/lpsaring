# Detail API (Per Endpoint)

Dokumen ini memetakan endpoint backend beserta skema request/response yang saat ini aktif di kode.

Lampiran wajib:
- [.github/copilot-instructions.md](../.github/copilot-instructions.md)

## Basis & Autentikasi
- Base path: `/api`
- Admin API: `/api/admin`
- Auth header (endpoint bertanda auth): `Authorization: Bearer <access_token>`

## Konvensi Error
- Auth endpoints sering memakai format:
  - `{ "error": "...", "details": [...] }`
- Endpoint lain sering memakai:
  - `{ "message": "..." }` atau `{ "success": false, "message": "..." }`
- Untuk detail validasi Pydantic: `details` / `errors` berisi array error.

---

# 1) Health
## GET /api/ping
**Auth:** Tidak
**Response 200**
- `message`: string
- `server_time_utc`: ISO datetime

## GET /api/health
**Auth:** Tidak
**Response 200**
- `status`: `ok` | `degraded`
- `checks`: `{ database: boolean, redis: boolean, mikrotik: boolean }`

---

# 2) Auth
## POST /api/auth/register
**Auth:** Tidak
**Request (UserRegisterRequestSchema)**
- `phone_number`: string (dinormalisasi ke format E.164, contoh: `+628...` atau `+675...`)
- `full_name`: string (min 2)
- `blok`: string (opsional)
- `kamar`: string (opsional; angka 1-6 atau `Kamar_#`)
- `is_tamping`: boolean
- `tamping_type`: string (opsional; wajib jika `is_tamping=true`)
- `register_as_komandan`: boolean

**Rules**
- Jika `register_as_komandan=false`:
  - `is_tamping=true` ⇒ `tamping_type` wajib, `blok`/`kamar` **harus kosong**.
  - `is_tamping=false` ⇒ `blok` dan `kamar` **wajib**.

**Response 201 (UserRegisterResponseSchema)**
- `message`: string
- `user_id`: UUID
- `phone_number`: string

## POST /api/auth/request-otp
**Auth:** Tidak
**Request (RequestOtpRequestSchema)**
- `phone_number`: string

**Format yang diterima (contoh)**
- Indonesia: `08xxxxxxxxxx`, `8xxxxxxxxx`, `62xxxxxxxxxx`, `+62xxxxxxxxxx`
- Internasional: `+67512345678`, `67512345678`, `0067512345678`

**Response 200 (RequestOtpResponseSchema)**
- `message`: string

## POST /api/auth/verify-otp
**Auth:** Tidak
**Request (VerifyOtpRequestSchema)**
- `phone_number`: string
- `otp`: string (6 digit)

Opsional (untuk captive/redirect MikroTik):
- `client_ip`: string (IP lokal klien hotspot)
- `client_mac`: string (MAC klien; jika kosong backend akan mencoba resolve dari MikroTik)
- `hotspot_login_context`: boolean (true jika dipanggil dari halaman captive)

**Response 200 (VerifyOtpResponseSchema)**
- `access_token`: string
- `token_type`: string (`bearer`)

Field tambahan (best-effort, tergantung mode hotspot):
- `hotspot_login_required`: boolean
- `hotspot_username`: string | null
- `hotspot_password`: string | null
- `session_token`: string | null
- `session_url`: string | null

Catatan penting:
- Secara default, OTP sukses akan mengikat & mengotorisasi device yang sedang dipakai (lihat ENV `OTP_AUTO_AUTHORIZE_DEVICE`).
- Jika OTP bypass code dipakai (`OTP_ALLOW_BYPASS=true` + `OTP_BYPASS_CODE`), auto-authorize device **tidak** dilakukan.

## GET /api/auth/me
**Auth:** Ya
**Response 200 (UserMeResponseSchema)**
- `id`, `phone_number`, `full_name`, `blok`, `kamar`, `is_tamping`, `tamping_type`
- `role`, `approval_status`, `is_active`, `is_unlimited_user`
- `total_quota_purchased_mb`, `total_quota_used_mb`, `quota_expiry_date`
- `device_brand`, `device_model`
- `created_at`, `updated_at`, `approved_at`, `last_login_at`

## PUT /api/auth/me/profile
**Auth:** Ya
**Request (UserProfileUpdateRequestSchema)**
- `full_name`: string
- `blok`: string (opsional)
- `kamar`: string (opsional)
- `is_tamping`: boolean (opsional)
- `tamping_type`: string (opsional)

**Catatan**: Implementasi hanya memperbarui `full_name` dan (jika role USER) `blok`/`kamar`.

**Response 200 (UserMeResponseSchema)**

## POST /api/auth/users/me/reset-hotspot-password
**Auth:** Ya (non-admin)
**Response 200**
- `success`: boolean
- `message`: string

## POST /api/auth/admin/login
**Auth:** Tidak
**Request**
- `username`: string (nomor HP)
- `password`: string

**Response 200 (VerifyOtpResponseSchema)**
- `access_token`, `token_type`

## POST /api/auth/me/change-password
**Auth:** Ya (Admin)
**Request (ChangePasswordRequestSchema)**
- `current_password`: string (min 6)
- `new_password`: string (min 6)

**Response 200**
- `message`: string

## POST /api/auth/logout
**Auth:** Ya
**Response 200**
- `message`: string

---

# 3) Packages (Public)
## GET /api/packages
**Auth:** Tidak
**Response 200**
- `success`: boolean
- `data`: `PackagePublic[]`
  - `id`, `name`, `price`, `description`
  - `duration_days`, `data_quota_gb`, `speed_limit_kbps`, `is_active`
- `message`: string

---

# 4) Settings (Public)
## GET /api/settings/public
**Auth:** Tidak
**Response 200**
Array `SettingSchema`:
- `setting_key`: string
- `setting_value`: string | null
- `description`: string | null
- `is_encrypted`: boolean

---

# 5) Public User
## POST /api/users/check-or-register
**Auth:** Tidak
**Request (PhoneCheckRequest)**
- `phone_number`: string
- `full_name`: string (opsional)

**Response 200 (PhoneCheckResponse)**
- `user_exists`: boolean
- `user_id`: UUID (opsional)
- `message`: string (opsional)

## POST /api/users/validate-whatsapp
**Auth:** Tidak
**Request (WhatsappValidationRequest)**
- `phone_number`: string

**Response 200**
- `isValid`: boolean
- `message`: string (opsional)

---

# 6) Promo (Public)
## GET /api/public/promos/active
**Auth:** Tidak
**Response 200**
Array `PromoEventResponseSchema` (tanpa `created_by`):
- `id`, `name`, `description`, `event_type`, `status`
- `start_date`, `end_date`
- `bonus_value_mb`, `bonus_duration_days`
- `created_at`, `updated_at`

---

# 7) User Profile & Data
## GET /api/users/me/profile
**Auth:** Ya
**Response 200 (UserProfileResponseSchema)**
- `id`, `phone_number`, `full_name`, `blok`, `kamar`
- `is_tamping`, `tamping_type`, `is_active`, `role`, `approval_status`
- `total_quota_purchased_mb`, `total_quota_used_mb`, `quota_expiry_date`, `is_unlimited_user`
- `device_brand`, `device_model`, `created_at`, `updated_at`, `last_login_at`

## PUT /api/users/me/profile
**Auth:** Ya (role USER)
**Request (UserProfileUpdateRequestSchema)**
- `full_name`, `blok`, `kamar`, `is_tamping`, `tamping_type`

**Rules**
- `is_tamping=true` ⇒ `tamping_type` wajib, `blok`/`kamar` harus kosong.
- `is_tamping=false` ⇒ `blok` & `kamar` wajib.

**Response 200**: `UserProfileResponseSchema`

## POST /api/users/me/reset-hotspot-password
**Auth:** Ya (non-admin)
**Response 200**
- `message`: string

## GET /api/users/me/login-history
**Auth:** Ya
**Query**: `limit` (1–20, default 7)
**Response 200**
Array:
- `login_time`: ISO datetime
- `ip_address`: string
- `user_agent_string`: string

## GET /api/users/me/quota
**Auth:** Ya
**Response 200 (UserQuotaResponse)**
- `total_quota_purchased_mb`, `total_quota_used_mb`, `remaining_mb`
- `hotspot_username`, `last_sync_time`
- `is_unlimited_user`, `quota_expiry_date`

## GET /api/users/me/weekly-usage
**Auth:** Ya
**Response 200 (WeeklyUsageResponse)**
- `weekly_data`: number[] (7 hari)

## GET /api/users/me/monthly-usage
**Auth:** Ya
**Query**: `months` (1–24, default 12)
**Response 200 (MonthlyUsageResponse)**
- `monthly_data`: Array `{ month_year: "YYYY-MM", usage_mb: number }`

## GET /api/users/me/weekly-spending
**Auth:** Ya
**Response 200**
- `categories`: string[]
- `series`: Array `{ name: string, data: number[] }`
- `total_this_week`: number

## GET /api/users/me/transactions
**Auth:** Ya
**Query**: `page` (default 1), `per_page` (<=50)
**Response 200**
- `success`: boolean
- `transactions`: Array
  - `id`, `midtrans_order_id`, `package_name`, `amount`, `status`
  - `payment_method`, `created_at`, `updated_at`
- `pagination`: `{ page, per_page, total_pages, total_items }`

---

# 8) Komandan
## POST /api/komandan/requests
**Auth:** Ya (role KOMANDAN)
**Request (QuotaRequestCreateSchema)**
- `request_type`: `QUOTA` | `UNLIMITED`
- `requested_mb`: number (wajib jika QUOTA)
- `requested_duration_days`: number (wajib jika QUOTA)

**Response 201 (QuotaRequestResponseSchema)**
- `id`: UUID
- `status`: `PENDING`
- `request_type`: `QUOTA` | `UNLIMITED`
- `message`: string

**Response 429 (Policy Limit)**
- `message`: string
- `retry_at`: ISO datetime (opsional)
- `retry_after_seconds`: number (opsional)

## GET /api/komandan/requests/history
**Auth:** Ya (role KOMANDAN)
**Query**: `page`, `itemsPerPage`, `sortBy`, `sortOrder`
**Response 200**
- `items`: Array
  - `id`, `created_at`, `request_type`, `status`
  - `requested_mb`, `requested_duration_days`
  - `granted_details` (opsional) `{ granted_mb, granted_duration_days }`
  - `processed_at`, `rejection_reason`, `processed_by_admin`
- `totalItems`: number

**Catatan Template Notifikasi**
- Notifikasi kuota menipis/masa aktif memakai template khusus berdasarkan role.
  - User: `user_quota_low`, `user_quota_expiry_warning`
  - Komandan: `komandan_quota_low`, `komandan_quota_expiry_warning`

---

# 9) Transactions
## POST /api/transactions/initiate
**Auth:** Ya
**Request**
- `package_id`: UUID

**Response 200**
- `snap_token`: string (opsional)
- `transaction_id`: UUID
- `order_id`: string
- `redirect_url`: string (opsional)

## POST /api/transactions/notification
**Auth:** Tidak (webhook Midtrans)
**Request**: payload Midtrans
**Response 200**
- `status`: `ok`

## GET /api/transactions/by-order-id/{order_id}
**Auth:** Ya (pemilik transaksi / admin)
**Response 200**
- `id`, `midtrans_order_id`, `midtrans_transaction_id`, `status`
- `amount`, `payment_method`, `payment_time`, `expiry_time`
- `va_number`, `payment_code`, `biller_code`, `qr_code_url`
- `hotspot_password`
- `package`: `{ id, name, description, price, data_quota_gb, is_unlimited }`
- `user`: `{ id, phone_number, full_name, quota_expiry_date, is_unlimited_user }`

## GET /api/transactions/{midtrans_order_id}/invoice
**Auth:** Ya
**Response 200**: PDF (`application/pdf`)

## GET /api/transactions/invoice/temp/{token}
## GET /api/transactions/invoice/temp/{token}.pdf
**Auth:** Tidak (tokenized)
**Response 200**: PDF (`application/pdf`)

---

# 10) Admin (Prefix: /api/admin)

## Dashboard
### GET /api/admin/dashboard/stats
**Auth:** Admin
**Response 200**
- `pendapatanHariIni`, `pendapatanBulanIni`
- `pendaftarBaru`, `penggunaAktif`, `akanKadaluwarsa`
- `kuotaTerjualMb`
- `transaksiTerakhir`: Array `{ id, amount, package: { name }, user: { full_name } }`
- `paketTerlaris`: Array `{ name, count }`
- `permintaanTertunda`

### GET /api/admin/metrics
**Auth:** Admin
**Response 200**
- `metrics`: object
  - `otp.request.success`, `otp.request.failed`
  - `otp.verify.success`, `otp.verify.failed`
  - `payment.success`, `payment.failed`
  - `admin.login.success`, `admin.login.failed`

## Notification Recipients
### GET /api/admin/notification-recipients?type=NEW_USER_REGISTRATION
**Auth:** Super Admin
**Response 200**
Array:
- `id`, `full_name`, `phone_number`, `is_subscribed`

### POST /api/admin/notification-recipients
**Auth:** Super Admin
**Request (NotificationRecipientUpdateSchema)**
- `notification_type`: enum
- `subscribed_admin_ids`: UUID[]

**Response 200**
- `message`, `total_recipients`

## Transactions (Admin)
### GET /api/admin/transactions
**Auth:** Admin
**Query**: `page`, `itemsPerPage`, `sortBy`, `sortOrder`, `search`, `user_id`, `start_date`, `end_date`
**Response 200**
- `items`: Array `{ id, order_id, amount, status, created_at, user: { full_name, phone_number }, package_name }`
- `totalItems`

### GET /api/admin/transactions/export
**Auth:** Admin
**Response 501**
- `message`

## User Management
### GET /api/admin/users
**Auth:** Admin
**Query**: `page`, `itemsPerPage`, `search`, `role`, `sortBy`, `sortOrder`
**Response 200**
- `items`: `UserResponseSchema[]`
- `totalItems`

### POST /api/admin/users
**Auth:** Admin
**Request (UserCreateByAdminSchema)**
- `phone_number`, `full_name`, `blok`, `kamar`, `is_tamping`, `tamping_type`, `role`

**Response 201**
- `UserResponseSchema`

### PUT /api/admin/users/{user_id}
**Auth:** Admin
**Request (UserUpdateByAdminSchema)**
- `full_name`, `blok`, `kamar`, `is_tamping`, `tamping_type`, `role`, `is_active`
- `is_unlimited_user`, `add_mb`, `add_gb`, `add_days`

**Response 200**
- `UserResponseSchema`

### PATCH /api/admin/users/{user_id}/approve
**Auth:** Admin
**Response 200**
- `message`
- `user`: `UserResponseSchema`

### POST /api/admin/users/{user_id}/reject
**Auth:** Admin
**Response 200**
- `message`

### DELETE /api/admin/users/{user_id}
**Auth:** Admin
**Response 200**
- `message`

### POST /api/admin/users/{user_id}/reset-hotspot-password
**Auth:** Admin
**Response 200**
- `message`

### POST /api/admin/users/{user_id}/generate-admin-password
**Auth:** Admin
**Response 200**
- `message`

### GET /api/admin/users/{user_id}/mikrotik-status
**Auth:** Admin
**Response 200**
- `user_id`
- `exists_on_mikrotik`: boolean
- `details`: object | null

### GET /api/admin/form-options/alamat
**Auth:** Admin
**Response 200**
- `bloks`: string[]
- `kamars`: string[]

## Quota Request Management
### GET /api/admin/quota-requests
**Auth:** Admin
**Query**: `page`, `itemsPerPage`, `status`, `sortBy`, `sortOrder`
**Response 200**
- `items`: `QuotaRequestListItemSchema[]` (plus `processed_by` & `granted_details`)
- `totalItems`

### POST /api/admin/quota-requests/{request_id}/process
**Auth:** Admin
**Request (RequestApprovalSchema)**
- `action`: `APPROVE` | `REJECT` | `REJECT_AND_GRANT_QUOTA`
- `rejection_reason`: string (wajib jika reject/partial)
- `granted_quota_mb`: number (opsional)
- `granted_duration_days`: number (opsional)
- `unlimited_duration_days`: number (wajib jika approve unlimited)

**Response 200**
- `message`
- `new_status`: string

## Package Management
### GET /api/admin/packages
**Auth:** Admin
**Query**: `page`, `itemsPerPage`
**Response 200**
- `items`: `PackageSchema[]`
- `totalItems`

### POST /api/admin/packages
**Auth:** Admin
**Request (PackageSchema)**
- `name`, `description`, `price`, `is_active`
- `data_quota_gb`, `duration_days`, `profile_id` (diisi otomatis)

**Response 201**
- `PackageSchema`

### PUT /api/admin/packages/{package_id}
**Auth:** Admin
**Request (PackageSchema)**
**Response 200**
- `PackageSchema`

### DELETE /api/admin/packages/{package_id}
**Auth:** Admin
**Response 200**
- `message`

## Profile Management
### GET /api/admin/profiles
**Auth:** Super Admin
**Response 200**
Array `ProfileSchema`:
- `id`, `profile_name`, `description`

### POST /api/admin/profiles
**Auth:** Super Admin
**Request (ProfileCreateUpdateSchema)**
- `profile_name`, `description`

**Response 201**
- `ProfileSchema`

### PUT /api/admin/profiles/{profile_id}
**Auth:** Super Admin
**Request (ProfileCreateUpdateSchema)**
**Response 200**
- `ProfileSchema`

### DELETE /api/admin/profiles/{profile_id}
**Auth:** Super Admin
**Response 200**
- `message`

## Promo Management
### POST /api/admin/promos
**Auth:** Super Admin
**Request (PromoEventCreateSchema)**
- `name`, `description`, `event_type`, `status`
- `start_date`, `end_date`
- `bonus_value_mb`, `bonus_duration_days`

**Response 201**
- `PromoEventResponseSchema`

### GET /api/admin/promos
**Auth:** Admin
**Query**: `page`, `itemsPerPage`, `sortBy`, `sortOrder`, `status`
**Response 200**
- `items`: `PromoEventResponseSchema[]`
- `totalItems`

### GET /api/admin/promos/{promo_id}
**Auth:** Admin
**Response 200**
- `PromoEventResponseSchema`

### PUT /api/admin/promos/{promo_id}
**Auth:** Super Admin
**Request (PromoEventUpdateSchema)**
**Response 200**
- `PromoEventResponseSchema`

### DELETE /api/admin/promos/{promo_id}
**Auth:** Super Admin
**Response 204**
- empty body

## Settings Management
### GET /api/admin/settings
**Auth:** Super Admin
**Response 200**
Array `SettingSchema`:
- `setting_key`, `setting_value`

### PUT /api/admin/settings
**Auth:** Super Admin
**Request (SettingsUpdateSchema)**
- `settings`: `{ key: value }`

**Response 200**
- `message`

## Action Logs
### GET /api/admin/action-logs
**Auth:** Admin
**Query**: `page`, `itemsPerPage`, `sortBy`, `sortOrder`, `search`, `admin_id`, `target_user_id`, `start_date`, `end_date`
**Response 200**
- `items`: `AdminActionLogResponseSchema[]`
- `totalItems`

### GET /api/admin/action-logs/export
**Auth:** Admin
**Query**: `format=csv|txt`
**Response 200**
- File download (CSV/TXT)

### DELETE /api/admin/action-logs
**Auth:** Super Admin
**Response 200**
- `message`

---

# Lampiran: Enum & Value Penting
- `UserRole`: `USER`, `KOMANDAN`, `ADMIN`, `SUPER_ADMIN`
- `RequestType`: `QUOTA`, `UNLIMITED`
- `RequestStatus`: `PENDING`, `APPROVED`, `PARTIALLY_APPROVED`, `REJECTED`
- `PromoEventStatus`: `DRAFT`, `ACTIVE`, `INACTIVE`
- `PromoEventType`: lihat `PromoEventType` di model
- `Tamping Types`:
  - Tamping luar, Tamping AO, Tamping Pembinaan, Tamping kunjungan, Tamping kamtib
  - Tamping klinik, Tamping dapur, Tamping mesjid, Tamping p2u
  - Tamping BLK, Tamping kebersihan, Tamping Humas, Tamping kebun
