# Incident 2026-03-21: Recreate False Negative — Health Check Internal Gagal Padahal Stack Sudah Naik

**Severity:** Medium  
**Status:** Resolved  
**Kategori:** Near-miss operasional / false negative deploy verification

---

## Ringkasan

Deploy `./deploy_pi.sh --recreate` pertama setelah publish Docker terbaru mengembalikan `RC=1`. Sekilas ini terlihat seperti deploy gagal. Namun pengecekan lanjutan menunjukkan stack aplikasi sebenarnya sudah hidup dan dapat melayani request penting.

Insiden ini dikategorikan sebagai near-miss karena kegagalan ada pada jalur verifikasi internal, bukan pada startup aplikasi inti. Tanpa audit lanjutan, operator bisa salah mengambil keputusan seperti rollback prematur atau menyimpulkan image terbaru belum sehat, padahal masalah utamanya adalah health check internal yang tidak representatif.

---

## Dampak

- Deploy pertama ditandai gagal oleh wrapper script.
- Ada risiko operator salah rollback atau salah menyimpulkan release image rusak.
- Tidak ada downtime berkepanjangan yang terkonfirmasi.
- Tidak ada data loss.

---

## Timeline Ringkas

1. Docker publish untuk commit target selesai hijau.
2. `./deploy_pi.sh --recreate` dijalankan pada produksi.
3. Script berakhir dengan `RC=1` setelah health check internal terhadap `global-nginx-proxy` timeout/gagal.
4. Health check terpisah dari workspace lokal dijalankan dan menunjukkan app stack sebenarnya hidup.
5. Dilakukan audit image runtime vs image `latest` di host.
6. Ditemukan bahwa verifikasi image runtime masih perlu dipastikan penuh.
7. `./deploy_pi.sh --recreate` dijalankan ulang.
8. Recreate kedua berakhir `RC=0` dan image backend/frontend runtime cocok dengan image terbaru.

---

## Gejala yang Terlihat

- wrapper deploy menulis status gagal,
- log deploy menyebut kegagalan health check via `global-nginx-proxy`,
- tetapi service inti terlihat sudah hidup,
- pengecekan `/login`, asset `_nuxt`, dan healthcheck pascadeploy terpisah menunjukkan hasil baik.

---

## Root Cause

Jalur deploy lama masih terlalu bergantung pada satu health check internal terhadap `global-nginx-proxy`. Pada insiden ini probe tersebut memberikan sinyal gagal, walaupun stack aplikasi inti sebenarnya telah naik.

Dengan kata lain, root cause bukan kerusakan aplikasi utama, tetapi gap antara:

- indikator sukses/gagal deploy di script,
- kondisi nyata stack backend/frontend di host.

Tambahan faktor yang membuat kejadian ini membingungkan: operator tetap perlu membedakan antara dua kemungkinan berikut:

1. stack memang sudah hidup tetapi script memberi false negative,
2. stack hidup, tetapi container runtime belum memakai image terbaru yang diharapkan.

Karena itu audit image runtime terhadap `latest` tetap diperlukan sebelum menyatakan deploy aman.

---

## Resolusi

Langkah penyelesaian yang terbukti benar:

1. jangan langsung rollback saat `--recreate` gagal pertama kali,
2. jalankan healthcheck terpisah yang mengecek endpoint publik yang lebih representatif,
3. verifikasi status container dan endpoint `/login` serta asset `_nuxt`,
4. bandingkan image ID container runtime dengan image `latest` di host,
5. rerun `./deploy_pi.sh --recreate` bila image runtime belum cocok atau jika healthcheck pertama jelas false negative.

Hasil akhir: recreate kedua berhasil penuh dan runtime memakai image terbaru.

---

## Guardrail Baru

Runbook produksi diperbarui dengan aturan berikut:

- `GET /api/ping` lokal boleh dianggap sehat jika hasilnya `200` atau `429`, karena endpoint ini bisa terkena rate limit saat dipanggil dari host/proxy lokal.
- `api/ping` tidak boleh menjadi satu-satunya penentu deploy sukses.
- Setelah recreate, operator harus mengombinasikan:
  - status container sehat,
  - endpoint `/login`,
  - satu asset `/_nuxt/...`,
  - kecocokan image runtime vs image `latest`.

---

## Pelajaran

1. Kode keluar non-zero dari deploy wrapper belum tentu berarti aplikasi gagal start.
2. Health check internal yang terlalu sempit dapat menghasilkan false negative.
3. Verifikasi image runtime sama pentingnya dengan verifikasi HTTP health.
4. Runbook harus membedakan kegagalan startup app dari kegagalan probe internal.