# Vuexy Baseline Strategy (Upgrade-Safe)

Dokumen ini mendefinisikan batas aman antara baseline Vuexy dan custom Nuxt di proyek ini.

## Baseline vs Custom
- Baseline referensi: `typescript-version/full-version` (Vite SPA) hanya sebagai _design/layer reference_.
- Runtime aktif: `lpsaring/frontend` (Nuxt 3 SSR) adalah implementasi produksi.

## Boundary
- **Core template area (adopted & maintained):**
  - `frontend/@core/**`
  - `frontend/@layouts/**`
  - `frontend/assets/styles/**`
- **Custom domain area (produk):**
  - `frontend/pages/**`
  - `frontend/components/**`
  - `frontend/composables/**`
  - `frontend/store/**`
  - `frontend/plugins/api.ts`

## Upgrade Rule
1. Jangan import runtime langsung dari `typescript-version/full-version` atau `starter-kit`.
2. Adaptasi template harus melalui copy terkontrol ke `frontend/@core` atau `frontend/@layouts`.
3. Setiap perubahan major pada `@core/@layouts` wajib diuji lint+typecheck+focused tests.
4. Jika sinkronisasi dengan baseline dibutuhkan, dokumentasikan delta di PR.

## Enforcement
- Script: `scripts/enforce_ui_standards.py`
- Rule saat ini memblok referensi lintas-folder ke baseline runtime.
