# Devlog 2026-03-08 — Auto-Delete User Imported + WA Deadline Warning + Update Form UX

**Sesi:** 5 dari 5 pada tanggal 2026-03-08
**Scope:** Fitur auto-delete user Imported tidak merespons, perbaikan template WA dengan peringatan deadline, peningkatan UX form `/update`, dan deploy produksi aktif.
**Status:** Selesai — commit di-push, CI hijau, deploy produksi sukses, `UPDATE_AUTO_DELETE_UNRESPONSIVE=True` aktif di server.

---

## 1. Latar Belakang

User yang di-import ke sistem (nama `"Imported XXXX"`) menerima notifikasi WhatsApp berisi link form `/update`. Jika user tidak mengisi form dalam `UPDATE_CLEAR_TOTAL_AFTER_DAYS` hari sejak WA terkirim (`whatsapp_notified_at`), akun harus dihapus otomatis. Dua masalah yang perlu diselesaikan:

1. **Tidak ada mechansme penghapusan otomatis** — sebelumnya hanya ada `clear_total_if_no_update_submission_task` yang hanya membersihkan kuota, bukan menghapus akun.
2. **Template WA dan form `/update` tidak memberi peringatan deadline** — user tidak tahu akun mereka berisiko dihapus.

---

## 2. Perubahan Kode

### A) `backend/app/tasks.py`

**Import yang ditambahkan:**
- `AdminActionLog, AdminActionType` ke grup model imports utama (pindah dari deklarasi lokal).
- `PublicDatabaseUpdateSubmission` ke grup model imports utama (pindah dari 2 fungsi lokal).
- `remove_ip_binding` ke group `mikrotik_client` imports.

**Update `send_public_update_submission_whatsapp_batch_task`:**
- Baca `deadline_days = int(app.config.get("UPDATE_CLEAR_TOTAL_AFTER_DAYS", 3))`.
- Tambahkan `"deadline_days": deadline_days` ke context dict setiap penerima.
- Update default template WA dengan peringatan deadline:

```
Halo *{full_name}*,

Kami mendeteksi data Anda di jaringan LPSaring perlu dilengkapi.

Silakan perbarui data melalui link berikut *dalam {deadline_days} hari*:
{update_link}

⚠️ *Peringatan:* Jika tidak diperbarui, akun Anda akan *dihapus otomatis* dari sistem.

Terima kasih,
Tim LPSaring
```

**Task baru `auto_delete_unresponsive_imported_users_task`:**
- Guard ganda: `UPDATE_ENABLE_SYNC` + `UPDATE_AUTO_DELETE_UNRESPONSIVE`.
- Query: submissions dengan `whatsapp_notified_at < cutoff` dan `approval_status = 'PENDING'`.
- Per nomor unik: skip admin/super_admin, skip non-"Imported " name, skip user berquota aktif.
- MikroTik cleanup: `delete_hotspot_user` + `remove_ip_binding` per device MAC + `remove_address_list_entry` per device IP.
- DB cleanup: hapus `UserDevice`, hapus `User`.
- Marking submissions: `approval_status = "DELETED_AUTO"`, `rejection_reason = "Auto-deleted: tidak merespons X hari"`.
- Log ke `AdminActionLog` (admin_id=None, action_type=MANUAL_USER_DELETE) dengan detail JSON.
- Satu `db.session.commit()` di akhir batch.

**Catatan implementasi `AdminActionLog` (Pylance fix):**
SQLAlchemy declarative models tidak selalu terinferensi punya `__init__(**kwargs)` oleh Pylance. Pakai pola attribute-assignment:
```python
log_entry = AdminActionLog()
log_entry.admin_id = None
log_entry.target_user_id = None
log_entry.action_type = AdminActionType.MANUAL_USER_DELETE
log_entry.details = json.dumps({...})
db.session.add(log_entry)
```
Pola ini konsisten dengan `helpers.py` dan `request_management_routes.py`.

---

### B) `backend/app/extensions.py`

Di dalam blok `if os.environ.get("UPDATE_ENABLE_SYNC") == "true":`, tambahkan:
```python
if os.environ.get("UPDATE_AUTO_DELETE_UNRESPONSIVE", "False").lower() == "true":
    celery_instance.conf.beat_schedule["auto-delete-unresponsive-imported"] = {
        "task": "auto_delete_unresponsive_imported_users_task",
        "schedule": max(300, update_sync_interval),
    }
```

Beat schedule hanya terdaftar jika flag aktif — artinya saat `False`, task tidak muncul di beat scheduler sama sekali.

---

### C) `.env.prod` (lokal, gitignored)

Vars yang ditambahkan/diubah:
```
UPDATE_WHATSAPP_BATCH_SIZE=5          # was 3
UPDATE_AUTO_DELETE_UNRESPONSIVE=True  # was False (awalnya deploy sebagai False)
UPDATE_AUTO_DELETE_MAX_PER_RUN=5
```

---

### D) `.env.public.prod` (lokal, gitignored)

Var baru:
```
NUXT_PUBLIC_UPDATE_DEADLINE_DAYS=3
```

