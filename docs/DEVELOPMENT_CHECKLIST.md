# Checklist Pre-Commit (Wajib Dijalankan)

Lampiran wajib:
- [.github/copilot-instructions.md](../.github/copilot-instructions.md)

## A) Aturan Pakai Checklist
- [x] Centang **hanya** item yang benar-benar dijalankan pada PR ini.
- [x] Item yang tidak relevan wajib ditulis `N/A` + alasan singkat (jangan dibiarkan ambigu).
- [x] Hapus checklist lama yang statis/usang; jangan simpan centang historis lintas PR.

## B) Wajib Cepat (Tanpa Build)
- [x] Frontend lint:
  - `cd frontend && pnpm run lint`
- [x] Frontend typecheck:
  - `cd frontend && pnpm run typecheck`
- [x] Frontend focused tests (minimal):
  - `cd frontend && pnpm vitest run tests/auth-access.test.ts tests/auth-guards.test.ts tests/payment-composables.test.ts tests/payment-status-polling.test.ts`
- [x] Backend test:
  - `cd backend && python -m pytest -q`
- [x] OpenAPI contract smoke:
  - `cd backend && python -m pytest -q tests/test_openapi_contract_smoke.py`
- [x] Contract gate:
  - `python scripts/contract_gate.py --base HEAD~1 --head HEAD`
- [x] Infra sanity:
  - `docker compose config`
  - `curl http://127.0.0.1/api/ping`

## C) Build Policy (Kondisional)
- [x] `pnpm run build` **WAJIB** jika:
  - ada perubahan dependensi (`package.json`/lockfile), atau
  - ada perubahan `nuxt.config.ts` / plugin runtime / route SSR kritikal.
- [x] Jika tidak memenuhi kondisi di atas, build boleh `N/A` (hemat waktu pre-commit).
- [x] CI policy:
  - PR: build frontend hanya saat ada perubahan runtime-critical frontend.
  - Push ke `main`: build frontend tetap selalu jalan sebagai final safety gate.

### Matriks Trigger `frontend_build` (CI PR)

| Perubahan | Build CI PR |
|---|---|
| `frontend/pages/**` | Wajib |
| `frontend/components/**` | Wajib |
| `frontend/layouts/**` | Wajib |
| `frontend/middleware/**` | Wajib |
| `frontend/plugins/**` | Wajib |
| `frontend/store/**` | Wajib |
| `frontend/composables/**` | Wajib |
| `frontend/utils/**` | Wajib |
| `frontend/types/**` | Wajib |
| `frontend/app.vue` | Wajib |
| `frontend/nuxt.config.ts` | Wajib |
| `frontend/package.json` / `frontend/pnpm-lock.yaml` | Wajib |
| Hanya `docs/**` | Skip boleh |
| Hanya `backend/**` | Skip boleh |
| Hanya test non-runtime frontend | Skip boleh |

Catatan:
- Jika ragu, pilih aman: jalankan build.
- Meski PR skip build, push/merge ke `main` tetap menjalankan build frontend.

## D) E2E (Direkomendasikan, Tanpa Build Ulang)
- [x] Jalankan E2E isolated tanpa build ulang:
  - `powershell -ExecutionPolicy Bypass -File .\scripts\simulate_end_to_end.ps1 -UseIsolatedCompose true -FreshStart false -Build false -UseOtpBypassOnly true`
- [x] Kriteria lulus E2E:
  - flow mencapai `[17/17]`
  - output akhir memuat `Done`
- [x] Jika perlu reset total environment E2E, jalankan ulang dengan `-FreshStart true`.

## E) QA Manual Inti (Kondisional per Scope)
- [ ] Auth/Captive: OTP regular/bypass sesuai mode yang diubah.
- [ ] Payment: status transaksi (pending/success/failed/cancelled) sesuai scope.
- [ ] Admin flow: approve user + halaman transaksi/admin relevan tetap normal.
- [ ] Backup/Restore/WA test hanya jika PR menyentuh area tersebut.

## F) Dokumentasi PR
- [x] Jika ubah endpoint/signature API: update
  - `contracts/openapi/openapi.v1.yaml`
  - `frontend/types/api/contracts.ts`
  - `docs/API_DETAIL.md`
- [x] Jika ubah alur penting: update doc teknis terkait (`DEVELOPMENT.md`/devlog/ops doc).

## G) Log Eksekusi PR Ini

Tanggal:
- 2026-02-26

Perintah yang dijalankan:
- `cd frontend && pnpm run lint`
- `cd frontend && pnpm run typecheck`
- `cd frontend && pnpm vitest run tests/auth-access.test.ts tests/auth-guards.test.ts tests/payment-composables.test.ts tests/payment-status-polling.test.ts`
- `cd backend && python -m pytest -q`
- `cd backend && python -m pytest -q tests/test_openapi_contract_smoke.py`
- `cd backend && python -m pytest -q tests/test_transactions_debt_settlement_modes.py`
- `python scripts/contract_gate.py --base HEAD~1 --head HEAD`
- `docker compose config`
- `curl http://127.0.0.1/api/ping`
- `powershell -ExecutionPolicy Bypass -File .\\scripts\\simulate_end_to_end.ps1 -UseIsolatedCompose true -FreshStart false -Build false -UseOtpBypassOnly true`

Hasil ringkas:
- Semua check otomatis lulus.
- Targeted debt-settlement backend test lulus (manual + auto path).
- E2E isolated selesai sampai `[17/17]` dengan output akhir `Done`.

Item `N/A` + alasan:
- `pnpm run build`: N/A pada sesi ini (tidak ada perubahan dependency/nuxt config/routing SSR kritikal).
- QA manual inti di Bagian E: N/A pada sesi ini karena validasi difokuskan ke automated checks + E2E isolated (otomatis), tanpa exploratory manual UI tambahan.
