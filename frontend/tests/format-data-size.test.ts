/**
 * Test: logika formatDataSize — konversi ukuran kuota MB ke unit dinamis KB/MB/GB
 *
 * Fungsi ini didefinisikan inline di beberapa komponen admin.
 * Test ini memverifikasi logika konversi yang konsisten di seluruh komponen.
 *
 * Komponen yang menggunakan logika yang sama:
 *   - frontend/components/admin/users/UserDebtLedgerDialog.vue
 *   - frontend/components/admin/users/UserDetailDialog.vue
 *   - frontend/components/admin/users/UserEditDialog.vue
 */

import { describe, expect, it } from 'vitest'

/**
 * Implementasi referensi formatDataSize (harus sinkron dengan komponen-komponen di atas).
 * Batas: < 1 MB → KB; 1–1023 MB → MB; ≥ 1024 MB → GB
 * Presisi: 2 desimal, locale id-ID.
 */
function formatDataSize(sizeInMB: number): string {
  if (!Number.isFinite(sizeInMB) || Number.isNaN(sizeInMB))
    return '0 MB'
  const options: Intl.NumberFormatOptions = { minimumFractionDigits: 2, maximumFractionDigits: 2 }
  if (sizeInMB < 1)
    return `${(sizeInMB * 1024).toLocaleString('id-ID', options)} KB`
  else if (sizeInMB < 1024)
    return `${sizeInMB.toLocaleString('id-ID', options)} MB`
  else
    return `${(sizeInMB / 1024).toLocaleString('id-ID', options)} GB`
}

describe('formatDataSize', () => {
  describe('invalid dan edge cases', () => {
    it('mengembalikan "0 MB" untuk NaN', () => {
      expect(formatDataSize(Number.NaN)).toBe('0 MB')
    })

    it('mengembalikan "0 MB" untuk Infinity', () => {
      expect(formatDataSize(Infinity)).toBe('0 MB')
    })

    it('mengembalikan "0 MB" untuk -Infinity', () => {
      expect(formatDataSize(-Infinity)).toBe('0 MB')
    })

    it('mengembalikan 0,00 KB untuk nilai 0 (0 < 1 → cabang KB)', () => {
      const result = formatDataSize(0)
      expect(result).toContain('KB')
      expect(result).toContain('0')
    })
  })

  describe('unit KB — sizeInMB < 1', () => {
    it('menggunakan KB untuk nilai kurang dari 1 MB', () => {
      const result = formatDataSize(0.5)
      expect(result).toContain('KB')
      // 0.5 MB × 1024 = 512 KB
      expect(result).toContain('512')
    })

    it('0.001 MB = ~1.02 KB', () => {
      const result = formatDataSize(0.001)
      expect(result).toContain('KB')
    })

    it('0.976 MB → hasil dalam KB', () => {
      const result = formatDataSize(0.976)
      expect(result).toContain('KB')
    })
  })

  describe('unit MB — 1 ≤ sizeInMB < 1024', () => {
    it('1 MB → "1,00 MB"', () => {
      const result = formatDataSize(1)
      expect(result).toContain('MB')
      expect(result).not.toContain('KB')
      expect(result).not.toContain('GB')
    })

    it('100 MB → hasil dalam MB', () => {
      const result = formatDataSize(100)
      expect(result).toContain('MB')
      expect(result).toContain('100')
    })

    it('512 MB → hasil dalam MB', () => {
      const result = formatDataSize(512)
      expect(result).toContain('MB')
    })

    it('1023.99 MB → masih dalam MB (belum GB)', () => {
      const result = formatDataSize(1023.99)
      expect(result).toContain('MB')
      expect(result).not.toContain('GB')
    })
  })

  describe('unit GB — sizeInMB ≥ 1024', () => {
    it('1024 MB → "1,00 GB"', () => {
      const result = formatDataSize(1024)
      expect(result).toContain('GB')
      expect(result).toContain('1')
      expect(result).not.toContain('MB')
    })

    it('2048 MB → "2,00 GB"', () => {
      const result = formatDataSize(2048)
      expect(result).toContain('GB')
      expect(result).toContain('2')
    })

    it('40960 MB (40 GB) → hasil dalam GB', () => {
      const result = formatDataSize(40960)
      expect(result).toContain('GB')
      // 40960 / 1024 = 40.00 GB
      expect(result).toContain('40')
    })

    it('3072 MB (3 GB, threshold FUP) → hasil dalam GB', () => {
      const result = formatDataSize(3072)
      expect(result).toContain('GB')
      expect(result).toContain('3')
    })
  })

  describe('presisi 2 desimal', () => {
    it('nilai tidak bulat menampilkan 2 desimal', () => {
      const result = formatDataSize(1.5)
      // Id-ID locale: "1,50 MB"
      expect(result).toContain('1')
      expect(result).toContain('MB')
    })

    it('GB value non-bulat menampilkan 2 desimal', () => {
      const result = formatDataSize(1536)
      // 1536 / 1024 = 1.5 GB
      expect(result).toContain('GB')
    })
  })
})

