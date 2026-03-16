# Incident 2026-03-17: Stale Quota Sync Redis Lock Setelah Recreate

Status: resolved oleh commit `359c8adb`.

## Ringkasan insiden

Sesudah deploy recreate, beat tetap berhasil mendispatch `sync_hotspot_usage_task`, tetapi worker baru tidak menjalankan full sync karena Redis masih memegang `quota_sync:run_lock` dari worker lama. Akibatnya sinkronisasi kuota pertama setelah recreate bisa false skip walau tidak ada task aktif yang benar-benar sedang berjalan.

## Gejala yang terlihat

- Log worker menunjukkan `Celery Task: Skip sinkronisasi (worker lain sedang berjalan).`
- `celery inspect active` tidak menunjukkan `sync_hotspot_usage_task` aktif.
- Redis masih menyimpan `quota_sync:run_lock` dengan TTL positif.
- Setelah key stale dihapus manual dan task didispatch ulang, full sync langsung bisa selesai normal sekitar `64.97910919599235s`.

## Dampak

- First natural quota sync pascarecreate tertahan sampai lock lama hilang atau dihapus.
- Sinkronisasi kuota/profil bisa tertunda walau deploy publik sendiri terlihat sehat.
- Jika dibiarkan, operator berisiko salah mengira ada worker aktif lain padahal masalahnya adalah lock yatim.

## Akar masalah

- `quota_sync:run_lock` sebelumnya dipercaya penuh sebagai indikator adanya task yang masih hidup.
- Recreate container/worker dapat meninggalkan key Redis sementara task aslinya sudah tidak ada.
- Tanpa korelasi dengan `celery inspect active`, worker baru tidak bisa membedakan lock hidup dengan lock yatim.

## Investigasi yang membuktikan masalah

1. Deploy recreate selesai dan health publik kembali normal.
2. Beat mendispatch task quota sync baru.
3. Worker baru tetap skip dengan pesan `worker lain sedang berjalan`.
4. Pemeriksaan active task kosong, tetapi Redis key `quota_sync:run_lock` masih ada dan TTL-nya masih positif.
5. Setelah key stale dihapus manual, dispatch berikutnya berjalan normal dan menyelesaikan full sync.

## Remediasi permanen

Perubahan permanen ada di `backend/app/tasks.py`:

- `_has_other_active_celery_task()` mengecek apakah benar ada `sync_hotspot_usage_task` lain yang aktif.
- `_acquire_quota_sync_run_lock()` tetap menghormati lock aktif, tetapi mereclaim lock stale jika inspector Celery memastikan tidak ada task sync aktif lain.
- `sync_hotspot_usage_task()` kini memakai helper ini sebelum memutuskan skip.

Coverage permanen ditambahkan di `backend/tests/test_tasks_hotspot_usage_sync.py` untuk memastikan:

- lock stale direclaim saat tidak ada task aktif lain
- path skip tetap benar saat memang ada task aktif lain

## Verifikasi pascaperbaikan

- Validasi lokal:
  - focused pytest: `4 passed`
  - focused Ruff: bersih
- Validasi produksi setelah redeploy `359c8adb`:
  - first natural full run `89cf4aa1-d136-4783-ba5b-5afb6404a1df` selesai `66.03892844100483s`
  - run berikutnya `2db9c38b-1a6e-4524-a1f2-2b3abc959c75` selesai `64.96492313599447s`
  - run berikutnya `e70af584-b31e-43b7-a9cf-8ccc65c85fe6` selesai `60.61185126903001s`
  - parity kritis tetap nol

## Runbook diagnosis singkat bila gejala serupa muncul lagi

```bash
COMPOSE_PROD="docker compose --env-file .env.prod -f docker-compose.prod.yml"

$COMPOSE_PROD exec -T celery_worker celery -A celery_worker.celery_app inspect active
$COMPOSE_PROD exec -T redis redis-cli GET quota_sync:run_lock
$COMPOSE_PROD exec -T redis redis-cli TTL quota_sync:run_lock
$COMPOSE_PROD logs --since 15m --no-color celery_worker celery_beat \
  | grep -E 'sync_hotspot_usage_task|Sinkronisasi|Skip sinkronisasi'
```

Aturan operasional:

- Jika `inspect active` menunjukkan task sync aktif lain, jangan sentuh lock.
- Jika `inspect active` kosong tetapi lock masih hidup, treat sebagai kandidat stale lock.
- Penghapusan manual `quota_sync:run_lock` hanya boleh dilakukan saat sudah dipastikan tidak ada task sync aktif lain.
- Setelah recovery, jalankan parity audit dan tunggu minimal satu full run quota sync berikutnya.

## Artefak terkait

- `tmp/prod_down_before_recreate_20260317_004412.log`
- `tmp/deploy_detached_20260317_004429.log`
- `tmp/parity_audit_postfix_20260317_004828.log`
- `tmp/parity_audit_final_stability_20260317.log`
- `tmp/quota_cycle_final_20260317.log`
- `tmp/quota_active_state_20260317.log`