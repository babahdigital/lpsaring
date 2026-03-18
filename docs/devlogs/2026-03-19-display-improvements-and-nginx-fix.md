# Devlog — Display UX & Nginx Hardening — 2026-03-19

Sesi ini melanjutkan sesi sebelumnya (18 Mar). Fokus utama: penyempurnaan tampilan data ukuran kuota (MB→GB dinamis), notifikasi profil user tidak lengkap, perbaikan tabel riwayat tunggakan, dan root-cause fix 502 intermiten nginx.

Commits: `7a106522` (frontend display & dashboard) + nginx sync tanpa commit (hanya push via `--sync-nginx-conf`).

---

## 1. Konversi MB → GB Dinamis — Admin Dialog

**Problem**: Tampilan admin (UserDetailDialog, UserEditDialog, UserDebtLedgerDialog) masih hardcode " MB" di template dan menggunakan `formatMb()` yang tidak menyertakan unit.

**Fix** (commit `7a106522`):

- `UserDetailDialog.vue`: ganti `formatMb(x) + " MB"` → `formatDataSize(x)` di debt alert dan tabel manual debt.
- `UserEditDialog.vue`: tambah `formatDataSize()` function; ganti display "Sisa Kuota (DB)", "Pemakaian (MikroTik)", dan tiga baris debt (Total/Otomatis/Manual).
- `UserDebtLedgerDialog.vue`: tambah `formatDataSize()` function; ganti chip summary (Total/Otomatis/Manual) dan ketiga kolom tabel (Jumlah/Dibayar/Sisa). Header kolom yang sebelumnya menyebut "(MB)" dihapus.

**Logic `formatDataSize`**:
```ts
function formatDataSize(sizeInMB: number): string {
  if (sizeInMB < 1)    return `${(sizeInMB * 1024).toLocaleString('id-ID', {2dp})} KB`
  if (sizeInMB < 1024) return `${sizeInMB.toLocaleString('id-ID', {2dp})} MB`
  return `${(sizeInMB / 1024).toLocaleString('id-ID', {2dp})} GB`
}
```

---

## 2. Notifikasi Profil Tidak Lengkap — Dashboard User

**Problem**: User yang baru mendaftar dan belum mengisi blok/kamar tidak mendapat panduan untuk melengkapi data.

**Fix** (commit `7a106522`, `dashboard/index.vue`):

- Tambah computed `showIncompleteProfileAlert`:
  - `false` jika role ADMIN, SUPER_ADMIN, atau KOMANDAN
  - `false` jika `is_tamping === true` (tamping tidak wajib punya blok/kamar)
  - `true` jika `blok` atau `kamar` null/kosong
- Template: VAlert `type="info" variant="tonal"` dengan tombol "Lengkapi Profil" → `/akun`
- Alert tidak memiliki tombol close (disengaja — penting untuk dilengkapi)

---

## 3. Penyempurnaan Tabel Riwayat Tunggakan

**Problem** (sesi lanjutan, 19 Mar):
- Kolom "Sisa" redundan — Status LUNAS/BELUM LUNAS sudah mencukupi
- Tanggal tidak menampilkan waktu
- Dialog admin kurang lebar di desktop
- Tabel user (riwayat) belum memiliki kolom Status

### Admin `UserDebtLedgerDialog.vue`

- Hapus kolom "Sisa"
- Pisah kolom "Tanggal" menjadi 2: "Tanggal Utang" (`debt_date`) dan "Dicatat Pada" (`created_at` dengan waktu WITA)
- Tambah kolom "Jatuh Tempo" (`due_date`) — chip merah jika belum lunas, default jika sudah lunas; tampil "—" jika null
- Kolom "Status": tambah timestamp `paid_at` di bawah chip LUNAS
- Tambah `due_date` ke interface `ManualDebtItem`
- Tambah `formatDatetimeLocal()` (ISO → lokal WITA) dan `formatDate()` (date string → format pendek)
- Dialog `max-width`: `900` → `1100`
- Tambah `.debt-table-scroll` (overflow-x: auto) + lebar kolom fix via CSS

### User `riwayat/index.vue`

- Hapus kolom "Sisa" dari tabel debt manual
- Ganti logika show button "Lunasi" dari `remaining_mb > 0` → `!it.is_paid` (lebih semantik)
- Tambah kolom "Status" dengan VChip LUNAS/BELUM LUNAS
- Update `colgroup` width dan CSS `min-width` tabel (740px → 820px)

---

## 4. Nginx Resolver Race Condition — Root Cause Fix

**Problem**: Setelah deploy salah (via `docker compose down` bukan `--recreate`), 502 intermiten berlanjut bahkan setelah container kembali aktif.

**Root cause**: Resolver nginx dikonfigurasi dengan dua server:
```nginx
resolver 127.0.0.11 8.8.8.8 ipv6=off valid=2s;
```
Nginx mengirim kueri ke keduanya paralel dan menggunakan respons tercepat. `8.8.8.8` kadang merespons lebih cepat dan mengembalikan NXDOMAIN untuk hostname internal Docker (lpsaring-backend, lpsaring-frontend). Nginx meng-cache NXDOMAIN 2 detik → request dalam window itu gagal 502.

**Fix**: Hapus `8.8.8.8`, hanya gunakan Docker DNS:
```nginx
resolver 127.0.0.11 ipv6=off valid=2s;
```

**Deployment**: Push via `deploy_pi.sh --sync-nginx-conf` → `nginx -s reload` di server.

**Verifikasi**: Error log bersih setelah 16:57 UTC. Client yang sebelumnya selalu 502 pada setiap menit kembali mendapat 200.

Detail lengkap: `docs/incidents/2026-03-19-nginx-resolver-race-condition-8.8.8.8.md`.

---

## 5. Deploy & Status Produksi

Urutan deployment sesi ini:

1. **Commit `7a106522`** — 4 file frontend (UserDetailDialog, UserEditDialog, UserDebtLedgerDialog, dashboard/index)
2. **CI run `23255956429`** — semua job hijau (changes, contract-gate, frontend, docker-build ×2)
3. **Docker Publish `23256130547`** — backend + frontend image dipush ke Docker Hub
4. **`deploy_pi.sh --recreate`** — DB backup (59.8 MB) → pull images → migration (no drift) → recreate containers → healthcheck OK
5. **nginx sync** — laksanakan `--sync-nginx-conf` → hapus 8.8.8.8 → nginx reload → verifikasi 200

Status produksi saat ini: seluruh 6 container healthy, error log bersih.

---

## File yang Dimodifikasi

| File | Perubahan |
|---|---|
| `frontend/components/admin/users/UserDetailDialog.vue` | `formatMb` → `formatDataSize` di debt alert/tabel |
| `frontend/components/admin/users/UserEditDialog.vue` | tambah `formatDataSize`, ganti 5 template |
| `frontend/components/admin/users/UserDebtLedgerDialog.vue` | rewrite tabel: hapus Sisa, tambah waktu, due_date, Status |
| `frontend/pages/dashboard/index.vue` | tambah `showIncompleteProfileAlert` dan VAlert |
| `frontend/pages/riwayat/index.vue` | hapus kolom Sisa, tambah Status chip |
| `nginx/conf.d/lpsaring.conf` | hapus `8.8.8.8` dari resolver |
| `docs/incidents/2026-03-19-nginx-resolver-race-condition-8.8.8.8.md` | **baru** |
| `docs/devlogs/2026-03-19-display-improvements-and-nginx-fix.md` | **baru** (file ini) |
