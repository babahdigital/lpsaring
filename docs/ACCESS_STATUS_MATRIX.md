# Access Status Matrix (Canonical)

Dokumen ini adalah sumber kebenaran tunggal status akses user lintas backend, frontend, docs, dan runbook.

## Status Enum
- `ok`
- `blocked`
- `inactive`
- `expired`
- `habis`
- `fup`

## Definisi
- `ok`: status frontend untuk user aktif normal **atau** unlimited yang belum expired.
- `blocked`: diblokir manual/admin atau policy debt limit.
- `inactive`: belum approved atau nonaktif.
- `expired`: masa aktif lewat (`quota_expiry_date < now`).
- `habis`: kuota habis (`purchased <= 0` atau `remaining <= 0`).
- `fup`: user masih aktif namun profile FUP diterapkan.

## Prioritas Resolusi (deterministik)
1. `blocked`
2. `inactive`
3. `expired`
4. `ok` (khusus unlimited/admin bypass)
5. `habis`
6. `fup`
7. `ok`

## Referensi Implementasi
- Backend resolver utama: `backend/app/services/access_policy_service.py`
- Backend constants/type: `backend/app/utils/access_status.py`
- Frontend type: `frontend/types/accessStatus.ts`
- Frontend resolver: `frontend/utils/authAccess.ts`
- Route policy: `frontend/utils/authRoutePolicy.ts`
- Status token auth: `backend/app/infrastructure/http/auth_routes.py`
- Parity contract: `contracts/access_status_parity_cases.json`

## Route Mapping
- Canonical status route (semua context):
  - `blocked -> /policy/blocked`
  - `inactive -> /policy/inactive`
  - `expired -> /policy/expired`
  - `habis -> /policy/habis`
  - `fup -> /policy/fup`
- Legacy compatibility (redirect otomatis via Nuxt routeRules):
  - `/login/{blocked|inactive|expired|habis|fup} -> /policy/*`
  - `/captive/{blokir|inactive|expired|habis|fup} -> /policy/*`
