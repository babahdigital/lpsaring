# Changelog

Semua perubahan penting pada proyek ini akan dicatat di file ini.
Format mengikuti [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) dan versi mengikuti SemVer.

Lampiran wajib:
- [.github/copilot-instructions.md](.github/copilot-instructions.md)

## [Unreleased]

### Added (2026-03-08 — Sesi 3: Stabilitas Infrastruktur)
- Docker log retention `json-file, max-size=50m, max-file=5` pada seluruh 4 service runtime (`backend`, `celery_worker`, `celery_beat`, `frontend`). Service `frontend` sebelumnya **tidak memiliki logging config sama sekali** — log hilang setiap container di-recreate. Sekarang log tersimpan di host dan bisa diinspeksi untuk investigasi outage.
- Devlog lengkap sesi infrastruktur ini tersedia di `docs/WORKLOG_2026-03-08_INFRA_STABILITY.md`.

### Changed (2026-03-08 — Sesi 3: Stabilitas Infrastruktur)
- `frontend/utils/hotspotIdentity.ts`: migrasi `sessionStorage` → `localStorage` (3 tempat: `isBrowserRuntime()`, `rememberHotspotIdentity()`, `getStoredHotspotIdentity()`). Identitas client (IP + MAC) kini persists lintas tab close/reopen. TTL 10 menit tetap dipertahankan.
- `frontend/store/auth.ts`: migrasi `sessionStorage` → `localStorage` untuk hint key `lpsaring:last-mikrotik-login-link` (2 tempat: `rememberMikrotikLoginHint()`, `getStoredMikrotikLoginHint()`).
- `frontend/pages/login/hotspot-required.vue`: migrasi `window.sessionStorage` → `window.localStorage` untuk baca `LAST_MIKROTIK_LOGIN_HINT_KEY`.
- `deploy_pi.sh`: ganti `docker container prune -f` (global — berbahaya untuk stack lain) dengan targeted per-container `docker rm` yang hanya berjalan jika container dalam state `exited/created/dead`. Container `running` dan container dari stack lain tidak tersentuh.
- `nginx/conf.d/lpsaring.conf`: hapus blok duplikat `set_real_ip_from` / `real_ip_header` / `real_ip_recursive` dari server context. Semua real_ip handling sudah ditangani global oleh `01-real-ip.conf` (Cloudflare IPs + RFC1918 + Docker bridge `192.168.0.0/20`).
- WireGuard `peer_mikrotik.conf`: persempit `AllowedIPs = 0.0.0.0/0` → `10.19.83.0/24`. Mencegah seluruh traffic hotspot client routing melalui VPN secara tidak perlu.
- WireGuard server config (live `wg0.conf`): tambah `PersistentKeepalive = 25` pada peer `peer_mikrotik` untuk stabilitas NAT traversal. MikroTik berada di balik NAT — tanpa keepalive, tunnel bisa drop saat idle.
- `docker-compose.prod.yml`: update logging options dari `10m×10` ke `50m×5` untuk `backend`, `celery_worker`, dan `celery_beat` agar konsisten dengan standar baru.

### Fixed (2026-03-08 — Sesi 3: Stabilitas Infrastruktur)
- `action_log_routes.py`: `func.count(AdminActionLog.id)` dalam konteks `select_from(subquery())` menyebabkan SQLAlchemy SAWarning cartesian product. Diperbaiki ke `func.count()` (tanpa argumen kolom luar).
- `action_log_routes.py`: `AdminActionLogResponseSchema.from_orm(log)` deprecated di Pydantic v2. Diperbaiki ke `model_validate(log)`. Schema sudah memiliki `from_attributes=True` di `ConfigDict`.
- `action_log_routes.py`: rename parameter tak terpakai `current_admin` → `_current_admin` di `get_action_logs` dan `export_action_logs` untuk menyelesaikan ruff F841.
- `eslint.config.js`: tambah `types/api/contracts.generated.ts` ke `ignores` agar `pnpm run lint --fix` tidak menghapus `/* eslint-disable */` dari file auto-generated.
- CI failure run `22810572908` dan `22810720221`: `frontend/tests/hotspot-identity.test.ts` masih mock `sessionStorage` setelah code diubah ke `localStorage`. Diperbaiki: `createSessionStorageMock` → `createStorageMock`, `vi.stubGlobal('sessionStorage')` → `vi.stubGlobal('localStorage')`, referensi langsung di TTL test. Verifikasi lokal: 85 tests pass. CI run `22811056993` → success.

