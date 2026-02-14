# Struktur Proyek (lpsaring)

Dokumen ini menjelaskan struktur folder utama agar navigasi kode lebih cepat.

Lampiran wajib:
- [.github/copilot-instructions.md](../.github/copilot-instructions.md)

## 1) Root
- backend/: API Flask + SQLAlchemy + migrasi + Celery.
- frontend/: Nuxt 3 + Vue 3 + Vuetify.
- infrastructure/: konfigurasi Nginx dan deployment.
- docs/: dokumentasi tambahan.

## 2) Backend (backend/)
- app/__init__.py: factory aplikasi, register blueprint.
- app/infrastructure/http/: route API dan schema request/response.
- app/infrastructure/db/: model SQLAlchemy.
- app/services/: logika bisnis (approval, profile, transaksi, dsb).
- app/tasks.py: Celery tasks.
- migrations/: Alembic revisions.
- run.py: entrypoint aplikasi.

## 3) Frontend (frontend/)
- pages/: route Nuxt (halaman UI).
- components/: komponen UI reusable.
- layouts/: layout global.
- store/: Pinia stores.
- composables/: helper fetch, snackbar, dsb.
- plugins/: setup Vuetify, icon adapter.
- types/: kontrak data frontend.
- utils/: helper utilitas.

## 4) Alur penting
- Registrasi: frontend/pages/login → backend/auth/register.
- Tamping: validasi di backend + tampilan di login, admin user dialog, akun.
- Approval admin: backend user approval + frontend admin/users.
- Transaksi: backend transactions + frontend pages/payment, pages/riwayat.

## 5) Dokumen terkait
- DEVELOPMENT.md: panduan dev lengkap.
- PROJECT_OVERVIEW.md: ringkasan proyek.
- docs/MIDTRANS_SNAP.md: integrasi Midtrans.
- docs/DOKUMENTASI_WHATSAPP_FONNTE.md: integrasi WhatsApp.
- .github/copilot-instructions.md: pondasi aturan pengembangan.
