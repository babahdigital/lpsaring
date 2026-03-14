# Changelog

Semua perubahan penting pada proyek ini akan dicatat di file ini.
Format mengikuti [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) dan versi mengikuti SemVer.

Lampiran wajib:
- [.github/copilot-instructions.md](.github/copilot-instructions.md)

## [Unreleased]

### Fixed (2026-03-14 — Payment Status Access, Captive Recovery, dan CI Node 24 Opt-In)

- **Public payment status guest access:** halaman publik pembayaran tidak lagi jatuh ke flow auth biasa saat dibuka memakai token `t`, sehingga `/payment/status` dan `/payment/finish` bisa diakses langsung dari link Midtrans/WhatsApp tanpa login lebih dulu. Middleware auth juga kini menjaga captive hints (`link_login_only`, `appLinkMikrotik`) tetap terbawa saat redirect login/captive.
- **Quota self-service routing parity:** aturan path self-service untuk status `fup`, `expired`, dan `habis` dipusatkan di helper yang sama dan dipakai konsisten oleh `frontend/store/auth.ts`, `frontend/middleware/auth.global.ts`, dan `frontend/components/policy/PolicyStatusView.vue`. Ini menutup loop di mana user `fup` yang ingin beli quota atau kembali ke dashboard dipaksa balik terus ke halaman policy.
- **Hotspot activation target selection:** `frontend/pages/login/hotspot-required.vue` tidak lagi memakai `/captive` sebagai fallback login hotspot manual. Flow "Aktifkan Internet" sekarang memprioritaskan URL router yang authoritative (`link_login_only` / `appLinkMikrotik`) dan memakai helper baru `frontend/utils/hotspotLoginTargets.ts` untuk normalisasi target lokal/home.arpa/private IP.
- **Regression coverage:** ditambahkan test untuk allowlist self-service auth guard dan pemilihan target login hotspot, sehingga regression pada payment-status public access dan captive recovery bisa tertangkap lebih awal.
- **CI deprecation warning:** action JavaScript di workflow utama dinaikkan ke mayor terbaru yang tersedia (`actions/checkout@v6`, `actions/setup-python@v6`, `actions/setup-node@v6`, `dorny/paths-filter@v4`, `docker/build-push-action@v7`, `docker/login-action@v4`, `docker/metadata-action@v6`, `docker/setup-buildx-action@v4`, `docker/setup-qemu-action@v4`, `actions/github-script@v8`). `FORCE_JAVASCRIPT_ACTIONS_TO_NODE24=true` tetap dipertahankan sebagai guardrail tambahan, sehingga warning deprecation Node 20 hilang tanpa mengubah policy release image atau men-trigger publish Docker pada push biasa.

### Documentation (2026-03-14)

- `docs/DEVLOG_2026-03-14.md` diperbarui dengan ringkasan fix payment/captive 14 Maret, hasil verifikasi live untuk `+628134071280` dan `+6283179074596`, serta audit log `nginx` dan `docker compose` pasca-deploy.

### Fixed (2026-03-14 — Audit Host Hotspot + Saturasi DB Worker)

- **Quota/IP selection hardening:** `get_hotspot_host_usage_map()` tidak lagi last-row-wins untuk MAC duplikat di `/ip/hotspot/host`. Selector kini memprioritaskan row hotspot lokal yang masih segar (`idle-time` kecil), baru memakai bytes sebagai tie-breaker. Ini mencegah quota sync, parity, dan candidate IP memakai ghost row `10.8.0.x` / IP publik saat row `172.16.2.0/23` yang benar juga ada.
- **Translated hotspot IP handling:** bila `address` original berada di luar CIDR hotspot tetapi `to-address` sudah berada di `HOTSPOT_CLIENT_IP_CIDRS`, helper map kini mengekspor `address` ter-resolve ke IP lokal yang benar dan menyimpan original IP sebagai `source_address`. Consumer lama otomatis membaca IP hotspot yang benar tanpa perlu query raw host table.
- **Ghost-host cleanup safety:** cleanup host di luar CIDR kini mensyaratkan adanya current in-subnet hotspot host row untuk MAC yang sama sebelum removal. DHCP/ARP saja tidak lagi cukup untuk menghapus row ghost, sehingga cleanup tidak mendorong device sehat ke state unauthorized.
- **Celery worker DB saturation:** task Celery sebelumnya membuat Flask app baru untuk hampir setiap task execution (`create_app()` per task) sehingga worker dapat menumpuk banyak SQLAlchemy engine/pool dan memenuhi PostgreSQL dengan koneksi idle. `backend/app/tasks.py` kini me-cache Flask app per worker process agar engine/pool dipakai ulang dan teardown session berjalan pada app instance yang stabil.
- **Quota sync settings session leak:** `sync_hotspot_usage_and_profiles()` sekarang memuat runtime settings sekali di awal lalu selalu melepas scoped session sebelum loop `db.session.begin()` per-user dimulai. Ini mencegah `sync_hotspot_usage_task` meledak berkala dengan `InvalidRequestError: A transaction is already begun on this Session.` saat pembacaan `application_settings` pra-loop sudah lebih dulu memicu implicit transaction.

