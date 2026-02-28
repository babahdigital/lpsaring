# Ops: Cleanup GitHub Actions (Caches + Workflow Runs)

Dokumen ini merangkum prosedur operasional untuk:
- menghapus cache GitHub Actions (agar storage tidak membengkak),
- menghapus workflow runs lama (mis. sisakan 2 terbaru).

Status terkini (2026-02-28):
- housekeeping otomatis sudah aktif via workflow `Actions Housekeeping`,
- default retention ketat: `keep_runs=2`, `keep_caches=0`,
- tetap tersedia prosedur manual untuk pembersihan darurat.

> Catatan keamanan: jangan menulis token/secret di dokumen ini.

## Prasyarat

- `gh` CLI ter-install dan sudah login.
- Akun punya akses repo.

Cek status login:

```bash
gh auth status
```

Repo contoh di dokumen ini:
- `OWNER=babahdigital`
- `REPO=lpsaring`

## 1) Audit cepat (berapa banyak cache & run)

```bash
gh api repos/$OWNER/$REPO/actions/caches?per_page=1 | jq '{total:.total_count}'

gh api repos/$OWNER/$REPO/actions/runs?per_page=1 | jq '{total:.total_count}'
```

Catatan:
- Cache bisa muncul lagi setelah ada workflow run baru.

## 2) Hapus SEMUA caches

### 2.1 Ambil list cache id

```bash
gh api repos/$OWNER/$REPO/actions/caches?per_page=100 | jq -r '.actions_caches[].id'
```

### 2.2 Delete per-id

Contoh loop bash:

```bash
for id in $(gh api repos/$OWNER/$REPO/actions/caches?per_page=100 | jq -r '.actions_caches[].id'); do
  echo "deleting cache id=$id"
  gh api -X DELETE repos/$OWNER/$REPO/actions/caches/$id
done
```

Jika cache banyak (lebih dari 100), lakukan paginate manual atau ulang beberapa kali sampai `total_count` = 0.

## 3) Hapus workflow runs lama, sisakan N terbaru

Tujuan umum: sisakan 2 run terbaru agar halaman Actions tidak penuh.

### 3.1 Ambil daftar run id terbaru

```bash
KEEP=2
RUN_IDS=$(gh api repos/$OWNER/$REPO/actions/runs?per_page=100 | jq -r '.workflow_runs[].id')
```

### 3.2 Delete selain N teratas

Contoh (gunakan `jq` untuk ambil selain N teratas):

```bash
KEEP=2
DELETE_IDS=$(gh api repos/$OWNER/$REPO/actions/runs?per_page=100 | jq -r --argjson keep "$KEEP" '.workflow_runs | sort_by(.created_at) | reverse | .[$keep:] | .[].id')

for id in $DELETE_IDS; do
  echo "deleting run id=$id"
  gh api -X DELETE repos/$OWNER/$REPO/actions/runs/$id
done
```

Catatan:
- Jika repo sangat aktif, lakukan ulang hingga total run sesuai yang diinginkan.

## 4) Verifikasi

```bash
gh api repos/$OWNER/$REPO/actions/caches?per_page=1 | jq '{total:.total_count}'

gh api repos/$OWNER/$REPO/actions/runs?per_page=1 | jq '{total:.total_count}'
```

## 5) Tips pencegahan (ringkas)

- Cache akan tumbuh lagi kalau workflow terus berjalan. Kalau sering tembus limit, pertimbangkan:
  - menurunkan jumlah key cache,
  - menambah cleanup step terjadwal,
  - atau memperkecil cache artifact yang tidak perlu.

## 6) Insiden aktual & penyelesaian (2026-02-27 s/d 2026-02-28)

### A. Gejala yang terjadi

- Storage cache mendekati/melewati limit (`~10 GB`), dengan ratusan entri cache.
- Workflow runs menumpuk dan menyulitkan audit cepat.
- Setelah cleanup, diperlukan retrigger pipeline bersih dari nol.

### B. Tindakan manual yang sudah dilakukan

1. Menghapus seluruh workflow runs lama dan menyisakan 2 run terbaru.
2. Menghapus seluruh Actions caches per `cache_id` sampai `total_count=0`.
3. Menghapus 2 run tersisa atas permintaan operasional, lalu retrigger pipeline.

### C. Perilaku CI yang dianggap normal

- Pada commit kosong (empty commit), workflow `ci` dapat menampilkan banyak job `skipped` selain `changes`.
- Penyebab: job gate memakai `paths-filter`; jika tidak ada perubahan file yang match, job tersebut tidak dieksekusi.
- Ini expected behavior dan tidak menandakan error pipeline.

### D. Perbaikan permanen (otomasi retention)

Ditambahkan workflow baru:
- `.github/workflows/actions-housekeeping.yml`

Fungsi:
- schedule tiap 6 jam (`cron: 0 */6 * * *`),
- manual trigger (`workflow_dispatch`) dengan parameter:
  - `keep_runs` (default `2`, dibatasi max `30`),
  - `keep_caches` (default `0`, dibatasi max `20`).

Cara kerja:
- hapus run **completed** lama di luar batas `keep_runs`,
- hapus cache lama berdasarkan `last_accessed_at` di luar batas `keep_caches`.

### E. Dampak operasional

Positif:
- storage Actions lebih stabil,
- halaman Actions lebih bersih,
- incident response lebih cepat.

Trade-off:
- histori run lama lebih cepat hilang,
- potensi cache miss meningkat sedikit (build tertentu bisa sedikit lebih lama).

### F. Rekomendasi default

- Gunakan baseline ketat: `keep_runs=2`, `keep_caches=0`.
- Saat investigasi historis diperlukan, jalankan manual housekeeping sementara dengan nilai lebih longgar.
