# Lite Test Checklist – Payment/Transactions

Checklist ini fokus pada payment lifecycle + halaman status + admin tagihan.

## A) Backend (manual cepat)

### Mode Snap (`PAYMENT_PROVIDER_MODE=snap`)
- Initiate: transaksi baru status `UNKNOWN` (Snap token/redirect ada).
- Snap close: tutup popup Snap → status menjadi `CANCELLED`.
- Pending/Success: status final mengikuti webhook Midtrans.

### Mode Core API (`PAYMENT_PROVIDER_MODE=core_api`)
- Initiate: transaksi baru status `PENDING` dan field instruksi terisi sesuai metode:
	- QRIS/GoPay/ShopeePay → `qr_code_url` (dan kadang deeplink)
	- VA bank → `va_number`
	- Mandiri (echannel) → `payment_code` + `biller_code`
- Status final: webhook mengubah jadi `SUCCESS/FAILED/EXPIRED/...`.

### Umum
- Expiry: biarkan `UNKNOWN/PENDING` lewat batas → task mengubah ke `EXPIRED`.

## B) Frontend (UI)

- URL status canonical: buka `/payment/status?order_id=...` (tanpa redirect).
	- Untuk link shareable lintas device (mis. dari WhatsApp), URL bisa membawa token: `/payment/status?order_id=...&t=<SIGNED_TOKEN>`.
- Core API: QR ditampilkan via proxy backend `/api/transactions/<order_id>/qr` (tidak direct ke domain provider).
	- Jika link membawa `t`, QR diambil via endpoint public: `/api/transactions/public/<order_id>/qr?t=...`.
- Snap.js: hanya lazy-load saat mode Snap dipakai (tidak ter-load saat Core API).

## C) Admin (Buat Tagihan)

- Admin → Users → Buat Tagihan:
	- Dropdown metode + bank VA mengikuti setting `CORE_API_ENABLED_PAYMENT_METHODS` + `CORE_API_ENABLED_VA_BANKS`.
	- WhatsApp berisi link `/payment/status?order_id=...` (idealnya dengan `&t=...` jika ingin bisa dibuka tanpa login) + detail VA/echannel bila metode VA.

## D) Automated (repo)

- Backend: `python -m ruff check .`
- Frontend: `pnpm lint`
- Backend tests (lite): `pytest -q backend/tests/test_transactions_lifecycle.py`
