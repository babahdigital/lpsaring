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

## 21) Vue template error: `Invalid end tag.`
**Gejala**:
- VS Code / Vue compiler menampilkan error:
	- `Invalid end tag.`

**Akar masalah umum**:
- Ada tag penutup dobel saat refactor layout (contoh: `</VWindow>` tertulis dua kali).

**Solusi**:
- Buka area yang ditandai error, cek struktur nesting template.
- Pastikan jumlah tag pembuka/penutup seimbang (terutama `VWindow`, `VRow/VCol`, `VDialog/VCard`).

## 22) Background bind device 403: `/users/me/devices/bind-current`
**Gejala**:
- Di console/network terlihat `POST /api/users/me/devices/bind-current` sering 403.

**Penyebab umum**:
- Binding device gagal (IP/MAC tidak resolvable, policy device limit, atau konteks captive portal tidak lengkap).

**Solusi yang dipakai di repo ini**:
- Tambah mode best-effort dengan query `?best_effort=1`.
	- Jika binding gagal, endpoint mengembalikan `200` dengan `success:false` (tidak spam 403).
	- 403 tetap untuk akun nonaktif / blocked.

## 23) CSP report-only spam: `Content-Security-Policy-Report-Only` / `script-src 'none'`
**Gejala**:
- Console spam laporan CSP report-only.

**Penyebab umum**:
- Ada lebih dari satu layer yang menyuntikkan CSP (upstream app + nginx + edge), sehingga policy bertabrakan.

**Mitigasi yang dipakai**:
- Di Nginx, hide CSP headers dari upstream agar hanya CSP Nginx yang terlihat:
	- `proxy_hide_header Content-Security-Policy;`
	- `proxy_hide_header Content-Security-Policy-Report-Only;`

**Catatan**:
- Jika masih muncul, kemungkinan berasal dari Cloudflare/edge (di luar container nginx).

## 26) SSH remote log audit salah quote: `No such container: ...bash_completion...`
**Gejala**:
- Saat menjalankan loop log audit via SSH, output docker menunjukkan error container tidak ditemukan dengan nama aneh (mis. path bash completion).

**Penyebab**:
- Ekspansi shell lokal/remote bercampur karena quoting command multi-layer tidak aman.

**Solusi**:
- Gunakan quoting ketat untuk command remote (hindari wildcard expansion tidak sengaja).
- Untuk loop berkala, kirim script kecil yang dieksekusi utuh di sisi remote, bukan rangkaian quote bertingkat yang rapuh.

## 27) Info sync: `Skip sync_hotspot_usage_and_profiles: global lock active`
**Gejala**:
- Muncul log info bahwa task sync dilewati karena global lock aktif.

**Makna**:
- Ini adalah proteksi overlap task (bukan crash), terjadi saat eksekusi sebelumnya masih memegang lock.

**Tindakan**:
- Anggap normal bila sesekali dan task berikutnya tetap sukses.
- Investigasi hanya jika terjadi terus-menerus disertai backlog/anomali performa.

## 17) Docker BuildKit snapshot error (cache corruption)
**Gejala**:
- `docker compose build` gagal dengan error snapshot/cache (BuildKit).

**Penyebab umum**:
- Cache BuildKit korup (terutama setelah build berulang / disk penuh / crash).

**Solusi cepat**:
- Bersihkan cache builder lalu build ulang:
	- `docker builder prune -af`
	- `docker system prune -af` (lebih agresif; hati-hati)

## 18) `abort(422)` berubah jadi 500 (HTTPException tertangkap)
**Gejala**:
- Backend seharusnya balas 422, tetapi yang keluar 500.

**Penyebab**:
- `HTTPException` dari `abort()` tertangkap oleh `except Exception` lalu dibungkus ulang.

**Solusi**:
- Tambahkan handler `except HTTPException: raise` sebelum `except Exception`.

## 19) Query `order_id` double di callback Snap finish
**Gejala**:
- URL jadi seperti `.../payment/finish?order_id=AAA&order_id=AAA`.

**Penyebab**:
- Finish URL sudah mengandung `order_id` tetapi Snap juga menambahkan `order_id`.

**Solusi**:
- Untuk Snap callbacks, pakai base URL tanpa query (mis. `/payment/finish`).

## 20) Snap.js masih ter-load saat mode Core API
**Gejala**:
- Browser tetap request `snap.js` walau mode Core API.

**Penyebab**:
- Plugin frontend auto-load Snap.js di banyak halaman.

