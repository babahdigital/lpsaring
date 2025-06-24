// server/api/validate-whatsapp.post.ts

// Fungsi untuk mengubah format nomor dari 08... ke 628...
function normalizeTo62(phone: string): string {
  const cleaned = phone.replace(/[\s-]/g, '')
  if (cleaned.startsWith('08'))
    return `62${cleaned.substring(1)}`

  if (cleaned.startsWith('+62'))
    return cleaned.substring(1)

  return cleaned
}

export default defineEventHandler(async (event) => {
  const config = useRuntimeConfig(event)
  const fonnteToken = config.fonnteToken

  // [PERBAIKAN] Pengecekan eksplisit untuk string kosong atau null/undefined.
  if (!fonnteToken || fonnteToken.length === 0) {
    throw createError({
      statusCode: 500,
      statusMessage: 'Konfigurasi server tidak lengkap: Token Fonnte tidak ditemukan.',
    })
  }

  const body = await readBody(event)
  const phoneNumber = body.phoneNumber as string

  // [PERBAIKAN] Pengecekan eksplisit untuk string kosong atau null/undefined.
  if (!phoneNumber || phoneNumber.length === 0) {
    throw createError({
      statusCode: 400,
      statusMessage: 'Nomor telepon wajib diisi.',
    })
  }

  try {
    const fonnteResponse = await $fetch<{
      status: boolean
      registered: string[]
      not_registered: string[]
      reason?: string
    }>('https://api.fonnte.com/validate', {
      method: 'POST',
      headers: {
        Authorization: fonnteToken,
      },
      body: {
        target: phoneNumber,
        countryCode: '62',
      },
    })

    if (fonnteResponse.status === true) {
      const normalizedNumber = normalizeTo62(phoneNumber)
      const isRegistered = fonnteResponse.registered.includes(normalizedNumber)

      return {
        isValid: isRegistered,
        message: isRegistered ? 'Nomor valid.' : 'Nomor WhatsApp tidak terdaftar.',
      }
    }
    else {
      // [PERBAIKAN] Menggunakan operator '??' untuk menangani nilai null/undefined.
      return {
        isValid: false,
        message: `Validasi gagal: ${fonnteResponse.reason ?? 'kesalahan tidak diketahui'}.`,
      }
    }
  }
  catch (error: any) {
    // Menangani error dari $fetch atau API Fonnte
    throw createError({
      // [PERBAIKAN] Menggunakan operator '??' untuk menangani nilai null/undefined.
      statusCode: error.statusCode ?? 500,
      // [PERBAIKAN] Menggunakan operator '??' untuk menangani nilai null/undefined.
      statusMessage: `Gagal menghubungi layanan validasi. ${error.statusMessage ?? ''}`,
    })
  }
})
