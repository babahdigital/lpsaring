# Devlog Hotspot Sync Hardening (2026-03-16 s.d. 2026-03-17)

Dokumen ini merangkum seri optimisasi hotspot sync yang dipromosikan ke produksi, insiden stale lock yang ditemukan setelah recreate, dan hasil verifikasi akhir di produksi.

## Tujuan

- Menurunkan runtime penuh `sync_hotspot_usage_task` yang sebelumnya terlalu lama untuk satu siklus produksi.
- Mengurangi round-trip RouterOS, DHCP, dan address-list yang tidak memberi perubahan nyata.
- Menutup false skip pascarecreate ketika Redis masih menyimpan `quota_sync:run_lock` dari worker lama.
- Memastikan parity kritis tetap aman setelah seluruh perubahan dipromosikan.

## Ringkasan hasil akhir

| Tahap | Commit | Runtime penuh |
| --- | --- | --- |
| Baseline sebelum seri optimisasi | sebelum `bcfa8524` | sekitar `450-484s` |
| Reuse managed status snapshot | `bcfa8524` | `323.9s` |
| Cache runtime settings per run | `a6edfd9a` | `317.12035042699426s` |
| Reduksi RouterOS self-heal call | `4f7a1110` | `64.97910919599235s` |
| Pasca recovery stale lock | `359c8adb` | `66.03892844100483s`, `64.96492313599447s`, `60.61185126903001s` |

Status akhir produksi:

- Full run quota sync stabil di kisaran `60-66s`.
- Counter parity kritis tetap `0`.
- Skip setelah beat tambahan hanya muncul karena `menunggu interval dinamis` atau karena memang ada task aktif lain, bukan karena lock yatim.

## Rangkaian commit utama

### `bcfa8524` - `perf: reuse managed status snapshot during hotspot sync`

Masalah utama:

- Satu siklus sinkronisasi masih membangun snapshot managed status berulang pada jalur yang sama, padahal snapshot itu bisa dipakai ulang selama satu run.

Solusi:

- `backend/app/services/hotspot_sync_service.py` diubah agar snapshot managed status dipakai ulang sepanjang satu cycle.
- Regresi ditambah di `backend/tests/test_hotspot_sync_address_list_status.py` dan `backend/tests/test_hotspot_sync_user_error_isolation.py`.

Dampak:

- Runtime penuh turun dari sekitar `450-484s` ke `323.9s`.

### `a6edfd9a` - `perf: cache hotspot sync runtime settings`

Masalah utama:

- Runtime settings dibaca berulang dari layer settings/database saat sync berjalan, membuat churn session dan keputusan runtime yang seharusnya bisa dibekukan sekali di awal run.

Solusi:

- `backend/app/services/hotspot_sync_service.py` kini memuat runtime settings sekali di awal sinkronisasi lalu meneruskannya ke flow internal.
- Regresi tambahan dimasukkan ke `backend/tests/test_hotspot_sync_address_list_status.py` dan `backend/tests/test_hotspot_sync_debt_limit.py`.

Dampak:

- Runtime turun lagi menjadi `317.12035042699426s`.

### `4f7a1110` - `perf: reduce redundant hotspot self-heal routeros calls`

Masalah utama:

- Self-heal binding, DHCP, dan cleanup hotspot host masih memicu round-trip RouterOS berulang.
- Sejumlah jalur melakukan no-op write atau fallback cleanup yang terus berjalan walau removal pertama sudah sukses.

Solusi:

- `backend/app/services/hotspot_sync_service.py` dipangkas agar no-op update dan self-heal call yang redundan tidak terus berjalan.
- `backend/app/services/device_management_service.py` memakai ulang koneksi aktif untuk DHCP/static lease path yang relevan.
- `backend/app/infrastructure/gateways/mikrotik_client.py` menghentikan best-effort hotspot host cleanup setelah removal pertama yang sukses.
- Coverage diperluas di `backend/tests/test_hotspot_sync_address_list_status.py`, `backend/tests/test_hotspot_sync_debt_limit.py`, dan `backend/tests/test_mikrotik_remove_hotspot_host_entries_best_effort.py`.

Dampak:

- Setelah deploy dan dispatch manual, full run produksi turun drastis ke `64.97910919599235s`.

### `359c8adb` - `fix: recover stale quota sync redis lock`

Masalah utama:

- Setelah recreate, beat tetap mendispatch `sync_hotspot_usage_task`, tetapi worker baru langsung log `Skip sinkronisasi (worker lain sedang berjalan)`.
- Redis masih menyimpan `quota_sync:run_lock` walau `celery inspect active` tidak menunjukkan task sinkronisasi aktif.

Solusi:

- `backend/app/tasks.py` menambahkan `_has_other_active_celery_task()` untuk memeriksa task aktif lintas worker.
- `backend/app/tasks.py` menambahkan `_acquire_quota_sync_run_lock()` untuk membedakan lock hidup vs lock yatim, lalu hanya melakukan reclaim saat tidak ada `sync_hotspot_usage_task` aktif lain.
- Regresi baru ditambahkan di `backend/tests/test_tasks_hotspot_usage_sync.py` untuk dua skenario penting:
  - lock stale direclaim bila tidak ada task aktif lain
  - skip tetap dipertahankan bila task aktif lain benar-benar ada

