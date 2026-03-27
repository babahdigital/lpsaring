# Referensi Pengembangan

Dokumen ini merangkum aturan pengembangan aktif, integrasi utama, dan checklist validasi sebelum perubahan dianggap siap.

Lampiran wajib:
- [.github/copilot-instructions.md](../.github/copilot-instructions.md)

## Jalur Kerja Harian

### Local stack

- Jalankan dev stack: `docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d`
- Lihat log: `docker compose logs -f backend frontend nginx`
- Hentikan stack: `docker compose -f docker-compose.yml -f docker-compose.dev.yml down`

### Validasi minimum

- Backend lint: `docker compose exec -T backend ruff check .`
- Frontend lint: `docker compose exec frontend pnpm run lint`
- Frontend typecheck: `docker compose exec frontend pnpm run typecheck` (script memuat `frontend/.env.local` agar guard `NUXT_PUBLIC_*` tetap terpenuhi saat validasi lokal)
- Backend tests: `docker compose exec -T backend python -m pytest backend/tests`
- Focused frontend tests auth/payment:
  `docker compose exec frontend pnpm run test -- tests/auth-access.test.ts tests/auth-guards.test.ts tests/access-status-parity.contract.test.ts tests/payment-composables.test.ts tests/payment-status-polling.test.ts`

### Validasi fokus hotspot sync

- Focused backend tests hotspot sync:
  `docker compose exec -T backend python -m pytest backend/tests/test_tasks_hotspot_usage_sync.py backend/tests/test_hotspot_sync_address_list_status.py backend/tests/test_hotspot_sync_debt_limit.py backend/tests/test_mikrotik_remove_hotspot_host_entries_best_effort.py`
- Focused lint hotspot sync:
  `docker compose exec -T backend ruff check backend/app/tasks.py backend/app/services/hotspot_sync_service.py backend/app/services/device_management_service.py backend/app/infrastructure/gateways/mikrotik_client.py backend/tests/test_tasks_hotspot_usage_sync.py backend/tests/test_hotspot_sync_address_list_status.py backend/tests/test_hotspot_sync_debt_limit.py backend/tests/test_mikrotik_remove_hotspot_host_entries_best_effort.py`

### Validasi fokus hotspot portal trust

- Focused frontend tests hotspot trust:
  `docker compose exec frontend pnpm run test -- tests/hotspot-trust.test.ts tests/hotspot-identity.test.ts tests/auth-middleware.runtime.test.ts tests/hotspot-login-targets.test.ts tests/hotspot-post-login-bridge.test.ts`
- Focused frontend lint hotspot trust:
  `docker compose exec frontend pnpm exec eslint middleware/auth.global.ts pages/captive/index.vue pages/login/index.vue pages/login/hotspot-required.vue store/auth.ts utils/hotspotIdentity.ts utils/hotspotTrust.ts tests/hotspot-trust.test.ts tests/hotspot-identity.test.ts tests/auth-middleware.runtime.test.ts`
- Jika perubahan menyentuh `runtimeConfig.public`, frontend typecheck tetap wajib dijalankan penuh.

## Kepemilikan File Env

- Root `.env`: interpolation Compose dan secret lintas service yang tidak dipublikasi.
- Root `.env.public` atau `.env.public.prod`: runtime config publik untuk frontend container.
- Root `.env.prod`: source of truth produksi untuk backend, migrate, Celery, dan Compose produksi.
- `backend/.env.local` dan `backend/.env.public`: overlay dev lokal. Jangan jadikan sumber kebenaran produksi.
- `frontend/.env.*`: hanya dipakai bila Nuxt dijalankan di luar Docker.

Variabel yang paling sensitif terhadap perilaku runtime:

- `APP_PUBLIC_BASE_URL`: URL publik untuk invoice, webhook, dan redirect.
- `IP_BINDING_TYPE_ALLOWED`: default policy hotspot (`regular` atau `bypassed`).
- `REQUIRE_EXPLICIT_DEVICE_AUTH` dan `OTP_AUTO_AUTHORIZE_DEVICE`: aturan otorisasi device baru.
- `DEVICE_AUTO_REPLACE_ENABLED`: auto-replace saat limit device penuh.
- `QUOTA_DEBT_LIMIT_MB`: hard block saat debt mencapai ambang.
- `MIKROTIK_DHCP_STATIC_LEASE_ENABLED` dan `MIKROTIK_DHCP_LEASE_SERVER_NAME`: stabilisasi IP berbasis static lease.

