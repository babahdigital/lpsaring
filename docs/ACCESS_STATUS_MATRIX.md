# Access Status Matrix

Dokumen ini adalah sumber kebenaran tunggal status akses user lintas backend, frontend, test contract, dan runbook operasional.

Lampiran wajib:
- [.github/copilot-instructions.md](../.github/copilot-instructions.md)

## Status Enum

- `ok`
- `blocked`
- `inactive`
- `expired`
- `habis`
- `fup`

## Definisi

- `ok`: user aktif normal atau unlimited yang belum expired.
- `blocked`: diblokir manual/admin atau terkena policy debt-limit.
- `inactive`: belum approved atau nonaktif.
- `expired`: masa aktif lewat.
- `habis`: kuota habis atau remaining mencapai nol.
- `fup`: user masih aktif tetapi sudah memakai profile FUP.

## Prioritas Resolusi

1. `blocked`
2. `inactive`
3. `expired`
4. `ok` untuk unlimited/admin bypass
5. `habis`
6. `fup`
7. `ok`

## Route Mapping

- `blocked -> /policy/blocked`
- `inactive -> /policy/inactive`
- `expired -> /policy/expired`
- `habis -> /policy/habis`
- `fup -> /policy/fup`

Legacy path tetap boleh redirect otomatis, tetapi canonical route tetap berada di bawah `/policy/*`.

## Enforcement Hotspot

- `blocked`: profile blocked dan address-list blocked, tetapi ip-binding device tidak di-hard-block secara broad.
- `inactive`: tidak boleh dianggap aktif jaringan.
- `expired`: profile expired dan status page expired.
- `habis`: profile habis, payment tetap harus bisa diakses sesuai walled-garden.
- `fup`: profile FUP tanpa mengubah definisi user menjadi nonaktif.

## Referensi Implementasi

- Backend resolver: `backend/app/services/access_policy_service.py`
- Backend enum dan ordering: `backend/app/utils/access_status.py`
- Frontend enum: `frontend/types/accessStatus.ts`
- Frontend resolver: `frontend/utils/authAccess.ts`
- Frontend route policy: `frontend/utils/authRoutePolicy.ts`
- Contract cases: `contracts/access_status_parity_cases.json`
- Gate parity: `scripts/access_status_parity_gate.py`

## Aturan Perubahan

- Jangan menambah status baru tanpa memperbarui backend, frontend, kontrak test, dan dokumen ini sekaligus.
- Perubahan policy status wajib ditinjau bersama [docs/REFERENCE_PENGEMBANGAN.md](REFERENCE_PENGEMBANGAN.md) dan [docs/workflows/PRODUCTION_OPERATIONS.md](workflows/PRODUCTION_OPERATIONS.md).