### Added (2026-03-08)
- MikroTik `DoH_Servers` address-list dengan 8 IP resolver publik (Google, Cloudflare, Quad9, OpenDNS) dan forward filter rule `drop` TCP/443 dari `LIST_LAN` ke list tersebut. Mencegah hotspot client bypass DNS enforcement via DNS-over-HTTPS.
- Task Celery baru `purge_stale_quota_keys_task` (harian 03:30): hapus Redis key `quota:last_bytes:mac:*` untuk MAC yang tidak tercatat di `UserDevice.last_seen_at` dalam 30 hari. Cegah akumulasi key TTL=-1 akibat MAC randomization. Dikontrol env `QUOTA_STALE_KEY_PURGE_ENABLED` dan `QUOTA_STALE_KEY_STALE_DAYS`.
- Task Celery baru `dlq_health_monitor_task` (setiap 15 menit): cek `celery:dlq`, kirim WA alert ke superadmin dengan preview 3 item terakhir DLQ jika non-empty. Throttle default 60 menit via Redis key. Dikontrol env `TASK_DLQ_ALERT_THROTTLE_MINUTES`.
- Devlog hardening MikroTik sesi ini: `docs/DEVLOG_2026-03-08_MIKROTIK_HARDENING.md`.

### Changed (2026-03-08)
- `QUOTA_SYNC_INTERVAL_SECONDS` diubah dari `300` ke `60` di `.env.prod`: sinkronisasi quota tiap 1 menit. Potensi overage turun dari ~375 MB (5 menit × 10 Mbps) ke ~75 MB.
- Celery Beat: tambah `"options": {"countdown": X}` pada tiga task MikroTik-dependent (`sync-unauthorized-hosts` +20s, `cleanup-waiting-dhcp-arp` +40s, `policy-parity-guard` +55s) untuk mencegah empat koneksi MikroTik API simultan yang menyebabkan `failed:89` timeout burst saat container restart.
- MikroTik anti-tethering mangle rule scope dipersempit: `dst-address 172.16.0.0/20` → `172.16.2.0/23` (hanya VLAN Klien, bukan semua VLAN termasuk staf/IoT).
- MikroTik simple queue `limit-at` diterapkan ke 7 VLAN child queue (IoT, Kamtib, Privated, Registrasi, Tamu, Aula, Wartelpas) sebagai guaranteed minimum bandwidth floor.
- MikroTik `Limit-Dinamis-Per-User-20M` (PCQ paket-fup): tambah burst `30M/60M, threshold 5M/10M, 6s`. User FUP mendapat boost awal 60M download selama 6 detik.
- MikroTik `Limit-Dinamis-Per-User-30M` (PCQ paket-aktif): tambah burst `60M/100M, threshold 10M/20M, 8s`. Queue idle saat ini karena `profile-aktif` sengaja tidak di-mark `paket-aktif` (bypass per-user PCQ — desain intentional). Burst siap aktif jika mangle mark ditambahkan di masa depan.

### Performance (2026-03-08)
- `sync-unauthorized-hosts`: safety guard loops (`forced_exempt_remove`, `forced_authorized_remove`, `forced_binding_dhcp_remove`, `forced_status_overlap_remove`) kini hanya memanggil `remove_address_list_entry` jika IP memang ada di unauthorized list. Sebelumnya ~141 no-op API call per cycle (69 authorized + 72 status IPs) dikirim ke MikroTik tanpa efek — kini skip otomatis via `existing_unauthorized_ips` set dari data yang sudah di-fetch.
- `_collect_dhcp_lease_snapshot` digabung dengan logika `lpsaring_macs` dalam satu pass DHCP lease (tidak ada API call tambahan).