## Policy Produk yang Harus Dijaga

### Auth dan device authorization

- OTP sukses secara default mengotorisasi device aktif ketika `OTP_AUTO_AUTHORIZE_DEVICE=True`.
- Bypass code tidak boleh mengotorisasi device otomatis.
- Jalur self-service bind device tetap melalui `POST /api/users/me/devices/bind-current`.
- `POST /api/auth/verify-otp` tidak boleh fail-hard hanya karena lookup router `IP -> MAC` transien jika router masih bisa membuktikan pasangan `client_mac -> client_ip` yang sama. Fallback seperti ini harus tetap konservatif: jangan memperlakukan raw MAC sebagai authoritative tanpa kecocokan IP dari router.

### Quota dan expiry

- Quota source of truth tetap berada di database.
- Sinkronisasi hotspot usage bersifat monotonic: penurunan counter host dianggap reset router, bukan pengurangan total usage.
- User unlimited tidak boleh membawa debt quota.
- Saat admin mengaktifkan akses unlimited, counter numerik quota user (`total_quota_purchased_mb`, `total_quota_used_mb`, `auto_debt_offset_mb`) harus di-reset agar state database tetap konsisten dengan mode unlimited yang aktif.
- Status akses lintas aplikasi wajib tetap sinkron dengan [docs/ACCESS_STATUS_MATRIX.md](ACCESS_STATUS_MATRIX.md).

### Timezone dan display kuota

- `APP_TIMEZONE` adalah source of truth tunggal untuk waktu lokal aplikasi. Offset dan label runtime harus diturunkan dari konfigurasi ini, bukan dari hardcode `UTC+7` atau `UTC+8` yang tersebar.
- Semua render tanggal/jam untuk UI, PDF, invoice, admin context, task reminder, dan payload WhatsApp wajib memakai helper terpusat di `backend/app/utils/formatters.py`, terutama `get_app_local_datetime()`, `format_app_datetime_display()`, `get_app_timezone_label()`, dan helper terkait.
- Helper kompatibilitas lama seperti `format_datetime_to_wita()` boleh tetap dipakai oleh call-site lama, tetapi implementasinya harus tetap mengikuti timezone aplikasi aktif.
- Tampilan kuota user-facing dalam GB harus memakai helper bersama `format_mb_to_gb()` agar output `xx.xx GB` konsisten di semua kanal.
- Jangan mengubah arithmetic domain kuota seperti `bytes_total`, `limit_bytes_total`, perhitungan MB/bytes enforcement, atau logika sinkronisasi counter menjadi helper display. Display formatting dan arithmetic runtime harus tetap dipisahkan.

### Payment dan transaksi

- Midtrans mendukung mode `snap` dan `core_api`; frontend hanya memuat Snap.js saat benar-benar dibutuhkan.
- Endpoint publik transaksi harus tetap selaras dengan OpenAPI dan typed contract frontend.
- Perubahan alur transaksi atau webhook wajib memperbarui [docs/API_DETAIL.md](API_DETAIL.md) dan [docs/workflows/OPENAPI_CONTRACT.md](workflows/OPENAPI_CONTRACT.md).

## Ringkasan Integrasi

### MikroTik

- Counter utama berasal dari `/ip/hotspot/host`.
- Enforcement device menggunakan `/ip/hotspot/ip-binding` berbasis MAC.
- Enforcement status akses IP menggunakan `/ip/firewall/address-list`.
- Static DHCP lease dipakai hanya jika server pin jelas dan benar.
- Audit atau perbaikan massal produksi mengikuti [docs/workflows/PRODUCTION_OPERATIONS.md](workflows/PRODUCTION_OPERATIONS.md).
- **Bypass_Server** address-list: IP portal + infrastruktur yang boleh diakses user `klient_inactive`. Perlu di-populate manual atau via scheduler untuk banking sites (7.3 pending).
- **klient_inactive** firewall: `accept src=klient_inactive dst=Bypass_Server` + `drop src=klient_inactive dst=LOCAL_NETWORKS`. User inactive/expired hanya bisa akses portal dan Bypass_Server.
- **Bypassed ip-binding**: MAC-only binding tanpa field `address` → `ip_binding_map[mac]["address"]` = "" → butuh fallback ke candidate IPs dari parity report untuk address-list sync yang benar.

## Fokus Aktif Parity Guard

