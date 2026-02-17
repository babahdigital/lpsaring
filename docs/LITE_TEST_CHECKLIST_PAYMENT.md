# Lite Test Checklist – Payment/Transactions

Checklist ini fokus hanya pada perubahan payment lifecycle + UI finish + admin transaksi.


## A) Backend (manual cepat)

- Initiate: pastikan transaksi baru statusnya `UNKNOWN` (bukan `PENDING`).
- Snap close: tutup popup Snap → status transaksi menjadi `CANCELLED`.
- Pending: pilih metode bayar VA/QRIS → status menjadi `PENDING`, `expiry_time` terisi.
- Success: selesaikan pembayaran → webhook mengubah `SUCCESS` dan paket ter-apply.
- Expiry: biarkan `UNKNOWN/PENDING` lewat batas → task mengubah ke `EXPIRED`.


## B) Frontend (UI)

- Tombol bayar: tidak menampilkan “Menunggu” kecuali ada `onPending` atau webhook.
- Halaman finish: `UNKNOWN` → “Belum Dimulai” + polling; `PENDING` → instruksi + expiry; `SUCCESS` → invoice aktif.
- Admin transaksi: kolom metode/kadaluwarsa terisi bila ada; tombol invoice hanya muncul untuk `SUCCESS`.


## C) Automated (repo)

- Backend: `python -m ruff check .`
- Frontend: `pnpm lint`
- Backend tests (lite): `pytest -q tests/test_transactions_lifecycle.py`
