# Lifecycle Transaksi & Midtrans (Internal)

Dokumen ini menjelaskan perilaku transaksi pembayaran Midtrans di proyek ini untuk 2 mode:
- Snap (`PAYMENT_PROVIDER_MODE=snap`)
- Core API (`PAYMENT_PROVIDER_MODE=core_api`)


## 1) Status Transaksi (Backend)

Field: `transactions.status` (enum string).

Status yang digunakan:

- `UNKNOWN` — transaksi dibuat saat user klik tombol bayar (Snap token sudah dibuat), tetapi belum ada indikasi user memilih metode pembayaran atau notifikasi Midtrans.
- `PENDING` — Midtrans menyatakan transaksi masih menunggu pembayaran (umumnya setelah user memilih metode dan mendapatkan instruksi bayar).
- `SUCCESS` — pembayaran sukses dan paket sudah di-apply ke user + sync ke MikroTik.
- `EXPIRED` — batas waktu pembayaran lewat.
- `CANCELLED` — user menutup popup Snap (ditandai dari frontend).
- `FAILED` — Midtrans menolak/deny atau error pembayaran.

Catatan:

- Jangan menampilkan “Menunggu” untuk `UNKNOWN`.
- `UNKNOWN` harus dianggap “Belum mulai / belum ada status Midtrans”.


## 2) Urutan Kejadian (High-level)

### A) Mode Snap
1. Frontend `POST /api/transactions/initiate`.
2. Backend membuat record transaksi `UNKNOWN` (Snap token/redirect tersedia) + menyimpan `expiry_time`.
3. Frontend memanggil `window.snap.pay(token, callbacks)`.
4. Jika user menutup Snap tanpa bayar: frontend memanggil `POST /api/transactions/{order_id}/cancel` → status `CANCELLED`.
5. Jika status berubah:
  - Midtrans memanggil webhook `POST /api/transactions/notification`.
  - Backend menyimpan payload mentah (`midtrans_notification_payload`) dan mengisi kolom penting (payment_type, expiry_time, VA/QR, dst).
  - Status transaksi diupdate sesuai notifikasi.

### B) Mode Core API (tanpa Snap)
1. Frontend `POST /api/transactions/initiate` dengan `payment_method` (qris/gopay/va/shopeepay) dan opsional `va_bank`.
2. Backend membuat record transaksi `PENDING` + menyimpan field instruksi pembayaran (QR/VA/deeplink) jika tersedia.
3. Frontend mengarahkan user ke URL status (canonical):
  - `/payment/status?order_id=<order_id>`
4. Midtrans webhook `POST /api/transactions/notification` akan mengubah status menjadi final (`SUCCESS/FAILED/EXPIRED/...`).


## 3) URL Status (Canonical)
URL yang dibagikan ke user dan dipakai internal adalah:
- `/payment/status?order_id=...`

Catatan:
- `/payment/finish` tetap ada untuk kompatibilitas callback/legacy, tapi UI user-facing memakai `/payment/status`.

## 4) Sumber Kebenaran Status

Sumber kebenaran utama:

- Webhook Midtrans: `POST /api/transactions/notification`.

Fallback (rekonsiliasi) saat user membuka halaman finish:

- `GET /api/transactions/by-order-id/{order_id}` akan mencoba cek ke Midtrans bila status masih `UNKNOWN` atau `PENDING`.


## 5) Expiry dan Pembersihan Status Nyangkut

Jika `expiry_time` sudah lewat dan status masih `UNKNOWN` atau `PENDING`, sistem akan mengubah menjadi `EXPIRED`.

Implementasi:

- Celery beat task: `expire_stale_transactions_task` (periodik).


## 6) Data Midtrans yang Disimpan

Agar transaksi bisa diaudit seperti contoh payload notifikasi Midtrans:

- `transactions.midtrans_notification_payload` menyimpan JSON mentah dari webhook/status check.
- Kolom transaksi yang diisi (jika tersedia):
  - `midtrans_transaction_id`
  - `payment_method` (payment_type)
  - `snap_redirect_url` (dipakai ulang untuk deeplink Core API: GoPay/ShopeePay)
  - `payment_time` (settlement_time/transaction_time)
  - `expiry_time`
  - `va_number`, `payment_code`, `biller_code`, `qr_code_url`


## 7) QR Code Proxy (CORS/Offline-friendly)
Untuk mode Core API yang menampilkan QR, frontend tidak mengambil QR langsung dari domain Midtrans.
Gunakan proxy backend:
- `GET /api/transactions/<order_id>/qr` (inline)
- `GET /api/transactions/<order_id>/qr?download=1` (attachment)

## 8) Prinsip UI

- Jangan pindah ke halaman finish dengan status `pending` sebelum event Snap `onPending` atau webhook menyatakan pending.
- Halaman status boleh melakukan refresh manual/polling ringan sampai status final (`SUCCESS/FAILED/EXPIRED/CANCELLED`).