- `policy_parity_guard_task` berjalan setiap 10 menit, auto-remediation 3-step: (1) upsert ip-binding, (2) sync address-list, (3) upsert DHCP lease.
- **Bypassed users**: tidak ada di `/ip/hotspot/host`. IP harus diambil dari `ip_binding_map[mac]["address"]` atau fallback ke candidate IPs dari parity report.
- **persistent address_list mismatch**: biasanya karena ip_binding `address` field kosong (MAC-only binding) → fix via IP fallback dari report IPs (commit terbaru Mar 18).
- Dashboard "Konsistensi Akses": tombol "Perbaiki Semua (N)" untuk bulk-fix, tanpa hard-cap 20 baris.
- Detail: [docs/devlogs/2026-03-18-holistic-audit-penyempurnaan.md](devlogs/2026-03-18-holistic-audit-penyempurnaan.md)

## Fokus Aktif Hotspot Sync

- Seri commit yang saat ini menjadi baseline produksi untuk hotspot sync adalah `bcfa8524` -> `a6edfd9a` -> `4f7a1110` -> `359c8adb`.
- Baseline produksi terakhir untuk full run `sync_hotspot_usage_task` berada di kisaran `60-66s` dengan counter parity kritis tetap nol.
- Detail implementasi, hasil ukur, dan artefak operasi disimpan di [docs/devlogs/2026-03-17-hotspot-sync-hardening.md](devlogs/2026-03-17-hotspot-sync-hardening.md).
- RCA khusus stale Redis lock pascarecreate disimpan di [docs/incidents/2026-03-17-stale-quota-sync-lock.md](incidents/2026-03-17-stale-quota-sync-lock.md).

## Fokus Aktif Hotspot Portal Trust

- Baseline produksi untuk trust boundary captive portal saat ini adalah commit `ab53b3ff`.
- Default trust policy produksi saat ini mengizinkan hotspot client CIDR `172.16.2.0/23` dan trusted login host `login.home.arpa`.
- Semua hint hotspot dari query, nested redirect, referrer, dan storage harus dianggap tidak trusted sampai lolos sanitasi frontend.
- Detail implementasi disimpan di [docs/devlogs/2026-03-17-hotspot-portal-trust-hardening.md](devlogs/2026-03-17-hotspot-portal-trust-hardening.md).
- RCA insiden foreign captive context disimpan di [docs/incidents/2026-03-17-foreign-hotspot-context.md](incidents/2026-03-17-foreign-hotspot-context.md).

### Midtrans

- Backend memakai `MIDTRANS_SERVER_KEY`, `MIDTRANS_CLIENT_KEY`, dan `MIDTRANS_IS_PRODUCTION`.
- Frontend memakai `NUXT_PUBLIC_MIDTRANS_CLIENT_KEY`.
- Webhook dan redirect harus berjalan melalui URL publik HTTPS yang valid.
- Status ketersediaan pembayaran publik kini dibaca dari `GET /api/settings/payment-availability` dan harus menjadi source of truth UI untuk halaman beli. Endpoint ini `no-store`, dihitung dari state circuit breaker `midtrans`, dan memakai pesan tunggal `PAYMENT_GATEWAY_UNAVAILABLE_MESSAGE` agar banner frontend dan error backend tetap sinkron.
- Untuk outage gateway pembayaran, jangan menambah toggle manual baru di frontend. Pola yang dijaga adalah event-driven: backend membuka breaker saat Midtrans gagal, halaman beli mem-poll status ini berkala, dan semua aksi beli/lunasi wajib disabled selama `available=false`.

### WhatsApp/Fonnte

