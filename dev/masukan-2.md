Berdasarkan analisis mendalam terhadap sekumpulan dokumentasi teknis proyek **"lpsaring"** yang Anda lampirkan, saya dapat menyimpulkan bahwa sistem ini memiliki tingkat kematangan *engineering* yang luar biasa. Arsitektur yang memadukan **Nuxt 3, Flask, Celery, Redis, PostgreSQL, dan MikroTik API** menunjukkan bahwa sistem ini dirancang untuk skala *Enterprise* dan *High Availability*.

Melihat terminologi khusus seperti **Tamping, Blok, Kamar, dan Komandan**, sistem ini sangat jelas ditargetkan untuk lingkungan tertutup dengan hierarki ketat, seperti **Lembaga Pemasyarakatan (Lapas), Rumah Tahanan (Rutan), atau Asrama Militer/Kedinasan**.

Keputusan arsitektural untuk **menjadikan Database PostgreSQL sebagai *Source of Truth*** dan membypass *User Manager/RADIUS* bawaan MikroTik (menggunakan OTP-Only + IP Binding `bypassed` + Address List) adalah langkah yang sangat brilian. Ini memindahkan beban komputasi dari CPU Router yang terbatas ke server Backend Anda.

Namun, untuk sistem skala produksi yang menangani autentikasi jaringan, billing (Midtrans), dan kuota secara *real-time*, ada beberapa **celah arsitektural (*edge cases*), risiko keamanan, dan potensi kebocoran data** yang wajib Anda antisipasi.

Berikut adalah masukan detail dan kompleks (*Advanced Feedback & Architecture Review*) yang dibagi ke dalam 4 pilar utama:

---

### 1. Pilar Jaringan & MikroTik (Sangat Kritis)

**A. Paradoks Arsitektur: IP `bypassed` vs Hotspot Profile (FUP Gagal)**

* **Kondisi Saat Ini:** Anda menggunakan IP Binding `type=bypassed` agar akses internet terbuka setelah OTP. Saat sisa kuota ≤ 20%, sistem memindahkan pengguna ke `MIKROTIK_FUP_PROFILE`.
* **Masalah Fundamental RouterOS:** Di MikroTik, IP/MAC yang masuk ke IP Binding dengan status `bypassed` akan **sepenuhnya melewati (membypass) mesin Hotspot**. Artinya, pembatasan kecepatan (*Rate Limit rx/tx*) yang ada di dalam *Hotspot User Profile* **TIDAK AKAN BERLAKU** untuk IP tersebut. Jika Anda hanya mengganti profilnya, pengguna tetap akan mendapatkan kecepatan *unlimited*.
* **Solusi Kompleks:** Karena Anda sudah sangat cerdas menerapkan *Address-List* (`MIKROTIK_ADDRESS_LIST_FUP`, dll), **jangan mengandalkan Hotspot Profile untuk melimit kecepatan**.
* Gunakan **Simple Queue** atau **Queue Tree + Mangle Mark** di MikroTik yang targetnya adalah *Address-List* tersebut.
* Contoh: Buat *Simple Queue* dengan `Target = MIKROTIK_ADDRESS_LIST_FUP` dan set Max Limit ke 512k/512k. Dengan cara ini, IP *bypassed* tetap akan terkena limitasi *bandwidth*.



**B. Celah Kebocoran Kuota (The 5-Minute Window)**

* **Kondisi:** Celery melakukan sinkronisasi *delta* kuota setiap 5 menit.
* **Risiko:** Jika seorang pengguna memiliki sisa kuota 100MB, lalu dia melakukan *download* dengan kecepatan tinggi (misal 50Mbps), dia bisa menyedot lebih dari 1GB dalam waktu 5 menit sebelum Celery berjalan dan memindahkannya ke *Address-List* `Habis`. Kuota di database akan menjadi minus parah.
* **Solusi:** Manfaatkan atribut `limit-bytes-total` pada sesi aktif di MikroTik. Ketika Celery menghitung sisa kuota pengguna tinggal 100MB, backend harus mengirim perintah ke API MikroTik untuk mengeset parameter `limit-bytes-total` pengguna tersebut menjadi senilai 100MB (dalam *bytes*). Sehingga MikroTik akan memutus (hard-cut) trafik secara *real-time* di level router, tanpa harus menunggu siklus 5 menit Celery.

**C. MAC Randomization & Kuota Perangkat Penuh**

