# Midtrans Snap – Dokumentasi Internal (Sandbox)

Dokumen ini merangkum langkah integrasi Snap berdasarkan dokumentasi resmi Midtrans:
- https://docs.midtrans.com/docs/snap
- https://docs.midtrans.com/docs/snap-snap-integration-guide

Lampiran wajib:
- [.github/copilot-instructions.md](../.github/copilot-instructions.md)

## 1) Mode Sandbox (Untuk Development)
Gunakan **Server Key** dan **Client Key** dari Sandbox terlebih dulu. Di project ini:
- Backend: `MIDTRANS_SERVER_KEY`, `MIDTRANS_CLIENT_KEY`, `MIDTRANS_IS_PRODUCTION=False`
- Frontend: `NUXT_PUBLIC_MIDTRANS_CLIENT_KEY`

## 2) Alur Integrasi (Ringkas)
Urutan integrasi Snap:
1. Backend membuat transaksi dan mendapatkan `token` Snap.
2. Frontend menampilkan Snap menggunakan `snap.js` + `token`.
3. Customer bayar di Snap.
4. Backend menerima status via HTTP Notification/Webhook.

## 3) Detail Langkah Integrasi
### A) Persiapan
- Buat akun Midtrans (Merchant Admin Portal).
- Ambil **Sandbox API Keys** (Server Key & Client Key).

### B) Backend – Buat Snap Token
Endpoint Sandbox:
- `POST https://app.sandbox.midtrans.com/snap/v1/transactions`

Header autentikasi:
- `Authorization: Basic BASE64(ServerKey + ":")`

Payload minimal:
- `transaction_details.order_id`
- `transaction_details.gross_amount`

Respons sukses akan mengembalikan:
- `token`
- `redirect_url`

> Catatan: disarankan mengirim `customer_details`, `item_details`, dan data transaksi lainnya agar tercatat di Dashboard Midtrans.

### C) Frontend – Tampilkan Snap
Tambahkan `snap.js` (Sandbox):
- `https://app.sandbox.midtrans.com/snap/snap.js`
- Set `data-client-key="<CLIENT_KEY_SANDBOX>"`

Metode tampilan:
- **Pop‑up**: `window.snap.pay('<TOKEN>')`
- **Embedded**: `window.snap.embed('<TOKEN>', { embedId: 'snap-container' })`

> Pastikan ada `<meta name="viewport" content="width=device-width, initial-scale=1">`.

#### C1) Snap JS – Callback & Opsi (Ringkas)
Snap menyediakan callback untuk menangani event pembayaran:
- `onSuccess(result)` → pembayaran sukses (status 200)
- `onPending(result)` → pembayaran pending (status 201)
- `onError(result)` → pembayaran gagal (status 4xx/5xx)
- `onClose()` → user menutup popup tanpa menyelesaikan pembayaran

Opsi umum yang sering dipakai:
- `language`: `id` atau `en`
- `autoCloseDelay`: detik, `0` untuk nonaktif
- `selectedPaymentType`: paksa metode pembayaran tertentu

Catatan:
- `snap.show()` / `snap.hide()` dapat dipakai untuk UX saat menunggu token.
- Jika callback tidak di-setup, Snap akan redirect ke Finish URL di Dashboard.

### D) Redirect & Notification
Atur di Dashboard:
- **Finish URL**, **Unfinish URL**, **Error URL**
- **Payment Notification URL** (Webhook)

Backend harus memproses notifikasi untuk update status transaksi.

**Catatan HTTPS:**
- Midtrans membutuhkan URL publik **HTTPS** untuk webhook dan redirect.
- Gunakan domain publik (mis. Cloudflare Tunnel) dan pastikan `APP_PUBLIC_BASE_URL` sudah benar.

### E) Testing (Sandbox)
Gunakan kartu uji:
- Card Number: `4811 1111 1111 1114`
- CVV: `123`
- Exp: bulan apa pun, tahun masa depan
- OTP/3DS: `112233`

## 4) Checklist Implementasi di Proyek Ini
- [ ] Set `MIDTRANS_SERVER_KEY` & `MIDTRANS_CLIENT_KEY` di `backend/.env.local` (dev) atau `.env.prod` (produksi)
- [ ] Set `MIDTRANS_IS_PRODUCTION=False`
- [ ] Set `NUXT_PUBLIC_MIDTRANS_CLIENT_KEY` di `.env.public` (dev) / `.env.public.prod` (prod)
	- Jika Nuxt jalan di host (opsional): pakai `frontend/.env.public` / `frontend/.env.local`
- [ ] Implement endpoint backend untuk create Snap token
- [ ] Frontend memanggil endpoint token, lalu `snap.pay` atau `snap.embed`
- [ ] Buat endpoint webhook untuk notifikasi transaksi
- [ ] Set Notification URL & Redirect URLs di Dashboard

## 6) Catatan Produksi Hotspot: Walled-Garden untuk Payment
Pada hotspot, user dengan status **habis/expired** sering masih diizinkan mengakses:
- portal/login,
- banking,
- payment gateway (Midtrans).

Temuan penting RouterOS:
- Wildcard seperti `*.domain.tld` **tidak selalu bekerja** untuk address-list/walled-garden host.
- Untuk mencegah kasus "tombol bayar muter"/Snap tidak muncul, gunakan **allowlist host FQDN eksplisit**.

Checklist ops (hotspot):
- Pastikan domain Midtrans yang dibutuhkan oleh `snap.js` bisa diakses saat kuota habis.
- Tambahkan legacy host jika diperlukan:
	- `veritrans.co.id` (legacy)

Catatan:
- Daftar host yang dibutuhkan bisa berubah, jadi lakukan uji dari klien dengan kuota habis.
- Sumber kebenaran perilaku akses habis/expired ada di policy MikroTik (walled-garden + address-list).

## 5) Referensi Lanjutan
- Integration Guide: https://docs.midtrans.com/docs/snap-snap-integration-guide
- Snap Advanced Features: https://docs.midtrans.com/docs/snap-advanced-feature
- Snap JS Reference: https://docs.midtrans.com/reference/snap-js
- Handle After Payment: https://docs.midtrans.com/docs/handle-after-payment
