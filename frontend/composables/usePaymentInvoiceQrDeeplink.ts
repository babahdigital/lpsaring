import type { ComputedRef } from 'vue'
import { computed, ref } from 'vue'
import type { TransactionDetailResponseContract, TransactionStatusContract } from '~/types/api/contracts'

interface UsePaymentInvoiceQrDeeplinkOptions {
  apiBaseUrl: ComputedRef<string>
  orderId: ComputedRef<string | null>
  statusToken: ComputedRef<string | null>
  finalStatus: ComputedRef<TransactionStatusContract>
  isPublicView: ComputedRef<boolean>
  isMobile: ComputedRef<boolean>
  transactionDetails: ComputedRef<TransactionDetailResponseContract | null>
  paymentMethod: ComputedRef<string | null>
  apiFetch: <T>(path: string, options?: Record<string, unknown>) => Promise<T>
  notify: (payload: { type: 'error' | 'warning' | 'info' | 'success'; title: string; text: string }) => void
  runtimePublicConfig: Record<string, unknown>
}

export function usePaymentInvoiceQrDeeplink(options: UsePaymentInvoiceQrDeeplinkOptions) {
  const {
    apiBaseUrl,
    orderId,
    statusToken,
    finalStatus,
    isPublicView,
    isMobile,
    transactionDetails,
    paymentMethod,
    apiFetch,
    notify,
    runtimePublicConfig,
  } = options

  const isDownloadingInvoice = ref(false)

  const invoicePath = computed(() => {
    if (!orderId.value)
      return ''
    return `/transactions/${orderId.value}/invoice`
  })

  const invoiceDownloadUrl = computed(() => {
    if (invoicePath.value === '')
      return ''
    return `${apiBaseUrl.value}${invoicePath.value}`
  })

  const canDownloadInvoice = computed(() => !isPublicView.value && finalStatus.value === 'SUCCESS' && invoicePath.value !== '')

  async function downloadInvoice() {
    if (invoicePath.value === '' || isDownloadingInvoice.value)
      return

    isDownloadingInvoice.value = true
    try {
      const blob = await apiFetch<Blob>(invoicePath.value, {
        method: 'GET',
        responseType: 'blob',
      })
      if (blob == null || blob.size === 0)
        throw new Error('Gagal menerima data file dari server (blob kosong).')

      const objectUrl = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = objectUrl
      link.download = `invoice-${orderId.value ?? 'transaksi'}.pdf`
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
      URL.revokeObjectURL(objectUrl)
      notify({ type: 'success', title: 'Berhasil', text: 'Invoice berhasil diunduh.' })
    }
    catch (err: any) {
      const message = err?.data?.message ?? err?.message ?? 'Gagal mengunduh invoice.'
      notify({ type: 'error', title: 'Gagal', text: message })
    }
    finally {
      isDownloadingInvoice.value = false
    }
  }

  const qrDownloadUrl = computed(() => {
    if (!orderId.value)
      return ''
    if (statusToken.value)
      return `${apiBaseUrl.value}/transactions/public/${encodeURIComponent(orderId.value)}/qr?t=${encodeURIComponent(statusToken.value)}&download=1`
    return `${apiBaseUrl.value}/transactions/${encodeURIComponent(orderId.value)}/qr?download=1`
  })

  const qrViewUrl = computed(() => {
    if (!orderId.value)
      return ''
    if (statusToken.value)
      return `${apiBaseUrl.value}/transactions/public/${encodeURIComponent(orderId.value)}/qr?t=${encodeURIComponent(statusToken.value)}`
    return `${apiBaseUrl.value}/transactions/${encodeURIComponent(orderId.value)}/qr`
  })

  const qrValue = computed(() => transactionDetails.value?.qr_code_url ?? '')
  const showQrCode = computed(() => {
    if (finalStatus.value !== 'PENDING' || qrValue.value === '')
      return false
    if (transactionDetails.value?.va_number)
      return false
    if (transactionDetails.value?.payment_code && transactionDetails.value?.biller_code)
      return false
    return true
  })

  const qrSize = computed(() => (isMobile.value ? 220 : 280))

  const appDeeplinkUrl = computed(() => {
    const url = transactionDetails.value?.deeplink_redirect_url
    return (typeof url === 'string' && url.trim() !== '') ? url.trim() : null
  })

  const deeplinkAppName = computed(() => {
    const pm = String(paymentMethod.value ?? '').trim().toLowerCase()
    if (pm === 'gopay')
      return 'GoPay'
    if (pm === 'shopeepay')
      return 'ShopeePay'
    return null
  })

  const showAppDeeplinkButton = computed(() => {
    if (finalStatus.value !== 'PENDING')
      return false
    return appDeeplinkUrl.value != null && deeplinkAppName.value != null
  })

  const showAppInstructions = computed(() => {
    if (finalStatus.value !== 'PENDING')
      return false
    return appDeeplinkUrl.value != null && deeplinkAppName.value != null
  })

  function openAppDeeplink() {
    const url = appDeeplinkUrl.value
    if (!url)
      return
    window.location.href = url
  }

  function normalizeWaNumber(phone: string): string {
    if (!phone)
      return ''
    const raw = phone.replace(/[^\d+]/g, '')
    if (raw.startsWith('+'))
      return raw.slice(1).replace(/[^\d]/g, '')
    const digits = raw.replace(/[^\d]/g, '')
    if (digits.startsWith('62'))
      return digits
    if (digits.startsWith('0'))
      return `62${digits.slice(1)}`
    return digits
  }

  const supportWaUrl = computed(() => {
    const supportRaw = String(runtimePublicConfig?.adminWhatsapp ?? runtimePublicConfig?.admin_whatsapp ?? runtimePublicConfig?.ADMIN_WHATSAPP ?? '').trim()
    const waBase = String(runtimePublicConfig?.whatsappBaseUrl ?? runtimePublicConfig?.whatsapp_base_url ?? runtimePublicConfig?.WHATSAPP_BASE_URL ?? 'https://wa.me').trim()
    const number = normalizeWaNumber(supportRaw)
    if (!number)
      return null
    return `${waBase.replace(/\/$/, '')}/${number}`
  })

  function openSupportWhatsApp() {
    if (!supportWaUrl.value)
      return
    window.open(supportWaUrl.value, '_blank', 'noopener,noreferrer')
  }

  return {
    invoicePath,
    invoiceDownloadUrl,
    canDownloadInvoice,
    isDownloadingInvoice,
    downloadInvoice,
    qrDownloadUrl,
    qrViewUrl,
    showQrCode,
    qrSize,
    appDeeplinkUrl,
    deeplinkAppName,
    showAppDeeplinkButton,
    showAppInstructions,
    openAppDeeplink,
    supportWaUrl,
    openSupportWhatsApp,
  }
}
