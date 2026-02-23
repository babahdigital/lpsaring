# Ringkasan API (High-Level)

Dokumen ini ringkas dan fokus pada modul inti. Untuk detail lengkap, lihat source di backend/app/infrastructure/http/.

Lampiran wajib:
- [.github/copilot-instructions.md](../.github/copilot-instructions.md)

## 1) Auth
- POST /auth/register
  - Registrasi user (tamping atau non‑tamping).
- POST /auth/request-otp
- POST /auth/verify-otp
- POST /auth/auto-login
- POST /auth/session/consume
- POST /auth/admin/login
- GET /auth/me
- PUT /auth/me/profile
- POST /auth/me/change-password

## 1.1) Devices (Self-service, User)
- GET /users/me/devices
- POST /users/me/devices/bind-current
- PUT /users/me/devices/{id}/label
- DELETE /users/me/devices/{id}

## 2) User Management (Admin)
- GET /admin/users
- POST /admin/users
- PUT /admin/users/{id}
- PATCH /admin/users/{id}/approve
- POST /admin/users/{id}/reject
- POST /admin/users/{id}/reset-hotspot-password
- POST /admin/users/{id}/generate-admin-password

## 3) Quota Requests
- GET /komandan/requests/history
- POST /komandan/requests
- GET /admin/quota-requests
- POST /admin/quota-requests/{id}/process

## 4) Packages & Transactions
- GET /packages
- POST /transactions/initiate
- POST /transactions/debt/initiate
- GET /transactions/by-order-id/{order_id}
- POST /transactions/{order_id}/cancel
- GET /transactions/{order_id}/invoice
- GET /transactions/{order_id}/qr
- GET /admin/transactions
- GET /admin/transactions/export

## 4.1) Admin – Buat Tagihan (User tertentu)
- POST /admin/transactions/bill
  - Alias kompatibilitas: POST /admin/transactions/qris

## 5) Maintenance & Misc
- GET /admin/dashboard/stats
- GET /admin/form-options/alamat

## Catatan
- Field tamping: is_tamping (boolean), tamping_type (string, wajib jika is_tamping true).
- Non‑tamping: blok + kamar wajib.
