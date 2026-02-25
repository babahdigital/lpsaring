export function useMerchantProfile() {
  const runtimeConfig = useRuntimeConfig()

  const merchantName = computed(() => String(runtimeConfig.public.merchantName ?? 'Babah Digital').trim() || 'Babah Digital')
  const merchantBusinessType = computed(() => String(
    runtimeConfig.public.merchantBusinessType ?? 'Jasa Telekomunikasi / ISP (Produk Digital)',
  ).trim() || 'Jasa Telekomunikasi / ISP (Produk Digital)')
  const merchantAddress = computed(() => String(runtimeConfig.public.merchantAddress ?? '').trim())
  const supportEmail = computed(() => String(runtimeConfig.public.merchantSupportEmail ?? '').trim())

  const supportWhatsAppRaw = computed(() => {
    const primary = String(runtimeConfig.public.merchantSupportWhatsapp ?? '').trim()
    if (primary)
      return primary

    return String(runtimeConfig.public.adminWhatsapp ?? '').trim()
  })

  const supportWhatsAppSanitized = computed(() => supportWhatsAppRaw.value.replace(/[^0-9+]/g, ''))

  const supportWhatsAppFormatted = computed(() => {
    const raw = supportWhatsAppSanitized.value
    if (!raw)
      return ''

    if (raw.startsWith('+62'))
      return `0${raw.slice(3)}`

    if (raw.startsWith('62'))
      return `0${raw.slice(2)}`

    return raw
  })

  const supportWhatsAppHref = computed(() => {
    const raw = supportWhatsAppSanitized.value
    if (raw === '')
      return null

    const base = String(runtimeConfig.public.whatsappBaseUrl ?? 'https://wa.me').replace(/\/$/, '')
    const plain = raw.replace(/^\+/, '')
    const phonePath = plain.startsWith('0') ? `62${plain.slice(1)}` : plain

    return `${base}/${phonePath}`
  })

  return {
    merchantName,
    merchantBusinessType,
    merchantAddress,
    supportEmail,
    supportWhatsAppFormatted,
    supportWhatsAppHref,
  }
}
