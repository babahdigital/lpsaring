# Instruksi Copilot (lpsaring)

## Gambaran Besar
- Portal hotspot dengan backend Flask (API + Celery) dan frontend Nuxt 3/Vuetify.
- Nginx mem-proxy `/api` ke backend dan `/` ke frontend (lihat infrastructure/nginx/conf.d/app.conf).
- Integrasi utama: MikroTik (RouterOS API), Midtrans (Snap), WhatsApp Fonnte.

## Arsitektur & Alur Data Penting
- Auth & captive flow: login/OTP di backend/app/infrastructure/http/auth_routes.py → frontend/pages/captive/ dan frontend/pages/login/.
- Transaksi: backend/app/infrastructure/http/transactions_routes.py (+ modul `transactions/*`) → Midtrans (Snap/Core API) → webhook update status → apply paket ke MikroTik.
- Admin transaksi: `backend/app/infrastructure/http/admin_routes.py` sekarang delegasi ke `backend/app/infrastructure/http/admin_contexts/*` (backups/notifications/transactions/billing/reports).
- WA invoice: Celery task di backend/app/tasks.py mengirim PDF; URL dibangun dari `APP_PUBLIC_BASE_URL`.
- Walled-garden sync: backend/app/services/walled_garden_service.py → MikroTik; host/IP allowlist wajib di-setting.

## Struktur & Alur Kode
- Backend entry: backend/app/__init__.py (factory `create_app()`), route di backend/app/infrastructure/http/, logika bisnis di backend/app/services/.
- Modular HTTP backend:
	- `backend/app/infrastructure/http/transactions/` untuk lifecycle transaksi (initiation/public/authenticated/webhook/invoice/idempotency/events).
	- `backend/app/infrastructure/http/admin_contexts/` untuk bounded context admin.
- Celery task di backend/app/tasks.py; model SQLAlchemy di backend/app/infrastructure/db/models/.
- Frontend: route di frontend/pages/, layout di frontend/layouts/, state di frontend/store/, composables di frontend/composables/.

## Konfigurasi & ENV
- ENV dipisah:
	- Root `.env.prod` = **konfigurasi produksi** untuk backend/migrate/celery + compose (JANGAN di-commit; upload saat deploy).
	- Root `.env.public.prod` = **konfigurasi produksi frontend** (Nuxt runtime) (JANGAN di-commit; upload saat deploy).
	- Template: `.env.prod.example` / `.env.public.prod.example` ada di repo sebagai referensi variabel.
	- `backend/.env.public` + `backend/.env.local` = overlay khusus DEV (bukan sumber kebenaran produksi).
	- `frontend/.env.*` hanya dipakai jika Nuxt dijalankan di luar Docker (opsional).
- `APP_PUBLIC_BASE_URL` dipakai untuk URL publik (invoice, webhook), wajib HTTPS saat produksi.
- Settings runtime dibaca lewat `settings_service.get_setting()`; nilai DB kosong akan fallback ke ENV.
- Mode OTP-only memakai `IP_BINDING_TYPE_ALLOWED=bypassed` sebagai default.
- Kuota dihitung dari `/ip/hotspot/host` (counter per MAC) karena bypass tidak menghasilkan sesi `/ip/hotspot/active` untuk user.
- Sinkronisasi kuota bersifat **monotonic** (counter host turun dianggap reset, total tetap akumulatif).
- Statistik harian/mingguan/bulanan mengikuti `APP_TIMEZONE` (default `Asia/Makassar`).
- Auto-enroll perangkat dari `/ip/hotspot/ip-binding` (berdasarkan `comment` berisi `user=<id>`), dibatasi `MAX_DEVICES_PER_USER`.
- Debug auto-enroll per MAC hanya jika `AUTO_ENROLL_DEBUG_LOG=True`.
- Walled-garden host/IP diatur via `WALLED_GARDEN_ALLOWED_HOSTS`/`WALLED_GARDEN_ALLOWED_IPS` dan disinkronkan ke MikroTik.
- Midtrans & WA bergantung pada URL publik; gunakan Cloudflare Tunnel (lihat DEVELOPMENT.md bagian HTTPS).

## Sistem Tunggakan Manual (Debt Manual)

### Model `UserQuotaDebt` (tabel `user_quota_debts`)
- `amount_mb`: kuota dalam MB. **Sentinel = 1** untuk paket Unlimited (bukan 0).
- `due_date`: selalu akhir bulan; **auto-compute backend** (`calendar.monthrange`) — tidak boleh diisi manual dari form.
- `price_rp`: harga aktual paket saat debt dibuat (BIGINT NULLABLE). Record lama: null → fallback ke `estimated_rp`.
- `paid_mb`, `is_paid`, `paid_at`: status pelunasan.
- `note`: format `"Paket: {nama} ({kuota}, Rp {harga})"`. Frontend: `parsePackageName(note)` ekstrak nama sebelum ` (`.

