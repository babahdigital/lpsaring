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

type DateInput = string | number | Date | null | undefined

const MONTH_SHORT_ID = ['Jan', 'Feb', 'Mar', 'Apr', 'Mei', 'Jun', 'Jul', 'Agu', 'Sep', 'Okt', 'Nov', 'Des'] as const
const MONTH_LONG_ID = ['Januari', 'Februari', 'Maret', 'April', 'Mei', 'Juni', 'Juli', 'Agustus', 'September', 'Oktober', 'November', 'Desember'] as const

function groupThousandsId(value: string): string {
  return value.replace(/\B(?=(\d{3})+(?!\d))/g, '.')
}

function getOffsetDateParts(input: DateInput, offsetHours: number) {
  const parsed = input instanceof Date ? new Date(input.getTime()) : new Date(input as string | number)
  if (Number.isNaN(parsed.getTime()))
    return null

  const shifted = new Date(parsed.getTime() + (offsetHours * 60 * 60 * 1000))

  return {
    day: shifted.getUTCDate(),
    month: shifted.getUTCMonth(),
    year: shifted.getUTCFullYear(),
    hours: shifted.getUTCHours(),
    minutes: shifted.getUTCMinutes(),
    seconds: shifted.getUTCSeconds(),
  }
}

function pad2(value: number): string {
  return value.toString().padStart(2, '0')
}

export function formatNumberId(value: number | null | undefined, maximumFractionDigits = 0, minimumFractionDigits = 0): string {
  const parsed = Number(value ?? 0)
  if (!Number.isFinite(parsed))
    return '0'

  const decimals = Math.max(0, Math.min(20, maximumFractionDigits))
  const minDecimals = Math.max(0, Math.min(decimals, minimumFractionDigits))
  const sign = parsed < 0 ? '-' : ''
  const fixed = Math.abs(parsed).toFixed(decimals)
  const [integerRaw, fractionRaw = ''] = fixed.split('.')
  const groupedInteger = groupThousandsId(integerRaw)

  if (decimals === 0)
    return `${sign}${groupedInteger}`

  const fractionTrimmed = fractionRaw.replace(/0+$/, '')
  const fractionPadded = fractionTrimmed.padEnd(minDecimals, '0')
  return fractionPadded.length > 0
    ? `${sign}${groupedInteger},${fractionPadded}`
    : `${sign}${groupedInteger}`
}

export function formatCurrencyIdr(value: number | null | undefined): string {
  return `Rp${formatNumberId(value, 0, 0)}`
}

export function formatDateMediumId(input: DateInput, offsetHours = 7): string {
  const parts = getOffsetDateParts(input, offsetHours)
  if (!parts)
    return '-'
  return `${pad2(parts.day)} ${MONTH_SHORT_ID[parts.month]} ${parts.year}`
}

export function formatDateLongId(input: DateInput, offsetHours = 7): string {
  const parts = getOffsetDateParts(input, offsetHours)
  if (!parts)
    return '-'
  return `${pad2(parts.day)} ${MONTH_LONG_ID[parts.month]} ${parts.year}`
}

export function formatDateTimeShortNumericId(input: DateInput, offsetHours = 7): string {
  const parts = getOffsetDateParts(input, offsetHours)
  if (!parts)
    return '-'
  const year2 = parts.year.toString().slice(-2)
  return `${pad2(parts.day)}/${pad2(parts.month + 1)}/${year2} ${pad2(parts.hours)}:${pad2(parts.minutes)}`
}

export function formatDateTimeShortMonthId(input: DateInput, offsetHours = 7): string {
  const parts = getOffsetDateParts(input, offsetHours)
  if (!parts)
    return '-'
  return `${pad2(parts.day)} ${MONTH_SHORT_ID[parts.month]} ${parts.year} ${pad2(parts.hours)}:${pad2(parts.minutes)}`
}

export function formatDateTimeMakassarId(input: DateInput): string {
  const parts = getOffsetDateParts(input, 8)
  if (!parts)
    return '-'
  return `${pad2(parts.day)} ${MONTH_SHORT_ID[parts.month]} ${parts.year} ${pad2(parts.hours)}:${pad2(parts.minutes)}:${pad2(parts.seconds)} WITA`
}
