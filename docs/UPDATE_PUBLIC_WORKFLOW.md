# Public Update Workflow (WhatsApp + Approval Admin + Auto-Delete)

Dokumen ini menjelaskan alur terbaru untuk pemutakhiran data via halaman publik `/update`.

## Tujuan
- Mengizinkan user melakukan update data lewat link WhatsApp personal.
- Mencegah klaim role palsu (`KOMANDAN`/`TAMPING`) dengan approval admin wajib.
- Menjaga anti-spam pengiriman WA lewat batch bertahap.
- **Auto-delete user Imported yang tidak merespons** setelah batas waktu deadline.

## Alur End-to-End
1. Sistem mengirim WhatsApp batch (maks `UPDATE_WHATSAPP_BATCH_SIZE`, default 5 nomor unik/siklus).
2. Pesan berisi link personal `/update?phone=<encoded>&name=<encoded>` dan **peringatan deadline** (`UPDATE_CLEAR_TOTAL_AFTER_DAYS` hari).
3. User buka link, form menampilkan **VAlert peringatan** deadline dan instruksi pengisian nama.
4. User submit payload ke `POST /api/users/database-update-submissions`.
5. Data masuk tabel staging `public_database_update_submissions` dengan status awal `PENDING`.
6. Admin review di panel `admin/users` (queue approval klaim role).
  - Panel approval hanya muncul jika ada data pending atau saat loading.
  - Jika tidak ada pending request, panel approval disembunyikan agar UI admin tetap bersih.
7. Admin `approve` atau `reject` pengajuan lewat endpoint admin update-submissions.
8. **[Auto-delete path]** Jika user tidak submit form dalam `UPDATE_CLEAR_TOTAL_AFTER_DAYS` hari sejak WA dikirim (`whatsapp_notified_at`), task Celery `auto_delete_unresponsive_imported_users_task` akan menghapus akun otomatis.

## Aturan Form `/update`
- `phone_number`
  - Wajib ada dari link WhatsApp.
  - Ditampilkan di UI tetapi `disabled/readonly`.
  - Submit ditolak jika nomor dari link tidak tersedia.
- **VAlert peringatan deadline** ditampilkan di atas form (selama form aktif):
  - Pesan: "Segera lengkapi data Anda dalam **N hari** sejak menerima pesan ini. Jika tidak diperbarui, akun Anda akan **dihapus otomatis** dari sistem."
  - `N` = `NUXT_PUBLIC_UPDATE_DEADLINE_DAYS` (default 3).
- Field `full_name`:
  - Placeholder: "Contoh: Budi Santoso"
  - Hint: "Masukkan nama lengkap Anda, bukan nama sistem"
- `role` yang valid: `USER`, `TAMPING`, `KOMANDAN`.
- Rule field kondisional:
  - `USER` => wajib `blok` dan `kamar`.
  - `TAMPING` => wajib `tamping_type`.
  - `KOMANDAN` => tanpa field tambahan.

## Endpoint Terkait

### Public
- `POST /api/users/database-update-submissions`
  - Menyimpan pengajuan ke tabel staging.
  - Tidak langsung mengubah role user aktif.
  - Fitur endpoint diproteksi flag backend `PUBLIC_DB_UPDATE_FORM_ENABLED`.

### Admin
- `GET /api/admin/update-submissions?status=PENDING&page=1&itemsPerPage=20`
- `POST /api/admin/update-submissions/{id}/approve`
- `POST /api/admin/update-submissions/{id}/reject`

## Efek Approval
- `approve`:
  - `KOMANDAN` -> role user jadi `KOMANDAN`.
  - `TAMPING` -> user tetap role `USER`, set `is_tamping=true`, isi `tamping_type`.
  - `USER` -> role user `USER`, set `blok/kamar`.
- `reject`:
  - Pengajuan diberi status `REJECTED` dan bisa menyimpan `rejection_reason`.

## Konfigurasi ENV Penting
- Backend (`/.env.prod`):
  - `PUBLIC_DB_UPDATE_FORM_ENABLED` — aktifkan endpoint + halaman update
  - `UPDATE_ENABLE_SYNC` — aktifkan task celery beat pengiriman WA
  - `UPDATE_SYNC_CHECK_INTERVAL_SECONDS` — interval check kirim WA (detik, default 600)
  - `UPDATE_WHATSAPP_BATCH_SIZE` — maks nomor/siklus pengiriman (default 5)
  - `UPDATE_CLEAR_TOTAL_AFTER_DAYS` — deadline hari sebelum auto-clear/delete (default 3)
  - `UPDATE_AUTO_DELETE_UNRESPONSIVE` — aktifkan auto-delete user tidak merespons (default False)
  - `UPDATE_AUTO_DELETE_MAX_PER_RUN` — maks user dihapus per 1 run task (default 5)
  - `UPDATE_WHATSAPP_IMPORT_MESSAGE_TEMPLATE` — override template WA (opsional)
  - `APP_PUBLIC_BASE_URL` — base URL untuk link update dalam pesan WA
