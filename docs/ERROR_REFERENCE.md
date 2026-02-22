# Referensi Error & Penyebab (Frontend)

Dokumen ini merangkum penyebab umum error TypeScript/Vue yang muncul agar menjadi referensi ke depan.

Lampiran wajib:
- [.github/copilot-instructions.md](../.github/copilot-instructions.md)

## 1) Konsistensi Tipe Data
**Gejala**: Banyak error di template (index signature, any, property not exist).
**Penyebab**:
- Kontrak API berubah (tamping, quota, role) tapi type frontend belum diperbarui.
- Ada duplikasi tipe antara berbagai file.

**Solusi**:
- Satukan tipe di folder types/.
- Pastikan response API dan tipe frontend sinkron.

## 2) useFetch/useApiFetch Generics
**Gejala**: Error terkait default, PickFrom, atau data tidak dikenal.
**Penyebab**:
- Generic type tidak diset eksplisit.
- default() mengembalikan object bukan Ref.

**Solusi**:
- Gunakan typed response dan hindari default() jika tidak perlu.
- Gunakan cast terkontrol atau helper typed.

## 3) $vuetify vs useDisplay
**Gejala**: Property $vuetify tidak ada.
**Penyebab**:
- Migrasi dari Vuetify lama ke Nuxt 3 / Vuetify 3.

**Solusi**:
- Gunakan useDisplay() untuk breakpoint dan replace penggunaan $vuetify.

## 4) Icon Adapter & Namespace Types
**Gejala**: IconSet/IconProps tidak terbaca.
**Penyebab**:
- Tipe Vuetify tidak diekspor seperti di versi sebelumnya.

**Solusi**:
- Gunakan type lokal sederhana di adapter.
- Hindari import type yang menyebabkan error.

## 5) Template Slot Typing
**Gejala**: item pada slot dianggap unknown.
**Penyebab**:
- Slot template tidak memiliki tipe eksplisit.

**Solusi**:
- Buat helper function untuk cast item.
- Hindari indexing langsung jika item dianggap any/unknown.

## 6) Perubahan Schema User (Tamping)
**Gejala**: Field is_tamping/tamping_type tidak ada di tipe atau form.
**Penyebab**:
- Perubahan DB & backend tidak diikuti frontend.

**Solusi**:
- Tambahkan field ke type user, form, dan validator.

## 7) ApexCharts Types
**Gejala**: property tidak dikenal di config chart.
**Penyebab**:
- Tipe Apex lebih ketat dari opsi real.

**Solusi**:
- Cast ke any untuk bagian tertentu.
- Simpan tipe strict untuk area inti saja.

## 8) Rekomendasi Pencegahan
- Terapkan lint rule yang konsisten.
- Buat changelog saat kontrak API berubah.
- Tambahkan smoke tests sederhana sebelum merge.

## 9) Buildx Frontend Exit Code 1 (CI Publish)
**Gejala**:

```text
buildx failed with: ERROR: failed to build: failed to solve: process "/bin/sh -c pnpm run build:icons --if-present && pnpm run build" did not complete successfully: exit code: 1
```

**Konteks**:
- Muncul pada workflow `Docker Publish & Optional Deploy`, job matrix frontend.
- Backend pada run yang sama bisa sukses.

**Kemungkinan penyebab**:
- Perbedaan environment build CI vs lokal (resource, cache, atau dependency state).
- Error build Nuxt tertutup ringkasan buildx sehingga stack trace asli tidak terlihat di bagian akhir log.

**Langkah investigasi minimum**:
1. Ambil log awal step `Build & push frontend` (bukan hanya baris terakhir).
2. Reproduksi lokal:
	- `pnpm run build:icons --if-present && pnpm run build`
	- `docker build -f frontend/Dockerfile-prod frontend`
3. Cocokkan commit SHA antara run CI dan hasil lokal.

## 10) Runtime TDZ Chunk Error (`Cannot access 'ee' before initialization`)
**Gejala**:

```text
Uncaught ReferenceError: Cannot access 'ee' before initialization
```

**Konteks**:
- Muncul pada aset minified `_nuxt/*.js`.
- Biasanya terkait urutan inisialisasi modul/chunk dan cache aset yang campur antar versi.

**Mitigasi yang sudah dilakukan**:
- Menghapus custom manual chunk splitting di `frontend/nuxt.config.ts` agar memakai strategi default Vite/Nuxt.

**Verifikasi pasca deploy**:
- Hard refresh (`Ctrl+F5`) atau uji incognito.
- Pastikan referensi file `_nuxt/*` di browser sesuai output build terbaru.