### Fixed (2026-03-08)
- `sync-unauthorized-hosts`: MAC yang pernah login OTP dan memiliki DHCP static lease dengan comment `lpsaring|static-dhcp` kini dilindungi dari unauthorized list meskipun ip-binding sementara tidak ada (e.g. MAC randomization per-SSID yang menyebabkan ip-binding stale). Guard baru: `dhcp_lpsaring_macs` check sebelum host masuk `desired` block.
- `register_or_update_device`: saat `allow_replace=True` (OTP login captive portal / explicit authorize), auto-replace perangkat terlama kini aktif tanpa memerlukan `DEVICE_AUTO_REPLACE_ENABLED=True` di env. Sebelumnya user yang MAC perangkatnya berubah (randomisasi) dan sudah penuh slot akan ditolak dengan error "Limit perangkat tercapai" meskipun OTP berhasil diverifikasi.

### Changed (2026-03-08)
- `apply_device_binding_for_login` kini hanya melakukan cleanup hotspot host pada jalur recovery unauthorized yang valid (IP memang berada di address-list `unauthorized` dan tidak termasuk exempt/bypass).
- Command scheduler `sync-unauthorized-hosts` tidak lagi menghapus trusted hotspot host sebagai efek samping; sinkronisasi difokuskan pada parity address-list unauthorized.
- `deploy_pi.sh --recreate` diperketat: `.env.public.prod` kini wajib tersedia dan selalu ikut tersinkron bersama `.env.prod`.
- Layout mobile frontend distabilkan saat refresh melalui `effectiveAppContentLayoutNav` agar kelas layout tidak kembali ke state yang salah di breakpoint kecil.
- Runbook operasional unauthorized/hotspot lifecycle diperbarui untuk menegaskan guard policy baru dan langkah audit scheduler/script RouterOS eksternal.

### Fixed (2026-03-08)
- Regression CI backend akibat ekspektasi test lama (cleanup host selalu dipanggil) telah diperbaiki dengan test yang selaras policy baru: cleanup hanya untuk recovery unauthorized.

### Added (2026-03-08)
- Devlog lengkap sesi hardening + investigasi insiden ditambahkan pada `docs/DEVLOG_2026-03-08.md`.

### Changed (2026-03-05)
- Alur release diperjelas: `ci.yml` tetap quality gate utama pada push `main`, sedangkan `.github/workflows/docker-publish.yml` diposisikan untuk publish image saja (tag `v*` atau `workflow_dispatch`), tanpa auto deploy Raspberry Pi.
- Dokumentasi publish/deploy diperbarui agar konsisten dengan policy manual deploy via `deploy_pi.sh --recreate` (`README.md`, `docs/PUBLISH_FLOW_AND_ERROR_STATUS.md`).
- Ditambahkan devlog audit terbaru `docs/DEVLOG_2026-03-05.md` yang merangkum hasil test lokal, simulasi produksi non-destruktif, dan matrix status findings/roadmap.
- Runbook monitoring diperluas dengan command terstandar deteksi noise cloudflared (`docs/OPERATIONS_COMMAND_STANDARD.md`, `docs/POST_DEPLOY_MONITORING_24H.md`).

### Fixed (2026-03-05)
- `apply_device_binding_for_login` tidak lagi berisiko `UnboundLocalError` saat `IP_BINDING_ENABLED=False`; regression test ditambahkan pada `backend/tests/test_device_management_service.py`.
- Parity `POST /api/auth/reset-login` disempurnakan: kini juga menghapus refresh token + user devices serta clear auth/refresh cookie setara alur `logout`.
- Sinkronisasi status address-list kini memfilter kandidat IP berdasarkan `MIKROTIK_UNAUTHORIZED_CIDRS`/`HOTSPOT_CLIENT_IP_CIDRS` sehingga IP di luar subnet hotspot (mis. `10.x`) tidak lagi ditulis ke list status managed.