### Added (2026-03-14)

- Test regresi baru untuk pemilihan hotspot host per-MAC, fallback `to-address` lokal, dan cache Flask app pada task worker (`backend/tests/test_mikrotik_get_hotspot_host_usage_map.py`, `backend/tests/test_tasks_create_app_cache.py`).
- Devlog audit operasional + log forensik baru: `docs/DEVLOG_2026-03-14.md`.
- Test regresi baru untuk memastikan pembacaan runtime settings pra-loop tidak lagi meninggalkan sesi SQLAlchemy aktif sebelum transaksi per-user dimulai (`backend/tests/test_hotspot_sync_user_error_isolation.py`).

### Fixed (2026-03-13 — Sesi Stabilitas Infra + Payment Loss + SIGKILL)

#### bind-current SIGKILL (commit `76e66bca`)
- **CRITICAL:** `apply_device_binding_for_login()` membuka 3 koneksi MikroTik TCP secara berurutan saat `client_ip=None` (panggilan dari dashboard tanpa captive portal): `_resolve_binding_ip` + `resolve_client_mac` + `_apply_post_auth_mikrotik_ops` → total bisa ~180s → gunicorn worker SIGKILL (timeout 120s) → 502 → user tidak dapat internet dari dashboard.
- Fix: gunakan **satu koneksi bersama** (`nullcontext(None)` / `get_mikrotik_connection()`) di `apply_device_binding_for_login` saat slow path (client_ip tidak valid). Koneksi shared diteruskan ke semua fungsi downstream via parameter `api_connection=None` baru. Fungsi yang dimodifikasi: `_resolve_binding_ip`, `resolve_client_mac`, `register_or_update_device`, `_apply_post_auth_mikrotik_ops`. Total koneksi: 3 → 1 (slow path, dashboard). Fast path (captive portal dengan client_ip valid) tetap 1 koneksi.

#### Webhook payment loss — 3 bug (commit `e550141e`)
- **generator double-yield** (`mikrotik_client.py`): `yield None` inside `try:` block menyebabkan `RuntimeError: generator didn't stop after throw()` saat caller raise exception dalam `with get_mikrotik_connection()` dengan api=None. Fix: acquire connection BEFORE any yield; semua kasus gagal dipindah ke luar blok try/except.
- **idempotency TTL terlalu panjang** (`idempotency.py`): Redis dedup key di-set saat webhook START; jika worker SIGKILL di ~120s, key bertahan 24 jam → retry diblokir → pembayaran hilang. Fix: TTL 86400s → 30s (burst dedup saja). Effect lock TTL 300s → 130s.
- **Nested MikroTik connections di webhook** (`transaction_service.py` + `hotspot_sync_service.py`): `sync_address_list_for_single_user` membuka koneksi EKSTRA di dalam konteks MikroTik webhook yang sudah ada → nested TCP → total >120s → SIGKILL → rollback DB. Fix: `api_connection=None` param via `nullcontext`; `transaction_service.py` meneruskan `mikrotik_api` yang sudah ada.

#### hotspot-required.vue "Aktifkan Internet" selalu gagal (commit `c39dcd0b`)
- Root cause: user dengan ip-binding `bypassed` TIDAK masuk ke `/ip/hotspot/host` MikroTik. `hotspot-session-status` mencari user di hotspot host → tidak ketemu → `missing-hints` → `binding_active=False` → semua 8 poll gagal → tampil fallback login.
- Fix A (backend): tambah `db-device-mac` fallback di `hotspot_status_handlers.py` — jika hotspot host kosong, ambil MAC dari DB `UserDevice` terbaru user (`is_authorized=True`) → cek ip-binding MikroTik by MAC.
- Fix B (frontend): jika `authorizeDevice()` return `true` → poll hanya 3× (bukan 8×) dengan interval 900ms → setelah itu langsung `continueToPortal()` (ip-binding sudah aktif, tidak perlu tunggu hotspot host entry).