### Invariant Kunci
1. **`due_date` selalu akhir bulan** — backend auto-compute; bukan input form admin.
2. **Paket Unlimited → `amount_mb = 1` (sentinel)** — agar `manual_debt_mb > 0` dan EOM block task mendeteksinya.
3. **EOM block tidak bergantung `due_date` per-item** — hanya cek `manual_debt_mb > 0` + tanggal kalender.
4. **WA reminder bergantung `due_date IS NOT NULL`** — record lama diisi via migration `20260319_c_populate_null_due_dates`.
5. **`price_rp` dari paket aktual** — bukan estimasi; jika null, frontend fallback ke `estimated_rp`.
6. **Display tanggal wajib terpusat** — gunakan `format_app_date_display()` / `format_app_datetime_display()` di `backend/app/utils/formatters.py`. Jangan membangun `dd-mm-yyyy` manual dengan slicing string di route/service baru.
7. **JSON aman untuk script** — field raw ISO/`yyyy-mm-dd` boleh tetap ada untuk parse/sort/backward compatibility, tetapi semua payload yang ditampilkan ke user/admin wajib menambahkan field `*_display` dengan format lokal `dd-mm-yyyy` atau `dd-mm-yyyy HH:MM:SS`.

### Alur Tambah Debt (Admin)
```
Admin → UserEditDialog.vue → PUT /api/admin/users/{id}
  → user_profile_service.py:
      is_unlimited = pkg.data_quota_gb <= 0
      amount_mb = 1 if is_unlimited else round(pkg_quota_gb * 1024)
      due_date = last day of debt_month (auto)
      add_manual_debt(amount_mb, due_date, price_rp=int(pkg.price), note=...)
      user.manual_debt_mb += amount_mb
```

### EOM Block Task (`enforce_end_of_month_debt_block_task`)
```
if today == last_day_of_month AND hour >= DEBT_EOM_BLOCK_MIN_HOUR:
  for user where manual_debt_mb > 0 AND quota_debt_total_mb > 0:
    → hard block (ip-binding blocked) + WA notifikasi
```

### WA Reminder Task (`send_manual_debt_reminders_task`)
```
query: is_paid=False AND due_date IS NOT NULL
kirim template 3 hari, 1 hari, 3 jam sebelum due_date
```

### Frontend Key Files (Debt)
- `components/admin/users/UserDebtLedgerDialog.vue` — ledger per-user + `getEffectiveDueDate()` fallback
- `components/admin/users/UserEditDialog.vue` — form tambah tunggakan; dropdown paket termasuk Unlimited
- `pages/riwayat/index.vue` — tampilan riwayat user + `getEffectiveDueDate()` fallback

### Migrations Terkait (urutan)
| Revision | Isi |
|----------|-----|
| `20260315_add_manual_debt_tables` | Buat tabel `user_quota_debts` |
| `20260318_add_due_date_to_manual_quota_debt` | Kolom `due_date DATE` |
| `20260319_add_price_rp_to_user_quota_debts` | Kolom `price_rp BIGINT NULLABLE` |
| `20260319_c_populate_null_due_dates` | Fill `due_date NULL` → last day of debt month |

---

## Operasional & Deploy Produksi (WAJIB Sistematis)
Prinsip: **lokal adalah source-of-truth**, Pi hanya target.

- Jangan edit `.env.prod` / `.env.public.prod` langsung di Pi kecuali emergency. Jika emergency terjadi, perubahan WAJIB disalin balik ke file lokal dan di-deploy ulang agar tidak drift.
- Jangan deploy ke Pi sebelum user meminta.
- Alur rapi (default):
	1) Perubahan code → lint/test lokal
	2) `git commit` → **`git push origin main`** (WAJIB sebelum trigger-build!)
	3) Tunggu CI hijau
	4) Publish image (tag `v*` atau `workflow_dispatch`) → tunggu hijau
	5) Deploy Pi via `deploy_pi.sh --recreate` (upload env lokal + pull image app terbaru + staged restart + healthcheck)

> **⚠ PERINGATAN DEPLOY:** Selalu `git push origin main` DULU sebelum `--trigger-build`.
> GitHub Actions build image dari `origin/main` di GitHub, **bukan** dari commit lokal yang belum di-push.
> Commit yang tidak di-push → build menggunakan image lama → health check tetap hijau tapi kode salah.
> Lihat: `docs/incidents/2026-03-19-deploy-unpushed-commits.md`

## Aturan Keamanan (WAJIB)
- Jangan pernah menampilkan/menyalin secret ke chat/log (contoh: token tunnel, API key, password).
- Hindari perintah yang mencetak secret secara tidak sengaja, misalnya `docker inspect` pada container yang membawa token sebagai argumen.

Catatan workflow publish:
- `.github/workflows/docker-publish.yml` jalan saat push tag `v*` atau manual `workflow_dispatch`.

