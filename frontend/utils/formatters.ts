// frontend/utils/formatters.ts
// Ini adalah versi JavaScript/TypeScript dari fungsi yang ada di backend/app/utils/formatters.py

/**
 * Menormalisasi berbagai format nomor telepon Indonesia ke format E.164 (+62).
 * Fungsi ini sengaja dibuat untuk mereplikasi logika di backend.
 * Aturan validasi: Nomor lokal (08xx) harus 10-12 digit.
 * @param {string | null | undefined} phoneNumber - Nomor telepon dalam format lokal (misal: 0812..., 62812...).
 * @returns {string} Nomor telepon dalam format E.164.
 * @throws {Error} Jika format nomor telepon tidak valid.
 */
export function normalize_to_e164(phoneNumber: string | null | undefined): string {
  if (!phoneNumber || typeof phoneNumber !== 'string') {
    throw new Error('Nomor telepon tidak boleh kosong.')
  }

  const cleaned = phoneNumber.replace(/[\s\-()+]/g, '').trim()
  if (!cleaned) {
    throw new Error('Nomor telepon tidak boleh kosong.')
  }

  let e164_number = ''
  if (cleaned.startsWith('08')) {
    e164_number = `+62${cleaned.substring(1)}`
  }
  else if (cleaned.startsWith('628')) {
    e164_number = `+${cleaned}`
  }
  else if (cleaned.startsWith('+628')) {
    e164_number = cleaned
  }
  else if (cleaned.startsWith('8') && cleaned.length >= 9) {
    e164_number = `+62${cleaned}`
  }
  else {
    throw new Error(`Format awalan nomor telepon '${phoneNumber}' tidak valid. Gunakan awalan 08, 628, atau +628.`)
  }

  // Aturan baru: panjang total nomor lokal 10-12 digit, berarti E.164 adalah 12-14 digit.
  if (e164_number.length < 12 || e164_number.length > 14) {
    throw new Error(`Panjang nomor telepon tidak valid. Harus antara 10-12 digit untuk format lokal (misal: 08xx).`)
  }

  // Regex baru: setelah +628, harus ada 8-10 digit lagi.
  if (!/^\+628[1-9]\d{7,9}$/.test(e164_number)) {
    throw new Error(`Nomor telepon '${phoneNumber}' memiliki format yang tidak valid.`)
  }

  return e164_number
}
