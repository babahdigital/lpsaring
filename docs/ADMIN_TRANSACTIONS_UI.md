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
