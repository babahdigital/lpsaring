# Devlog Hotspot Auto-Bridge Probe Priority (2026-03-18)

Dokumen ini merangkum patch frontend yang mengubah prioritas target auto-bridge hotspot, promosi ke produksi, dan analisis login terakhir yang terjadi sebelum patch aktif.

## Tujuan

- Mengurangi ketergantungan auto-bridge pada host lokal seperti `login.home.arpa` atau IP private router.
- Menjaga login manual tetap memakai URL router resmi ketika user memang perlu membukanya.
- Mendokumentasikan perbedaan antara login normal sebelum patch dan perilaku yang diharapkan sesudah patch aktif.

## Perubahan kode yang dipromosikan

Commit yang dipromosikan ke produksi: `d8b1b07b` dengan pesan `fix: prefer public probe for hotspot auto bridge`.

File yang berubah:

- `frontend/utils/hotspotLoginTargets.ts`
  - menambahkan deteksi target hotspot lokal (`.home.arpa`, `localhost`, `.local`, IP private/link-local)
  - `resolveHotspotBridgeTarget()` sekarang memprioritaskan `NUXT_PUBLIC_HOTSPOT_CONTEXT_PROBE_URL` untuk auto-bridge bila hint router termasuk target lokal
- `frontend/pages/login/hotspot-required.vue`
  - auto-bridge tetap menavigasi ke target bridge terpilih
  - hint login manual yang disimpan tetap memakai URL login router, bukan probe publik
- `frontend/tests/hotspot-login-targets.test.ts`
  - menambahkan regresi untuk memastikan target lokal memilih probe publik bila tersedia
  - menambahkan fallback saat probe tidak tersedia dan kasus target publik non-lokal

## Alasan perubahan

Analisis sebelumnya menunjukkan flow otomatis masih sering mengarah ke `login.home.arpa` untuk recovery context. Pada Android Chrome/WebView, host ini bisa memunculkan `DNS_PROBE_FINISHED_NXDOMAIN` alih-alih memberi transisi yang halus ke captive login.

Prinsip baru yang dipakai:

- auto-bridge memakai probe HTTP publik bila hint router berupa target lokal
- login manual tetap memakai URL router trusted agar user masih bisa memaksa halaman hotspot resmi bila dibutuhkan

Dengan pola ini, bridge otomatis bergerak lewat jalur yang lebih stabil untuk browser modern tanpa menghilangkan recovery manual.

## Validasi lokal sebelum promosi

Validasi yang dijalankan:

- `tests/hotspot-login-targets.test.ts` lulus `7/7`
- `tests/hotspot-post-login-bridge.test.ts` tetap lulus `6/6`
- lint file yang disentuh lulus

## Promosi ke produksi

Urutan promosi hari ini:

1. commit `d8b1b07b` dipush ke `main`
2. CI untuk HEAD dinyatakan hijau
3. Docker publish manual dijalankan lewat workflow `docker-publish.yml`
4. produksi sengaja diturunkan dulu dengan `docker compose --env-file .env.prod -f docker-compose.prod.yml down --remove-orphans`
5. deploy dilanjutkan dengan `./deploy_pi.sh --recreate`
6. health container dan `/api/ping` publik diverifikasi

Artefak operasi utama:

- `tmp/deploy_down_recreate_20260318_012949.log`

Status pascadeploy yang tervalidasi:

- `backend` up
- `frontend` up dan `healthy`
- `db` up dan `healthy`
- `redis` up dan `healthy`
- `celery_worker` up
- `celery_beat` up
- `/api/ping` publik merespons `pong from backend!`

## Analisis login terakhir sebelum patch aktif

Access log terbaru yang relevan menunjukkan ada login user nyata sebelum patch aktif, lalu setelah deploy belum ada login user baru pada window yang sama; trafik sesudah deploy yang terlihat didominasi akses admin.

Evidence utama dari login prepatch:

- `17/Mar/2026 15:17:49 +0000` `POST /api/auth/request-otp` → `200`
- `17/Mar/2026 15:18:27 +0000` `POST /api/auth/verify-otp` → `200`
- `17/Mar/2026 15:18:27 +0000` `GET /api/auth/me` → `200`

Interpretasi:

- login tersebut normal dari sisi auth backend karena OTP request dan verify sama-sama sukses
- tidak ada sinyal error backend/worker yang menunjukkan kegagalan auth pada window postdeploy yang diperiksa
- public nginx log tidak memperlihatkan lanjutan ke `/dashboard` setelah `auth/me 200`, tetapi untuk flow prepatch ini itu belum cukup untuk menyimpulkan gagal karena browser bisa saja meninggalkan portal publik menuju bridge/router path yang tidak tercatat di nginx publik

