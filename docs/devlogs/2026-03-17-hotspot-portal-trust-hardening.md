# Devlog Hotspot Portal Trust Hardening (2026-03-16 s.d. 2026-03-17)

Dokumen ini merangkum investigasi wrong-link hotspot, alasan env default saja tidak cukup, implementasi trust boundary frontend, dan verifikasi produksi setelah patch dipromosikan.

## Tujuan

- Mencegah context captive dari jaringan lain masuk ke portal publik LPSaring.
- Memastikan flow hotspot LPSaring yang sah tetap berjalan normal.
- Menjadikan trust policy hotspot eksplisit, dapat dikonfigurasi, dan bisa diregresikan lewat test.
- Menyediakan runbook operasional yang membedakan foreign context leak dari bug auth atau deploy biasa.

## Masalah awal

Keluhan pengguna mengarah ke wrong login link pada flow hotspot, terutama di area `frontend/pages/login/hotspot-required.vue`. Investigation awal menunjukkan env publik LPSaring sudah dibatasi, tetapi gejala tetap muncul.

Kesimpulan penting dari fase audit:

- masalah tidak berasal dari URL default LPSaring yang salah
- masalah juga bukan regresi auth backend atau Redis
- sumber utamanya adalah public portal menerima hint hotspot asing dari request runtime

## Mengapa env saja tidak cukup

Sebelum fix, alur hotspot/login dapat membaca context dari beberapa sumber:

- query route
- nested redirect `link_login_only`
- `document.referrer`
- `localStorage`

Fallback env hanya menentukan nilai default ketika sumber-sumber itu kosong. Begitu browser atau captive portal asing mengirimkan hint sendiri, frontend lama bisa memproses nilai tersebut tanpa verifikasi yang cukup.

Itu sebabnya pembatasan env tidak otomatis menutup kasus `wartelpas.net` atau `172.16.12.1`: masalahnya berada di trust boundary, bukan di fallback default.

## Bukti yang menutup RCA

- Evidence historis produksi memperlihatkan request dengan `link_login_only=http://172.16.12.1/login`, `client_ip=172.16.12.x`, dan referrer `wartelpas.net`.
- Di sisi lain, flow hotspot LPSaring yang sah tetap muncul dengan `login.home.arpa` dan `client_ip` di `172.16.2.x` atau `172.16.3.x`.
- Cross-check ke konfigurasi Wartelpas membuktikan itu memang jaringan lain, bukan variasi LPSaring:
  - subnet Wartelpas `172.16.12.1/24`
  - public API/login memakai domain sendiri

Kesimpulan: public portal LPSaring perlu fail-closed terhadap context hotspot asing.

## Ringkasan hasil akhir

| Area | Sebelum | Sesudah |
| --- | --- | --- |
| Sumber identity hotspot | query/referrer/storage dipercaya terlalu longgar | semua sumber disanitasi lewat allowlist |
| Login hint router | fallback env mudah dioverride oleh input asing | host router divalidasi eksplisit |
| Client subnet | implicit | explicit allowlist `172.16.2.0/23` |
| Referrer portal | bisa ikut membentuk identity | hanya host trusted yang boleh dipakai |
| Foreign context | bisa masuk ke `/captive` dan bridge login | dibuang sebelum flow activation |
| Coverage | belum ada guard khusus foreign context | ada regression tests khusus |

Commit utama yang mempromosikan solusi ini adalah `ab53b3ff` dengan pesan `fix: reject foreign hotspot portal context`.

## Rangkaian implementasi utama

### 1. Pusat trust policy baru di frontend

File baru `frontend/utils/hotspotTrust.ts` menjadi source of truth untuk seluruh keputusan trust hotspot.

Kemampuan utama file ini:

- decode berlapis untuk nilai hotspot yang sering datang dalam bentuk encoded berulang
- parsing daftar CIDR dari env publik
- normalisasi host router login
- sanitasi login hint dari URL langsung atau nested redirect
- verifikasi referrer hotspot sebelum dipakai sebagai fallback

Fungsi yang menjadi pusat keputusan:

- `resolveHotspotTrustConfig()`
- `isTrustedHotspotClientIp()`
- `sanitizeResolvedHotspotIdentity()`
- `sanitizeHotspotLoginHint()`
- `extractTrustedHotspotLoginHintFromQuery()`
- `isTrustedHotspotReferrer()`

### 2. Identity dan storage dibuat fail-closed

`frontend/utils/hotspotIdentity.ts` diubah agar:

- query identity hanya diterima bila `client_ip` berada di CIDR trusted
- MAC tetap dinormalisasi, tetapi dibuang bila IP tidak trusted
- fallback referrer hanya berlaku bila host referrer trusted
- stored identity stale atau foreign dibersihkan dari local storage
- partial query tetap boleh merge dengan identity trusted yang sudah tersimpan, sehingga bind flow sah tidak pecah

### 3. Middleware dan store berhenti membawa foreign context

`frontend/middleware/auth.global.ts` dan `frontend/store/auth.ts` diubah untuk memastikan:

- guest hanya diarahkan ke `/captive` bila context trusted
- link login router dari route atau storage disanitasi sebelum dipakai
- recovery query untuk `/login/hotspot-required` tidak lagi membawa foreign hint
- flow auth biasa tetap berjalan walau hint hotspot dibuang

### 4. Halaman captive dan hotspot-required diblok lebih awal

`frontend/pages/captive/index.vue` dan `frontend/pages/login/hotspot-required.vue` sekarang menolak foreign context sebelum:

- auto-login
- one-click activation
- manual hotspot login bridge

Dengan pola ini, foreign context dihentikan di boundary terdepan, bukan sesudah user telanjur masuk ke flow aktivasi.