#### Infrastruktur hardening (commit `e4129451`)
- **MikroTik TCP connection leak** (`mikrotik_client.py`): `finally` block tidak memanggil `api_instance.disconnect()` jika pool tidak support `return_api` → socket tertahan sampai GC → socket table MikroTik penuh → 502.
- **Redis tanpa memory limit**: `maxmemory=0` → OOM risk. Fix: `--maxmemory 256mb --maxmemory-policy allkeys-lru`.
- **SQLAlchemy stale connection**: `pool_pre_ping=False, pool_recycle=-1` → koneksi stale setelah PostgreSQL timeout 8 jam. Fix: `pool_pre_ping=True, pool_recycle=3600`; `pool_size=3, max_overflow=5` di ProductionConfig saja.
- **Nested MikroTik connections** (`hotspot_sync_service.py`): `_remove_ip_binding()` membuka koneksi baru padahal sudah berada di dalam `with get_mikrotik_connection()`. Fix: tambah `api_connection=None` param.
- **Gunicorn worker timeout lama**: `--timeout 30` → `--timeout 120`, tambah `--graceful-timeout 120` dan `--keep-alive 2`.
- **OS security patches**: curl CVE + libfreetype6 + nftables diperbarui via `apt-get upgrade`.

#### Config & tasks (commit `c8db533c`)
- `RefreshToken` field names salah: `is_revoked` → `revoked_at`, `created_at` → `issued_at` (sesuai model).
- SQLAlchemy `pool_size`/`max_overflow` di `TestingConfig` menyebabkan error pada SQLite StaticPool. Fix: `TestingConfig.SQLALCHEMY_ENGINE_OPTIONS = {}`.
- Task Celery baru: `purge_quota_mutation_ledger_task` (hapus entri >90 hari, jalan 04:00 daily) dan `revoke_expired_refresh_tokens_task` (hapus expired/revoked tokens, jalan 04:30 daily).

#### Nuxt healthcheck SSR noise (commit `74ad19bb`)
- Healthcheck pakai `/login` → trigger SSR → backend poll 401 setiap 15 detik. Fix: tambah `frontend/server/routes/health.get.ts` (lightweight, no SSR), update healthcheck ke `/health`.

### Added (2026-03-13 — Sesi Admin Features, commit `ccec1df6`)

- **Admin "Perbaiki Transaksi"** (`POST /api/admin/transactions/<order_id>/reconcile`): tombol "Perbaiki" di halaman admin transaksi untuk status `FAILED`/`EXPIRED`/`CANCELLED`/`UNKNOWN`. Verifikasi ke Midtrans, inject quota jika sudah lunas, kirim WA invoice, log `AdminActionLog`. Lihat `docs/ADMIN_TRANSACTIONS_UI.md` section 6.
- **Admin user list device count**: kolom "KONEKSI" di `/admin/users` tampilkan badge jumlah device aktif ("X dev" atau "Belum login") berdasarkan `device_count` (`is_authorized=True`) dari subquery di `user_management_routes.py`.

### Changed (2026-03-13)

- `contracts/openapi/openapi.v1.yaml`: tambah path `POST /admin/transactions/{order_id}/reconcile` + schema `AdminTransactionReconcileResponse` (commit `dbc30493`).
- `frontend/types/api/contracts.generated.ts`: export type baru, update `GeneratedApiContractMap`, recompute `OPENAPI_SOURCE_SHA256`.
- `frontend/types/api/contracts.ts`: export `AdminTransactionReconcileResponse`.
- `docs/API_DETAIL.md`: tambah dokumentasi endpoint reconcile di section 6 Admin Transactions.


- **CRITICAL:** `sync_hotspot_usage_task` tidak memiliki Redis mutex lock. Dengan `--concurrency=4`, keempat worker Celery bisa lolos throttle check secara bersamaan (race condition pada baca `quota_sync:last_run_ts`) dan menjalankan `sync_hotspot_usage_and_profiles()` secara concurrent → circular `UPDATE user_devices` → **243 PostgreSQL deadlock** sepanjang hari (25–30/jam), 200+ worker respawn/jam. Diperbaiki dengan menambahkan `redis.SET NX` atomic lock (`quota_sync:run_lock`, TTL=120s) sebelum task execution. Lock dilepas di `finally{}` setelah task selesai. Hanya satu worker yang bisa hold lock; worker lain skip langsung.
- `QUOTA_SYNC_INTERVAL_SECONDS` diubah `60` → `120` di `.env.prod` sebagai lapisan kedua (belt-and-suspenders) untuk mengurangi frekuensi scheduling pressure.

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