### Added (2026-03-05)
- Script ops baru `scripts/check_cloudflared_noise.py` untuk menghitung rasio `context canceled` cloudflared dan memberi exit code alert (`ok/warn/critical`).
- Command CLI baru `flask heal-hotspot-status-address-list` untuk audit/cleanup entry status managed `lpsaring|status=` yang berada di luar CIDR hotspot, dengan mode `--dry-run` dan `--apply` serta opsi resync user terdampak.

### Changed (2026-03-03)
- Dokumentasi produksi diperbarui untuk arsitektur DigitalOcean split-stack (`nginx` + `cloudflared` global terpisah dari app compose), termasuk pembaruan diagram arsitektur, checklist Cloudflare Tunnel, dan standar command operasional.
- Ditambahkan runbook baru `docs/DO_PRODUCTION_DEPLOYMENT.md` serta checklist rollback `docs/DO_ROLLBACK_CHECKLIST.md` sebagai acuan operasional deploy/restore/rollback terbaru.
- `docker-compose.prod.yml` dokumentatif sekarang diposisikan sebagai app stack saja (tanpa service `nginx`/`cloudflared`) pada dokumentasi aktif.

### Fixed (2026-03-02)
- Dashboard admin users card mapping diperbaiki: kartu `Akan Kadaluwarsa` dan `Menunggu Persetujuan` kini terisi dari metrik yang benar.
- Endpoint `/api/admin/dashboard/stats` kini menambahkan field `menungguPersetujuan` (count user `approval_status=PENDING`) agar selaras dengan UI dashboard.
- Section `Preview Cleanup Nonaktif` di halaman admin users sekarang otomatis disembunyikan jika tidak ada kandidat pada `Top Kandidat Deactivate` maupun `Top Kandidat Delete`.

### Changed (2026-03-02)
- Verifikasi operasional dashboard admin di produksi ditambahkan ke alur release: cek log endpoint `dashboard/stats|metrics|metrics/access-parity|backups`, cek data transaksi `SUCCESS`, dan cek health stack pasca deploy prune.

### Fixed (2026-03-02)
- `deploy_pi.sh` kini menambahkan preflight deteksi Alembic drift untuk rantai migrasi `20260302_*` (public update submissions) dan auto-stamp terkontrol sebelum `flask db upgrade`, sehingga deploy tidak lagi macet pada kasus `DuplicateTable/DuplicateColumn`.
- Healthcheck frontend produksi dipastikan memakai binary absolut `/nodejs/bin/node` agar status container `frontend` konsisten `healthy`.

### Changed (2026-03-02)
- Opsi `--clean` di `deploy_pi.sh` sekarang wajib disertai `--confirm-clean-data-loss` untuk mencegah eksekusi destruktif tanpa konfirmasi eksplisit.
- Ditambahkan opsi `--no-auto-stamp-alembic-drift` untuk mematikan auto-remediation drift Alembic saat dibutuhkan investigasi manual.

### Changed (2026-03-02)
- Dokumentasi public update workflow disempurnakan untuk mencakup: staging-vs-approval behavior, visibility panel approval admin saat pending kosong, matrix feature flag backend/frontend, dan checklist validasi minimal pasca perubahan.
- Sinkronisasi ringkasan endpoint pada `docs/API_OVERVIEW.md` dan addendum kontrak pada `docs/API_DETAIL.md` agar konsisten dengan implementasi `/update` terbaru.

### Fixed (2026-03-02)
- Frontend typecheck error pada `pages/login/hotspot-required.vue` diperbaiki (typing helper `isDemoUser`), sehingga verifikasi lint/typecheck untuk file terkait update kembali bersih.

### Added (2026-03-02)
- Public update submission workflow berbasis role `USER/TAMPING/KOMANDAN` dengan validasi field kondisional yang diselaraskan dengan form register `/login`.
- Queue approval klaim role di admin users (`/api/admin/update-submissions`) dengan aksi approve/reject agar klaim `komandan/tamping` tidak langsung diterapkan otomatis.
- Personalisasi link update per nomor pada pesan WhatsApp batch (`/update?phone=...&name=...`) sehingga nomor terisi otomatis dari link resmi.

