# API Detail (Contract-Driven)

Dokumen ini sekarang menjadi **ringkasan semigenerated** dari kontrak API prioritas.

Sumber kebenaran utama:
- `contracts/openapi/openapi.v1.yaml`
- `frontend/types/api/contracts.generated.ts`

Lampiran wajib:
- [.github/copilot-instructions.md](../.github/copilot-instructions.md)

## Tujuan Dokumen
- Menyediakan peta endpoint prioritas yang mudah dibaca tim ops/dev.
- Menegaskan bahwa detail request/response harus mengikuti kontrak OpenAPI.
- Menghindari drift FE-BE dari dokumentasi manual yang panjang.

## Scope Endpoint Prioritas (v1)

### 1) Auth
- `POST /api/auth/register`
- `POST /api/auth/request-otp`
- `POST /api/auth/verify-otp`
- `POST /api/auth/auto-login`
- `GET /api/auth/hotspot-session-status`
- `POST /api/auth/session/consume`
- `GET /api/auth/me`
- `PUT /api/auth/me/profile`

### 2) User Profile
- `GET /api/users/me/profile`
- `PUT /api/users/me/profile`

### 3) Devices
- `GET /api/users/me/devices`
- `POST /api/users/me/devices/bind-current`
- `PUT /api/users/me/devices/{device_id}/label`
- `DELETE /api/users/me/devices/{device_id}`

### 4) Transactions
- `POST /api/transactions/initiate`
- `POST /api/transactions/debt/initiate`
- `GET /api/transactions/by-order-id/{order_id}`
- `GET /api/transactions/public/by-order-id/{order_id}`
- `POST /api/transactions/{order_id}/cancel`
- `POST /api/transactions/public/{order_id}/cancel`
- `GET /api/transactions/{order_id}/qr`
- `GET /api/transactions/public/{order_id}/qr`

### 5) Admin Users
- `GET /api/admin/users`
- `POST /api/admin/users`
- `PUT /api/admin/users/{user_id}`

### 6) Admin Transactions
- `GET /api/admin/transactions`
- `GET /api/admin/transactions/{order_id}/detail`

### 7) Admin Settings
- `GET /api/admin/settings`
- `PUT /api/admin/settings`

### 8) Admin Requests
- `GET /api/admin/quota-requests`
- `POST /api/admin/quota-requests/{request_id}/process`

### 9) Admin Metrics
- `GET /api/admin/metrics`
- `GET /api/admin/metrics/access-parity`
- `POST /api/admin/metrics/access-parity/fix`

## Konvensi Error (Target Konsolidasi)
- Gunakan envelope standar:
  - `code`
  - `message`
  - `details` (opsional)
  - `request_id` (opsional)

Catatan:
- Endpoint legacy yang belum sepenuhnya konsisten harus dimigrasi bertahap.
- PR yang mengubah endpoint prioritas wajib menyertakan update kontrak + typed contract + dokumen ini.

## Addendum Operasional
Untuk detail operasional, edge-case, dan catatan implementasi runtime (yang tidak cocok disimpan di kontrak formal), lihat:
- `docs/API_DETAIL_OPS_ADDENDUM.md`

## Rule Update Wajib (CI Gate)
Jika ada perubahan signature endpoint prioritas (route/path/method), PR harus mengubah:
1. `contracts/openapi/openapi.v1.yaml`
2. `frontend/types/api/contracts.generated.ts`
3. `frontend/types/api/contracts.ts`
4. `docs/API_DETAIL.md`

CI akan gagal jika syarat ini tidak terpenuhi.

## Addendum 2026-02-26
- Batch hardening transaksi/payment melakukan refactor internal wiring dan pemecahan concern frontend.
- Tidak ada perubahan signature endpoint prioritas (path/method tetap).
- Sinkronisasi dokumen ini, OpenAPI, dan typed contract dilakukan untuk memenuhi contract gate CI.

## Addendum 2026-02-28
- Auth/captive flow diperluas dengan endpoint verifikasi sesi hotspot realtime: `GET /api/auth/hotspot-session-status`.
- Flow auto-login (`POST /api/auth/auto-login`) sekarang diwajibkan melewati trusted identity path:
  - IP klien harus berada dalam `HOTSPOT_CLIENT_IP_CIDRS`,
  - MAC authoritative diambil dari router (bukan authority dari payload mentah),
  - mismatch `client_mac` request vs MAC router ditolak hard.
- Flow verify OTP mempertahankan prinsip tidak memetakan user dari active-session by-IP; keputusan hotspot-required memakai state ip-binding ownership user.