### 5. Runtime config dibuat eksplisit

`frontend/nuxt.config.ts` dan env examples menambahkan dua config publik baru:

- `NUXT_PUBLIC_HOTSPOT_ALLOWED_CLIENT_CIDRS`
- `NUXT_PUBLIC_HOTSPOT_TRUSTED_LOGIN_HOSTS`

Default produksi yang dipakai saat ini:

- client CIDR: `172.16.2.0/23`
- trusted login host: `login.home.arpa`

Catatan implementasi:

- parser menerima CSV biasa
- parser juga bisa menerima array JSON sederhana
- host dari URL login router resmi tetap bisa ikut masuk lewat merge `trustedLoginUrls`

Contoh ekspansi yang aman bila ada router resmi baru:

```env
NUXT_PUBLIC_HOTSPOT_ALLOWED_CLIENT_CIDRS=172.16.2.0/23,172.16.4.0/24
NUXT_PUBLIC_HOTSPOT_TRUSTED_LOGIN_HOSTS=login.home.arpa,router2.home.arpa
```

## Cakupan file yang berubah di patch trust hardening

Commit `ab53b3ff` menyentuh 14 file dan menambahkan dua file baru.

Area utama yang berubah:

- env examples:
  - `.env.public.prod.example`
  - `frontend/.env.example`
  - `frontend/.env.public.example`
- trust and identity:
  - `frontend/utils/hotspotTrust.ts`
  - `frontend/utils/hotspotIdentity.ts`
- routing and state:
  - `frontend/middleware/auth.global.ts`
  - `frontend/store/auth.ts`
- pages:
  - `frontend/pages/captive/index.vue`
  - `frontend/pages/login/index.vue`
  - `frontend/pages/login/hotspot-required.vue`
- config:
  - `frontend/nuxt.config.ts`
- tests:
  - `frontend/tests/hotspot-trust.test.ts`
  - `frontend/tests/hotspot-identity.test.ts`
  - `frontend/tests/auth-middleware.runtime.test.ts`

## Regression coverage yang ditambahkan

Coverage penting yang sekarang ada:

- `frontend/tests/hotspot-trust.test.ts`
  - menerima IP trusted di `172.16.2.0/23`
  - menolak `172.16.12.20`
  - menerima `login.home.arpa`
  - menolak `wartelpas.net` dan `172.16.12.1`
  - menolak nested redirect foreign
- `frontend/tests/hotspot-identity.test.ts`
  - identity query tetap normal di subnet trusted
  - fallback referrer trusted tetap bekerja
  - stored identity trusted tetap bisa dipakai
  - subnet foreign dan referrer foreign dibuang
- `frontend/tests/auth-middleware.runtime.test.ts`
  - guest dengan context trusted tetap diarahkan ke `/captive`
  - guest dengan context foreign tidak lagi diarahkan ke captive flow
- `frontend/tests/hotspot-post-login-bridge.test.ts`
  - auto-bridge pasca-login hanya jalan bila masih ada hint router trusted
  - login manual dari luar hotspot tidak lagi ikut ter-bridge hanya karena env fallback `login.home.arpa` tersedia

Focused suite hotspot/auth yang dipakai saat promosi perubahan ini lulus penuh, lalu dilanjutkan dengan full frontend lint, frontend typecheck, dan backend Ruff yang juga lulus.

## Promosi dan verifikasi produksi

Urutan promosi yang dijalankan:

1. commit `ab53b3ff` dipush ke `main`
2. CI untuk HEAD hijau
3. Docker publish manual hijau
4. produksi diturunkan dulu bila perlu refresh penuh
5. deploy recreate image terbaru dijalankan
6. health publik dan container diverifikasi

Hasil pascadeploy:

- semua service Compose kembali `up`
- frontend sehat (`healthy`)
- `/api/ping` publik merespons normal
- audit publik terfokus hari ini tidak menemukan hit `wartelpas`, `172.16.12.1`, atau flow login/hotspot yang error

## Pelajaran penting

- Public captive portal adalah trust boundary, bukan sekadar halaman UX.
- Query string, referrer, dan local storage tidak boleh diperlakukan sebagai trusted input hanya karena mereka berasal dari browser user.
- Menambahkan allowlist resmi jauh lebih aman daripada menambah fallback atau pengecualian ad hoc.
- Fallback env seperti `NUXT_PUBLIC_APP_LINK_MIKROTIK` boleh tetap dipakai sebagai target recovery manual, tetapi tidak boleh sendirian memicu auto-bridge pasca-login tanpa hint hotspot trusted.
- Jika ada jaringan hotspot resmi baru, perubahan harus dilakukan lewat config allowlist plus regression tests, bukan dengan menonaktifkan guard.

## Tindak lanjut operasional yang direkomendasikan

- Setelah setiap deploy yang menyentuh flow captive/login, audit cepat access log untuk `link_login_only`, `/captive`, `/hotspot-required`, `wartelpas`, dan subnet asing.
- Jika hari yang sama belum ada trafik captive nyata, lakukan satu user journey hotspot end-to-end untuk memastikan guard tetap pass pada traffic sah.
- Jangan treat kosongnya log hari ini sebagai bukti absolut bahwa tidak ada foreign portal; itu hanya berarti tidak ada request yang masuk ke potongan waktu tersebut.

## Artefak operasi yang dipakai

- `tmp/audit_runtime_20260317_034658.log`
- `tmp/audit_nginx_20260317_034711.log`
- `tmp/audit_nginx_today_20260317_034904.log`
- `tmp/final_public_ping_now_20260317_034107.log`
- `tmp/deploy_hotspot_fix_20260316_233354.log`