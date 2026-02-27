# OpenAPI Contract Workflow (Auth/Profile/Devices/Transactions)

Lampiran wajib:
- [.github/copilot-instructions.md](../.github/copilot-instructions.md)

## Tujuan

Mencegah drift kontrak Backend ↔ Frontend pada flow kritikal dengan satu sumber kebenaran yang eksplisit.

## Source of Truth

- OpenAPI utama:
  - `contracts/openapi/openapi.v1.yaml`
- Typed contract frontend (sinkron manual bertahap):
  - `frontend/types/api/contracts.generated.ts` (generated)
  - `frontend/types/api/contracts.ts` (compatibility aliases)

## Aturan Update

1. **Perubahan endpoint prioritas wajib mulai dari OpenAPI**
  - Tambah/ubah field request/response dulu di `contracts/openapi/openapi.v1.yaml`.
2. **Lalu generate typed contract frontend**
  - Jalankan: `python scripts/generate_ts_contracts_from_openapi.py`
  - File output: `frontend/types/api/contracts.generated.ts`
  - `frontend/types/api/contracts.ts` hanya layer alias kompatibilitas.
3. **Baru ubah implementasi backend/frontend**
   - Implementasi harus mengikuti kontrak, bukan sebaliknya.
4. **Dokumentasi endpoint ringkas tetap di-maintain**
  - `docs/API_DETAIL.md` sebagai indeks contract-driven.
  - Detail operasional/edge-case dipindah ke `docs/API_DETAIL_OPS_ADDENDUM.md`.

## CI Gate (Wajib)

Workflow CI menjalankan gate otomatis (`scripts/contract_gate.py`) dengan aturan:

- Jika ada perubahan signature endpoint prioritas (deteksi perubahan `@...route(...)` di `backend/app/infrastructure/http/**`), maka PR **wajib** mengubah:
  1. `contracts/openapi/openapi.v1.yaml`
  2. `frontend/types/api/contracts.generated.ts`
  3. `frontend/types/api/contracts.ts`
  4. `docs/API_DETAIL.md`

- Jika salah satu tidak berubah, CI akan fail.

Tambahan enforcement yang aktif:
- Backend smoke test kontrak: `backend/tests/test_openapi_contract_smoke.py` memvalidasi path + method prioritas tetap ada di `contracts/openapi/openapi.v1.yaml`.
- API quality gate: `scripts/api_quality_gate.py` memvalidasi:
  - cakupan path prioritas,
  - konsistensi response `401` untuk endpoint secured,
  - `ErrorResponse` wajib `code` + `message`,
  - sinkronisasi hash OpenAPI vs `contracts.generated.ts`.

Catatan implementasi terbaru (2026-02-27):
- Perhitungan hash source OpenAPI telah dinormalisasi lintas OS (newline `CRLF`/`LF`) di:
  - `scripts/generate_ts_contracts_from_openapi.py`
  - `scripts/api_quality_gate.py`
- Tujuan: mencegah false mismatch hash saat generate di Windows tetapi diverifikasi di Linux runner CI.
- Frontend focused tests di CI kini mencakup auth + payment composables:
  - `tests/auth-access.test.ts`
  - `tests/auth-guards.test.ts`
  - `tests/payment-composables.test.ts`
  - `tests/payment-status-polling.test.ts`
- CI mem-publish manifest daftar focused test ke `GITHUB_STEP_SUMMARY` melalui variabel `FOCUSED_FRONTEND_TESTS`.

## Scope v1 (aktif)

- Auth:
  - register, request-otp, verify-otp, session/consume, auth/me, auth/me/profile
- Profile:
  - users/me/profile
- Devices:
  - users/me/devices, bind-current, update label, delete
- Transactions:
  - initiate, debt/initiate, by-order-id, public/by-order-id, cancel, public/cancel, qr, public/qr

## Catatan Kompatibilitas

- Kontrak ini disusun **additive-first** agar aman untuk migrasi bertahap.
- Untuk field legacy yang masih dipakai frontend lama, pertahankan sampai fase cleanup disetujui.
- Error envelope standar (`code`, `message`, `details`, `request_id`) adalah target konsolidasi bertahap.

## Checklist PR Kontrak

- [ ] OpenAPI diupdate
- [ ] Typed contract frontend diupdate
- [ ] Endpoint/backend implementation diupdate (jika diperlukan)
- [ ] Frontend consumer terdampak diupdate
- [ ] Docs ringkas (`API_DETAIL`) disesuaikan
- [ ] Jika ada catatan runtime/ops, update `API_DETAIL_OPS_ADDENDUM`

## Troubleshooting cepat (kasus riil)

### 1) `Generated contracts out of date`

Gejala:
- `scripts/api_quality_gate.py` fail dengan pesan generated contract tidak sinkron.

Langkah:
1. Jalankan `python scripts/generate_ts_contracts_from_openapi.py`.
2. Commit perubahan `frontend/types/api/contracts.generated.ts`.
3. Jalankan ulang `python scripts/api_quality_gate.py`.

### 2) Mismatch hash lintas OS (Windows vs Linux)

Gejala:
- Lokal PASS, CI tetap FAIL di sinkronisasi hash OpenAPI.

Akar masalah:
- beda newline (`CRLF` vs `LF`) mempengaruhi hash byte-level.

Status penyelesaian:
- sudah diperbaiki permanen dengan normalisasi newline sebelum hashing di generator + gate script.
