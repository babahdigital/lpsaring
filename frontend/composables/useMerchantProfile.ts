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

  const supportWhatsAppFormatted = computed(() => supportWhatsAppRaw.value.replace(/[^0-9+]/g, ''))

  const supportWhatsAppHref = computed(() => {
    const raw = supportWhatsAppFormatted.value
    if (raw === '')
      return null

    const base = String(runtimeConfig.public.whatsappBaseUrl ?? 'https://wa.me').replace(/\/$/, '')
    const phonePath = raw.replace(/^\+/, '')

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