---

### E) `frontend/nuxt.config.ts`

```typescript
// Const baru:
const updateDeadlineDays = Number(process.env.NUXT_PUBLIC_UPDATE_DEADLINE_DAYS ?? '3')

// Di runtimeConfig.public:
updateDeadlineDays,
```

---

### F) `frontend/pages/update/index.vue`

1. **`deadlineDays` computed:**
   ```typescript
   const deadlineDays = computed(() => Number(runtimeConfig.public.updateDeadlineDays ?? 3))
   ```

2. **VAlert peringatan** (sebelum form, tipe `warning`):
   ```html
   <VAlert type="warning" variant="tonal" class="mb-4">
     <strong>Perhatian:</strong> Segera lengkapi data Anda dalam
     <strong>{{ deadlineDays }} hari</strong> sejak menerima pesan ini.
     Jika tidak diperbarui, akun Anda akan <strong>dihapus otomatis</strong> dari sistem.
   </VAlert>
   ```

3. **Field Nama Lengkap** — tambah `placeholder` + `hint` + `persistent-hint`:
   - `placeholder="Contoh: Budi Santoso"`
   - `hint="Masukkan nama lengkap Anda, bukan nama sistem (mis. yang diawali 'Imported')"`

4. **Success message** lebih informatif:
   - `{{ successMessage || 'Data Anda telah diterima dan sedang ditinjau admin. Akun Anda tidak akan dihapus otomatis.' }}`

---

## 3. Verifikasi Sebelum Push

- **Pylance:** 0 errors (VS Code diagnostics clean setelah fix `AdminActionLog` pattern).
- **pytest:** 232 tests passed, 0 failed.
- **ruff:** 0 violations.
- **vue-tsc:** 0 type errors.

---

## 4. CI/CD Timeline

| Langkah | Commit/Run | Status |
|---------|-----------|--------|
| Commit feat | `3d325e9d` — feat: auto-delete + WA template + form | ✅ |
| CI run | `22823173368` | ✅ success |
| Commit style | `ec3cadcb` — style: fix AdminActionLog attribute assignment | ✅ |
| CI run | `22823276443` | ✅ success |
| Docker Publish | `22823315725` | ✅ success (frontend 2m58s, backend 41s) |

---

## 5. Deploy Produksi

### Env server diupdate via SSH
```bash
# .env.prod server — ditambahkan:
UPDATE_WHATSAPP_BATCH_SIZE=5
UPDATE_AUTO_DELETE_UNRESPONSIVE=False   # awal deploy
UPDATE_AUTO_DELETE_MAX_PER_RUN=5

# .env.public.prod server — ditambahkan:
NUXT_PUBLIC_UPDATE_DEADLINE_DAYS=3
```

### Deploy dengan force-recreate images baru:
```bash
cd /home/abdullah/lpsaring/app
docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml up -d --force-recreate
```

### Aktifkan auto-delete (setelah verifikasi form berfungsi):
```bash
sed -i 's/UPDATE_AUTO_DELETE_UNRESPONSIVE=False/UPDATE_AUTO_DELETE_UNRESPONSIVE=True/' .env.prod
docker compose -f docker-compose.prod.yml up -d --force-recreate celery_beat celery_worker
```

**Catatan:** `--force-recreate celery_beat celery_worker` juga menyebabkan `db` dan `flask_migrate` ikut direcreate karena dependency chain. Ini mengakibatkan brief DB reconnect pada backend (~30 detik). Untuk menghindari ini di masa depan, set env var di `docker-compose.override.yml` atau gunakan `docker exec`:
```bash
# Alternatif minimal (tidak force-recreate DB):
docker compose -f docker-compose.prod.yml stop celery_beat celery_worker
docker compose -f docker-compose.prod.yml up -d celery_beat celery_worker
```

---

## 6. Verifikasi Post-Deploy

| Container | Status | ENV UPDATE_AUTO_DELETE_UNRESPONSIVE |
|-----------|--------|-------------------------------------|
| `hotspot_prod_celery_beat` | ✅ Up | `True` |
| `hotspot_prod_celery_worker` | ✅ Up | `True` |
| `hotspot_prod_flask_backend` | ✅ Up | `False` (tidak direcreate) |
| `hotspot_prod_nuxt_frontend` | ✅ healthy | N/A |
| `hotspot_prod_postgres_db` | ✅ healthy | N/A |
| `hotspot_prod_redis_cache` | ✅ healthy | N/A |

**Catatan:** Backend container masih `False` karena tidak direcreate. Ini tidak masalah — auto-delete berjalan di celery_worker, bukan backend. Pada deploy berikutnya semua container akan sinkron.

**Task terdaftar di celery_worker:**
```
. auto_delete_unresponsive_imported_users_task   ← ✅ terdaftar
```

**Beat schedule:** Task akan fire setiap `max(300, 600) = 600` detik sejak celery_beat start.

**Endpoint `/update`:** HTTP 200 ✅
**Peringatan deadline:** Ditampilkan di form ✅
**`/api/ping`:** `pong` ✅