Dampak:

- First natural run pascarecreate kembali jalan normal di `66.03892844100483s`.
- Putaran berikutnya stabil di `64.96492313599447s` dan `60.61185126903001s`.

## Timeline promosi ke produksi

1. Commit `4f7a1110` dipush ke `main`.
2. CI manual `23153560162` berhasil.
3. Docker publish manual `23153564061` berhasil.
4. Deploy recreate dijalankan dan health publik diverifikasi.
5. Setelah deploy pertama, ditemukan stale Redis lock yang menahan first natural quota sync.
6. Commit `359c8adb` dibuat untuk recovery stale lock dan dipush ke `main`.
7. Docker publish manual `23154972860` berhasil.
8. Produksi diturunkan dulu dengan `down --remove-orphans`, lalu dideploy ulang memakai `./deploy_pi.sh --detach-local --recreate`.
9. Setelah redeploy, beberapa siklus quota sync dan parity audit dijalankan untuk memastikan stabilitas.

## Verifikasi produksi

### Health publik dan container

- Semua service Compose app stack kembali `up`.
- Endpoint `/api/ping` merespons `200`.
- Halaman `/login` merespons `200`.
- Asset `/_nuxt/...` ikut berhasil dilayani.

### Siklus quota sync yang tervalidasi

- `89cf4aa1-d136-4783-ba5b-5afb6404a1df`
  - durasi `66.03892844100483s`
  - `processed=90`
  - `updated_usage=24`
  - `profile_updates=0`
  - `binding_self_healed=1`
  - `dhcp_self_healed=34`
  - `failed=0`
- `2db9c38b-1a6e-4524-a1f2-2b3abc959c75`
  - durasi `64.96492313599447s`
  - bentuk hasil tetap sehat seperti run sebelumnya
- `e70af584-b31e-43b7-a9cf-8ccc65c85fe6`
  - durasi `60.61185126903001s`
  - bentuk hasil tetap sehat seperti run sebelumnya

### Hasil parity audit

Counter kritis terakhir yang tervalidasi:

- `status_without_binding=0`
- `critical_without_binding=0`
- `unauthorized_overlap=0`
- `status_multi_overlap=0`
- `binding_dhcp_ip_mismatch=0`

Residual non-kritis yang masih dicatat:

- `authorized_mac_without_dhcp` sempat `2` pada audit pascaperbaikan, lalu naik ke `24` pada audit stabilitas lanjutan.
- Counter ini diperlakukan sebagai drift device authorized yang sedang offline sampai ada audit per-device yang membuktikan sebaliknya.

### Audit residual lanjutan

Audit parity lanjutan yang dijalankan setelah dokumentasi awal selesai menunjukkan residual live terbaru justru sudah turun kembali ke `2` device authorized tanpa DHCP lease.

Karakteristik dua residual tersebut:

- Keduanya masih punya `ip-binding` bertipe `bypassed` dan comment user/uid yang valid.
- Keduanya masih muncul di `/ip/hotspot/host` sebagai host `bypassed`, sehingga masalahnya bukan hilangnya binding atau parity kritis.
- Keduanya tidak memiliki row `/ip/dhcp-server/lease` saat audit dilakukan.

Interpretasi operasional saat ini:

- Residual ini tetap tergolong non-kritis karena `critical_without_binding=0`, `unauthorized_overlap=0`, dan `binding_dhcp_ip_mismatch=0`.
- Device tersebut lebih tepat diperlakukan sebagai kandidat drift DHCP yang perlu audit targetted, bukan blocker deploy atau parity failure.

Artefak audit follow-up:

- `tmp/parity_authorized_without_dhcp_latest.log`
- `tmp/parity_authorized_without_dhcp_latest.json`

## Artefak operasi yang dipakai sebagai sumber kebenaran

- Deploy:
  - `tmp/deploy_detached_20260317_001805.log`
  - `tmp/prod_down_before_recreate_20260317_004412.log`
  - `tmp/deploy_detached_20260317_004429.log`
- Parity:
  - `tmp/parity_audit_20260317_002046.log`
  - `tmp/parity_audit_postfix_20260317_004828.log`
  - `tmp/parity_audit_final_stability_20260317.log`
- Snapshot stabilitas:
  - `tmp/nginx_poststable_20260317_005229.log`
  - `tmp/worker_poststable_20260317_005326.log`
  - `tmp/quota_cycle_final_20260317.log`
  - `tmp/quota_active_state_20260317.log`

## Pelajaran operasional

- Untuk command SSH yang panjang, output wrapper terminal tidak boleh dijadikan source of truth; capture ke file lokal `tmp/` lebih andal.
- Redis lock tanpa validasi task aktif tidak cukup aman untuk worker yang bisa direcreate sewaktu-waktu.
- `authorized_mac_without_dhcp` harus dibaca sebagai sinyal audit lanjutan, bukan blocker deploy, selama counter parity kritis tetap nol.

## Tindak lanjut yang masih opsional

- Audit targetted untuk daftar `authorized_mac_without_dhcp` bila ingin membersihkan residual offline drift.
- Pertahankan focused test hotspot sync setiap kali ada perubahan di `backend/app/tasks.py`, `backend/app/services/hotspot_sync_service.py`, atau gateway MikroTik.