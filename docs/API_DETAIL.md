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
- `POST /api/admin/users/{user_id}/quota-adjust` — Koreksi langsung `total_quota_purchased_mb` dan/atau `total_quota_used_mb`. **Khusus Super Admin.** Body: `{ set_purchased_mb?: int, set_used_mb?: int, reason: string }`. Minimal satu dari keduanya wajib ada. Dicatat di `quota_mutation_ledger` dengan source `quota.adjust_direct`.
- `POST /api/admin/users/seed-imported-update-submissions` — Seed `PublicDatabaseUpdateSubmission` records for users with `full_name LIKE 'Imported %'` agar mereka mendapat notifikasi WA untuk update data. Body opsional: `test_phone` (string), `dry_run` (bool).
- `GET /api/admin/update-submissions`
- `POST /api/admin/update-submissions/{id}/approve`
- `POST /api/admin/update-submissions/{id}/reject`

### 5.1) Public Update Submission
- `POST /api/users/database-update-submissions` — Submit form pemutakhiran data. Memerlukan feature flag `PUBLIC_DB_UPDATE_FORM_ENABLED=true`.
- `GET /api/users/database-update-submissions/status?phone=<string>` — Cek status submission berdasarkan nomor HP. Publik, tanpa autentikasi. Response: `{ success: boolean, status: "none" | "reviewing" | "approved" }`.

### 6) Admin Transactions
- `GET /api/admin/transactions`
- `GET /api/admin/transactions/{order_id}/detail`
- `POST /api/admin/transactions/{order_id}/reconcile` — Verifikasi ke Midtrans & perbaiki transaksi EXPIRED/FAILED jika sudah lunas. Membutuhkan role admin. Response: `{ message, transaction_status, midtrans_status, quota_applied, whatsapp_sent }`.

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

## Addendum 2026-03-02
- Public update workflow (`POST /api/users/database-update-submissions` + admin update-submissions approve/reject) dipertegas sebagai alur staging→approval (bukan auto-mutate user role).
- Dokumentasi env update form diselaraskan:
  - backend gate: `PUBLIC_DB_UPDATE_FORM_ENABLED`
  - frontend gate: `NUXT_PUBLIC_PUBLIC_DB_UPDATE_FORM_ENABLED` dengan fallback `NUXT_PUBLIC_DB_UPDATE_FORM_ENABLED`.
- Frontend compatibility fix untuk halaman update diselesaikan agar template typecheck tetap valid pada tombol kembali login (handler internal dipakai, bukan pemanggilan langsung di template).

## Addendum 2026-03-09
- Tambah endpoint `POST /api/admin/users/{user_id}/quota-adjust` untuk koreksi kuota langsung oleh Super Admin. Endpoint menimpa nilai `total_quota_purchased_mb` dan/atau `total_quota_used_mb` secara langsung dengan audit trail penuh di `quota_mutation_ledger`. Ini adalah endpoint operasional (bukan consumer — tidak ada di v1 public contract sebelumnya).
- Perbaikan kebijakan debt: `set_user_unlimited()` kini hanya menghapus auto-debt via offset, manual debt (`manual_debt_mb`) dipertahankan. Test `test_stress_race_manual_debt_then_set_unlimited_invariants` diperbarui untuk mencerminkan kebijakan baru ini.
- Fix insiden quota drain (lock_ttl=120→3600 di `sync_hotspot_usage_task`) — lihat `docs/DEVLOG_2026-03-09_QUOTA_DRAIN_INCIDENT.md`.
