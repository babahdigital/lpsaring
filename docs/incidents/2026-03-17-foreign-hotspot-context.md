# Incident 2026-03-17: Foreign Hotspot Portal Context Masuk ke LPSaring

Status: resolved oleh commit `ab53b3ff`.

## Ringkasan insiden

Portal publik LPSaring sempat menerima context captive dari jaringan lain, terutama Wartelpas. Gejalanya berupa wrong login link, context hotspot yang salah di halaman `/captive`, dan risiko bridge/manual activation mengarah ke router yang bukan milik LPSaring.

Masalah ini bukan disebabkan oleh fallback env LPSaring yang salah. Akar masalahnya adalah frontend sebelumnya belum memiliki trust boundary eksplisit untuk menyaring hint hotspot dari query string, nested redirect, referrer, dan local storage.

## Gejala yang terlihat

- Historical request publik membawa `link_login_only=http://172.16.12.1/login` atau host `wartelpas.net`.
- Beberapa request membawa `client_ip` di subnet `172.16.12.x`, padahal hotspot client LPSaring berada di `172.16.2.0/23`.
- User bisa mendarat ke flow captive/login LPSaring dengan context router asing walau default env LPSaring sudah menunjuk ke `login.home.arpa`.
- Wrong-link tidak muncul sebagai hardcoded bug sederhana di source, tetapi sebagai context leak lintas portal.

## Dampak

- UX login hotspot dapat salah arah.
- Jalur auto-login, one-click activation, dan manual login bridge berisiko memakai hint router dari jaringan lain.
- Portal publik berpotensi mencampur context captive antar network walau backend auth utama, database, Redis, dan deploy tetap sehat.
- Masalah ini tergolong trust-boundary failure di frontend, bukan kegagalan auth backend inti.

## Akar masalah

- `NUXT_PUBLIC_APP_LINK_MIKROTIK` dan `NUXT_PUBLIC_MIKROTIK_LOGIN_URL` hanya memberi fallback default, bukan validasi atas input runtime.
- Sebelum fix, identitas hotspot dan login hint dapat datang dari beberapa sumber yang dipercaya terlalu longgar:
  - query route
  - nested redirect `link_login_only`
  - `document.referrer`
  - `localStorage`
- Sumber tersebut bisa membawa context asing ke domain publik LPSaring, lalu frontend memprosesnya seolah-olah itu portal hotspot yang valid.
- Cross-check ke Wartelpas membuktikan ini benar-benar jaringan terpisah, bukan variasi resmi LPSaring:
  - subnet Wartelpas berada di `172.16.12.1/24`
  - login/API Wartelpas memakai domain sendiri

## Investigasi yang membuktikan masalah

1. Audit source pada `frontend/pages/login/hotspot-required.vue`, `frontend/pages/login/index.vue`, `frontend/middleware/auth.global.ts`, `frontend/store/auth.ts`, `frontend/utils/hotspotIdentity.ts`, dan flow captive lain tidak menemukan wrong-link yang hardcoded ke Wartelpas.
2. Validasi lokal untuk flow hotspot/login lulus, sehingga masalahnya bukan typo sederhana pada route aktif.
3. Log historis produksi menunjukkan dua pola yang berbeda:
   - flow trusted LPSaring memakai `login.home.arpa` dan `client_ip` di `172.16.2.x` atau `172.16.3.x`
   - flow foreign membawa `wartelpas.net`, `172.16.12.1`, atau `172.16.12.x`
4. Ini membuktikan masalah utamanya adalah portal publik menerima context asing tanpa filter tegas.

## Remediasi permanen

Perubahan permanen dipusatkan pada trust boundary frontend:

- `frontend/utils/hotspotTrust.ts`
  - menambahkan `HotspotTrustConfig`
  - default allowlist client CIDR `172.16.2.0/23`
  - default trusted login host `login.home.arpa`
  - helper utama:
    - `resolveHotspotTrustConfig()`
    - `isTrustedHotspotClientIp()`
    - `sanitizeResolvedHotspotIdentity()`
    - `sanitizeHotspotLoginHint()`
    - `extractTrustedHotspotLoginHintFromQuery()`
    - `isTrustedHotspotReferrer()`
