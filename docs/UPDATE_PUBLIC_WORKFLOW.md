# Public Update Workflow (WhatsApp + Approval Admin)

Dokumen ini menjelaskan alur terbaru untuk pemutakhiran data via halaman publik `/update`.

## Tujuan
- Mengizinkan user melakukan update data lewat link WhatsApp personal.
- Mencegah klaim role palsu (`KOMANDAN`/`TAMPING`) dengan approval admin wajib.
- Menjaga anti-spam pengiriman WA lewat batch bertahap.

## Alur End-to-End
1. Sistem mengirim WhatsApp batch (maks `UPDATE_WHATSAPP_BATCH_SIZE`, default 3 nomor unik/siklus).
2. Pesan berisi link personal `/update?phone=<encoded>&name=<encoded>`.
3. User buka link, form otomatis mengisi nomor dari query.
4. User submit payload ke `POST /api/users/database-update-submissions`.
5. Data masuk tabel staging `public_database_update_submissions` dengan status awal `PENDING`.
6. Admin review di panel `admin/users` (queue approval klaim role).
7. Admin `approve` atau `reject` pengajuan lewat endpoint admin update-submissions.

## Aturan Form `/update`
- `phone_number`
  - Wajib ada dari link WhatsApp.
  - Ditampilkan di UI tetapi `disabled/readonly`.
  - Submit ditolak jika nomor dari link tidak tersedia.
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
- `PUBLIC_DB_UPDATE_FORM_ENABLED`
- `UPDATE_ENABLE_SYNC`
- `UPDATE_SYNC_CHECK_INTERVAL_SECONDS`
- `UPDATE_WHATSAPP_BATCH_SIZE`
- `UPDATE_WHATSAPP_IMPORT_MESSAGE_TEMPLATE`
- `APP_PUBLIC_BASE_URL`

## Catatan Keamanan
- Klaim role dari form publik tidak boleh langsung diterapkan ke tabel user aktif.
- Satu-satunya jalur mutasi role klaim update adalah endpoint admin approval.
- Nomor telepon berasal dari link sistem agar identitas submitter terikat ke target distribusi WA.
