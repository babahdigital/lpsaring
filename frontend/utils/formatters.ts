// frontend/utils/formatters.ts
// Ini adalah versi JavaScript/TypeScript dari fungsi yang ada di backend/app/utils/formatters.py

/**
 * Menormalisasi nomor telepon ke format E.164.
 * Fungsi ini sengaja dibuat untuk mereplikasi logika di backend.
 * Dukungan:
 * - Indonesia (legacy): 08xxx, 628xxx, +628xxx, 8xxx -> +628xxx
 * - Internasional: +<digits> (mis. +675...) -> dipertahankan
 *
 * Batasan panjang:
 * - E.164 generic: 8-14 digit (tanpa '+')
 * @param {string | null | undefined} phoneNumber - Nomor telepon dalam format lokal (misal: 0812..., 62812...).
 * @returns {string} Nomor telepon dalam format E.164.
 * @throws {Error} Jika format nomor telepon tidak valid.
 */
export function normalize_to_e164(phoneNumber: string | null | undefined): string {
  // PERBAIKAN: Mengganti !phoneNumber dengan pengecekan null/undefined yang eksplisit
  if (phoneNumber == null || typeof phoneNumber !== 'string') {
    throw new Error('Nomor telepon tidak boleh kosong.')
  }

  const raw = phoneNumber.trim()
  const cleaned = raw.replace(/[\s\-()]/g, '').trim()
  // PERBAIKAN: Mengganti !cleaned dengan pengecekan string kosong yang eksplisit
  if (cleaned === '') {
    throw new Error('Nomor telepon tidak boleh kosong.')
  }

  // Generic E.164: +[1-9]\d{7,14} (E.164 max 15 digits)
  if (cleaned.startsWith('+')) {
    const digits = cleaned.replace(/[^\d]/g, '')
    const e164 = `+${digits}`
    if (!/^\+[1-9]\d{7,14}$/.test(e164))
      throw new Error('Format nomor telepon internasional tidak valid. Gunakan format +<kodeNegara><nomor>.')
    return e164
  }

  // Prefix internasional umum: 00<cc><number> -> +<cc><number>
  if (cleaned.startsWith('00') && cleaned.length > 2) {
    const digits = cleaned.replace(/[^\d]/g, '').slice(2)
    const e164 = `+${digits}`
    if (!/^\+[1-9]\d{7,14}$/.test(e164))
      throw new Error('Format nomor telepon internasional tidak valid. Gunakan format +<kodeNegara><nomor>.')
    return e164
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
    // Jika bukan pola Indonesia, anggap input sudah mengandung country code tanpa '+' (mis. 675..., 44..., dll)
    const digits = cleaned.replace(/[^\d]/g, '')
    const e164 = `+${digits}`
    if (/^\+[1-9]\d{7,14}$/.test(e164))
      return e164
    throw new Error(`Format awalan nomor telepon '${phoneNumber}' tidak valid. Gunakan awalan 08, 628, +628, atau format internasional +<kodeNegara>...`)
  }

  // Validasi Indonesia: setelah +628, harus ada 8-12 digit lagi (lebih longgar untuk variasi panjang)
  if (!/^\+628[1-9]\d{7,11}$/.test(e164_number))
    throw new Error(`Nomor telepon '${phoneNumber}' memiliki format yang tidak valid.`)

  return e164_number
}

export function format_to_local_phone(phoneNumber: string | null | undefined): string {
  if (!phoneNumber)
    return ''

  const cleaned = phoneNumber.replace(/[\s\-()+]/g, '')
  if (cleaned.startsWith('628'))
    return `0${cleaned.substring(2)}`
  if (cleaned.startsWith('8'))
    return `0${cleaned}`
  return cleaned
}

export function format_for_whatsapp_link(phoneNumber: string | null | undefined): string {
  if (!phoneNumber)
    return ''
  const cleaned = phoneNumber.replace(/[\s\-()]/g, '').trim()
  if (cleaned.startsWith('+'))
    return cleaned.substring(1).replace(/[^\d]/g, '')
  const digits = cleaned.replace(/[^\d]/g, '')
  if (digits.startsWith('0'))
    return `62${digits.substring(1)}`
  if (digits.startsWith('62'))
    return digits
  // Jika user sudah memasukkan country code selain 62 tanpa '+', biarkan apa adanya.
  return digits
}
