# Admin UI – Transaksi (Internal)

Dokumen ini menjelaskan struktur halaman Admin → Transaksi dan field yang ditampilkan.


## 1) Sumber Data

Halaman admin transaksi memanggil:

- `GET /api/admin/transactions`

Field minimal yang dikembalikan:

- `order_id`, `amount`, `status`, `created_at`
- `payment_method`, `payment_time`, `expiry_time` (jika ada)
- `midtrans_transaction_id` (jika ada)
- `user.full_name`, `user.phone_number`
- `package_name`


## 2) Kolom Tabel

Rekomendasi kolom (ringkas):

- Nama Pengguna
- ID Invoice (order_id)
- Paket
- Metode (payment_method)
- Jumlah
- Status
- Kadaluarsa (expiry_time)
- Tanggal (created_at)
- Aksi (Invoice)


## 3) Mapping Status ke Label

- `UNKNOWN` → "Belum Mulai"
- `PENDING` → "Menunggu"
- `SUCCESS` → "Sukses"
- `EXPIRED` → "Kadaluarsa"
- `CANCELLED` → "Dibatalkan"
- `FAILED` → "Gagal"


## 4) Aksi Invoice

Invoice hanya valid untuk status `SUCCESS`.

- Endpoint: `GET /api/transactions/{order_id}/invoice`

Catatan:

- Invoice membutuhkan autentikasi (cookie). Tombol invoice sebaiknya membuka tab baru.

## 5) Admin → Users → Buat Tagihan

Fitur ini digunakan admin untuk membuat invoice untuk user tertentu dan mengirim instruksi pembayaran melalui WhatsApp.

Endpoint:
- `POST /api/admin/transactions/bill`
	- Alias kompatibilitas: `POST /api/admin/transactions/qris`

Payload:
- `user_id`, `package_id`
- `payment_method`: `qris|gopay|va|shopeepay`
- `va_bank`: jika `payment_method=va`

Catatan UI:
- Dropdown metode pembayaran dan bank VA mengikuti setting Core API:
	- `CORE_API_ENABLED_PAYMENT_METHODS`
	- `CORE_API_ENABLED_VA_BANKS`

Field transaksi yang biasanya terisi untuk membantu user membayar:
- `qr_code_url` (QRIS/GoPay/ShopeePay)
- `snap_redirect_url` (dipakai ulang sebagai deeplink Core API)
- `va_number` (bank transfer)
- `payment_code` + `biller_code` (Mandiri e-channel)
