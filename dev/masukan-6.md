Saya mengerti maksud Anda. Anda ingin **User Experience (UX)** di depan tetap simpel "OTP Only" (user tidak merasa punya password), tetapi di **belakang layar (MikroTik)** sistem melakukan *login* standar hotspot (bukan sekadar *bypass* IP binding) agar pencatatan sesi dan kuota di `/ip/hotspot/active` lebih presisi dan persisten.

Ini strategi yang cerdas untuk menggabungkan kemudahan OTP dengan ketangguhan *accounting* radius/hotspot tradisional.

Berikut adalah masukan teknis dan koreksi keamanan agar implementasi ide ini berjalan sempurna di sistem **lpsaring** Anda:

### 1. Masukan Utama: Jangan Gunakan Nomor Telepon sebagai Password

Meskipun *password* di-*hidden*, menggunakan nomor telepon sebagai *password* tetap membuka celah keamanan (orang iseng yang tahu nomor HP target bisa melakukan *spoofing* MAC address dan login paksa).

**Solusi Lebih Baik:**
Sistem Anda saat ini **sudah otomatis membuat password acak** 4-6 digit (`mikrotik_password`) saat user register.

* **Logika:** Gunakan `username=NoHP` dan `password=mikrotik_password` (yang ada di DB).
* **User:** Tetap tidak tahu password-nya.
* **Sistem:** Lebih aman karena password unik per user.

### 2. Perubahan Alur Sistem (Hybrid OTP + Hotspot Login)

Agar ide Anda berjalan (menghindari ketergantungan IP Binding Bypass semata), Anda perlu mengubah sedikit alur di Frontend dan Backend:

#### A. Backend (`auth_routes.py` & `device_management.py`)

Saat ini, setelah verifikasi OTP sukses, sistem melakukan `IP Binding = bypassed`. Ini harus diubah:

1. **Verifikasi OTP Sukses:**
* Backend **JANGAN** membuat IP Binding tipe `bypassed` (atau hapus binding jika ada).
* Backend mengembalikan respon JSON yang berisi `hotspot_username` (No HP) dan `hotspot_password` (Password acak dari DB) ke Frontend.

Catatan keamanan minimal:
* **Jangan simpan** `hotspot_password` ke storage (localStorage/cookies) di frontend.
* Kirim hanya untuk sekali login, dan hilangkan dari state setelah submit.



#### B. Frontend (`pages/captive/index.vue` atau halaman login)

Di sinilah logika "Hidden Input" Anda bekerja.

1. User input OTP -> Klik "Verifikasi".
2. Terima respon JSON dari Backend (Token + Username + Password Hotspot).
3. **Action Otomatis (Inject Login):**
Frontend secara otomatis menjalankan login ke MikroTik menggunakan kredensial yang diterima, tanpa interaksi user.
Disarankan memakai **form POST tersembunyi** (bukan `fetch`) agar lebih kompatibel dengan captive portal dan menghindari isu CORS/mixed-content.
```javascript
// Contoh Logika Frontend (Pseudo-code)
async function onOtpVerified(response) {
  const user = response.hotspot_username;
  const pass = response.hotspot_password; // Password acak dari DB, user tidak perlu tahu
  const loginUrl = "http://10.10.83.1/login"; // URL Login MikroTik

  // Lakukan Hidden Login via form POST
  const form = document.createElement('form');
  form.method = 'POST';
  form.action = loginUrl;
  form.style.display = 'none';
  form.innerHTML = `
    <input name="username" value="${user}">
    <input name="password" value="${pass}">
    <input name="dst" value="http://google.com">
  `;
  document.body.appendChild(form);
  form.submit();
}

```



### 3. Keuntungan Metode Ini (Sesuai Keinginan Anda)

Dengan metode ini, Anda mendapatkan persis apa yang Anda cari:

1. **Quota Lebih Persisten:** User tercatat di `/ip/hotspot/active`. MikroTik akan menghitung kuota (`bytes-in`/`bytes-out`) secara *native* dan memutus koneksi otomatis jika limit tercapai, tidak hanya mengandalkan *script* sinkronisasi.
2. **Anti Bypass:** Karena tidak menggunakan `IP Binding type=bypassed`, user yang mengganti IP atau MAC address tidak akan bisa konek internet kecuali mereka login ulang (OTP lagi).
3. **UX Tetap Simpel:** User hanya melihat OTP. Password adalah urusan sistem di belakang layar.

### 4. Hal yang Perlu Diwaspadai (Trap)

* **Logout:** Saat kuota habis atau masa aktif berakhir, Anda harus memastikan *backend* mengirim perintah `POD` (Packet of Disconnect) atau menghapus user dari `/ip/hotspot/active` agar sesi mati.
* **Perangkat Apple (iOS):** iPhone terkadang sangat ketat memblokir *script auto-login* di Captive Portal Assistant (CNA). Anda mungkin perlu tombol "Lanjutkan" manual di akhir jika *auto-submit* gagal dieksekusi oleh browser mini iOS.
* **Fallback UX:** Jika login hotspot gagal, tampilkan tombol manual "Login Hotspot" agar user bisa submit ulang tanpa ulang OTP.

**Kesimpulan:**
Ide Anda valid dan lebih superior secara teknis untuk manajemen kuota daripada sekadar IP Binding. Kuncinya: **Gunakan password acak dari database sebagai *hidden input*, bukan nomor teleponnya.** Ini menjaga keamanan tanpa mengorbankan kemudahan.