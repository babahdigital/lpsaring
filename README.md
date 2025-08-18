# Hotspot Portal

A comprehensive WiFi hotspot management system with user authentication, access control, and monitoring features.

## Recent Improvements

### MAC Address Detection Enhancement (2023-09-29)

Fixed MAC address detection for regular browsers accessing the portal directly instead of via captive portal redirection.

- Enhanced RouterOS API client with multiple detection methods
- Improved ping mechanisms to better populate ARP tables
- Added retry logic for more reliable detection
- Optimized caching strategies for both frontend and backend
- Added TCP Connection and DNS Static table lookups

See [MAC-DETECTION-BROWSER-FIX.md](docs/MAC-DETECTION-BROWSER-FIX.md) for detailed documentation.

## Deployment Notes (2025-08)

### 1. Squash Migration (Optional Fresh Deploy Only)
File: `backend/migrations/versions/20250811_00_squashed_base.py`

Gunakan hanya untuk instalasi BARU ketika ingin skip seluruh sejarah migrasi lama:
1. Inisialisasi database kosong.
2. Jalankan perintah Alembic stamp langsung ke revisi squash:
   `alembic stamp 20250811_00` (atau via script deploy Anda).
3. Jalankan upgrade normal berikutnya apabila ada migrasi setelah squash.

JANGAN menjalankan migrasi squash ini pada database produksi yang sudah berisi data—tetap gunakan urutan migrasi historis normal sampai head terbaru.

### 2. Penambahan Kolom `ip_address` di `user_devices`
Model sudah menambahkan kolom ini. Jika database produksi belum memilikinya, jalankan migrasi baru (lihat contoh migrasi di bawah) untuk menjaga konsistensi.

Contoh Alembic (ringkas):
```python
def upgrade():
	with op.batch_alter_table('user_devices') as batch:
		if not _col_exists('user_devices', 'ip_address'):
			batch.add_column(sa.Column('ip_address', sa.String(45)))
```

### 3. Internal Metrics
Endpoint: `/metrics`
- Histogram: `mac_lookup_duration_bucket{le="..."}` dan alias Prometheus klasik `mac_lookup_duration_seconds_bucket{le="..."}` plus `_sum` dan `_count`.
- Rekomendasi scrape interval: 15s–30s.

### 4. Redis Pipelining
Aktifkan dengan env: `REDIS_PIPELINE_BATCH_SIZE=20` (misal). Buffer flush ketika mencapai batch size atau 10ms.

### 5. Async Mode Lookup
Aktifkan dengan env: `MIKROTIK_ASYNC_MODE=true` (dipakai jika tidak mengaktifkan parallel host/dhcp/arp). Mengurangi blocking apabila koneksi MikroTik lambat.

### 6. Grace Cache & Rencana Gauge Tambahan
Grace in-memory cache dipakai untuk menghindari flicker MAC ketika refresh cepat. Rencana opsional (belum aktif): tambahkan gauge untuk
`mac_lookup_grace_cache_size` dan failure ratio untuk observability lanjutan.

---
Lanjutkan penyesuaian sesuai kebutuhan produksi Anda.