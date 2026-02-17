# Lifecycle Transaksi & Midtrans (Internal)

Dokumen ini menjelaskan perilaku transaksi pembayaran Midtrans Snap di proyek ini: status yang dipakai, kapan status berubah, dan data apa yang disimpan.


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

1. Frontend `POST /api/transactions/initiate`.
2. Backend membuat record transaksi `UNKNOWN` + menyimpan `expiry_time` lokal.
3. Frontend memanggil `window.snap.pay(token, callbacks)`.
4. Jika user menutup Snap tanpa bayar: frontend memanggil `POST /api/transactions/{order_id}/cancel` → status `CANCELLED`.
5. Jika user memilih metode bayar / status berubah:
   - Midtrans memanggil webhook `POST /api/transactions/notification`.
   - Backend menyimpan payload mentah (`midtrans_notification_payload`) dan mengisi kolom penting (payment_type, expiry_time, VA/QR, dst).
   - Status transaksi diupdate sesuai notifikasi.


## 3) Sumber Kebenaran Status

Sumber kebenaran utama:

- Webhook Midtrans: `POST /api/transactions/notification`.

Fallback (rekonsiliasi) saat user membuka halaman finish:

- `GET /api/transactions/by-order-id/{order_id}` akan mencoba cek ke Midtrans bila status masih `UNKNOWN` atau `PENDING`.


## 4) Expiry dan Pembersihan Status Nyangkut

Jika `expiry_time` sudah lewat dan status masih `UNKNOWN` atau `PENDING`, sistem akan mengubah menjadi `EXPIRED`.

Implementasi:

- Celery beat task: `expire_stale_transactions_task` (periodik).


## 5) Data Midtrans yang Disimpan

Agar transaksi bisa diaudit seperti contoh payload notifikasi Midtrans:

- `transactions.midtrans_notification_payload` menyimpan JSON mentah dari webhook/status check.
- Kolom transaksi yang diisi (jika tersedia):
  - `midtrans_transaction_id`
  - `payment_method` (payment_type)
  - `payment_time` (settlement_time/transaction_time)
  - `expiry_time`
  - `va_number`, `payment_code`, `biller_code`, `qr_code_url`


## 6) Prinsip UI

- Jangan pindah ke halaman finish dengan status `pending` sebelum event Snap `onPending` atau webhook menyatakan pending.
- Halaman finish boleh melakukan polling ringan sampai status final (`SUCCESS/FAILED/EXPIRED/CANCELLED`).