**Solusi**:
- Snap.js harus lazy-load hanya saat benar-benar dipakai (`useMidtransSnap()`), bukan dari plugin global.

## 14) OTP terkirim tapi user tidak bisa login (verify-otp tidak terpanggil)
**Gejala**:
- User klik “Kirim OTP” berhasil (OTP masuk WhatsApp), tapi setelah input OTP tombol verifikasi tidak jalan / tidak ada perubahan.

## 28) Auto-login tidak pernah terpanggil di client (OTP berulang)
**Gejala**:
- Pada log produksi terlihat dominan `request-otp`/`verify-otp`, tetapi endpoint `POST /api/auth/auto-login` nyaris/tidak terlihat.
- User cenderung berulang meminta OTP meski sebelumnya sudah pernah login di perangkat yang sama.

**Penyebab**:
- Inisialisasi auth sisi client tidak konsisten memanggil jalur best-effort auto-login setelah hydration.

**Solusi**:
- Pastikan plugin auth memanggil `initializeAuth()` di `app:mounted` pada sisi client.
- Pertahankan `initializeAuth()` idempotent di store agar pemanggilan aman.

**Verifikasi**:
- Pantau rasio endpoint:
	- `/api/auth/auto-login`
	- `/api/auth/request-otp`
	- `/api/auth/verify-otp`
- Target: terdapat hit `auto-login` pada skenario session valid/perangkat terotorisasi.

## 29) User sudah login (JWT valid) tapi tidak diarahkan ke `login/hotspot-required`
**Gejala**:
- User sudah punya session/JWT, membuka `/login` atau `/`, namun tidak diarahkan ke `login/hotspot-required` padahal hotspot session belum aktif.

**Penyebab**:
- Middleware guard route guest belum melakukan precheck `GET /api/auth/hotspot-session-status` untuk user yang sudah login.

**Solusi**:
- Tambahkan precheck hotspot di `auth.global.ts` untuk route guest (`/`, `/login`, `/register`, `/daftar`) pada user non-admin.
- Jika `hotspot_login_required === true` dan `hotspot_binding_active !== true`, redirect ke `/login/hotspot-required` (termasuk passthrough `client_ip`/`client_mac` jika ada).
- Jika precheck gagal, fallback ke flow normal (best-effort, tidak hard-fail).
- `hotspot_session_active` adalah alias legacy untuk kompatibilitas klien lama.

**Verifikasi**:
- Unit/runtime test skenario berikut harus lulus:
	- hotspot required + inactive => redirect hotspot-required,
	- hotspot required + active => tidak redirect hotspot-required,
	- precheck error => fallback normal,
	- admin => skip precheck.

## 30) `useNuxtApp` tidak diimport eksplisit pada middleware (silent failure dalam `try/catch`)
**Gejala**:
- Test menunjukkan endpoint precheck tidak pernah dipanggil (`$api` call count = 0), tetapi middleware tampak tidak crash karena tertutup `try/catch`.

**Penyebab**:
- Composable global dipakai tanpa import eksplisit di konteks middleware + harness test tertentu.

**Solusi**:
- Import eksplisit dari `#app`:
	- `import { defineNuxtRouteMiddleware, navigateTo, useNuxtApp } from '#app'`

**Catatan**:
- Error jenis ini berbahaya karena bisa tersembunyi oleh fallback `catch`, jadi perlu test call assertion (bukan hanya assertion redirect akhir).
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

## 24) Datepicker/Kalender masih tidak konsisten di dialog
**Gejala**:
- Pada skenario tertentu (terutama dialog fullscreen/scrollable), popup kalender kadang terasa tidak stabil posisinya atau interaksi tidak konsisten.

**Konteks**:
- Sudah ada perbaikan sebelumnya untuk positioning/ukuran Flatpickr, namun laporan terbaru menunjukkan isu masih muncul di sebagian alur.

**Penyebab yang paling mungkin**:
- Konflik antara positioning popup dengan container dialog yang memiliki kombinasi `overflow`, transform, dan viewport mobile.
- Re-render komponen input saat state dialog berubah cepat (open/close/switch tab) sehingga state popup ikut reset.

**Status saat ini**:
- **Open / Known Issue**.

**Arah penyempurnaan**:
1. Standarisasi wrapper date input dan opsi Flatpickr pada semua dialog terkait.
2. Pastikan append target popup konsisten (hindari menempel pada parent yang terpotong overflow).
3. Tambahkan regression checklist khusus kalender di mobile + desktop sebelum rilis.

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