- `frontend/utils/hotspotIdentity.ts`
  - identitas hotspot dari query, referrer, dan storage sekarang disanitasi
  - identity di subnet asing otomatis dibuang
  - stored identity stale atau tidak trusted dibersihkan
- `frontend/middleware/auth.global.ts`
  - guest hanya diarahkan ke `/captive` bila context hotspot trusted
  - foreign context tidak lagi memaksa redirect captive/login bridge
- `frontend/store/auth.ts`
  - stored router hint dan route hint disaring sebelum dipakai untuk auto-login atau activation
- `frontend/pages/captive/index.vue`
  - halaman captive menolak foreign context dan menampilkan pesan blokir
- `frontend/pages/login/hotspot-required.vue`
  - bridge/manual activation diblok bila context router tidak trusted
- `frontend/pages/login/index.vue`
  - login OTP tetap bisa berjalan, tetapi hint hotspot asing tidak dibawa masuk ke flow activation
- `frontend/nuxt.config.ts` dan env examples
  - runtime config baru:
    - `NUXT_PUBLIC_HOTSPOT_ALLOWED_CLIENT_CIDRS`
    - `NUXT_PUBLIC_HOTSPOT_TRUSTED_LOGIN_HOSTS`

## Verifikasi pascaperbaikan

- Focused frontend regression untuk hotspot/auth lulus, termasuk skenario:
  - reject subnet asing `172.16.12.x`
  - reject host `wartelpas.net`
  - reject nested redirect foreign `link_login_only`
  - middleware hanya membawa captive context trusted
- Full validation sebelum push:
  - frontend ESLint pass
  - frontend typecheck pass
  - backend Ruff pass
- Deploy produksi selesai sehat:
  - semua service `up`
  - frontend `healthy`
  - `/api/ping` publik merespons normal
- Audit publik terfokus setelah deploy tidak menemukan hit hari ini untuk:
  - `wartelpas`
  - `172.16.12.1`
  - `link_login_only`
  - `/hotspot-required`
  - public `401/5xx` pada flow login/hotspot

## Runbook diagnosis singkat bila gejala serupa muncul lagi

```bash
ssh -i ~/.ssh/id_raspi_ed25519 -p 1983 abdullah@159.89.192.31 \
  'tail -n 400 /home/abdullah/nginx/logs/access.log \
    | grep -E "link_login_only|/captive|/login|/hotspot-required|wartelpas|172\.16\.12\.1| 500 | 401 " || true'

COMPOSE_PROD="docker compose --env-file .env.prod -f docker-compose.prod.yml"

$COMPOSE_PROD logs --since 20m --no-color backend frontend \
  | grep -Ei "link_login_only|hotspot-required|wartelpas|172\.16\.12\.1|Traceback|Exception" || true
```

Aturan interpretasi:

- `link_login_only` dengan host trusted seperti `login.home.arpa` masih normal.
- `client_ip` harus tetap berada di `172.16.2.0/23` kecuali allowlist resmi memang diperluas.
- Hit yang membawa `wartelpas`, `172.16.12.1`, atau subnet asing harus diperlakukan sebagai foreign context.
- Jika log publik kosong untuk hari ini, artinya trust boundary belum diuji oleh user journey hotspot terbaru; verifikasi lanjutan harus memakai sesi captive nyata.

## Aturan perubahan kedepan

- Jangan pernah melonggarkan filter hanya karena ada one-off device yang membawa query aneh.
- Jika LPSaring menambah router login atau subnet hotspot resmi, update allowlist di env publik dan ulangi focused tests.
- Jangan bergantung pada env fallback saja untuk masalah trust boundary. Semua hint runtime dari browser/router tetap harus divalidasi.

## Artefak terkait

- `tmp/audit_runtime_20260317_034658.log`
- `tmp/audit_nginx_20260317_034711.log`
- `tmp/audit_nginx_today_20260317_034904.log`
- `tmp/final_public_ping_now_20260317_034107.log`