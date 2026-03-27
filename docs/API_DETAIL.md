# API Detail

Dokumen ini adalah ringkasan kontrak API yang paling sering berubah dan wajib diperbarui ketika signature endpoint prioritas berubah.

Lampiran wajib:
- [.github/copilot-instructions.md](../.github/copilot-instructions.md)

## Source Of Truth

- Spesifikasi utama: `contracts/openapi/openapi.v1.yaml`
- Typed contract frontend: `frontend/types/api/contracts.generated.ts` dan `frontend/types/api/contracts.ts`
- Gate CI: `scripts/api_quality_gate.py`, `scripts/access_status_parity_gate.py`, dan `scripts/contract_gate.py`

Perubahan endpoint prioritas dianggap lengkap hanya jika keempat artefak berikut bergerak bersama:

1. Implementasi backend
2. OpenAPI
3. Typed contract frontend
4. Dokumen ini

## Aturan Kontrak Bersama

- Endpoint yang butuh autentikasi harus punya response `401` di OpenAPI.
- Error envelope tetap memakai `ErrorResponse` dengan field wajib `code` dan `message`.
- Endpoint publik tidak boleh memaksa frontend mengirim secret server-side.
- Endpoint admin tetap berada di bawah namespace `/admin/**` dan harus divalidasi dengan guard role terkait.
- `GET /settings/payment-availability` harus tetap `no-store`, tidak butuh autentikasi, dan menjadi source of truth UI untuk disable banner/tombol beli saat circuit breaker Midtrans terbuka.

## Endpoint Prioritas

### Auth

- `POST /auth/register`
- `POST /auth/request-otp`
- `POST /auth/verify-otp`
- `POST /auth/auto-login`
- `POST /auth/admin/login`
- `POST /auth/status-token/verify`
- `POST /auth/session/consume`
- `GET /auth/me`
- `GET /auth/me/profile`

### User self-service

- `GET /users/me/profile`
- `GET /users/me/quota-debts`
- `GET /users/me/devices`
- `POST /users/me/devices/bind-current`
- `DELETE /users/me/devices/{device_id}`
- `PATCH /users/me/devices/{device_id}/label`

### Transactions

- `POST /transactions/initiate`
- `POST /transactions/debt/initiate`
- `GET /transactions/by-order-id/{order_id}`
- `GET /transactions/public/by-order-id/{order_id}`
- `POST /transactions/{order_id}/cancel`
- `POST /transactions/public/{order_id}/cancel`
- `GET /transactions/{order_id}/qr`
- `GET /transactions/public/{order_id}/qr`

### Public settings

- `GET /settings/payment-availability`

### Admin

- `GET /admin/users`
- `GET /admin/users/{user_id}`
- `GET /admin/users/{user_id}/mikrotik-status`
- `GET /admin/users/{user_id}/detail-summary`
- `GET /admin/users/{user_id}/detail-report/export?format=pdf`
- `POST /admin/users/{user_id}/detail-report/send-whatsapp`
- `GET /admin/users/detail-report/temp/{token}.pdf`
- `GET /admin/users/{user_id}/debts`
- `POST /admin/users/{user_id}/debts/{debt_id}/settle`
- `POST /admin/users/{user_id}/debts/settle-all`
- `POST /admin/users/{user_id}/debts/send-whatsapp`
- `POST /admin/users/{user_id}/reset-login`
- `POST /admin/users/{user_id}/reset-password`
- `GET /admin/users/debts/temp/{token}.pdf`
- `GET /admin/users/debt-settlements/temp/{token}.pdf`
- `GET /admin/settings`
- `GET /admin/quota-requests`
- `POST /admin/quota-requests/{request_id}/process`
- `GET /admin/transactions`
- `POST /admin/transactions/bill`
- `GET /admin/transactions/{order_id}/detail`
- `GET /admin/mikrotik/verify-rules`

## Pola Sinkronisasi

Jika signature endpoint berubah, lakukan urutan ini:

1. Perbarui route, schema, dan service backend.
2. Perbarui `contracts/openapi/openapi.v1.yaml`.
3. Regenerasi typed contract frontend.
4. Sesuaikan pemakaian frontend, test, dan dokumen ini.
5. Jalankan gate lokal atau CI yang relevan.

## Validasi Lokal Yang Disarankan

- `python scripts/api_quality_gate.py`
- `python scripts/contract_gate.py --base HEAD~1 --head HEAD`
- `docker compose exec -T backend python -m pytest backend/tests/test_openapi_contract_smoke.py -q`

## Catatan Fitur Detail Pengguna Admin

- `GET /admin/users/{user_id}/mikrotik-status` mengembalikan hasil live check/sinkron terakhir MikroTik plus ringkasan kuota database yang dipakai dialog admin.
- `GET /admin/users/{user_id}/detail-summary` adalah source of truth untuk pill status/profile/dialog detail admin. Frontend tidak boleh menebak fallback profile sendiri bila response ini tersedia.
- `GET /admin/users/{user_id}/detail-report/export?format=pdf` menghasilkan PDF detail operasional user.
- `POST /admin/users/{user_id}/detail-report/send-whatsapp` menerima `recipient_mode=user|internal`. Mode `user` akan mengirim ke nomor pengguna, sedangkan mode `internal` wajib menyertakan `recipient_user_ids` agar PDF hanya dikirim ke admin/super admin yang dipilih.
- `POST /admin/users/{user_id}/detail-report/send-whatsapp` mengembalikan `queued_count`, `recipient_mode`, dan daftar `recipients` agar frontend bisa menampilkan siapa yang benar-benar menerima kiriman.
- `GET /admin/users/detail-report/temp/{token}.pdf` adalah URL publik sementara untuk attachment PDF detail pengguna yang dikirim ke WhatsApp. Jika token invalid/kedaluwarsa, endpoint akan menampilkan halaman HTML yang mudah dipahami pengguna, bukan raw JSON.

Workflow lengkap kontrak ada di [docs/workflows/OPENAPI_CONTRACT.md](workflows/OPENAPI_CONTRACT.md).