- Pengiriman server-side memakai token API di backend.
- Deep link frontend ke WhatsApp admin hanya bergantung pada `NUXT_PUBLIC_ADMIN_WHATSAPP` dan `NUXT_PUBLIC_WHATSAPP_BASE_URL`.
- Jangan pernah menaruh token provider di env publik atau frontend.
- Knob runtime yang paling relevan untuk kecepatan kirim OTP saat ini adalah `WHATSAPP_HTTP_TIMEOUT_SECONDS`, `WHATSAPP_SEND_DELAY_MIN_MS`, dan `WHATSAPP_SEND_DELAY_MAX_MS`.
- Saat ini aplikasi belum menulis metrik durasi kirim OTP/provider latency secara eksplisit. `POST /auth/request-otp` berhasil hanya membuktikan request auth diterima backend, bukan membuktikan OTP sudah terkirim cepat ke handset.
- Jika perlu audit performa OTP, gunakan kombinasi access log, backend log, dan dashboard/log provider WhatsApp; jangan menyimpulkan latency delivery hanya dari selisih waktu `request-otp` ke `verify-otp` karena itu juga mencakup waktu user menerima dan mengetik kode.
- Notifikasi invoice transaksi sekarang harus dicatat ke `transaction_events` saat queued dan saat task Celery memproses hasil kirimnya. Jangan menambah jalur invoice WA baru yang hanya menulis log container tanpa event DB, karena itu mengembalikan blind spot observability yang baru saja ditutup.
- Untuk attachment PDF server-side yang perlu diakses provider WhatsApp tanpa sesi admin/user, gunakan token sementara berbasis `notification_service` dengan salt khusus per jenis dokumen. Jangan mendaur ulang token invoice untuk debt report atau dokumen lain.
- Debt report WhatsApp admin-user memakai jalur terpisah dari invoice transaksi. Secara desain, debt report tidak ditulis ke `transaction_events` karena bukan lifecycle pembayaran; gunakan endpoint admin + PDF temp route tersendiri agar boundary-nya tetap jelas.
- Khusus notifikasi debt manual, aplikasi kini mengekspos metrik degradasi `notification.render.degraded`, `notification.whatsapp.send_failed`, `notification.whatsapp.user_debt_added.detail_degraded`, dan `notification.whatsapp.user_debt_added.detail_degraded.items` melalui admin metrics. Gunakan metrik ini bersama log backend bila pesan debt sukses terkirim tetapi rincian item terlihat tidak lengkap.
- Jalur admin `PUT /api/admin/users/{id}` adalah boundary resmi untuk debt manual. Payload `debt_date` wajib lolos validasi schema dan akan dinormalisasi ke `date`; due date debt manual dihitung otomatis ke akhir bulan untuk flow paket maupun `debt_add_mb`.
- Schema admin user create/update dapat mengembalikan `blok` dan `kamar` sebagai enum Pydantic. Sebelum menyentuh model SQLAlchemy `User`, nilai itu wajib dinormalisasi kembali ke string storage (`A`, `Kamar_1`, dst.) agar flush Postgres tidak gagal dengan `can't adapt type 'UserBlok'` atau `UserKamar`.
- Normalisasi tampilan tanggal wajib memakai helper terpusat di `backend/app/utils/formatters.py`: `format_app_date_display()` untuk tanggal dan `format_app_datetime_display()` untuk datetime. Untuk JSON/API, pertahankan field raw ISO/`yyyy-mm-dd` bila masih dipakai sorting/parsing, lalu tambahkan field `*_display` berformat `dd-mm-yyyy` atau `dd-mm-yyyy HH:MM:SS` untuk konsumsi UI/report/WA context.
- Untuk payload `user_debt_added`, timestamp header dan detail item harus melalui helper timezone yang sama. Jangan lagi mengonversi detail item dengan WIB/WITA hardcoded karena itu mudah menciptakan selisih jam antarbagian pesan.
- Untuk report/reminder debt manual, total nominal aktif harus dijumlah dari item debt terbuka yang tercatat (`price_rp` / `remaining_rp`) bila tersedia. Jangan menurunkan nominal manual dari aggregate MB melalui estimator paket termurah, karena itu bisa meng-understate tagihan user.
- Label `debt otomatis` di UI, PDF, dan notifikasi harus diperlakukan sebagai `nilai referensi`, bukan nominal exact. Sebaliknya, debt manual boleh menampilkan nominal exact bila item debt memang menyimpan harga paketnya.
- Aktivasi unlimited dari jalur admin harus mengirim notifikasi khusus `user_unlimited_activated_by_admin` dan menyuplai context yang cukup jelas untuk menjelaskan profil akses dan masa aktif unlimited yang baru.
- Di dialog admin edit user, mode `Unlimited` dan `Tunggakan Kuota` harus tetap saling eksklusif agar operator tidak memberi kombinasi state yang membingungkan atau bertentangan dengan policy debt.
- Untuk report riwayat mutasi kuota via WhatsApp, backend harus men-generate PDF via WeasyPrint dan mengirimnya sebagai attachment ke Fonnte. Route publik bertoken dengan salt `quota-report` disediakan agar provider WhatsApp bisa mengambil file tanpa sesi admin. Jangan mendaur ulang token atau salt dari debt report atau invoice untuk quota history.
- Reset password dari admin hanya boleh dijalankan oleh user dengan role ADMIN. Endpoint harus menolak non-ADMIN request dengan 403. Frontend harus menyembunyikan tombol jika role bukan ADMIN.
- Dialog admin fullscreen/scrollable pada mobile sebaiknya memakai native scroll container alih-alih `perfect-scrollbar` bila ada indikasi lag sentuhan atau warning non-passive listener. CSS boleh dipakai untuk polishing, tetapi bypass library tetap menjadi jalur utama untuk menghapus bottleneck interaksi.
- Manual dispatch GitHub Actions dari workspace Windows ini bisa gagal walaupun `gh auth status` sehat bila resolver sistem memprioritaskan jalur IPv6/NAT64 `api.github.com` yang sedang rusak. Jika error mengarah ke `wsarecv`, `WinError 10054`, atau `connection reset`, audit address family `api.github.com` dan pakai workaround forcing IPv4 sebelum menyimpulkan workflow/token bermasalah.