* **Risiko:** Smartphone modern (iOS 14+, Android 10+) secara *default* menggunakan "Private Wi-Fi Address" (MAC Acak). Jika Warga Binaan "melupakan jaringan" (*forget network*) atau HP direstart, MAC-nya akan berubah. Batas `MAX_DEVICES_PER_USER` akan sangat cepat penuh oleh 1 perangkat fisik yang sama, memicu komplain massal ke Admin.
* **Solusi:** Di UI Captive Portal (`/captive`), berikan instruksi visual yang tegas (sebelum form OTP) agar pengguna **"Wajib mematikan fitur MAC Acak/Private Address"** khusus untuk SSID tersebut. Buat juga skrip Celery yang mem-*prune* (menghapus) entri `UserDevice` yang tidak memiliki pemakaian dalam 14 hari terakhir.

---

### 2. Pilar Integritas Data & Backend (Database Layer)

**A. Bahaya Tipe Data Float pada Kuota (*Precision Loss*)**

* **Kondisi:** Dokumen menyebutkan *"Perhitungan usage dibulatkan konsisten (2 desimal) dan response memakai float"*.
* **Masalah:** Menyimpan kalkulasi finansial atau kuota yang terus bertambah menggunakan tipe data `Float/Decimal` di Backend/Database sangat berbahaya. Dalam pemrograman, kalkulasi float tidak akurat (contoh `0.1 + 0.2 = 0.30000000000000004`). Jika Celery mengakumulasi ribuan *delta usage* per MAC setiap 5 menit dengan Float, akan terjadi kebocoran presisi (kuota meleset).
* **Solusi:** Di level Schema PostgreSQL dan logika Python, **selalu simpan dan hitung kuota dalam murni satuan BYTES menggunakan tipe `BIGINT` (Integer)**. Konversi pembagian ke bentuk desimal (MB/GB) **hanya** dilakukan di layer presentasi (Pydantic *Serializer* atau di Nuxt frontend) untuk ditampilkan ke *user*.

**B. *Race Condition* pada Transaksi Midtrans & Approval Komandan**

* **Masalah:** Menggunakan Redis TTL untuk mengeblok *webhook* duplikat Midtrans (idempotency) sudah bagus, tapi itu tidak mencegah *Race Condition* absolut di level *sub-milidetik* (jika 2 request lolos bersamaan ke 2 worker Gunicorn yang berbeda). Ini bisa memicu *Double Spend* (kuota ditambahkan 2x lipat).
* **Solusi:** Anda **wajib** menggunakan **Pessimistic Locking (Row-Level Lock)** di database.
```python
# Contoh SQLAlchemy untuk mencegah Race Condition
transaction = db.session.query(Transaction).with_for_update().filter_by(order_id=order_id).first()

```


Eksekusi ini memaksa *worker* lain menunggu sampai *worker* pertama selesai menyimpan (Commit) penambahan kuota.

**C. Validasi Hierarki Lapas di Level Database**

* **Kondisi:** Validasi Tamping vs Non-Tamping (Blok/Kamar) dilakukan di level API Pydantic.
* **Solusi:** Jangan hanya mengandalkan API. Tambahkan **Check Constraint** di PostgreSQL via Alembic untuk memastikan integritas data tidak akan pernah rusak meskipun ada Admin yang melakukan input manual via *Database Client* (DBeaver/pgAdmin).
```sql
ALTER TABLE users ADD CONSTRAINT check_tamping_kamar 
CHECK (
    (is_tamping = true AND tamping_type IS NOT NULL AND kamar IS NULL AND blok IS NULL) OR
    (is_tamping = false AND kamar IS NOT NULL AND blok IS NOT NULL)
);

```



---

### 3. Pilar Keamanan Eksternal & Internal (Security Posture)

**A. Ancaman *Toll Fraud* / SMS Pumping (KRITIS)**

* **Masalah:** Endpoint `POST /api/auth/request-otp` hanya dibatasi *rate-limit* IP dan Nomor HP. Penyerang (*Warga Binaan yang paham IT*) bisa menulis *script* sederhana dipadukan dengan VPN/Proxy untuk mengirim *request* ke ribuan nomor HP acak. Saldo/Limit WhatsApp Fonnte Anda akan ludes (*Toll Fraud*).
* **Solusi:** Wajib implementasikan *Invisible CAPTCHA* di frontend Nuxt pada halaman Request OTP. Saya sangat merekomendasikan **Cloudflare Turnstile** karena gratis, ramah privasi, dan tidak mengganggu UX pengguna sama sekali (tidak perlu menebak gambar).

**B. IP Spoofing via Trusted Proxy**