Kesimpulan operasional untuk login 10 menit sebelum patch:

- **normal dari sisi autentikasi**
- **belum bisa dipakai untuk memvalidasi patch baru**, karena event tersebut terjadi sebelum image baru aktif di produksi

## Kondisi sesudah deploy

Window access log yang sama menunjukkan setelah deploy tidak ada login user baru yang cukup lengkap untuk menguji perilaku patch ini end-to-end. Trafik yang terlihat sesudah deploy terutama berupa akses admin ke `/admin/users` dan endpoint admin terkait.

Artinya, status saat ini adalah:

- patch sudah terpasang di runtime produksi
- health aplikasi sudah normal
- validasi user login nyata sesudah patch masih menunggu trafik hotspot/login berikutnya

## Catatan terkait monitoring kecepatan OTP

Patch yang dipromosikan hari ini tidak mengubah jalur kirim OTP atau konfigurasi provider WhatsApp. Monitoring yang dilakukan pada sesi ini juga berfokus pada:

- keberhasilan auth (`request-otp`, `verify-otp`, `auth/me`)
- perilaku redirect/captive/hotspot sesudah login
- health runtime pascadeploy

Artinya, sesi ini **belum menghasilkan monitoring latency OTP yang dedicated**. Evidence yang ada hanya cukup untuk menyatakan auth sukses, bukan untuk mengukur apakah OTP sampai ke perangkat dengan cepat.

Status dokumentasi observabilitas OTP setelah sesi ini:

- referensi knob runtime dan batas observabilitas ditambahkan ke `docs/REFERENCE_PENGEMBANGAN.md`
- devlog ini mencatat bahwa validasi sesi sekarang belum bisa dipakai sebagai benchmark kecepatan OTP

## Follow-up verifikasi OTP saat submit

Analisis lanjutan sesudah deploy menemukan failure mode yang berbeda dari isu auto-bridge. Pada access log 12 jam, ada rangkaian request captive berikut:

- `17/Mar/2026 17:21:50 +0000` `POST /api/auth/request-otp` → `200`
- `17/Mar/2026 17:22:06 +0000` `POST /api/auth/verify-otp` → `503`
- `17/Mar/2026 17:22:19 +0000` `POST /api/auth/verify-otp` → `401`
- `17/Mar/2026 17:22:27 +0000` `POST /api/auth/request-otp` → `429`
- `17/Mar/2026 17:22:53 +0000` `POST /api/auth/request-otp` → `200`
- `17/Mar/2026 17:23:29 +0000` `POST /api/auth/verify-otp` → `200`

Interpretasi operasional:

- problem terjadi saat user men-submit OTP, bukan pada pengiriman OTP ke WhatsApp
- `verify-otp 503` berpotensi menghabiskan OTP yang baru saja valid, sehingga retry berikutnya bisa jatuh ke `401`
- saat user langsung minta OTP baru, cooldown request masih aktif sehingga user juga bisa terkena `429`

Patch backend follow-up yang ditambahkan pada sesi ini:

- `backend/app/infrastructure/http/auth_contexts/verify_otp_handlers.py`
  - menambahkan fallback konservatif ketika lookup router `IP -> MAC` gagal atau tidak menemukan device
  - fallback hanya dipakai jika router masih bisa membuktikan `client_mac -> client_ip` yang sama persis dengan IP yang dikirim client
  - raw `client_mac` tidak langsung dipercaya tanpa kecocokan IP dari router
  - source fallback ditandai sebagai `mikrotik_mac_hint`, sehingga takeover lintas user tetap tidak diperlakukan sebagai sumber trust setingkat lookup router normal
- `backend/tests/test_auth_verify_otp_auto_authorize.py`
  - menambahkan regresi untuk kasus fallback sukses
  - menambahkan regresi untuk memastikan fallback tetap ditolak bila `MAC -> IP` mengarah ke IP yang berbeda

Tujuan patch ini adalah menurunkan kemungkinan user terkena `503 -> 401 -> 429` hanya karena lookup `IP -> MAC` router sedang transien, tanpa melonggarkan trust boundary menjadi sekadar menerima MAC mentah.

## Pelajaran penting

- Untuk login yang terjadi sebelum patch aktif, `verify-otp 200` + `auth/me 200` tanpa lanjutan `/dashboard` di public nginx **tidak otomatis berarti gagal**.
- Public nginx tidak melihat navigasi lokal ke router seperti `login.home.arpa`, jadi analisis flow hotspot harus memisahkan auth success dari final browser navigation.
- Jika auto-bridge memakai host lokal, browser Android bisa gagal di lapisan DNS/UI walau auth backend sebenarnya sehat.
