# Payments (Snap & Core API) – Index

Dokumen ini adalah indeks/pondasi untuk semua perubahan pembayaran.

## Konsep Utama
- Mode pembayaran ditentukan dari Setting Admin (General):
  - `PAYMENT_PROVIDER_MODE=snap` → UI pembayaran via Snap (Snap.js)
  - `PAYMENT_PROVIDER_MODE=core_api` → tanpa Snap UI (server-to-server), instruksi ditampilkan di portal
- URL status pembayaran (canonical, dibagikan ke user):
  - `/payment/status?order_id=...`
- `/payment/finish` dipertahankan untuk kompatibilitas callback/legacy.

## Perilaku Penting
- Snap.js **tidak** auto-load global.
  - Hanya lazy-load saat mode Snap dipakai.
- Core API menampilkan QR via proxy backend untuk menghindari CORS + mengurangi dependency browser ke domain provider:
  - `GET /api/transactions/<order_id>/qr` (inline)
  - `GET /api/transactions/<order_id>/qr?download=1`

## Admin – Buat Tagihan
- Admin → Users → Buat Tagihan
  - Endpoint: `POST /api/admin/transactions/bill`
  - Alias: `POST /api/admin/transactions/qris`
- Metode dan bank VA yang tampil/valid mengikuti setting:
  - `CORE_API_ENABLED_PAYMENT_METHODS`
  - `CORE_API_ENABLED_VA_BANKS`

## Env yang Relevan
- Prefix order_id transaksi user (beli paket):
  - `MIDTRANS_ORDER_ID_PREFIX=BD-LPSR`
- Prefix order_id tagihan admin:
  - `ADMIN_BILL_ORDER_ID_PREFIX=BD-LPSR`
- Prefix order_id pelunasan tunggakan/hutang kuota (debt settlement):
  - `DEBT_ORDER_ID_PREFIX=DEBT`
  - Format default:
    - Total tunggakan: `DEBT-40BF16F55C2B`
    - Hutang manual: `DEBT-<uuid>~<suffix>`

## Dokumen Detail
- Lifecycle transaksi + data yang disimpan:
  - `docs/TRANSACTIONS_MIDTRANS_LIFECYCLE.md`
- Snap mode (referensi internal):
  - `docs/MIDTRANS_SNAP.md`
- Checklist test cepat:
  - `docs/LITE_TEST_CHECKLIST_PAYMENT.md`
- Error reference:
  - `docs/ERROR_REFERENCE.md`
