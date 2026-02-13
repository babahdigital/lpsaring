**BISA, Pak Abdullah.**

Konsepnya benar: **bypass di hotspot hanya untuk melewati login page**, tetapi **kontrol trafik tetap dilakukan oleh Firewall/Queue**. Dalam skenario OTP-only, bypass menjadi mode utama agar akses internet langsung terbuka setelah OTP sukses.

Saat IP Binding diset ke `type=bypassed`, trafik user tersebut **TIDAK** lagi diatur oleh rule dinamis Hotspot (seperti limitasi user profile hotspot). Karena itu, trafiknya akan jatuh ke **Firewall Filter** dan **Simple Queue** reguler/manual.

Berikut adalah implementasi script lengkap sesuai skenario yang Bapak minta:

### 1. Skenario Blokir (Expired / Quota Habis / Blokir Manual)

*Logika:* User yang ada di address list `klien_blok` atau `quota_habis` tidak boleh ke internet, TAPI harus tetap bisa akses server lokal (untuk topup atau cek status).

Lampiran wajib:
- [.github/copilot-instructions.md](../.github/copilot-instructions.md)

Script ini harus ditaruh di paling atas (`place-before=0`) agar dieksekusi duluan sebelum rule lain.

```mikrotik
/ip firewall filter

# 1. IZINKAN AKSES KE SERVER LOKAL (Wajib ditaruh sebelum rule drop)
# Ganti 10.0.0.6 dengan IP Server Nuxt/Web Bapak
add chain=forward src-address-list=klien_blok dst-address=10.0.0.6 action=accept comment="Allow Blocked User to Server"
add chain=forward src-address-list=quota_habis dst-address=10.0.0.6 action=accept comment="Allow Quota Habis to Server"

# 1b. IZINKAN AKSES KE DOMAIN PENTING UNTUK TOPUP/PEMBAYARAN
# (Tambahkan sesuai kebutuhan: Midtrans, CDN, Google Fonts, DNS Resolver)
# Contoh jika pakai address-list untuk allowed-payment:
# add chain=forward src-address-list=klien_blok dst-address-list=allowed_payment action=accept comment="Allow Payment Hosts"
# add chain=forward src-address-list=quota_habis dst-address-list=allowed_payment action=accept comment="Allow Payment Hosts"

# 2. IZINKAN DNS (Sangat disarankan agar domain portal/payment bisa resolve)
add chain=forward src-address-list=klien_blok protocol=udp dst-port=53 action=accept comment="Allow DNS"
add chain=forward src-address-list=quota_habis protocol=udp dst-port=53 action=accept comment="Allow DNS"

# 3. BLOKIR AKSES INTERNET SISANYA
# Drop semua trafik forward dari list blok/quota habis yang mau ke internet
add chain=forward src-address-list=klien_blok action=drop comment="Drop Internet - Klien Blok"
add chain=forward src-address-list=quota_habis action=drop comment="Drop Internet - Quota Habis"

```

**Penjelasan:**

* Rule pertama memastikan user masih bisa membuka web `lpsaring.local` (server Bapak).
* Rule ketiga mematikan akses ke IP selain server lokal (internet mati).

---

### 2. Skenario FUP (Limitasi Kecepatan)

*Logika:* User yang di-bypass biasanya *unlimited*. Kita akan paksa limitasi menggunakan **Simple Queue** yang menargetkan `address-list`.

```mikrotik
/queue simple

# Buat Queue khusus untuk list FUP
# Max-Limit sesuaikan (misal: Upload 1Mbps / Download 2Mbps)
add name="Limit_Klien_FUP" target=klien_fup max-limit=1M/2M packet-marks="" place-before=0

```

**Catatan Penting:**
Pastikan rule ini berada di posisi **paling atas (0)** atau di atas queue parent lain (seperti `hotspot-default`). Karena di MikroTik, antrian dibaca dari atas ke bawah. Jika di atasnya ada queue yang targetnya `0.0.0.0/0` (global), maka queue FUP ini tidak akan jalan.

---

### 3. Menggunakan Mangle (Opsional / Advanced)

