import type { ComputedRef, Ref } from 'vue'
import { computed } from 'vue'
import { format, isValid as isValidDate, parseISO } from 'date-fns'
import { id as dateLocaleId } from 'date-fns/locale'
import type { TransactionDetailResponseContract, TransactionStatusContract } from '~/types/api/contracts'

type AlertType = 'success' | 'warning' | 'error' | 'info'

interface UsePaymentFinishPresentationOptions {
  finalStatus: ComputedRef<TransactionStatusContract>
  isPublicView: ComputedRef<boolean>
  transactionDetails: Ref<TransactionDetailResponseContract | null>
  errorMessageFromQuery: Ref<string | null>
  isDebtSettlement: ComputedRef<boolean>
  packageName: ComputedRef<string>
  displayHotspotUsername: ComputedRef<string | null>
  userName: ComputedRef<string>
  paymentMethod: ComputedRef<string | null>
}

function formatDate(isoString?: string | null): string {
  if (isoString == null)
    return '-'
  try {
    const parsedDate = parseISO(isoString)
    if (isValidDate(parsedDate) === false)
      throw new Error('Invalid date')
    return format(parsedDate, 'iiii, dd MMMM yyyy, HH:mm \'WITA\'', { locale: dateLocaleId })
  }
  catch {
    return 'Tanggal Invalid'
  }
}

function getBankNameFromVA(paymentMethodValue?: string | null): string {
  if (paymentMethodValue == null)
    return 'Bank'
  const lowerPm = paymentMethodValue.toLowerCase()
  if (lowerPm === 'echannel')
    return 'Mandiri'
  const parts = lowerPm.split('_')
  if (parts.length > 1 && parts[1] === 'va') {
    const bankCode = parts[0]
    const bankMap: { [key: string]: string } = {
      bca: 'BCA',
      bni: 'BNI',
      bri: 'BRI',
      cimb: 'CIMB Niaga',
      permata: 'Bank Permata',
      mandiri: 'Mandiri',
      bsi: 'BSI',
    }
    return bankMap[bankCode] ?? bankCode.toUpperCase()
  }
  return paymentMethodValue.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())
}

