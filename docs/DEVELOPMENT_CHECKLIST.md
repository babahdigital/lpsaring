# Checklist Sebelum Lanjut Pengembangan

Lampiran wajib:
- [.github/copilot-instructions.md](../.github/copilot-instructions.md)

## 1) Validasi Kontrak API
- [ ] Pastikan schema User terbaru (tamping, quota, role) sudah final.
- [ ] Endpoint registrasi, login, approval, transaksi diverifikasi.
- [ ] Update type frontend sesuai response backend.

## 2) Konsistensi Tipe Frontend
- [ ] Semua type berada di folder types/.
- [ ] Tidak ada duplikasi type untuk entity yang sama.
- [ ] useFetch/useApiFetch di-typed dengan benar.

## 3) Infrastruktur Dev
- [ ] .env root, backend/.env, frontend/.env terisi.
- [ ] Docker Compose berjalan tanpa error.
- [ ] /api/ping dan halaman frontend bisa diakses.
- [ ] Frontend dev server host aktif (port 3010).
- [ ] `pnpm` terpasang di host dan `pnpm install` sudah dijalankan di `frontend/`.

## 4) Lint & Type Check
- [ ] Jalankan lint frontend.
- [ ] Jalankan typecheck frontend (Nuxt).
- [ ] Periksa TS errors = 0.
- [ ] Pastikan build tidak gagal.
- [ ] Jalankan build analyze jika ada perubahan dependensi frontend.

## 4.1) Testing
- [ ] Jalankan pytest backend.
- [ ] Jika env DB belum ada, pytest memakai fallback sqlite in-memory (khusus testing).
- [ ] Jalankan vitest frontend.

## 4.2) QA Alur Captive & OTP
- [ ] Verify OTP pada mode regular (`IP_BINDING_TYPE_ALLOWED=regular`) mengembalikan `hotspot_login_required=true` dan kredensial hotspot.
- [ ] (Opsional) Jika pakai mode bypass, Verify OTP mengembalikan `hotspot_login_required=false`.
- [ ] Verify OTP tanpa `client_ip/client_mac` (captive context) tetap sukses jika `hotspot_login_context=true`.
- [ ] Debug binding menampilkan sumber IP/MAC yang benar (local-ip dan public-ip).
- [ ] Redirect status `/login/*` dan `/captive/*` sesuai role (User vs Komandan).
- [ ] Address-list sesuai status (active/fup/habis/expired) untuk IP terikat.
- [ ] Walled-garden sync berhasil tanpa error.

## 5) UI/UX Validasi
- [ ] Alur registrasi tamping vs non‑tamping bekerja.
- [ ] Admin dapat approve user tamping.
- [ ] Dashboard dan riwayat transaksi tampil normal.

## 6) Smoke Test Alur Utama
- [x] Register user baru.
- [x] Login (OTP).
- [x] Admin approve user.
- [x] Beli paket & pastikan transaksi sukses.

## 7) Dokumentasi Minimum
- [ ] Update README.
- [ ] Update DEVELOPMENT.md jika ada perubahan besar.
- [ ] Catat perubahan API yang signifikan.
- [ ] Lampirkan tautan .github/copilot-instructions.md di dokumen terkait.

## 8) Post-Deploy Smoke Test
- [x] /api/ping mengembalikan status OK.
- [x] Login admin berhasil dan bisa membaca settings.
- [x] Registrasi user baru dan approve admin berhasil.
- [x] Request OTP dan verifikasi OTP berhasil.
- [x] Pembelian paket sukses atau transaksi sandbox berhasil.

## 9) Backup/Restore & WhatsApp Admin
- [ ] Admin dapat membuat backup dari halaman `/admin/backup`.
- [ ] Super Admin dapat menjalankan restore dari backup yang tersedia.
- [ ] File backup bisa diunduh dan diverifikasi ukurannya tidak nol.
- [ ] Tes kirim WhatsApp dari halaman admin berhasil ke nomor uji.
