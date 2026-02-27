# Operasi: Audit & Cleanup MikroTik (Raspberry Pi)

Dokumen ini untuk kasus:
- Ada user masih terblokir / ada entry `blocked` yang "nyangkut".
- Anda pernah bypass manual di MikroTik sehingga comment / entry menjadi tidak konsisten dengan DB.
- Anda ingin audit total dan bersihkan *stale blocked* tanpa menghapus database.

> Penting: **jangan menghapus comment ip-binding sembarangan**. Sistem memakai token di comment (`uid=...` / `user=08...`) untuk mapping MAC → user (auto-enroll device & beberapa cleanup).

## 1) Validasi service di Raspberry Pi (Docker)

Jalankan di server (folder project produksi, mis. `/home/abdullah/sobigidul`):

- Cek container up:
  - `docker compose -f docker-compose.prod.yml ps`

- Pastikan Celery **worker** dan **beat** jalan (nama service tergantung compose Anda):
  - `docker compose -f docker-compose.prod.yml logs -n 200 celery_worker`
  - `docker compose -f docker-compose.prod.yml logs -n 200 celery_beat`

- Cari tanda-tanda:
  - `Celery Task: Memulai sinkronisasi kuota dan profil hotspot.`
  - `Celery Task: Skip sinkronisasi (menunggu interval dinamis).`
  - Error koneksi MikroTik / Redis.

Jika beat tidak jalan, sinkronisasi otomatis quota/status memang tidak terjadi.

## 2) Audit total MikroTik vs DB (dry-run)

Jalankan dari container backend (disarankan), agar pakai env produksi yang sama:

- `docker compose -f docker-compose.prod.yml exec backend python scripts/audit_mikrotik_total.py --print-json`

Atau output manusia:

- `docker compose -f docker-compose.prod.yml exec backend python scripts/audit_mikrotik_total.py`

Yang dicek oleh script:
- Jumlah address-list `blocked`.
- Jumlah ip-binding dan yang `type=blocked`.
- Deteksi *stale blocked* (address-list blocked yang punya token `uid=`/`user=` tapi user **tidak expected blocked** menurut DB + aturan debt-limit).

## 3) Cleanup stale blocked (aman, fokus address-list blocked saja)

Jika hasil audit menunjukkan `stale_blocked_detected > 0`, lakukan cleanup:

- `docker compose -f docker-compose.prod.yml exec backend python scripts/audit_mikrotik_total.py --cleanup-stale-blocked --apply`

- `docker compose -f docker-compose.prod.yml exec backend /opt/venv/bin/python scripts/audit_mikrotik_total.py --print-json`
Atau output manusia:

- `docker compose -f docker-compose.prod.yml exec backend /opt/venv/bin/python scripts/audit_mikrotik_total.py`
Jika hasil audit menunjukkan `stale_blocked_detected > 0`, lakukan cleanup:

- `docker compose -f docker-compose.prod.yml exec backend /opt/venv/bin/python scripts/audit_mikrotik_total.py --cleanup-stale-blocked --apply`

Efeknya:
- Menghapus entry di `/ip/firewall/address-list` list `MIKROTIK_ADDRESS_LIST_BLOCKED` yang terdeteksi stale.
- Tidak mengubah ip-binding.

## 4) Verifikasi flow quota-debt blocker

Flow quota-debt hard block hanya aktif jika `QUOTA_DEBT_LIMIT_MB > 0`.

Checklist cepat:
- Pastikan setting `QUOTA_DEBT_LIMIT_MB` sesuai (0 = nonaktif).
- Pastikan task `sync_hotspot_usage_task` berjalan berkala (Celery beat).
- Ketika `debt_mb >= limit`:
  - DB user menjadi `is_blocked=True` + `blocked_reason=quota_debt_limit|...`
  - MikroTik:
    - ip-binding type `blocked` untuk MAC device yang authorized
    - firewall address-list `blocked` untuk IP kandidat

Jika Anda bypass manual di MikroTik namun DB masih `is_blocked=True` (atau debt masih di atas limit), maka saat sync berikutnya sistem akan mem-block lagi.

## 5) Kalau “auto sync” tidak jalan sama sekali

Penyebab paling umum:
- Celery beat tidak running.
- Redis tidak reachable (throttle timestamp / lock error).
- MikroTik API unreachable atau circuit-breaker open.
- `ENABLE_MIKROTIK_OPERATIONS` atau `ENABLE_MIKROTIK_OPERATIONS` terset off (via settings/env).

Langkah lanjut:
- Cek log `celery_beat`, `celery_worker`, dan `backend`.
- Jalankan audit di atas untuk melihat apakah backend bisa connect ke MikroTik dari lingkungan produksi.

## 6) Audit harian otomatis (Celery)

Sistem menyediakan task harian `audit_mikrotik_reconciliation_task` untuk menjalankan audit reconciliation otomatis.

Kontrol utama (env/settings):
- `ENABLE_MIKROTIK_AUDIT_RECONCILIATION=True|False`
- `MIKROTIK_AUDIT_CRON_HOUR` (default `4`)
- `MIKROTIK_AUDIT_CRON_MINUTE` (default `15`)
- `MIKROTIK_AUDIT_AUTO_CLEANUP_STALE_BLOCKED=True|False` (opsional aktifkan cleanup saat task harian)

Catatan:
- Mode default task harian adalah audit/report (tanpa cleanup).
- Cleanup otomatis hanya berjalan jika `MIKROTIK_AUDIT_AUTO_CLEANUP_STALE_BLOCKED=True`.

## 7) Guard MAC lintas user (self-authorize)

Untuk mencegah konflik attribution kuota karena MAC ganda lintas akun:

- Sistem menerapkan guard claim-transfer MAC lintas user di service device.
- Saat MAC terdeteksi sudah dipakai akun lain dan masih aktif, claim akan ditolak kecuali alur takeover terkontrol (mis. flow yang mengizinkan replace).
- Kontrol via `DEVICE_GLOBAL_MAC_CLAIM_TRANSFER_ENABLED` (default `True`).

## 8) Hardening DB untuk MAC global (bertahap)

Migration `20260227_add_safe_global_mac_unique_index` menambahkan penguatan di level database secara aman:

- Membuat index bantu: `ix_user_devices_mac_authorized` (`WHERE is_authorized = TRUE`).
- Jika **tidak ada** duplikasi MAC authorized saat migration dijalankan, sistem otomatis membuat unique index global:
  - `uq_user_devices_authorized_mac_global` pada `UPPER(mac_address)` dengan filter `is_authorized = TRUE`.
- Jika masih ada duplikasi, migration tetap sukses (deploy tidak terblokir), dan unique index global belum dibuat sampai data konflik dibersihkan.

Rekomendasi ops:
- Jalankan audit konflik MAC terlebih dulu sebelum maintenance window.
- Setelah duplikasi dibersihkan, jalankan migration ulang/lanjutkan deployment untuk mengaktifkan unique index global.