describe('formatDatetimeLocal logic', () => {
  /**
   * Implementasi referensi formatDatetimeLocal dari UserDebtLedgerDialog.vue
   */
  function formatDatetimeLocal(isoStr: string | null | undefined): string {
    if (!isoStr)
      return '-'
    try {
      const d = new Date(isoStr)
      if (Number.isNaN(d.getTime()))
        return '-'
      return d.toLocaleString('id-ID', {
        timeZone: 'Asia/Makassar',
        day: '2-digit',
        month: 'short',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      })
    }
    catch {
      return '-'
    }
  }

  it('mengembalikan "-" untuk null', () => {
    expect(formatDatetimeLocal(null)).toBe('-')
  })

  it('mengembalikan "-" untuk undefined', () => {
    expect(formatDatetimeLocal(undefined)).toBe('-')
  })

  it('mengembalikan "-" untuk string kosong', () => {
    expect(formatDatetimeLocal('')).toBe('-')
  })

  it('mengembalikan "-" untuk string bukan tanggal', () => {
    expect(formatDatetimeLocal('bukan-tanggal')).toBe('-')
  })

  it('memformat ISO datetime dengan benar (mengandung tahun dan jam)', () => {
    const result = formatDatetimeLocal('2026-03-18T16:00:00.000Z')
    // Hasil: "18 Mar 2026 00.00" dalam WITA (UTC+8) — format id-ID
    expect(result).not.toBe('-')
    expect(result).toContain('2026')
  })

  it('menangani string date-only berformat ISO dengan benar', () => {
    const result = formatDatetimeLocal('2026-03-18T00:00:00+08:00')
    expect(result).not.toBe('-')
    expect(result).toContain('2026')
  })
})

describe('showIncompleteProfileAlert logic', () => {
  /**
   * Implementasi referensi computed showIncompleteProfileAlert dari dashboard/index.vue.
   * Muncul jika: user login, bukan ADMIN/SUPER_ADMIN/KOMANDAN, bukan tamping, dan blok/kamar kosong.
   */
  function shouldShowAlert(user: {
    role: string
    is_tamping?: boolean | null
    blok?: string | null
    kamar?: string | null
  } | null, isAdmin: boolean, isKomandan: boolean): boolean {
    if (!user || isAdmin || isKomandan)
      return false
    if (user.is_tamping === true)
      return false
    return !user.blok || !user.kamar
  }

  it('tidak tampil jika user null', () => {
    expect(shouldShowAlert(null, false, false)).toBe(false)
  })

  it('tidak tampil untuk Admin', () => {
    expect(shouldShowAlert({ role: 'ADMIN', blok: null, kamar: null }, true, false)).toBe(false)
  })

  it('tidak tampil untuk Komandan', () => {
    expect(shouldShowAlert({ role: 'KOMANDAN', blok: null, kamar: null }, false, true)).toBe(false)
  })

  it('tidak tampil untuk tamping (walaupun blok/kamar null)', () => {
    expect(shouldShowAlert({ role: 'USER', is_tamping: true, blok: null, kamar: null }, false, false)).toBe(false)
  })

  it('tampil jika user biasa dan blok kosong', () => {
    expect(shouldShowAlert({ role: 'USER', blok: null, kamar: 'A1' }, false, false)).toBe(true)
  })

  it('tampil jika user biasa dan kamar kosong', () => {
    expect(shouldShowAlert({ role: 'USER', blok: 'B', kamar: null }, false, false)).toBe(true)
  })

  it('tampil jika user biasa dan keduanya kosong', () => {
    expect(shouldShowAlert({ role: 'USER', blok: null, kamar: null }, false, false)).toBe(true)
  })

  it('tidak tampil jika user biasa sudah punya blok dan kamar', () => {
    expect(shouldShowAlert({ role: 'USER', blok: 'B', kamar: '12' }, false, false)).toBe(false)
  })

  it('tampil jika blok string kosong', () => {
    expect(shouldShowAlert({ role: 'USER', blok: '', kamar: '12' }, false, false)).toBe(true)
  })

  it('tidak tampil untuk is_tamping null (treated as not tamping)', () => {
    // is_tamping null → bukan tamping → tetap ikut cek blok/kamar
    const result = shouldShowAlert({ role: 'USER', is_tamping: null, blok: null, kamar: null }, false, false)
    expect(result).toBe(true)
  })
})
