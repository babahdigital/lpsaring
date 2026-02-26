# Payments (Snap & Core API) – Index

Dokumen ini adalah indeks/pondasi untuk semua perubahan pembayaran.

## Konsep Utama
- Mode pembayaran ditentukan dari Setting Admin (General):
  - `PAYMENT_PROVIDER_MODE=snap` → UI pembayaran via Snap (Snap.js)
  - `PAYMENT_PROVIDER_MODE=core_api` → tanpa Snap UI (server-to-server), instruksi ditampilkan di portal
- URL status pembayaran (canonical, dibagikan ke user):
  - `/payment/status?order_id=...`
  - Untuk link shareable lintas device (mis. via WhatsApp), server dapat menambahkan token bertanda tangan:
    - `/payment/status?order_id=...&t=<SIGNED_TOKEN>`
- `/payment/finish` dipertahankan untuk kompatibilitas callback/legacy.
  - Untuk Snap, callback finish tidak membawa `order_id` (untuk mencegah query double), tetapi token `t` boleh dibawa.

## Keamanan Link Status (Public)
- Endpoint public yang memakai `t` bersifat *read-only* dan akan menyamarkan data sensitif user (contoh: nomor HP / internal id) agar aman jika link tersebar.

## Perilaku Penting
- Snap.js **tidak** auto-load global.
  - Hanya lazy-load saat mode Snap dipakai.
- Core API menampilkan QR via proxy backend untuk menghindari CORS + mengurangi dependency browser ke domain provider:
  - `GET /api/transactions/<order_id>/qr` (inline)
  - `GET /api/transactions/<order_id>/qr?download=1`
  - Untuk akses public (link membawa `t`):
    - `GET /api/transactions/public/<order_id>/qr?t=...` (inline)
    - `GET /api/transactions/public/<order_id>/qr?t=...&download=1`

## Admin – Buat Tagihan
- Admin → Users → Buat Tagihan
  - Endpoint: `POST /api/admin/transactions/bill`
  - Alias: `POST /api/admin/transactions/qris`
- Metode dan bank VA yang tampil/valid mengikuti setting:
  - `CORE_API_ENABLED_PAYMENT_METHODS`
  - `CORE_API_ENABLED_VA_BANKS`

## Env yang Relevan
- TTL token link status shareable (public):
  - `TRANSACTION_STATUS_TOKEN_MAX_AGE_SECONDS` (default 7 hari; clamp min 5 menit, max 30 hari)
- Rate limit endpoint public (Flask-Limiter):
  - `PUBLIC_TRANSACTION_STATUS_RATE_LIMIT` (default `60 per minute`)
  - `PUBLIC_TRANSACTION_QR_RATE_LIMIT` (default `30 per minute`)
  - `PUBLIC_TRANSACTION_CANCEL_RATE_LIMIT` (default `20 per minute`)
- Prefix order_id transaksi user (beli paket):
  - `MIDTRANS_ORDER_ID_PREFIX=BD-LPSR`
- Prefix order_id tagihan admin:
  - `ADMIN_BILL_ORDER_ID_PREFIX=BD-LPSR`
- Prefix order_id pelunasan tunggakan/hutang kuota (debt settlement):
  - `DEBT_ORDER_ID_PREFIX=DEBT`
  - Format default:
    - Total tunggakan: `DEBT-40BF16F55C2B`
    - Hutang manual: `DEBT-<manual_debt_id>~<suffix>`
      - Format baru (lebih pendek, aman batas 50 char Midtrans): `<manual_debt_id>` = UUID Base64URL tanpa padding (22 char)
      - Masih kompatibel dengan format lama: UUID dengan dash (36 char) / hex (32 char) / Base32 tanpa padding (26 char)

## Demo Mode (Uji Flow Pembayaran tanpa Mengganggu User Reguler)

Untuk kebutuhan demo/staging yang dijalankan di environment produksi secara terkontrol, tersedia flag backend berikut:

- `DEMO_MODE_ENABLED`
- `DEMO_ALLOWED_PHONES`
- `DEMO_BYPASS_OTP_CODE`
- `DEMO_SHOW_TEST_PACKAGE`
- `DEMO_PACKAGE_IDS`

Catatan perilaku:
- Bypass OTP hanya berlaku untuk nomor yang sudah ada di `DEMO_ALLOWED_PHONES` dan sudah disiapkan sistem.
- Paket nonaktif dapat ditampilkan/dibeli untuk user demo sesuai konfigurasi env.
- User reguler tetap mengikuti aturan normal (tanpa bypass dan tanpa akses paket testing).
- Enforce visibilitas paket demo dilakukan di backend berdasarkan requester terautentikasi (status `is_demo_user`), bukan mengandalkan toggle global di frontend.
- Frontend hanya menjadi representasi UI dari status user; flag public demo frontend bersifat opsional/kompatibilitas dan bukan sumber otorisasi utama.

## Dokumen Detail
- Lifecycle transaksi + data yang disimpan:
  - `docs/TRANSACTIONS_MIDTRANS_LIFECYCLE.md`
- Snap mode (referensi internal):
  - `docs/MIDTRANS_SNAP.md`
- Checklist test cepat:
  - `docs/LITE_TEST_CHECKLIST_PAYMENT.md`
- Error reference:
  - `docs/ERROR_REFERENCE.md`

## Frontend Payment Refactor (Status Page)

Halaman `frontend/pages/payment/finish.vue` sekarang menggunakan composable terpisah untuk memudahkan maintainability tanpa mengubah UX utama:

- `usePaymentPublicTokenFlow`:
  - normalisasi query `order_id` + token `t`/`token`
  - fallback authenticated → public endpoint untuk link shareable
- `usePaymentStatusPolling`:
  - polling ringan selama status belum final
- `usePaymentInstructions`:
  - instruksi VA/QR/deeplink terpusat
- `usePaymentSnapAction`:
  - callback Snap (`onSuccess`/`onPending`/`onError`/`onClose`) terstandardisasi

## Test Coverage Payment (Focused)

Focused tests yang aktif:
- `frontend/tests/payment-composables.test.ts`
- `frontend/tests/payment-status-polling.test.ts`

Keduanya ikut dijalankan pada CI step focused frontend tests bersama auth guard tests.
