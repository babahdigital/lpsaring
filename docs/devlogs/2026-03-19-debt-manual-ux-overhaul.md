# Devlog — Debt Manual UX Overhaul — 2026-03-19

Commits: `ee2f67a6` → `130edd30` → `c36e9310` → `e6358ee3`
Migrations: `20260318_add_due_date_to_manual_quota_debt` (sesi sebelumnya) +
`20260319_add_price_rp_to_user_quota_debts` + `20260319_c_populate_null_due_dates`

---

## Latar Belakang

Tabel tunggakan manual di dialog admin (`UserDebtLedgerDialog.vue`) dan halaman riwayat user
(`riwayat/index.vue`) memiliki beberapa UX problem yang dilaporkan:

1. Kolom "Jatuh Tempo" selalu kosong ("Belum ditetapkan") meski debt sudah dibuat
2. Harga ditampilkan sebagai estimasi (bukan harga paket aktual)
3. Kolom Paket/Info menampilkan full note string alih-alih nama paket saja
4. Paket Unlimited tidak muncul di dropdown tambah tunggakan
5. Tombol Lunasi warnanya mepet ke teks (kurang padding)

---

## Root Cause Analysis

### 1. `due_date` Selalu Null

**Root cause (sesi sebelumnya, fixed `ee2f67a6`):**
`user_profile_service.py` memanggil `data.get("due_date")` namun schema/form menggunakan key
`debt_due_date`. Selalu return `None`.

**Fix:** Ubah key → `data.get("debt_due_date")`, tambah `debt_due_date` ke `UserUpdateByAdminSchema`.

**Root cause lanjutan (fixed `130edd30`):**
Setelah `due_date` bisa diisi dari form, desain berubah: jatuh tempo SELALU akhir bulan (tidak
boleh manual). Form date-picker `debt_due_date` dihapus; backend kini auto-compute.

```python
# user_profile_service.py
_debt_date = _debt_date_raw if isinstance(_debt_date_raw, date) else date.today()
_last_day = calendar.monthrange(_debt_date.year, _debt_date.month)[1]
_auto_due_date = _debt_date.replace(day=_last_day)
```

**Root cause record lama (fixed `c36e9310`):**
Record yang dibuat sebelum `130edd30` masih `due_date = NULL` di DB → WA reminder task
(`send_manual_debt_reminders_task`) memfilter `due_date IS NOT NULL` → tidak dapat reminder.

**Fix:** Migration `20260319_c_populate_null_due_dates`:
```sql
UPDATE user_quota_debts
SET due_date = (
    date_trunc('month', COALESCE(debt_date, created_at::date))
    + interval '1 month' - interval '1 day'
)::date
WHERE due_date IS NULL
```

**Frontend fallback (belt-and-suspenders):**
`getEffectiveDueDate(debt_date, due_date)` di `UserDebtLedgerDialog.vue` dan `riwayat/index.vue`
menghitung hari terakhir bulan dari `debt_date` jika `due_date` masih null.

---

### 2. Harga Estimasi vs Aktual

**Root cause:** `UserQuotaDebt` model tidak punya kolom harga. Rute admin menghitung
`estimated_rp` dari paket termurah (tidak selalu cocok dengan paket yang dipilih).

**Fix:** Migration `20260319_add_price_rp_to_user_quota_debts` menambah `price_rp BIGINT NULLABLE`.
`add_manual_debt()` menerima `price_rp: Optional[int] = None` dan menyimpannya.
`user_profile_service.py` meneruskan `price_rp=int(pkg.price)`.

Response schema `UserQuotaDebtItemResponseSchema` tambah `price_rp: Optional[int] = None`.
Frontend: `price_rp ?? estimated_rp` di kolom Harga.

---

### 3. Paket Unlimited Tidak Muncul

**Root cause:** Dua lapis filter memblokir unlimited:
- **Backend:** `if pkg_quota_gb <= 0: return False, "Paket debt harus memiliki kuota..."` di `user_profile_service.py`
- **Frontend:** `filter(pkg => pkg.data_quota_gb > 0)` di `debtPackageOptions`

**Fix:**
- Backend: hapus guard; untuk unlimited, gunakan sentinel `amount_mb = 1` agar
  `enforce_end_of_month_debt_block_task` tetap mendeteksi (`manual_debt_mb > 0`).
- `pkg_quota_str = "Unlimited" if pkg_quota_gb <= 0 else f"{pkg_quota_gb:g} GB"` untuk note.
- Frontend: hapus filter `data_quota_gb > 0`; label dropdown "Unlimited" jika `data_quota_gb === 0`.