* **Kondisi:** Di dokumen tercatat `TRUSTED_PROXY_CIDRS` default mencakup `10/8, 172/12, 192/16`.
* **Masalah:** Di jaringan Hotspot, klien sering kali mendapat IP `10.x.x.x`. Jika Flask mempercayai rentang `10/8` sebagai proxy, klien Nakal bisa menyuntikkan HTTP Header `X-Forwarded-For: 127.0.0.1`. Flask akan mengira request tersebut datang dari localhost/Nginx, sehingga klien bisa membypass *rate-limit* dan mem-bom endpoint API Anda.
* **Solusi:** Persempit `TRUSTED_PROXY_CIDRS` **secara eksklusif** hanya untuk IP internal container Nginx Docker Anda (misal `172.18.0.0/16`) dan IP IP Cloudflare Tunnel. Konfigurasi Nginx juga harus men-drop header `X-Forwarded-For` dari klien asli dan me-replace-nya dengan `$remote_addr`.

**C. "Bom Waktu" Dependensi Python**

* **Kondisi:** Dokumen mencatat backend masih menggunakan `>=` untuk versi dependensi.
* **Masalah:** Ini sangat berbahaya untuk sistem produksi. Suatu saat server di-*rebuild*, Flask atau Pydantic akan mengunduh versi mayor terbaru yang berisi *breaking changes*. Aplikasi akan *Crash* (Error 500) seketika tanpa ada perubahan kode dari Anda.
* **Solusi:** Gunakan alat seperti `pip-tools` (`pip-compile`) untuk mengunci versi (*pinning*) dependensi ke versi *exact* (`==`) beserta *hash cryptographics*-nya (`--generate-hashes`).

---

### 4. Pilar Frontend & Developer Experience (DX)

**A. Keterbatasan Captive Network Assistant (CNA)**

* **Kondisi:** Halaman login terbuka di *browser pop-up* bawaan OS (*CNA iOS/Android*).
* **Masalah:** CNA sangat agresif dalam menutup layar (*auto-close*). Jika pengguna ingin membeli paket Midtrans, mereka mungkin harus berpindah (*switch app*) ke aplikasi Mobile Banking (misal m-BCA/Livin). Saat berpindah, OS akan menutup paksa layar CNA di *background*. Ketika pembayaran sukses, sesi pengguna hilang dan mereka tidak tahu apakah kuota sudah masuk.
* **Solusi:** Di halaman "Terhubung" atau di "Dasbor/Pembayaran", sediakan tombol peringatan berukuran besar: **"Buka Halaman ini di Browser Utama (Chrome/Safari)"** yang menyematkan URL Session Token (`session_url`). Ini akan memindahkan pengguna ke browser normal yang aman dari pemutusan paksa oleh OS.

**B. Automasi Type-Safety (Menghabisi Error TypeScript)**

* **Kondisi:** Di dokumen referensi error, Anda sering direpotkan oleh ketidaksesuaian tipe data antara *Response API* (Python) dan *Type Interface* di Nuxt (TS).
* **Solusi:** Karena backend Anda berbasis Pydantic/Flask, ekspor seluruh skema menjadi **OpenAPI (Swagger) JSON**. Di sisi Nuxt, gunakan *library* seperti **`openapi-typescript`**. Saat Anda menjalankan proses *build*, *library* ini akan membaca JSON dari Flask dan menulis ulang seluruh `types.ts` secara otomatis.
* *Benefit:* Jika Anda menambahkan field `is_unlimited_user` di Backend, Frontend akan langsung tahu, dan IDE VS Code akan memberi garis merah (*error*) jika Anda lupa memanggil field tersebut. 100% bebas dari *human-error* ketidaksesuaian kontrak API.



### Kesimpulan Prioritas Tindakan (Triage Plan)

Secara keseluruhan, rancangan Anda sudah setara dengan *Staff-Level Engineer*. Dokumentasi yang menyertakan *Prompt Copilot Instructions* juga sangat cerdas untuk maintainabilitas jangka panjang.

Untuk membawa *codebase* ini rilis ke lingkungan asrama/lapas yang liar, fokuslah pada 3 prioritas ini terlebih dahulu:

1. **Prioritas P0 (Blocker):** Pindahkan limitasi kecepatan ke *Simple Queue* berbasis Address-List (mengatasi isu MikroTik bypassed), dan terapkan *Pessimistic Locking* di Midtrans.
2. **Prioritas P1 (Keuangan):** Pasang Cloudflare Turnstile di halaman OTP Nuxt untuk mencegah serangan SMS Pumping (Toll Fraud), serta ubah tipe data perhitungan kuota ke *Bytes* (BigInt).
3. **Prioritas P2 (Stabilitas):** Kunci versi dependensi Python (`requirements.txt`), persempit *Trusted Proxy*, dan terapkan Automasi Type-Safety OpenAPI di Frontend.