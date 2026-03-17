# Incident 2026-03-18: Verify OTP Fail-Hard Saat Router MAC Lookup Transien

Status: resolved oleh commit `cd5c38da`.

## Ringkasan insiden

Flow captive hotspot sempat mengalami kegagalan saat user men-submit OTP. Gejala yang terlihat bukan keterlambatan pengiriman OTP ke WhatsApp, tetapi kegagalan pada endpoint `POST /api/auth/verify-otp` setelah OTP yang benar sudah dimasukkan user.

Pola yang teramati di production access log:

- `request-otp` sukses
- `verify-otp` pertama gagal `503`
- retry `verify-otp` langsung berubah menjadi `401`
- request OTP baru terlalu cepat kemudian terkena `429`

Ini adalah failure mode di jalur verify/post-submit, bukan di jalur delivery OTP.

## Gejala yang terlihat

- User captive memasukkan OTP yang benar tetapi request verify bisa gagal dengan `503`.
- Retry beberapa detik kemudian bisa menjadi `401 Invalid or expired OTP code`.
- Saat user langsung meminta OTP baru, cooldown request bisa memunculkan `429`.
- Dari sisi user, pengalaman ini terlihat seperti OTP "tidak bekerja" atau "submit OTP macet", padahal request awal sudah masuk ke backend.

## Dampak

- UX login hotspot terganggu karena satu OTP yang valid bisa terasa "habis sia-sia".
- User bisa terjebak pada urutan error `503 -> 401 -> 429` sebelum akhirnya bisa meminta OTP baru.
- Insiden ini meningkatkan friction pada captive flow yang memang sudah sensitif terhadap state router dan browser.

## Evidence utama

Rangkaian request yang terekam pada access log produksi:

- `17/Mar/2026 17:21:50 +0000` `POST /api/auth/request-otp` → `200`
- `17/Mar/2026 17:22:06 +0000` `POST /api/auth/verify-otp` → `503`
- `17/Mar/2026 17:22:19 +0000` `POST /api/auth/verify-otp` → `401`
- `17/Mar/2026 17:22:27 +0000` `POST /api/auth/request-otp` → `429`
- `17/Mar/2026 17:22:53 +0000` `POST /api/auth/request-otp` → `200`
- `17/Mar/2026 17:23:29 +0000` `POST /api/auth/verify-otp` → `200`

Interpretasi urutan di atas:

- verify pertama gagal karena jalur verify masih fail-hard saat verifikasi MAC router transien
- OTP kemungkinan sudah terkonsumsi sebelum request benar-benar menyelesaikan binding/auth flow, sehingga retry berikutnya jatuh ke `401`
- cooldown request OTP tetap bekerja, sehingga user tidak bisa langsung meminta OTP baru tanpa jeda

## Akar masalah

Sebelum fix, `verify_otp_impl` melakukan urutan konservatif berikut:

1. verifikasi OTP ke Redis
2. hapus OTP dari Redis saat cocok
3. lanjutkan validasi identitas perangkat berbasis router (`resolve_client_mac(client_ip)`)
4. jika lookup `IP -> MAC` gagal, request diakhiri `503`

Masalahnya, jalur ini tidak punya fallback aman seperti yang sudah dimiliki `auto-login` untuk kasus hint router transien. Akibatnya:

- request verify bisa gagal keras walau `client_ip` dan `client_mac` dari captive context sebenarnya valid
- karena OTP sudah tidak tersedia lagi di Redis, retry verify berikutnya tidak lagi bisa memakai kode yang sama

Ini bukan trust-boundary bug. Ini adalah gap reliability antara dua auth path:

- `POST /api/auth/auto-login` sudah memiliki fallback konservatif dari `client_mac -> client_ip`
- `POST /api/auth/verify-otp` belum memiliki fallback setara

## Remediasi permanen

Perubahan permanen dilakukan pada backend:

- `backend/app/infrastructure/http/auth_contexts/verify_otp_handlers.py`
  - menambahkan helper pemulihan IP dari hint `client_mac` melalui router
  - saat `resolve_client_mac(client_ip)` gagal atau tidak menemukan device, jalur verify sekarang boleh mencoba fallback konservatif
  - fallback hanya dianggap valid bila router mengembalikan `client_mac -> client_ip` yang sama persis dengan IP hotspot yang dikirim client
  - raw `client_mac` tidak dipercaya tanpa konfirmasi IP yang cocok dari router
  - source fallback ditandai sebagai `mikrotik_mac_hint`, sehingga tidak diperlakukan sebagai trust setingkat lookup router normal untuk kasus takeover lintas user

## Verifikasi pascaperbaikan

- Focused backend pytest untuk `backend/tests/test_auth_verify_otp_auto_authorize.py` lulus `8/8`
- Regresi baru mencakup:
  - fallback sukses saat `IP -> MAC` gagal tetapi `MAC -> IP` mengembalikan IP yang sama
  - fallback tetap ditolak saat `MAC -> IP` mengembalikan IP yang berbeda
- Patch dipromosikan ke produksi melalui:
  - CI manual run `23208958760` sukses
  - Docker publish manual run `23208961882` sukses
  - deploy `down --remove-orphans` lalu `./deploy_pi.sh --recreate`
- Audit runtime sesudah deploy memastikan marker source fallback benar-benar ada di container backend aktif
- Sweep log aplikasi `15m` setelah deploy tidak menunjukkan exception baru terkait verify-otp

## Status residual setelah deploy

- Patch sudah aktif di runtime produksi
- Health publik kembali normal setelah restart window singkat
- Belum ada bukti traffic user baru yang pasti mengeksekusi cabang fallback ini di produksi setelah deploy, sehingga validasi branch fallback pada trafik nyata masih menunggu login hotspot berikutnya

## Runbook diagnosis singkat bila gejala serupa muncul lagi

```bash
ssh -i ~/.ssh/id_raspi_ed25519 -p 1983 abdullah@159.89.192.31 \
  'cd /home/abdullah/nginx/logs && grep -E "verify-otp|request-otp|auth/me|hotspot-required|captive/terhubung" lpsaring_access.log | tail -n 250'

ssh -i ~/.ssh/id_raspi_ed25519 -p 1983 abdullah@159.89.192.31 \
  'cd /home/abdullah/lpsaring/app && docker compose --env-file .env.prod -f docker-compose.prod.yml logs --since=30m --no-color backend frontend celery_worker | grep -Ei "verify-otp|router|mikrotik|warning|error|exception" || true'
```

Aturan interpretasi:

- `verify-otp 503` yang diikuti `401` dan `request-otp 429` adalah sinyal kuat bahwa verify flow gagal setelah OTP tervalidasi tetapi sebelum auth flow selesai bersih.
- Jika backend container aktif mengandung marker `should_try_mac_hint_fallback`, maka patch fallback sudah terdeploy dan perlu dicari apakah kegagalan baru terjadi di jalur lain.
- Jika tidak ada login user baru sesudah deploy, jangan klaim efektivitas patch fallback di trafik nyata; status yang benar adalah "deployed and audit-clean".

## Artefak terkait

- `tmp/verify_otp_access_12h_20260318.log`
- `tmp/verify_otp_backend_12h_20260318.log`
- `tmp/deploy_verify_otp_20260318_020624.log`
- `docs/devlogs/2026-03-18-hotspot-auto-bridge-probe-priority.md`