### Changed (2026-03-02)
- Form publik `/update` sekarang membaca nomor dari query link WhatsApp, menampilkan input nomor dalam mode `disabled/readonly`, dan menolak submit jika nomor dari link tidak tersedia.
- Skema `public_database_update_submissions` diperluas dengan tracking approval (`approval_status`, `processed_by_user_id`, `processed_at`, `rejection_reason`) serta atribut role (`tamping_type`, `blok/kamar` nullable by role).
- Batch pengiriman WhatsApp tetap dibatasi per siklus (`UPDATE_WHATSAPP_BATCH_SIZE`, default 3 nomor unik) dan sekarang menggunakan template default berbasis `{update_link}`.

### Added (2026-03-02)
- Dokumentasi komprehensif sesi hardening + operasional ditambahkan pada `docs/DEVLOG_2026-03-02.md` (timeline deploy, root cause unauthorized, detail error/log, hasil verifikasi, dan rekomendasi lanjut).
- Policy state-by-state untuk arsitektur layered gate ditetapkan di `docs/LAYERED_GATE_POLICY_MATRIX.md`.

### Changed (2026-03-02)
- Flow frontend OTP/captive disederhanakan dengan menghapus halaman perantara `captive/otorisasi-perangkat`; otorisasi perangkat kini inline pada flow login/captive.
- Dokumentasi indeks aktif/historis diperbarui agar rujukan analisa, matrix kebijakan, dan jejak implementasi terbaru bisa ditelusuri dari satu pintu.

### Fixed (2026-03-02)
- Hardening unauthorized sync menutup false-positive untuk entitas trusted (DB authorized / ip-binding non-blocked / DHCP valid), menambahkan cleanup stale hotspot host, dan lock Redis untuk mencegah overlap scheduler.

### Fixed (2026-03-01)
- Backend hotspot session status tetap berbasis `ip-binding` (tanpa `/ip/hotspot/active`) dan menutup false-positive status `terhubung` akibat fallback user-level yang terlalu longgar.
- Fallback `HOTSPOT_SESSION_STATUS_ALLOW_USER_LEVEL_FALLBACK` kini default **False**; ketika diaktifkan pun fallback hanya dijalankan jika `client_ip` cocok dengan hasil `get_hotspot_user_ip` (sumber hotspot host/DHCP lease/ARP).
- Route wiring endpoint `/api/auth/hotspot-session-status` diperbarui agar menggunakan `get_hotspot_user_ip` sebagai validasi silang sebelum fallback user-level.

### Added (2026-03-01)
- Test backend untuk hotspot-session-status diperluas: skenario fallback berbasis kecocokan IP ditambahkan, termasuk guard saat IP mismatch agar tidak mengangkat status `terhubung` secara keliru.

### Changed (2026-03-01)
- Script `scripts/run_local_ci.ps1` kini memakai resolver path compose yang lebih robust (absolute/relative/workspace-relative).
- Script `scripts/simulate_end_to_end.ps1` diperkuat untuk jalur E2E: resolve compose path fleksibel, isolasi user test, cleanup artefak test, snapshot+restore admin settings, fallback verify-otp no-context, serta verifikasi reset-login/logout/re-login yang lebih deterministik.

### Changed (2026-02-27)
- Frontend status routing dipusatkan ke `/policy/*`; halaman status legacy di `/login/*` dan `/captive/*` dihapus dari `pages` dan diganti kompatibilitas redirect via `routeRules` Nuxt.
- Flow captive diperketat dengan `captive_context` (sessionStorage) agar konteks captive tidak dapat menavigasi ke area terbatas (`/dashboard`, `/beli`, `/requests`, `/akun`) untuk user non-admin.
- Halaman `captive/terhubung` disederhanakan menjadi CTA tunggal (`Mulai Browsing`) + auto-close/fallback redirect yang aman.
- Route pembelian captive dipusatkan: `/captive/beli` tidak lagi memiliki implementasi halaman terpisah; akses lama tetap diarahkan ke `/beli`.
- Legal docs dibuat publik pada root route (`/privacy`, `/terms`) sebagai alias ke halaman legal utama agar tidak terkesan eksklusif merchant-only.

