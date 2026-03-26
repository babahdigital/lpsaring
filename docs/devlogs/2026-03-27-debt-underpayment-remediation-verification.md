# Devlog: 2026-03-27 - Debt Underpayment Remediation Verification

**Tanggal**: 27 Maret 2026  
**Author**: Abdullah (via GitHub Copilot)  
**Scope**: verifikasi produksi pasca deploy fix label riwayat debt, audit historis underpayment debt online, dan arsip hasil remediasi

---

## Ringkasan

Batch ini menutup tiga pekerjaan operasional terakhir setelah fix debt settlement online dirilis ke produksi:

1. spot-check API riwayat transaksi admin dan user langsung ke host produksi,
2. audit ulang seluruh transaksi debt settlement sukses untuk memastikan tidak ada kasus underpayment lain yang lolos,
3. arsip hasil remediasi final untuk dua user terdampak.

Hasil akhir:

- label riwayat transaksi debt di API produksi sudah benar (`Partial Debt` / `Pelunasan Debt`),
- audit historis tidak menemukan user tambahan di luar dua order yang sudah dikoreksi,
- dua debt koreksi berhasil dibuat di produksi dan dua WhatsApp koreksi berhasil masuk antrean Fonnte.

---

## Verifikasi API Produksi

Verifikasi dilakukan langsung terhadap API publik produksi `https://lpsaring.babahdigital.net` memakai bearer token valid yang dibuat dari app production.

### 1. User history API

Endpoint:

- `GET /api/users/me/transactions?per_page=20`

Hasil spot-check untuk user `+6289527796925`:

- order `BD-DBLP-28C1A6E02017` muncul dengan `package_name = "Pelunasan Debt"`
- order `BD-DBLP-E0_wMuJYQJCC-_SFXchOGA~557C` muncul dengan `package_name = "Partial Debt"`

Ini membuktikan label riwayat user tidak lagi jatuh ke `N/A` atau kosong untuk transaksi debt.

### 2. Admin transaction history API

Endpoint:

- `GET /api/admin/transactions?per_page=20&search=BD-DBLP-28C1A6E02017`
- `GET /api/admin/transactions/BD-DBLP-28C1A6E02017/detail`

Hasil spot-check:

- payload list admin mengembalikan item order `BD-DBLP-28C1A6E02017` dengan `package_name = "Pelunasan Debt"`
- payload detail admin untuk order yang sama juga mengembalikan `package_name = "Pelunasan Debt"`

Ini menutup verifikasi bahwa jalur admin list dan detail sama-sama memakai resolver label debt yang baru.

---

## Audit Historis Lanjutan

Audit dijalankan ulang di produksi menggunakan command:

```bash
flask audit-debt-settlement-underpayments --dry-run
```

Ringkasan output setelah remediasi apply sebelumnya:

- `order=BD-DBLP-28C1A6E02017 ... shortage=Rp 130.000 ... existing_correction=yes`
- `order=BD-DBLP-5ECAA2086E66 ... shortage=Rp 40.000 ... existing_correction=yes`
- `order=BD-DBLP-E0_wMuJYQJCC-_SFXchOGA~557C ... shortage=Rp 0`
- `order=BD-DBLP-649ABEF093C2 ... shortage=Rp 0`
- summary: `DRY-RUN selesai: shortage_found=2 skipped_existing=2`

Interpretasi operasional:

- seluruh shortage historis yang terdeteksi tetap hanya dua order yang sudah diketahui,
- keduanya sekarang sudah memiliki debt koreksi, sehingga audit menandainya sebagai `existing_correction=yes`,
- tidak ada shortage tambahan untuk transaksi debt settlement sukses lain yang ikut tersapu audit ini.

Dengan demikian, tidak ditemukan user tambahan di luar dua kasus yang sudah diremediasi.

---

## Hasil Remediasi Produksi

Apply mode yang sebelumnya dijalankan di produksi menghasilkan ringkasan:

- `shortage_found=2`
- `created=2`
- `skipped_existing=0`
- `wa_sent=2`

Detail entri koreksi yang berhasil tersimpan:

| User | Phone | Order | Koreksi | Kuota Debt | Due Date |
| --- | --- | --- | ---: | ---: | --- | 
| Puguh Rahmansyah | `+6289527796925` | `BD-DBLP-28C1A6E02017` | `Rp 130.000` | `13312 MB` (`13 GB`) | `2026-04-02` |
| Ikhsan Fajar | `+6283167629438` | `BD-DBLP-5ECAA2086E66` | `Rp 40.000` | `4096 MB` (`4 GB`) | `2026-03-30` |

Catatan tambahan dari verifikasi DB:

- kedua entri koreksi tersimpan dengan note prefix `Koreksi kekurangan pembayaran debt online`
- saldo cached `manual_debt_mb` setelah apply terbaca `13312` untuk Puguh
- saldo cached `manual_debt_mb` setelah apply terbaca `4097` untuk Ikhsan, yang berarti `4096 MB` debt koreksi baru + `1 MB` sisa debt lama yang memang sudah ada sebelumnya

---

## Status WhatsApp Koreksi

Fonnte mengembalikan status sukses masuk antrean untuk dua nomor terdampak:

- Puguh Rahmansyah: target `6289527796925`, queue id `148995999`
- Ikhsan Fajar: target `6283167629438`, queue id `148996001`

Tidak ada indikasi kegagalan enqueue pada dua notifikasi koreksi ini.

---

## Kesimpulan Operasional

Status akhir batch ini adalah **selesai penuh**:

- fix label riwayat debt sudah aktif di API produksi,
- audit historis sudah dijalankan ulang dan tidak menemukan kasus tambahan,
- dua user terdampak sudah menerima debt koreksi dan WhatsApp koreksi,
- jalur audit kini reusable untuk pengecekan ulang di masa depan tanpa edit data manual langsung di database.

Artefak bukti utama batch ini:

- hasil apply produksi: `SUKSES: shortage_found=2 created=2 skipped_existing=0 wa_sent=2`
- hasil audit ulang: `DRY-RUN selesai: shortage_found=2 skipped_existing=2`
- payload API user/admin produksi yang mengembalikan `Partial Debt` dan `Pelunasan Debt`