# 2026-03-21 Invoice Notification Audit and Debt WA Share

## Ringkasan

Batch ini menutup blind spot observability untuk notifikasi invoice WhatsApp dan menambahkan jalur admin untuk mengirim ringkasan tunggakan manual beserta lampiran PDF debt report ke WhatsApp user.

## Latar Belakang

Sebelumnya:
- alur transaksi Midtrans sudah tercatat baik di `transaction_events` untuk `INITIATED`, `NOTIFICATION`, dan `MIKROTIK_APPLY_SUCCESS`
- enqueue dan hasil kirim WhatsApp invoice tidak tercatat di database
- verifikasi invoice WA harus bergantung pada retensi log Docker/Celery
- admin hanya bisa melihat PDF debt report atau melunasi debt, tetapi belum bisa mengirim ringkasan tunggakan manual ke user via WhatsApp dengan attachment PDF

## Perubahan Implementasi

### 1. Transaction event untuk invoice WhatsApp

Saat webhook Midtrans sukses atau admin reconcile sukses mengantrekan invoice WA, aplikasi kini menulis event:
- `WHATSAPP_INVOICE_QUEUED`

Saat worker Celery memproses pengiriman, task kini bisa menulis event lanjutan:
- `WHATSAPP_INVOICE_SEND_ATTEMPT`
- `WHATSAPP_INVOICE_SEND_SUCCESS`
- `WHATSAPP_INVOICE_PDF_FAILED`
- `WHATSAPP_INVOICE_TEXT_FALLBACK_SUCCESS`
- `WHATSAPP_INVOICE_TEXT_FALLBACK_FAILED`
- `WHATSAPP_INVOICE_SEND_EXCEPTION`

Catatan desain:
- event tetap memakai `source=APP`
- event hanya ditulis bila task menerima `transaction_id`
- debt-report WA tidak dipaksakan masuk ke `transaction_events` karena bukan lifecycle transaksi pembayaran

### 2. Temp token khusus debt report PDF

Ditambahkan helper baru di `notification_service`:
- `generate_temp_debt_report_token(user_id)`
- `verify_temp_debt_report_token(token)`

Token ini dipisahkan dari invoice token dengan salt serializer yang berbeda agar ruang akses dokumen tidak tercampur.

### 3. Route public sementara untuk lampiran debt report

Ditambahkan route bertoken:
- `GET /api/admin/users/debts/temp/<token>`
- `GET /api/admin/users/debts/temp/<token>.pdf`

Route ini merender PDF yang sama dengan export admin debt report, tetapi tanpa sesi admin, sehingga aman dipakai sebagai attachment URL oleh provider WhatsApp selama token masih valid.

### 4. Tombol admin kirim WhatsApp debt report

Ditambahkan endpoint admin:
- `POST /api/admin/users/{user_id}/debts/send-whatsapp`

Perilaku endpoint:
- menolak jika user tidak ada, akses admin tidak sah, atau tidak ada item manual debt yang masih terbuka
- membangun ringkasan tunggakan manual dari data yang sama dengan export PDF
- menghasilkan URL PDF temporary bertoken
- merender template WhatsApp khusus `user_debt_report_with_pdf`
- mengantrekan pengiriman PDF ke task Celery

### 5. UI admin debt

Frontend admin diperbarui di dua titik:
- ikon WhatsApp kecil pada cluster aksi status tunggakan di dialog edit user
- tombol `WhatsApp` di header/footer dialog `Riwayat Tunggakan`

Target UX:
- admin bisa tetap preview PDF terlebih dahulu
- admin juga punya aksi langsung untuk mengirim ringkasan + attachment tanpa keluar dari dialog tunggakan

## Template WhatsApp Baru

Ditambahkan template `user_debt_report_with_pdf` dengan konteks:
- `full_name`
- `total_manual_debt_gb`
- `total_manual_debt_amount_display`
- `open_items`
- `debt_detail_lines`
- `debt_pdf_url`

Template ini dirancang untuk:
- menampilkan total tunggakan
- merangkum daftar item terbuka
- tetap menyertakan tautan fallback jika attachment PDF gagal dibuka di sisi user

## Audit Produksi Terkait

Audit read-only production untuk dua nomor yang diminta user menunjukkan:

### `+6285122598880`
- user: `Didi Hidayat`
- status: `APPROVED`, aktif, tidak diblokir
- transaksi terbaru: `BD-LPSR-F2867B092231`
- nominal: `100000`
- status: `SUCCESS`
- payment method: `qris`
- event DB yang ada: `INITIATED`, `MIDTRANS_WEBHOOK/NOTIFICATION/SUCCESS`, `MIKROTIK_APPLY_SUCCESS`

### `+6285385471441`
- user: `Dedi Rahaman`
- status: `APPROVED`, aktif, tidak diblokir
- transaksi terbaru: `BD-LPSR-E96EB28697CF`
- nominal: `300000`
- status: `SUCCESS`
- payment method: `qris`
- event DB yang ada: `INITIATED`, `MIDTRANS_WEBHOOK/NOTIFICATION/SUCCESS`, `MIKROTIK_APPLY_SUCCESS`

Keduanya mengonfirmasi bahwa:
- Midtrans automation hidup
- webhook masuk
- apply ke hotspot selesai
- blind spot verifikasi berada di leg invoice WhatsApp, bukan di leg pembayaran atau aktivasi paket

## Validasi

Terverifikasi selama batch ini:
- diagnostics editor bersih pada file backend/frontend yang disentuh
- `backend/tests/test_notification_templates.py` lulus (`7 passed`)
- template baru debt report render dengan placeholder lengkap
- temp token debt report lulus roundtrip test

Catatan tooling:
- typecheck frontend penuh via shell Windows/Git Bash tidak memberi output penutup yang deterministik pada sesi ini, sehingga validasi frontend mengandalkan diagnostics editor pada file yang berubah

## Dampak Operasional

Sesudah batch ini:
- verifikasi invoice WA tidak perlu bergantung penuh pada log Docker
- operator bisa audit notifikasi invoice langsung dari `transaction_events`
- admin bisa mengirim ringkasan tunggakan manual ke WhatsApp user dengan attachment PDF debt report yang valid sementara
- format PDF debt report tetap satu sumber kebenaran yang sama antara export admin dan attachment WhatsApp