### Fixed (2026-02-27)
- Konsistensi middleware auth/status-guard dibersihkan dari dependensi route status legacy.
- Referensi legal back-navigation dan allowlist pembelian diperbarui agar tidak lagi bergantung pada path legacy `/captive/beli`.
- Regression test middleware diperluas untuk kasus captive-context blocking dan diselaraskan dengan route policy terpusat.

### Added
- Frontend: halaman publik merchant center (`/merchant-center`, `/merchant-center/privacy`, `/merchant-center/terms`) dengan konten legal yang disesuaikan untuk alur produksi.
- Frontend: composable profil merchant terpusat untuk konsumsi data identitas dan kontak merchant lintas halaman legal.
- Konfigurasi public runtime baru untuk identitas merchant:
	- `NUXT_PUBLIC_MERCHANT_NAME`
	- `NUXT_PUBLIC_MERCHANT_BUSINESS_TYPE`
	- `NUXT_PUBLIC_MERCHANT_ADDRESS`
	- `NUXT_PUBLIC_MERCHANT_SUPPORT_EMAIL`
	- `NUXT_PUBLIC_MERCHANT_SUPPORT_WHATSAPP`
- Backend: kontrol demo mode berbasis ENV untuk OTP bypass terkontrol dan visibilitas/pembelian paket testing pada user demo.

### Changed
- Legal page merchant/privacy/terms diselaraskan gaya visualnya mengikuti acuan internal desain, termasuk penyempurnaan pass kedua agar tampilan lebih halus.
- Normalisasi tampilan nomor WhatsApp merchant untuk konteks Indonesia (`+62/62` tampil sebagai `0...`), sementara non-Indonesia tetap format internasional.
- Dokumentasi devlog/worklog/error reference diperbarui untuk mencatat hasil deploy produksi dan status issue yang masih terbuka.
- Demo flow pembelian paket kini sepenuhnya berbasis status user login (`is_demo_user`) dari backend, bukan toggle global frontend.
- UI halaman beli dan captive disederhanakan untuk mode demo: informasi mode memakai badge ringkas dan label tombol paket terblokir diperpendek.

### Fixed
- Backend `/api/packages`: paket testing nonaktif tidak lagi muncul ke user reguler; hanya user demo yang eligible dapat melihat paket demo nonaktif.
- Frontend `/beli` dan `/captive/beli`: label tombol disable mode demo diperbaiki agar lebih pendek dan konsisten.
- Deploy produksi terbaru via `deploy_pi.sh --prune` berhasil dengan health check `/api/ping` OK.

### Known Issues
- Datepicker/kalender pada skenario dialog tertentu masih dapat menunjukkan perilaku popup yang belum konsisten; status masih open untuk sesi perbaikan lanjutan.

### Added
- Backend: fallback sqlite in-memory untuk pytest saat env DB belum tersedia.
- Frontend: script `typecheck` dan perbaikan typing `useApiFetch` untuk default data.
- CI: workflow sederhana untuk lint backend, pytest, dan lint frontend.
- Backend: mode CSRF ketat untuk request tanpa Origin/Referer dengan allowlist IP/CIDR.
- Backend: unit test CSRF guard dan normalisasi MAC.
- Backend: env `DEBT_ORDER_ID_PREFIX` untuk mengubah prefix order_id pelunasan tunggakan (tetap kompatibel dengan order lama `DEBT-...`).

