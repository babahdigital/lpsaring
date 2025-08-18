// frontend/utils/formatters.ts
// VERSI SINKRON DENGAN backend/app/utils/formatters.py

/**
 * Menormalisasi berbagai format nomor telepon Indonesia ke format E.164 (+62).
 * Logika ini diselaraskan sepenuhnya dengan backend.
 * @param {string} phoneNumber - Nomor telepon dalam format 08, 628, atau 8.
 * @returns {string} Nomor telepon dalam format E.164.
 * @throws {Error} Jika format atau panjang nomor telepon tidak valid.
 */
export function normalize_to_e164(phoneNumber: string): string {
  if (!phoneNumber || typeof phoneNumber !== 'string') {
    throw new Error('Nomor telepon tidak boleh kosong.')
  }

  // Hapus semua karakter non-digit, sama seperti re.sub(r'[^\d]', '', ...) di Python.
  const cleaned = phoneNumber.replace(/\D/g, '')
  if (!cleaned) {
    throw new Error('Nomor telepon tidak boleh kosong.')
  }

  let e164_number = ''
  if (cleaned.startsWith('0')) {
    e164_number = `+62${cleaned.substring(1)}`
  }
  else if (cleaned.startsWith('62')) {
    e164_number = `+${cleaned}`
  }
  else if (cleaned.startsWith('8')) {
    e164_number = `+62${cleaned}`
  }
  else {
    throw new Error(`Format awalan nomor telepon '${phoneNumber}' tidak valid. Gunakan awalan 08, 628, atau 8.`)
  }

  if (e164_number.length < 12 || e164_number.length > 14) {
    throw new Error('Panjang nomor telepon tidak valid. Harus antara 10-12 digit untuk format lokal (misal: 08xx).')
  }

  if (!/^\+628[1-9]\d{7,9}$/.test(e164_number)) {
    throw new Error(`Nomor telepon '${phoneNumber}' memiliki format yang tidak valid.`)
  }

  return e164_number
}

/**
 * Mengubah format E.164 (+62) atau format lain menjadi format lokal (08).
 * Logika ini diselaraskan sepenuhnya dengan backend.
 * @param {string | null | undefined} phoneNumber - Nomor telepon yang akan diubah.
 * @returns {string | null} Nomor telepon dalam format lokal atau null jika input tidak valid.
 */
export function format_to_local_phone(phoneNumber: string | null | undefined): string | null {
  if (!phoneNumber) {
    return null
  }

  try {
    const cleaned = String(phoneNumber).replace(/\D/g, '')

    if (cleaned.startsWith('62')) {
      return `0${cleaned.substring(2)}`
    }
    else if (cleaned.startsWith('8')) {
      return `0${cleaned}`
    }
    else if (cleaned.startsWith('0')) {
      return cleaned
    }
    else {
      // Untuk format lain (misal: nomor asing), kembalikan nomor yang sudah bersih
      return cleaned
    }
  }
  catch {
    return null
  }
}

/**
 * Memformat nomor telepon agar sesuai untuk tautan WhatsApp (wa.me).
 * Fungsi frontend-spesifik, tidak ada di backend.
 * @param {string | null | undefined} phoneNumber - Nomor telepon, idealnya dalam format lokal atau E.164.
 * @returns {string} Nomor telepon dalam format numerik untuk URL WhatsApp (misal: 62812...).
 */
export function format_for_whatsapp_link(phoneNumber: string | null | undefined): string {
  if (!phoneNumber) {
    return ''
  }

  try {
    const e164_number = normalize_to_e164(phoneNumber)
    // Hapus karakter '+' dari hasil normalisasi
    return e164_number.substring(1)
  }
  catch {
    // Fallback jika normalisasi gagal: bersihkan dan coba konversi manual
    const cleaned = String(phoneNumber).replace(/\D/g, '')
    if (cleaned.startsWith('0')) {
      return `62${cleaned.substring(1)}`
    }
    // Jika sudah dalam format 62 atau format tidak dikenal, kembalikan saja
    return cleaned
  }
}