- Frontend (`/.env.public.prod` → `nuxt.config.ts` runtimeConfig.public):
  - `NUXT_PUBLIC_PUBLIC_DB_UPDATE_FORM_ENABLED` (prioritas utama)
  - `NUXT_PUBLIC_DB_UPDATE_FORM_ENABLED` (fallback kompatibilitas)
  - `NUXT_PUBLIC_UPDATE_DEADLINE_DAYS` — jumlah hari deadline ditampilkan di VAlert (default 3)

## Auto-Delete User Tidak Merespons

### Mekanisme
Task `auto_delete_unresponsive_imported_users_task` (Celery Beat, setiap `max(300, UPDATE_SYNC_CHECK_INTERVAL_SECONDS)` detik):
1. Guard: `UPDATE_ENABLE_SYNC=True` dan `UPDATE_AUTO_DELETE_UNRESPONSIVE=True` (kedua-duanya harus true).
2. Baca `deadline_days` dari `UPDATE_CLEAR_TOTAL_AFTER_DAYS` (min 1).
3. Hitung `cutoff = now_utc - timedelta(days=deadline_days)`.
4. Query submissions: `whatsapp_notified_at IS NOT NULL`, `whatsapp_notified_at < cutoff`, `approval_status = 'PENDING'`.
5. Per nomor unik (max `UPDATE_AUTO_DELETE_MAX_PER_RUN`):
   - Cari user di DB → skip jika tidak ditemukan.
   - Skip jika role `ADMIN` atau `SUPER_ADMIN`.
   - Skip jika `full_name` tidak diawali `"Imported "`.
   - Skip jika `quota_expiry_date > now_utc` (kuota masih aktif).
   - Delete hotspot user + IP binding + address-list dari MikroTik.
   - Delete `UserDevice` dan `User` dari DB.
   - Update submission: `approval_status = "DELETED_AUTO"`, `rejection_reason = "Auto-deleted: tidak merespons X hari"`.
   - Catat ke `AdminActionLog` (action_type `MANUAL_USER_DELETE`, admin_id `None`).
6. Commit DB sekali di akhir.

### Safety Default
- `UPDATE_AUTO_DELETE_UNRESPONSIVE=False` saat deploy pertama — task terdaftar di beat tapi SKIP karena guard.
- Aktifkan ke `True` hanya setelah verifikasi WA sudah terkirim dan deadline sudah berlalu.
- Quota guard mencegah user aktif terhapus tanpa sengaja.
- Max per run mencegah penghapusan massal tak terkendali.

### Cara Aktifkan di Produksi
```bash
# Di server Pi:
sed -i 's/UPDATE_AUTO_DELETE_UNRESPONSIVE=False/UPDATE_AUTO_DELETE_UNRESPONSIVE=True/' \
    /home/abdullah/lpsaring/app/.env.prod
cd /home/abdullah/lpsaring/app
docker compose -f docker-compose.prod.yml up -d --force-recreate celery_beat celery_worker
# Verifikasi:
docker exec hotspot_prod_celery_beat env | grep UPDATE_AUTO_DELETE
# Expected: UPDATE_AUTO_DELETE_UNRESPONSIVE=True
```

## Catatan Implementasi Frontend
- Halaman `/update` hanya menampilkan form jika runtime flag frontend bernilai aktif.
- Nomor telepon diambil dari query `phone`/`msisdn`; jika tidak tersedia, submit diblok dengan pesan error.
- Tombol kembali login setelah submit sukses menggunakan handler internal (`goToLogin`) untuk menjaga kompatibilitas typecheck template.

## Validasi Minimum Setelah Perubahan
- Frontend typecheck: `pnpm run typecheck`.
- Frontend lint terarah:
  - `pnpm exec eslint pages/update/index.vue pages/admin/users.vue pages/login/hotspot-required.vue nuxt.config.ts`.
- Frontend test runtime: `pnpm run test`.

## Catatan Keamanan
- Klaim role dari form publik tidak boleh langsung diterapkan ke tabel user aktif.
- Satu-satunya jalur mutasi role klaim update adalah endpoint admin approval.
- Nomor telepon berasal dari link sistem agar identitas submitter terikat ke target distribusi WA.