## 25) Paket testing nonaktif terlihat ke user reguler
**Gejala**:
- Pada mode demo, paket testing nonaktif kadang masih muncul di list paket untuk user reguler.

**Penyebab**:
- Kontrol visibilitas demo terlalu bergantung pada state UI/frontend, belum sepenuhnya difilter berdasarkan requester di backend.

**Solusi yang dipakai di repo ini**:
- Backend endpoint `/api/packages` memvalidasi requester terautentikasi dan eligibility demo user.
- Paket demo nonaktif hanya ditambahkan untuk user demo yang eligible.
- Frontend tetap menampilkan state UI sesuai hasil backend + status `is_demo_user`.

**Verifikasi**:
- User reguler: paket testing nonaktif tidak muncul.
- User demo eligible: paket testing tampil dan paket non-testing terblokir sesuai kebijakan demo.
- Jika UX tidak presisi di mobile, pertimbangkan fallback tabel (lebih stabil dan jelas).

## 28) Audit user gagal ketemu karena format nomor telepon
**Gejala**:
- Query operasional untuk nomor lokal (format `08...`) tidak menemukan user di DB.

**Penyebab**:
- Data produksi disimpan dalam format E.164 (`+62...`), bukan format lokal.

**Solusi**:
- Saat audit/manual SQL, selalu cari dengan variasi normalisasi (`08...`, `62...`, `+62...`) atau gunakan suffix terkontrol.
- Untuk script operasional, normalisasi nomor dulu sebelum query.

## 29) Router menunjukkan `regular`, tetapi user tidak ada di DB
**Gejala**:
- Ditemukan ip-binding `type=None`/`regular` dengan comment `user=<nomor>|uid=<uuid>`, tetapi user/uid tidak ada lagi di DB.

**Penyebab**:
- Artefak stale/orphan di RouterOS dari cleanup lama yang tidak tuntas.

**Contoh nyata (06-03-2026)**:
- Nomor `082164599907` tidak ditemukan di DB, namun router masih punya ip-binding comment `user=082164599907|uid=d332b5fb-45f9-4ae0-9a40-0c4e174b7026` dengan `type=None` (efektif `regular`).

**Solusi**:
- Hapus ip-binding orphan berdasarkan marker comment (`uid=` / `user=`) atau MAC.
- Jalankan parity audit berkala untuk mendeteksi marker router yang tidak punya pasangan DB.
- Standarkan deprovisioning memakai cleanup user-level (`reset-login`/admin cleanup) bukan hanya delete row.

## 30) Ekspektasi salah: delete device menghapus semua artefak jaringan + token
**Gejala**:
- Diasumsikan `DELETE /users/me/devices/<id>` juga menghapus DHCP lease, ARP, host, dan session token device.

**Penyebab**:
- Endpoint ini saat ini hanya device-level cleanup minimum.

**Perilaku aktual**:
- Ya: remove ip-binding + managed address-list + row `user_devices`.
- Tidak: DHCP lease, ARP, hotspot host explicit cleanup, revoke refresh token per-device.

**Solusi**:
- Gunakan `reset-login` bila butuh cleanup menyeluruh user-level (network + sessions).
- Dokumentasikan perbedaan scope agar tim support tidak salah ekspektasi.

## 31) Blip deploy: `502` karena backend DNS/upstream belum siap
**Gejala**:
- Sesaat setelah recreate deploy, Nginx memberi `502` untuk endpoint API tertentu.

**Penyebab**:
- Transisi startup service, resolver/upstream belum siap pada menit deploy.

**Solusi**:
- Anggap sebagai transien jika cepat pulih dan healthcheck berikutnya hijau.
- Verifikasi dengan:
	- `lpsaring_error.log` (resolve/connect upstream)
	- ringkasan status `2xx/4xx/5xx` pada jendela deploy.
- Jika menetap, investigasi DNS upstream/container health.

## 32) SSH heredoc/quoting membuat audit command tampak hang
**Gejala**:
- Command SSH multi-quote/heredoc kadang berhenti tanpa output jelas atau menghasilkan error shell aneh.

**Penyebab**:
- Quoting bertingkat rentan pecah antara shell lokal dan remote.

**Solusi**:
- Gunakan helper script terpisah lalu pipe ke `docker exec -i ... python -`.
- Hindari wildcard/regex berat dalam satu command string panjang.
- Untuk job panjang, tulis output ke file sementara remote lalu `tail`/`grep` terpisah.
