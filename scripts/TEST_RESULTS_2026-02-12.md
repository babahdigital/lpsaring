# Hasil Simulasi E2E (2026-02-12)

Command:
- powershell.exe -ExecutionPolicy Bypass -File scripts/simulate_end_to_end.ps1

Outcome:
- Selesai 100% sampai [14.6/14]

Cakupan uji utama:
- Startup container + readiness check API
- Migrasi + seed data + admin login
- OTP request (retry cooldown) + verify OTP via X-Forwarded-For
- Device binding + debug resolution
- Uji halaman status frontend dan redirect berbasis cookie
- Uji signed status blocked/inactive
- Flow Komandan (opsional) dengan IP terpisah
- Simulasi transaksi paket
- Simulasi kuota (fup/habis/expired) + apply MikroTik + validasi address-list
- Sync walled-garden

Hasil penting:
- Address-list OK untuk status habis dan expired pada IP terikat (172.16.15.253)
- Status akhir user: expired, redirect sesuai ekspektasi

Catatan:
- Jika IP hotspot tidak tersedia, validasi address-list menggunakan fallback ip-binding atau MAC authorized

## Tambahan Hasil (2026-02-13)

Command:
- powershell.exe -ExecutionPolicy Bypass -File scripts/simulate_end_to_end.ps1

Outcome:
- Selesai 100% sampai [14.6/14]

Hasil penting:
- Fallback MAC-only terkonfirmasi di log backend: raw input IP kosong dan resolved IP berasal dari MAC device.
- Debug binding resolution tidak lagi 500, hasil local-ip dan public-ip tercetak.
 - Status page sempat 404 ketika frontend base mengarah ke backend/prod; script kini memprioritaskan `http://localhost` untuk uji halaman redirect.
 - Status page sekarang punya assert otomatis (gagal jika 404) untuk `/login/*` dan `/captive/*`.

## Tambahan Hasil (2026-02-13 - Regular Mode, opsi legacy)

Command:
- powershell.exe -ExecutionPolicy Bypass -File scripts/simulate_end_to_end.ps1 -AppEnv local

Outcome:
- Selesai 100% sampai [14.6/14]

Hasil penting:
- Mode regular aktif: `hotspot_login_required=true` dan `hotspot_username/password` dikembalikan saat OTP verify.
- Captive flow mengirim `hotspot_login_context=true` sehingga kredensial tetap dikirim meski IP/MAC kosong.
- Verify-OTP binding context terekam: IP klien valid + MAC dari client (lihat log backend).
- Status blocked/inactive ditolak backend sesuai ekspektasi.

Catatan:
- Redis AOF aktif untuk menjaga last_bytes per-MAC saat restart.
- Address-list masih bisa memuat IP dari host Docker (172.18.0.1); validasi IP nyata tetap perlu di production.

## Tambahan Hasil (2026-02-13 - OTP Bypass 000000)

Command:
- powershell.exe -ExecutionPolicy Bypass -Command "& 'D:\Data\Projek\hotspot\lpsaring\scripts\simulate_end_to_end.ps1' -AppEnv local -UseOtpBypassOnly:$true"

Outcome:
- Selesai 100% sampai [17/17]

Hasil penting:
- Status blocked/inactive ditolak backend sesuai ekspektasi.
- Status akhir user: expired, redirect sesuai ekspektasi.
- Redis persistence smoke (clear last_bytes + sync) berjalan tanpa error.
- Verify OTP tanpa client_ip/client_mac (captive context) berjalan.
- Mock Midtrans webhook diterima.