## 11) Pylance `reportCallIssue` pada model SQLAlchemy (keyword args)
**Gejala**:
- Pylance menampilkan error seperti:
	- `No parameter named "admin_id"`
	- `No parameter named "target_user_id"`
	- dst.

**Penyebab**:
- Model SQLAlchemy declarative menerima `**kwargs` saat runtime, tetapi Pylance tidak selalu bisa menginfer signature `__init__`.

**Solusi (pola yang dipakai di repo ini)**:
- Hindari `Model(field=value, ...)` untuk model declarative yang memicu false-positive.
- Gunakan pola set attribute:
	- `obj = Model(); obj.field = value; ...`

## 12) Vitest error `require() of ES Module ... not supported` (jsdom)
**Gejala**:
- `pnpm test` gagal dengan error ESM/CJS saat start worker, contoh:
	- `require() of ES Module ... not supported`

**Penyebab**:
- Kombinasi dependency transitive (jsdom → html-encoding-sniffer → ESM module) tidak kompatibel dengan loader CJS pada environment tertentu.

**Solusi cepat (untuk unit test non-DOM)**:
- Jika test hanya unit test util tanpa DOM, set `vitest` environment ke `node` (bukan `jsdom`).
- Jika butuh DOM test, alternatifnya: isolate test DOM ke config terpisah atau upgrade/downgrade dependency yang memicu ESM/CJS mismatch.

## 13) Perubahan backend tidak kebaca di container (butuh rebuild)
**Gejala**:
- Setelah edit file Python di host, API di container masih pakai versi lama.

**Penyebab**:
- Mode default `docker-compose.yml` membuild backend menjadi image dan **tidak** me-mount source code `./backend:/app`.

**Solusi**:
- Pilihan A (default): rebuild backend:
	- `docker compose up -d --build backend`
- Pilihan B (dev mount): jalankan override yang memount source backend dan menyalakan reload.

## 14) OTP terkirim tapi user tidak bisa login (verify-otp tidak terpanggil)
**Gejala**:
- User klik “Kirim OTP” berhasil (OTP masuk WhatsApp), tapi setelah input OTP tombol verifikasi tidak jalan / tidak ada perubahan.
- Di log backend hanya terlihat `POST /api/auth/request-otp` (200), sementara `POST /api/auth/verify-otp` tidak muncul.

**Akar masalah umum**:
- Frontend terlalu ketat memakai `otpCode.length === 6`.
	- Jika OTP dipaste mengandung spasi/strip/teks (mis. `Kode: 123 456`), panjang menjadi bukan 6.
	- Pada beberapa device, binding `VOtpInput` bisa menghasilkan nilai non-string sehingga `.length` tidak valid.

**Solusi yang dipakai di repo ini**:
- Sanitasi OTP di frontend: ambil digit saja dan kirim 6 digit terakhir.
- Kondisi disable tombol verifikasi juga memakai hasil sanitasi digit.

**Verifikasi (Production)**:
```bash
docker logs --since 2h hotspot_prod_flask_backend | egrep -a 'POST /api/auth/(request-otp|verify-otp)'
```

Jika `verify-otp` tidak ada, masalahnya di client/submit (bukan reset-login atau MikroTik).

## 15) Mixed Content HMR (HTTPS page → ws:// diblok)
**Gejala**:
```text
Mixed Content: The page was loaded over HTTPS, but attempted to connect to the insecure WebSocket endpoint 'ws://.../_nuxt/...'
```

**Akar masalah**:
- HMR client mencoba konek lewat `ws://` sementara origin page `https://` (browser memblokir).

**Solusi**:
- Jangan memaksa `hmr.protocol = 'ws'` secara default.
- Biarkan Vite derive dari `window.location` (HTTPS → WSS).
- Jika perlu override untuk remote dev, gunakan env `VITE_HMR_HOST`, `VITE_HMR_PROTOCOL=wss`, `VITE_HMR_CLIENT_PORT=443`.

## 16) vue3-apexcharts error `Cannot read properties of null (reading 'destroy')`
**Gejala**:
```text
Uncaught (in promise) TypeError: Cannot read properties of null (reading 'destroy')
```

**Konteks umum**:
- Terjadi saat chart re-render cepat (resize observer / hydration / conditional render) sehingga instance chart sudah null saat watcher mencoba destroy.

**Mitigasi yang disarankan**:
- Hindari mount/unmount chart berulang pada area yang sangat reaktif.
- Jika UX tidak presisi di mobile, pertimbangkan fallback tabel (lebih stabil dan jelas).