## Guardrail Audit Release

- Jika user melaporkan perilaku lama masih terlihat setelah publish dan recreate, jangan langsung mengasumsikan deploy gagal. Audit tiga lapisan secara berurutan: revision image yang berjalan, isi source `main` yang menjadi bahan image, lalu source file aktual yang memegang perilaku tersebut.
- Untuk regresi yang menyentuh admin log, debt/unlimited, atau device self-heal, pastikan verifikasi tidak berhenti di container status. Selalu cek juga route/backend service, template notifikasi, dan file Vue yang menjadi sumber UI terakhir.
- Catatan release wajib membedakan antara perubahan yang memang sudah pernah dibahas di chat dan perubahan yang sudah benar-benar masuk ke repo. Drift di antara keduanya harus dicatat eksplisit di devlog agar tidak terulang.

## Aturan Saat Mengubah Kode

- Perubahan backend wajib divalidasi dengan lint backend.
- Perubahan frontend wajib divalidasi dengan lint frontend, dan typecheck bila menyentuh TypeScript/Vue.
- Perubahan auth, captive, quota, device, atau payment flow wajib menjalankan focused tests yang relevan.
- Perubahan endpoint prioritas wajib sinkron dengan OpenAPI, typed contract, dan [docs/API_DETAIL.md](API_DETAIL.md).
- Perubahan deploy, backup, atau operasi produksi wajib memperbarui [docs/workflows/PRODUCTION_OPERATIONS.md](workflows/PRODUCTION_OPERATIONS.md).
- Perubahan terkait timezone, format tanggal, atau representasi kuota user-facing wajib memperjelas di dokumentasi apakah perubahan tersebut hanya display atau juga menyentuh arithmetic/runtime semantics.

## Dokumen Pendamping

- [docs/PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md)
- [docs/API_DETAIL.md](API_DETAIL.md)
- [docs/VUEXY_BASELINE_STRATEGY.md](VUEXY_BASELINE_STRATEGY.md)
- [docs/devlogs/README.md](devlogs/README.md)
- [docs/devlogs/2026-03-21-timezone-centralization-and-release-ops.md](devlogs/2026-03-21-timezone-centralization-and-release-ops.md)
- [docs/devlogs/2026-03-22-manual-debt-accuracy-and-admin-edit-ux.md](devlogs/2026-03-22-manual-debt-accuracy-and-admin-edit-ux.md)
- [docs/devlogs/2026-03-18-holistic-audit-penyempurnaan.md](devlogs/2026-03-18-holistic-audit-penyempurnaan.md)
- [docs/devlogs/2026-03-17-hotspot-portal-trust-hardening.md](devlogs/2026-03-17-hotspot-portal-trust-hardening.md)
- [docs/devlogs/2026-03-17-hotspot-sync-hardening.md](devlogs/2026-03-17-hotspot-sync-hardening.md)
- [docs/incidents/README.md](incidents/README.md)
- [docs/incidents/2026-03-22-manual-debt-report-undercount.md](incidents/2026-03-22-manual-debt-report-undercount.md)
- [docs/incidents/2026-03-21-recreate-healthcheck-false-negative.md](incidents/2026-03-21-recreate-healthcheck-false-negative.md)
- [docs/incidents/2026-03-17-foreign-hotspot-context.md](incidents/2026-03-17-foreign-hotspot-context.md)
- [docs/incidents/2026-03-17-stale-quota-sync-lock.md](incidents/2026-03-17-stale-quota-sync-lock.md)
- [docs/workflows/OPENAPI_CONTRACT.md](workflows/OPENAPI_CONTRACT.md)
- [docs/workflows/CI_CD.md](workflows/CI_CD.md)
- [docs/workflows/PRODUCTION_OPERATIONS.md](workflows/PRODUCTION_OPERATIONS.md)