Jika Bapak ingin menggunakan Mangle (misalnya untuk memisahkan trafik game/sosmed pada user FUP), Bapak bisa menandai paketnya terlebih dahulu.

```mikrotik
/ip firewall mangle

# Tandai koneksi dari user FUP
add chain=prerouting src-address-list=klien_fup action=mark-connection new-connection-mark=conn_fup passthrough=yes comment="Mark Conn FUP"

# Tandai paket dari koneksi tersebut
add chain=prerouting connection-mark=conn_fup action=mark-packet new-packet-mark=pkt_fup passthrough=no comment="Mark Packet FUP"

```

Setelah paket ditandai (`pkt_fup`), Bapak bisa menggunakannya di **Queue Tree** atau **Simple Queue** pada parameter `packet-marks`.

### Kesimpulan Alur Logika (Rekomendasi Produksi)

1. **User Konek:** Gunakan **IP Binding bypassed** sebagai default untuk kontrol perangkat.
2. **Cek Firewall Filter:**
* Jika IP masuk list `klien_blok` / `quota_habis` → hanya boleh akses portal & payment (allowlist), selain itu **DROP**.
3. **Cek Queue:**
* Jika IP masuk list `klien_fup` → limitasi bandwidth sesuai rule.
* Jika IP tidak ada di list manapun → akses normal sesuai profile.

**Bypass** adalah mode utama untuk OTP-only. Kontrol user tetap dilakukan via address-list dan queue.

---

## Perbaikan Konfigurasi WebSocket (HMR) untuk lpsaring.local

Jika `lpsaring.local` diarahkan ke **Nginx host/Laragon** (bukan container), gunakan contoh berikut di konfigurasi Nginx host:

```nginx
map $http_upgrade $connection_upgrade {
	default upgrade;
	''      close;
}

server {
	listen 80;
	server_name lpsaring.local;

	location /_nuxt/ {
		proxy_pass http://localhost:3010;
		proxy_http_version 1.1;
		proxy_set_header Upgrade $http_upgrade;
		proxy_set_header Connection $connection_upgrade;
		proxy_set_header Host $host;
	}

	location / {
		proxy_pass http://localhost:3010;
		proxy_http_version 1.1;
		proxy_set_header Upgrade $http_upgrade;
		proxy_set_header Connection $connection_upgrade;
		proxy_set_header Host $host;
	}
}
```

Jika `lpsaring.local` diarahkan ke **Nginx container (Docker)**, maka konfigurasi yang dipakai adalah:
- [infrastructure/nginx/conf.d/app.conf](../infrastructure/nginx/conf.d/app.conf)

---

## Cara Mengarahkan lpsaring.local ke Nginx Container

1) **Pastikan port 80 container terbuka** (sudah ada di docker-compose: `80:80`).

2) **Matikan Nginx host/Laragon** yang memakai port 80, karena jika aktif dia akan mengambil alih request.

3) **Arahkan DNS lokal ke IP server Docker**:
- Jika akses dari **PC yang menjalankan Docker**:
	- Tambahkan di file hosts Windows:
		- `C:\Windows\System32\drivers\etc\hosts`
		- Tambahkan baris: `127.0.0.1 lpsaring.local`
- Jika akses dari **HP/komputer lain di jaringan**:
	- Arahkan `lpsaring.local` ke IP server, misalnya `10.0.0.6` (bisa lewat DNS router atau file hosts di device).

Setelah itu, `lpsaring.local` akan masuk ke Nginx container dan HMR WebSocket tidak 404.

---

## Pembagian Environment (Local vs Public)

File yang disediakan:
- [frontend/.env.local](../frontend/.env.local)
- [frontend/.env.public](../frontend/.env.public)
- [backend/.env.local](../backend/.env.local)
- [backend/.env.public](../backend/.env.public)

Cara pakai (pilih salah satu mode):
1) Salin file yang diinginkan menjadi `.env`:
	- Frontend: salin `frontend/.env.local` atau `frontend/.env.public` → `frontend/.env`
	- Backend: salin `backend/.env.local` atau `backend/.env.public` → `backend/.env`
2) Restart container agar env baru terbaca.