**Catatan penting:** `enforce_end_of_month_debt_block_task` tidak menggunakan `due_date` per-item —
ia hanya cek `manual_debt_mb > 0` dan tanggal kalender. Sentinel `amount_mb = 1` cukup untuk
trigger blocking. WA reminder task membutuhkan `due_date IS NOT NULL` (sudah diisi oleh migration).

---

### 4. Nama Paket di Kolom Paket/Info

**Root cause:** Note disimpan sebagai `"Paket: Nama Paket (20 GB, Rp 200.000)"`. Kolom
menampilkan full string.

**Fix:** `parsePackageName(note)`:
```typescript
function parsePackageName(note: string | null | undefined): string | null {
  if (!note) return null
  const prefix = 'Paket: '
  if (!note.startsWith(prefix)) return note
  const rest = note.slice(prefix.length)
  const parenIdx = rest.indexOf(' (')
  return parenIdx > 0 ? rest.slice(0, parenIdx) : rest
}
```

---

## Perubahan File

### Backend

| File | Perubahan |
|------|-----------|
| `migrations/versions/20260319_add_price_rp_to_user_quota_debts.py` | Tambah kolom `price_rp BIGINT NULLABLE` |
| `migrations/versions/20260319_c_populate_null_due_dates.py` | Fill `due_date` NULL dari `debt_date`/`created_at` |
| `app/infrastructure/db/models.py` | `UserQuotaDebt.price_rp: Mapped[Optional[int]]` |
| `app/services/user_management/user_debt.py` | `add_manual_debt(price_rp=None)` param + store |
| `app/services/user_management/user_profile.py` | Hapus guard unlimited; auto-compute `due_date`; pass `price_rp` |
| `app/infrastructure/http/schemas/user_schemas.py` | Hapus `debt_due_date` dari request; tambah `price_rp` ke response |

### Frontend

| File | Perubahan |
|------|-----------|
| `components/admin/users/UserDebtLedgerDialog.vue` | `ManualDebtItem` tambah `debt_date`+`price_rp`; `parsePackageName`; `getEffectiveDueDate`; padding tombol Lunasi |
| `components/admin/users/UserEditDialog.vue` | Hapus `debt_due_date` form; VAlert "akhir bulan otomatis"; hapus filter `data_quota_gb > 0` di dropdown; label Unlimited |
| `pages/riwayat/index.vue` | `getEffectiveDueDate` fallback; kolom Jatuh Tempo dengan chip |

### Test

| File | Perubahan |
|------|-----------|
| `tests/test_user_quota_debt_item_response_schema.py` | Assert `price_rp is None` + `due_date is None` |

---

## Logika EOM Block & WA Reminder

```
EOM Block Task (enforce_end_of_month_debt_block_task):
  → Cek user.manual_debt_mb > 0 (tidak peduli due_date per-item)
  → Block saat hari terakhir bulan, setelah DEBT_EOM_BLOCK_MIN_HOUR
  → Paket unlimited: sentinel amount_mb=1 → manual_debt_mb += 1 → task mendeteksi

WA Reminder Task (send_manual_debt_reminders_task):
  → Filter: is_paid=False AND due_date IS NOT NULL
  → Kirim 3 hari, 1 hari, 3 jam sebelum due_date
  → Record lama: kini terisi via migration → reminder berjalan
```

---

## Deploy & Verifikasi

| Commit | SHA | Alembic Output |
|--------|-----|----------------|
| Debt UX overhaul #1 | `ee2f67a6` | Tidak ada migration baru |
| Debt harga+akhir bulan+unlimited | `130edd30` | `Running upgrade ... -> 20260319_add_price_rp_to_user_quota_debts` |
| Fill due_date + fallback | `c36e9310` | `Running upgrade ... -> 20260319_c_populate_null_due_dates` |
| Button padding style | `e6358ee3` | `CURRENT_REV=20260319_c_populate_null_due_dates` (up-to-date) |

> **INSIDEN:** Tiga deploy pertama menggunakan image lama karena commit belum di-push ke
> `origin/main` sebelum `--trigger-build`. Lihat
> [`docs/incidents/2026-03-19-deploy-unpushed-commits.md`](../incidents/2026-03-19-deploy-unpushed-commits.md).

---

## Status Akhir

- `CURRENT_REV=20260319_c_populate_null_due_dates` — DB up-to-date
- Semua container healthy post `e6358ee3`
- WA reminder akan menjangkau semua record tunggakan yang lama
- Paket unlimited dapat dipilih (jika ada di DB dengan `data_quota_gb = 0`)