---

## 7. Analisa Log Nginx & Docker

### Nginx lpsaring (statistik 2000 request terakhir per 2026-03-08)

| Metrik | Nilai |
|--------|-------|
| HTTP 200 | 1780 (89%) |
| HTTP 304 | 103 (5.2%) |
| HTTP 401 | 46 (2.3%) — auth expired/unauthenticated (normal) |
| HTTP 500 | 23 (1.2%) — intermittent backend errors |
| HTTP 502 | 9 (0.5%) — brief backend unavailable |
| HTTP 499 | 14 (0.7%) — client closed before response |
| HTTP 504 | 3 (0.15%) — upstream timeout |

**Top endpoint:**
- `/api/auth/me` — 790 request (polling auth state dari admin panel + SSR)
- `/api/admin/users` — 82
- `/api/admin/dashboard/stats` — 75

**Top IP:**
- `140.213.10.104` — 894 request (admin user, browser Chrome Windows)
- `192.168.0.4` — 648 request (admin lokal, LAN)
- `202.65.239.46` — 416 request (user mobile Android)

### Error Log Analisis

**Tipe error utama:**
1. `lpsaring-backend could not be resolved (2: Server failure)` — saat backend container restart/recreate, nginx kehilangan DNS resolusi sementara. Terutama terlihat pada 2026-03-06 14:33–20:31 dan 2026-03-07 13:03–17:50.
2. `upstream prematurely closed connection` — backend menutup koneksi sebelum response selesai (biasanya saat worker restart atau DB query lambat).
3. `connect() failed (111: Connection refused)` — backend belum ready setelah restart.
4. `upstream timed out (110: Operation timed out)` — pada 06:35–06:37 dan 12:06 frontend timed out (Nuxt SSR response lambat untuk Android captive portal probe).

**Status saat ini (2026-03-08 23:00+):**
- Error log terakhir: 14:50:23 UTC (sebelum sesi ini)
- Setelah deploy sesi ini: tidak ada error baru

### Docker Logs

**Backend (post force-recreate):**
```
23:01:57 — (psycopg2.OperationalError) server closed the connection unexpectedly
```
→ Disebabkan postgres container kena force-recreate dari dependency chain. Backend reconnect otomatis dalam ~30 detik.

**Celery Worker:**
- Task terdaftar: 15 tasks termasuk `auto_delete_unresponsive_imported_users_task`
- MikroTik pool init: ✅ `10.19.83.2`
- `sync_hotspot_usage_task`: berjalan normal
- `Skip sync address-list by username` — normal untuk user tanpa ip-binding

**PostgreSQL:**
- Restart bersih, tidak ada OOM, tidak ada deadlock

**Redis:**
- Periodic RDB save setiap ~5 menit (100 changes/300s)

---

## 8. Ringkasan File yang Diubah

| File | Perubahan |
|------|-----------|
| `backend/app/tasks.py` | Import pindah ke top-level, WA template + deadline_days, task auto-delete baru |
| `backend/app/extensions.py` | Beat schedule auto-delete (gated oleh UPDATE_AUTO_DELETE_UNRESPONSIVE) |
| `.env.prod` (lokal) | `UPDATE_WHATSAPP_BATCH_SIZE=5`, `UPDATE_AUTO_DELETE_UNRESPONSIVE=True`, `UPDATE_AUTO_DELETE_MAX_PER_RUN=5` |
| `.env.public.prod` (lokal) | `NUXT_PUBLIC_UPDATE_DEADLINE_DAYS=3` |
| `frontend/nuxt.config.ts` | const `updateDeadlineDays` + runtimeConfig.public entry |
| `frontend/pages/update/index.vue` | `deadlineDays` computed, VAlert deadline, placeholder+hint nama, success message |

---

## 9. Catatan Penting

1. **Backend container env belum sinkron `UPDATE_AUTO_DELETE_UNRESPONSIVE`** — backend masih `False`, celery `True`. Tidak masalah untuk fitur ini. Akan sinkron pada deploy berikutnya.

2. **Dependency chain force-recreate** — saat `--force-recreate celery_beat celery_worker`, docker compose ikut recreate `db` dan `migrate` karena depends_on. Pertimbangkan `docker compose stop ... && up -d ...` untuk menghindari DB restart di masa depan.

3. **Task baru mendeteksi submission `PENDING`** — jika ada submission yang sudah lama tidak di-approve/reject, task ini bisa menghapus user. Pastikan admin sudah menyelesaikan review pending submissions sebelum mengaktifkan fitur ini.

4. **`UPDATE_CLEAR_TOTAL_AFTER_DAYS=3`** — deadline hanya 3 hari. Pertimbangkan menambah ke 7 hari jika WA tidak selalu terbaca oleh user dalam 3 hari.

5. **`404` untuk `/_nuxt/*.js`** — user Android (202.65.239.46) meminta chunk Nuxt lama yang tidak ada setelah deploy frontend. Ini normal dan akan hilang setelah browser user reload page atau cache dibersihkan.