Referensi:
- `docs/workflows/PRODUCTION_OPERATIONS.md`
- `deploy_pi.sh`
- `docs/workflows/CI_CD.md`

## Kebijakan Device/MAC (OTP, Random MAC)
Tujuan: user tidak “ke-block” setelah OTP sukses walau MAC berubah (privacy/random MAC).

- `REQUIRE_EXPLICIT_DEVICE_AUTH=True` mengaktifkan mekanisme `pending-auth` untuk device baru.
- `OTP_AUTO_AUTHORIZE_DEVICE=True` (default) berarti **OTP sukses = user mengotorisasi device yang sedang dipakai**, sehingga tidak masuk `pending-auth` pada jalur OTP.
- Pengecualian: jika login memakai `OTP_BYPASS_CODE`, auto-authorize tidak dilakukan (lebih aman).

## Kebijakan DHCP Static Lease (Anti Putus-Nyambung)
- Jika `MIKROTIK_DHCP_STATIC_LEASE_ENABLED=True`, WAJIB set `MIKROTIK_DHCP_LEASE_SERVER_NAME` ke DHCP server hotspot utama (mis. `Klien`).
- Backend versi terbaru tidak akan menulis lease managed `lpsaring|static-dhcp` tanpa pin server, dan tidak akan mengupdate lease milik server lain.

## Dokumentasi Wajib
- Setiap dokumen teknis yang diperbarui **wajib menyertakan tautan lampiran** ke `.github/copilot-instructions.md` sebagai pondasi pengembangan (dokumen ini tidak perlu melampirkan dirinya sendiri).

## Workflow Dev (Disarankan)
- Jalankan stack: `docker compose up -d`.
- Lihat log: `docker compose logs -f backend|frontend|nginx`.
- Lint backend: `docker compose exec -T backend ruff check .` (config di backend/ruff.toml).
- Lint frontend: `docker compose exec frontend pnpm run lint`.
- Focused frontend tests (auth + payment):
	- `docker compose exec frontend pnpm run test -- tests/auth-access.test.ts tests/auth-guards.test.ts tests/payment-composables.test.ts tests/payment-status-polling.test.ts`
- Smoke kontrak OpenAPI backend:
	- `docker compose exec -T backend python -m pytest backend/tests/test_openapi_contract_smoke.py -q`

Catatan:
- CI mem-validasi backend dengan `python -m ruff check backend` (ruff error seperti F401 harus bersih sebelum deploy).
- Jika menjalankan lint/test dari host (venv lokal), pastikan hasilnya sama dengan container/CI.

Catatan VS Code (opsional):
- Boleh jalankan `pnpm install` di host (folder `frontend/`) agar TypeScript/Vue language features terbaca tanpa error di editor.
- Source of truth untuk lint/typecheck/test tetap dari container.

## Aturan Wajib Saat Mengubah Kode
- Jika mengubah file backend (backend/**), WAJIB jalankan: `docker compose exec -T backend ruff check .`.
- Jika mengubah file frontend (frontend/**), WAJIB jalankan: `docker compose exec frontend pnpm run lint`.
- Jika mengubah keduanya, jalankan kedua lint di atas.
- Jika mengubah flow payment/auth frontend, WAJIB jalankan focused frontend tests auth+payment.
- Jika mengubah signature endpoint prioritas (`backend/app/infrastructure/http/**`), WAJIB sinkronkan:
	- `contracts/openapi/openapi.v1.yaml`
	- `frontend/types/api/contracts.ts`
	- `docs/API_DETAIL.md`
- Semua perintah dev dijalankan di container agar konsisten (lihat DEVELOPMENT.md).
- Setiap perubahan perilaku/flow WAJIB update dokumentasi yang relevan (minimal docs/REFERENCE_PENGEMBANGAN.md dan/atau DEVELOPMENT.md) agar tidak ada kebingungan.

Aturan deploy:
- Jangan deploy bila CI belum hijau.
- Jangan “patch cepat” di Pi (manual SSH edit). Gunakan `deploy_pi.sh` agar idempotent.

## Konvensi Proyek
- Backend: hindari one-liner control flow; gunakan `is None`/`is not None`, bukan `== None`.
- Frontend: jangan hardcode URL; gunakan runtime config/ENV (`NUXT_PUBLIC_*`).
- Perubahan terkait captive/auto-login ada di backend/app/infrastructure/http/auth_routes.py dan frontend/pages/captive/.

## Contoh Lokasi Kunci
- MikroTik client: backend/app/infrastructure/gateways/mikrotik_client.py.
- Settings & enkripsi: backend/app/services/settings_service.py.
- Walled garden: backend/app/services/walled_garden_service.py.
- Finish payment: frontend/pages/payment/finish.vue.

## Referensi Teknis
- Docs umum: README.md, DEVELOPMENT.md, PROJECT_OVERVIEW.md.
- Integrasi: docs/REFERENCE_PENGEMBANGAN.md, docs/workflows/PRODUCTION_OPERATIONS.md.