### Changed
- Backend: sinkronisasi kuota menggunakan delta per-MAC (Redis last-bytes) + pembulatan MB konsisten.
- Backend: kebijakan hotspot login/ip-binding kini mendukung mode campuran berbasis status user (`HOTSPOT_BYPASS_STATUSES`), bukan hanya global `IP_BINDING_TYPE_ALLOWED`.
- Backend: verifikasi OTP kini mengizinkan auto-otorisasi perangkat pada login OTP agar tidak langsung masuk kondisi blokir pending-auth.
- Frontend: tampilan kuota mendukung MB desimal pada chart.
- Keamanan: CSRF origin guard untuk cookie auth dan JSON error handler konsisten.
- Health endpoint selalu HTTP 200 dengan status `ok`/`degraded`.
- Nginx: CSP produksi dipersempit (hapus `unsafe-eval`).
- CI/CD: workflow publish memakai Dockerfile produksi eksplisit per service dan build arg `NODE_OPTIONS` untuk stabilitas build frontend.
- Frontend: pipeline build Docker menambahkan `nuxt prepare` sebelum build untuk kompatibilitas `--ignore-scripts`.
### Added
- Dokumentasi detail endpoint API (request/response).
- Panduan kontribusi (flow PR, lint, testing).
- Template changelog ini.
- Endpoint opsi Mikrotik untuk form admin.
- Integrasi Snap.js Midtrans dengan loader aman dan promise readiness.
- Tampilan harga per hari/GB di halaman beli.
- Tombol unduh invoice dan refresh status pembayaran.
- Pengiriman invoice PDF via WhatsApp (backend).
- Endpoint health check untuk DB/Redis/Mikrotik.
- Endpoint metrics admin untuk OTP/payment/login.
- Script verifikasi walled-garden.
- Backend: script opsional `backend/scripts/normalize_phone_numbers.py` untuk scan/report/apply normalisasi `users.phone_number` ke E.164.
- Deploy: opsi `--sync-phones` dan `--sync-phones-apply` di `deploy_pi.sh` untuk menjalankan normalisasi nomor telepon dari dalam container backend.

### Changed
- Validasi nomor telepon ke format E.164 saat login/daftar.
- Redirect /register dan /daftar ke tab registrasi.
- Base URL lokal aplikasi ke HTTP (lpsaring.local).
- Cloudflared tunnel menggunakan HTTP/2.
- UI admin paket disederhanakan (hilangkan kelola profil di halaman paket).
- Penanganan HMR Nuxt memakai WS saat host HMR kosong.
- Pesan error pembayaran lebih informatif di captive.
- Auth session dipindah ke cookie `HttpOnly` server-side.
- Rate limit spesifik untuk OTP dan admin login ditambahkan.
- CSP header diberlakukan di Nginx.
- OTP anti-abuse memakai cooldown dan batas percobaan.
- WhatsApp: notifikasi low-quota diperkecil agar tidak noise (default cukup 5%; FUP 20% tetap via notifikasi status).
- Task Celery memakai retry/backoff dan DLQ sederhana.
- Public settings di-cache untuk mengurangi beban DB.

### Fixed
- Frontend: pelunasan tunggakan (Lunasi) tidak lagi mengirim event click sebagai `manual_debt_id` (fix 422).
- Frontend: dialog metode pembayaran pelunasan disamakan dengan dialog di `/beli` (dashboard/riwayat), termasuk per-item hutang manual.
- Backend: estimasi harga hutang kuota memilih paket referensi berdasarkan kecocokan kuota (closest-fit), bukan termurah-by-price.
- CI/Backend: perbaikan Ruff `F821` akibat variabel sisa pasca refactor.

### Changed
- Frontend: saat Core API aktif, GoPay/ShopeePay dapat redirect langsung ke deeplink bila backend mengembalikan `redirect_url`.
- OTP request 400 akibat body kosong.
- Redirect captive yang berulang (link_orig).
- Ikon Tabler tidak muncul (nama ikon diperbaiki).
- Flow pembayaran Midtrans pada captive dan halaman beli.
- Snap.js tidak terbaca karena script belum siap.
- WSS HMR gagal saat 443 tidak aktif.
- Log dan error handling saat inisiasi pembayaran.
- Frontend (Admin Dashboard): tooltip ApexCharts tidak lagi redundant/duplikat pada chart donut "Paket Terlaris".

## [0.1.0] - 2026-02-08
### Added
- Inisialisasi dokumentasi proyek dan checklist pengembangan.