export function formatCurrency(value?: number | null): string {
  if (value == null)
    return 'Rp -'
  return new Intl.NumberFormat('id-ID', {
    style: 'currency',
    currency: 'IDR',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(value)
}

export function formatToLocalPhone(phoneNumber?: string | null): string | null {
  if (phoneNumber == null)
    return null
  const raw = phoneNumber.trim()
  if (raw === '')
    return null
  if (raw === '-' || raw.toLowerCase() === 'null' || raw.toLowerCase() === 'undefined')
    return null
  const cleaned = raw.replace(/\D/g, '')
  if (cleaned === '')
    return null
  if (cleaned.startsWith('62'))
    return `0${cleaned.substring(2)}`
  return raw
}

export function usePaymentFinishPresentation(options: UsePaymentFinishPresentationOptions) {
  const {
    finalStatus,
    isPublicView,
    transactionDetails,
    errorMessageFromQuery,
    isDebtSettlement,
    packageName,
    displayHotspotUsername,
    userName,
    paymentMethod,
  } = options

  const paymentMethodBadgeLabel = computed(() => {
    const pm = String(paymentMethod.value ?? '').trim().toLowerCase()
    if (!pm)
      return null
    if (pm === 'qris')
      return 'QRIS'
    if (pm === 'gopay')
      return 'GoPay'
    if (pm === 'shopeepay')
      return 'ShopeePay'
    if (pm === 'echannel')
      return 'Mandiri'

    if (pm.endsWith('_va')) {
      const bank = pm.replace(/_va$/, '')
      return getBankNameFromVA(`${bank}_va`)
    }

    return pm.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())
  })

  const vaNumberLabel = computed(() => {
    const bank = getBankNameFromVA(paymentMethod.value)
    return bank ? `VA ${bank}` : 'VA'
  })

  const alertType = computed((): AlertType => {
    switch (finalStatus.value) {
      case 'SUCCESS': return 'success'
      case 'PENDING': return 'warning'
      case 'FAILED':
      case 'EXPIRED':
      case 'ERROR': return 'error'
      default: return 'info'
    }
  })

  const alertTitle = computed((): string => {
    switch (finalStatus.value) {
      case 'SUCCESS': return 'Pembayaran Berhasil'
      case 'PENDING': return 'Menunggu Pembayaran'
      case 'FAILED': return 'Pembayaran Gagal'
      case 'EXPIRED': return 'Waktu Pembayaran Habis'
      case 'CANCELLED': return 'Transaksi Dibatalkan'
      case 'ERROR': return 'Terjadi Kesalahan Pembayaran'
      case 'UNKNOWN': return 'Pembayaran Belum Dimulai'
      default: return 'Status Transaksi Tidak Diketahui'
    }
  })

  const alertIcon = computed((): string => {
    switch (finalStatus.value) {
      case 'SUCCESS': return 'tabler-check'
      case 'PENDING': return 'tabler-clock'
      case 'FAILED': return 'tabler-x'
      case 'EXPIRED': return 'tabler-clock-off'
      case 'CANCELLED': return 'tabler-ban'
      case 'ERROR': return 'tabler-alert-triangle'
      case 'UNKNOWN': return 'tabler-loader-2'
      default: return 'tabler-help-circle'
    }
  })

  const detailMessage = computed((): string => {
    if (isPublicView.value) {
      switch (finalStatus.value) {
        case 'SUCCESS':
          return 'Pembayaran telah berhasil diverifikasi oleh sistem.'
        case 'PENDING':
          if (transactionDetails.value?.expiry_time)
            return `Silakan selesaikan pembayaran sebelum ${formatDate(transactionDetails.value?.expiry_time)}.`
          return 'Pembayaran masih menunggu penyelesaian.'
        case 'FAILED':
          return 'Pembayaran gagal diproses.'
        case 'EXPIRED':
          return 'Waktu pembayaran sudah habis.'
        case 'CANCELLED':
          return 'Transaksi telah dibatalkan.'
        case 'ERROR':
          return 'Terjadi kesalahan saat memuat status pembayaran.'
        case 'UNKNOWN':
          return 'Status pembayaran belum tersedia.'
        default:
          return 'Status transaksi belum dapat dipastikan.'
      }
    }

    if (finalStatus.value === 'ERROR' && errorMessageFromQuery.value != null && transactionDetails.value == null)
      return errorMessageFromQuery.value

    if (isDebtSettlement.value) {
      switch (finalStatus.value) {
        case 'SUCCESS':
          return 'Pelunasan tunggakan kuota berhasil. Terima kasih — status akun akan kembali normal setelah sistem sinkronisasi.'
        case 'PENDING':
          return 'Pembayaran pelunasan tunggakan sedang menunggu. Selesaikan pembayaran sesuai instruksi agar tunggakan dihapus.'
        case 'FAILED':
          return 'Pembayaran pelunasan tunggakan gagal. Silakan coba lagi atau gunakan metode pembayaran lain.'
        case 'EXPIRED':
          return 'Waktu pembayaran pelunasan tunggakan sudah habis. Silakan mulai transaksi baru.'
        case 'CANCELLED':
          return 'Transaksi pelunasan tunggakan dibatalkan.'
        case 'UNKNOWN':
          return 'Pelunasan tunggakan belum dimulai atau status belum terbaca.'
        case 'ERROR':
          return 'Terjadi kesalahan saat proses pembayaran pelunasan tunggakan.'
        default:
          return 'Status transaksi pelunasan tunggakan tidak diketahui.'
      }
    }

    const safePackageName = packageName.value ?? 'paket yang dipilih'
    const safeUsername = displayHotspotUsername.value
    const safeDisplayName = String(userName.value ?? '').trim()
    const quotaRaw = transactionDetails.value?.package?.data_quota_gb
    const hasQuota = typeof quotaRaw === 'number' && Number.isFinite(quotaRaw) && quotaRaw > 0
    const quotaLabel = hasQuota ? ` (${quotaRaw} GB)` : ''

    switch (finalStatus.value) {
      case 'SUCCESS': {
        const identityLabel = [safeUsername, safeDisplayName].filter(v => v && v !== '').join(' · ')
        const purchaseMessage = identityLabel
          ? `Pembelian paket ${safePackageName}${quotaLabel} untuk ${identityLabel} berhasil.`
          : `Pembelian paket ${safePackageName}${quotaLabel} berhasil.`
        return `${purchaseMessage} Status layanan telah diperbarui.`
      }
      case 'PENDING':
        if (transactionDetails.value?.expiry_time)
          return `Mohon selesaikan pembayaran sebelum ${formatDate(transactionDetails.value?.expiry_time)} menggunakan instruksi di bawah ini.`
        return 'Mohon selesaikan pembayaran menggunakan instruksi yang ditampilkan di Midtrans. Status akan diperbarui otomatis.'
      case 'FAILED':
        return `Pembayaran untuk transaksi ${transactionDetails.value?.midtrans_order_id ?? ''} telah gagal. Silakan coba untuk memesan ulang.`
      case 'EXPIRED':
        return `Batas waktu pembayaran untuk transaksi ${transactionDetails.value?.midtrans_order_id ?? ''} telah terlewati. Silakan coba untuk memesan ulang.`
      case 'CANCELLED':
        return `Transaksi ${transactionDetails.value?.midtrans_order_id ?? ''} telah dibatalkan.`
      case 'ERROR':
        return 'Terjadi kesalahan pada proses pembayaran. Jika Anda merasa ini adalah kesalahan sistem, silakan hubungi administrator.'
      case 'UNKNOWN':
        return 'Transaksi sudah dibuat, namun pembayaran belum dimulai atau status belum diterima. Silakan buka kembali pembayaran atau tunggu pembaruan status.'
      default:
        return 'Status transaksi ini belum dapat dipastikan. Sistem kami sedang melakukan pengecekan lebih lanjut.'
    }
  })

  const statusInfoBox = computed(() => {
    switch (finalStatus.value) {
      case 'SUCCESS':
        return {
          type: 'success' as const,
          icon: 'tabler-check' as const,
          title: 'Akses Internet Aktif',
          text: 'Paket internet Anda sudah ditambahkan dan siap digunakan sekarang juga.',
        }
      case 'CANCELLED':
        return {
          type: 'info' as const,
          icon: 'tabler-info-circle' as const,
          title: 'Informasi',
          text: 'Tidak ada dana yang dipotong dari rekening Anda. Anda dapat membuat pesanan baru apabila ingin melanjutkan.',
        }
      case 'FAILED':
      case 'EXPIRED':
      case 'ERROR':
        return {
          type: 'error' as const,
          icon: 'tabler-alert-triangle' as const,
          title: 'Peringatan Transaksi',
          text: 'Silakan periksa saldo Anda atau pastikan jaringan internet stabil sebelum mencoba kembali.',
        }
      default:
        return null
    }
  })

  const showSpecificPendingInstructions = computed(() => {
    if (finalStatus.value !== 'PENDING' || transactionDetails.value == null)
      return false
    const td = transactionDetails.value
    const hasVa = typeof td.va_number === 'string' && td.va_number.trim() !== ''
    const hasEchannel = td.payment_code != null && td.biller_code != null
    const hasQr = typeof td.qr_code_url === 'string' && td.qr_code_url.trim() !== ''
    const hasDeeplink = typeof td.deeplink_redirect_url === 'string' && td.deeplink_redirect_url.trim() !== ''
    return hasVa || hasEchannel || hasQr || hasDeeplink
  })

  const showEchannel = computed(() => {
    if (finalStatus.value !== 'PENDING' || transactionDetails.value == null)
      return false
    const pm = paymentMethod.value?.toLowerCase()
    return pm === 'echannel' && transactionDetails.value.payment_code != null && transactionDetails.value.biller_code != null
  })

  return {
    paymentMethodBadgeLabel,
    vaNumberLabel,
    alertType,
    alertTitle,
    alertIcon,
    detailMessage,
    statusInfoBox,
    showSpecificPendingInstructions,
    showEchannel,
  }
}
