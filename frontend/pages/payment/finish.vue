<script setup lang="ts">
import { useNuxtApp, useRuntimeConfig } from '#app'
import { ClientOnly } from '#components'
import { format, isValid as isValidDate, parseISO } from 'date-fns'
import { id as dateLocaleId } from 'date-fns/locale'
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useDisplay } from 'vuetify'
import { useSnackbar } from '~/composables/useSnackbar'

// --- Interface Data Disesuaikan dengan Backend (snake_case) ---
interface PackageDetails {
  id: string
  name: string
  description?: string | null
  price?: number | null
  data_quota_gb?: number | null
}
interface UserDetails {
  id: string
  phone_number: string
  full_name?: string | null
  quota_expiry_date?: string | null
}
type TransactionStatus = 'SUCCESS' | 'PENDING' | 'FAILED' | 'EXPIRED' | 'CANCELLED' | 'ERROR' | 'UNKNOWN'

interface TransactionDetails {
  id: string
  midtrans_order_id: string
  midtrans_transaction_id?: string | null
  status: TransactionStatus
  purpose?: string | null
  debt_type?: 'auto' | 'manual' | null
  debt_mb?: number | null
  debt_note?: string | null
  amount?: number | null
  payment_method?: string | null
  snap_token?: string | null
  snap_redirect_url?: string | null
  deeplink_redirect_url?: string | null
  payment_time?: string | null
  expiry_time?: string | null
  va_number?: string | null
  payment_code?: string | null
  biller_code?: string | null
  qr_code_url?: string | null
  hotspot_password?: string | null
  package?: PackageDetails | null
  user?: UserDetails | null
}
// --- Akhir Interface Data ---

const route = useRoute()
const router = useRouter()
const { $api } = useNuxtApp()
const runtimeConfig = useRuntimeConfig()
const { add: addSnackbar } = useSnackbar()
const { smAndDown } = useDisplay()
const { ensureMidtransReady } = useMidtransSnap()
const isHydrated = ref(false)
const isMobile = computed(() => (isHydrated.value ? smAndDown.value : false))

const transactionDetails = ref<TransactionDetails | null>(null)
const isLoading = ref(true)
const isRefreshing = ref(false)
const fetchError = ref<string | null>(null)
const copySuccess = ref<string | null>(null)
const isDownloadingInvoice = ref(false)
const isPolling = ref(false)
const errorMessageFromQuery = ref<string | null>(
  typeof route.query.msg === 'string' ? decodeURIComponent(route.query.msg) : null,
)

const statusTokenFromQuery = computed(() => {
  const raw = (route.query.t ?? route.query.token)
  if (Array.isArray(raw))
    return typeof raw[0] === 'string' ? raw[0].trim() || null : null
  return typeof raw === 'string' ? raw.trim() || null : null
})
const orderIdFromQuery = computed(() => {
  const raw = route.query.order_id
  if (Array.isArray(raw))
    return typeof raw[0] === 'string' ? raw[0] : null
  return typeof raw === 'string' ? raw : null
})

const orderId = computed(() => {
  if (transactionDetails.value?.midtrans_order_id)
    return transactionDetails.value.midtrans_order_id
  return orderIdFromQuery.value
})

const isDebtSettlement = computed(() => {
  const oid = orderId.value ?? ''
  if (transactionDetails.value?.purpose === 'debt')
    return true
  if (oid.startsWith('DEBT-'))
    return true
  return route.query.purpose === 'debt'
})

function formatDebtMb(value?: number | null): string | null {
  if (value == null)
    return null
  const n = Math.round(Number(value))
  if (!Number.isFinite(n) || n <= 0)
    return null
  return `${n} MB`
}

async function fetchTransactionDetails(orderId: string, options?: { showLoading?: boolean, silent?: boolean }) {
  const showLoading = options?.showLoading !== false
  const silent = options?.silent === true

  if (showLoading)
    isLoading.value = true
  else
    isRefreshing.value = true

  if (!silent)
    fetchError.value = null
  try {
    const response = await $api<TransactionDetails>(`/transactions/by-order-id/${orderId}`)
    if (response == null || typeof response !== 'object' || response.midtrans_order_id == null || response.status == null) {
      throw new Error('Respons API tidak valid atau tidak lengkap.')
    }
    transactionDetails.value = response
  }
  catch (err: any) {
    // If user opens a shareable link from WhatsApp/another device, they may not have auth cookies.
    // Fallback to public, token-protected endpoint when `t` is provided.
    const statusCode = err?.response?.status ?? err?.statusCode
    if ((statusCode === 401 || statusCode === 403) && statusTokenFromQuery.value) {
      try {
        const publicUrl = `/transactions/public/by-order-id/${encodeURIComponent(orderId)}?t=${encodeURIComponent(statusTokenFromQuery.value)}`
        const publicResponse = await $api<TransactionDetails>(publicUrl)
        if (publicResponse == null || typeof publicResponse !== 'object' || publicResponse.midtrans_order_id == null || publicResponse.status == null)
          throw new Error('Respons API public tidak valid atau tidak lengkap.')
        transactionDetails.value = publicResponse
        fetchError.value = null
        return
      }
      catch (fallbackErr: any) {
        // continue to normal error handling below
        err = fallbackErr
      }
    }

    if (silent)
      return
    const status = err.response?.status ?? err.statusCode ?? 'N/A'
    const description = err.data?.message ?? 'Terjadi kesalahan.'
    if (status === 404) {
      fetchError.value = `Transaksi dengan Order ID '${orderId}' tidak ditemukan.`
    }
    else {
      fetchError.value = `Gagal memuat detail transaksi (Kode: ${status}). ${description}`
    }
    transactionDetails.value = null
  }
  finally {
    isLoading.value = false
    isRefreshing.value = false
  }
}

function isFinalStatus(status: TransactionStatus): boolean {
  return status === 'SUCCESS' || status === 'FAILED' || status === 'EXPIRED' || status === 'CANCELLED'
}

onMounted(() => {
  isHydrated.value = true
  const raw = route.query.order_id
  const orderIdFromQueryValue = Array.isArray(raw) ? raw[0] : raw
  const statusFromQuery = typeof route.query.status === 'string' ? route.query.status.toUpperCase() : undefined

  if (typeof orderIdFromQueryValue === 'string' && orderIdFromQueryValue.trim() !== '') {
    const cleaned = orderIdFromQueryValue.trim()
    void fetchTransactionDetails(cleaned)
  }
  else if (statusFromQuery === 'ERROR' && errorMessageFromQuery.value != null) {
    fetchError.value = `Pembayaran Gagal: ${errorMessageFromQuery.value}`
    isLoading.value = false
  }
  else {
    fetchError.value = 'Order ID tidak valid atau tidak ditemukan.'
    isLoading.value = false
  }
})

const finalStatus = computed((): TransactionStatus => {
  const statusFromQuery = typeof route.query.status === 'string' ? route.query.status.toUpperCase() as TransactionStatus : undefined
  if (transactionDetails.value?.status != null && transactionDetails.value.status !== 'UNKNOWN') {
    return transactionDetails.value.status
  }
  if (statusFromQuery != null && ['SUCCESS', 'PENDING', 'FAILED', 'EXPIRED', 'CANCELLED', 'ERROR'].includes(statusFromQuery)) {
    return statusFromQuery
  }
  return transactionDetails.value?.status ?? 'UNKNOWN'
})

const invoicePath = computed(() => {
  if (!orderId.value)
    return ''
  return `/transactions/${orderId.value}/invoice`
})

const invoiceDownloadUrl = computed(() => {
  if (invoicePath.value === '')
    return ''
  const base = (runtimeConfig.public.apiBaseUrl ?? '/api').replace(/\/$/, '')
  return `${base}${invoicePath.value}`
})

const canDownloadInvoice = computed(() => finalStatus.value === 'SUCCESS' && invoicePath.value !== '')

const userPhoneNumberRaw = computed(() => transactionDetails.value?.user?.phone_number ?? null)
const userName = computed(() => transactionDetails.value?.user?.full_name ?? 'Pengguna')
const packageName = computed(() => {
  if (isDebtSettlement.value) {
    const debtType = transactionDetails.value?.debt_type ?? null
    if (debtType === 'auto') {
      const mbText = formatDebtMb(transactionDetails.value?.debt_mb ?? null)
      if (mbText)
        return `Bayar Kuota ${mbText}`
      return 'Pelunasan Tunggakan Kuota'
    }

    if (debtType === 'manual') {
      const note = String(transactionDetails.value?.debt_note ?? '').trim()
      if (note)
        return note
      return 'Pelunasan Hutang Manual'
    }

    return 'Pelunasan Tunggakan Kuota'
  }
  return transactionDetails.value?.package?.name ?? 'Paket Tidak Diketahui'
})

const debtNote = computed(() => (isDebtSettlement.value ? 'Pelunasan Tunggakan Quota' : null))
const paymentMethod = computed(() => transactionDetails.value?.payment_method ?? null)
const displayHotspotUsername = computed(() => formatToLocalPhone(userPhoneNumberRaw.value) ?? '-')

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

  // bank VA: bni_va, permata_va, etc
  if (pm.endsWith('_va')) {
    const bank = pm.replace(/_va$/, '')
    return getBankNameFromVA(`${bank}_va`)
  }

  return pm.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())
})

function formatToLocalPhone(phoneNumber?: string | null): string {
  if (phoneNumber == null)
    return '-'
  const cleaned = phoneNumber.replace(/\D/g, '')
  if (cleaned.startsWith('62'))
    return `0${cleaned.substring(2)}`
  return phoneNumber
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

function formatCurrency(value?: number | null): string {
  if (value == null)
    return 'Rp -'
  return new Intl.NumberFormat('id-ID', { style: 'currency', currency: 'IDR', minimumFractionDigits: 0, maximumFractionDigits: 0 }).format(value)
}

const alertType = computed((): 'success' | 'warning' | 'error' | 'info' => {
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
  if (finalStatus.value === 'ERROR' && errorMessageFromQuery.value != null && transactionDetails.value == null) {
    return errorMessageFromQuery.value
  }

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
  const safeUsername = displayHotspotUsername.value ?? 'akun Anda'
  const safePhoneNumber = formatToLocalPhone(userPhoneNumberRaw.value) ?? 'nomor Anda'

  switch (finalStatus.value) {
    case 'SUCCESS':
      if (transactionDetails.value?.package?.data_quota_gb === 0) {
        return `Langganan paket ${safePackageName} Anda telah berhasil diaktifkan. Anda kini dapat menggunakan internet tanpa batas kuota hingga ${formatDate(transactionDetails.value?.user?.quota_expiry_date)}. Kredensial login akan atau sudah dikirim via WhatsApp ke ${safePhoneNumber}.`
      }
      else {
        const quotaDisplay = transactionDetails.value?.package?.data_quota_gb
        return `Pembelian paket ${safePackageName} (${quotaDisplay} GB) untuk ${safeUsername} (${userName.value}) berhasil. Kredensial login akan atau sudah dikirim via WhatsApp ke ${safePhoneNumber}.`
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

async function copyToClipboard(textToCopy: string | undefined | null, type: string) {
  if (textToCopy == null || navigator.clipboard == null) {
    addSnackbar({ type: 'error', title: 'Gagal Menyalin', text: 'Gagal menyalin: Fitur tidak didukung oleh browser Anda.' })
    return
  }
  try {
    await navigator.clipboard.writeText(textToCopy)
    copySuccess.value = type
    addSnackbar({ type: 'success', title: 'Berhasil', text: `${type} berhasil disalin ke clipboard!` })
    setTimeout(() => {
      copySuccess.value = null
    }, 2500)
  }
  catch {
    addSnackbar({ type: 'error', title: 'Gagal Menyalin', text: `Gagal menyalin ${type}.` })
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
    const bankMap: { [key: string]: string } = { bca: 'BCA', bni: 'BNI', bri: 'BRI', cimb: 'CIMB Niaga', permata: 'Bank Permata', mandiri: 'Mandiri', bsi: 'BSI' }
    return bankMap[bankCode] ?? bankCode.toUpperCase()
  }
  return paymentMethodValue.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())
}

function goToSelectPackage() {
  router.push({ path: '/beli' })
}

async function refreshStatus() {
  if (orderId.value)
    await fetchTransactionDetails(orderId.value, { showLoading: false })
}

async function cancelTransactionSilently(orderIdToCancel: string) {
  try {
    if (statusTokenFromQuery.value) {
      const url = `/transactions/public/${encodeURIComponent(orderIdToCancel)}/cancel?t=${encodeURIComponent(statusTokenFromQuery.value)}`
      await $api(url, { method: 'POST' })
    }
    else {
      await $api(`/transactions/${encodeURIComponent(orderIdToCancel)}/cancel`, { method: 'POST' })
    }
  }
  catch {
    // ignore (unauthorized, already final, network error)
  }
}

async function downloadInvoice() {
  if (invoicePath.value === '' || isDownloadingInvoice.value)
    return
  isDownloadingInvoice.value = true
  try {
    const blob = await $api<Blob>(invoicePath.value, {
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
    addSnackbar({ type: 'success', title: 'Berhasil', text: 'Invoice berhasil diunduh.' })
  }
  catch (err: any) {
    const message = err?.data?.message ?? err?.message ?? 'Gagal mengunduh invoice.'
    addSnackbar({ type: 'error', title: 'Gagal', text: message })
  }
  finally {
    isDownloadingInvoice.value = false
  }
}

const qrDownloadUrl = computed(() => {
  if (!orderId.value)
    return ''
  const base = (runtimeConfig.public.apiBaseUrl ?? '/api').replace(/\/$/, '')
  if (statusTokenFromQuery.value)
    return `${base}/transactions/public/${encodeURIComponent(orderId.value)}/qr?t=${encodeURIComponent(statusTokenFromQuery.value)}&download=1`
  return `${base}/transactions/${encodeURIComponent(orderId.value)}/qr?download=1`
})

const qrViewUrl = computed(() => {
  if (!orderId.value)
    return ''
  const base = (runtimeConfig.public.apiBaseUrl ?? '/api').replace(/\/$/, '')
  if (statusTokenFromQuery.value)
    return `${base}/transactions/public/${encodeURIComponent(orderId.value)}/qr?t=${encodeURIComponent(statusTokenFromQuery.value)}`
  return `${base}/transactions/${encodeURIComponent(orderId.value)}/qr`
})

function goToDashboard() {
  router.push({ path: '/dashboard' })
}

const vaInstructionTitle = computed(() => {
  const pm = paymentMethod.value?.toLowerCase() ?? ''
  if (pm.includes('bca'))
    return 'Cara bayar VA BCA'
  if (pm.includes('bni'))
    return 'Cara bayar VA BNI'
  if (pm.includes('bri'))
    return 'Cara bayar VA BRI'
  if (pm.includes('permata'))
    return 'Cara bayar VA Permata'
  if (pm.includes('cimb'))
    return 'Cara bayar VA CIMB'
  return 'Cara bayar Virtual Account'
})

const vaInstructions = computed(() => {
  return [
    'Buka aplikasi mobile banking / internet banking / ATM bank Anda.',
    'Pilih menu Transfer → Virtual Account.',
    'Masukkan nomor Virtual Account di atas, lalu konfirmasi pembayaran.',
    'Kembali ke halaman ini dan klik “Cek Status Pembayaran”.',
  ]
})

const vaNumberLabel = computed(() => {
  const bank = getBankNameFromVA(paymentMethod.value)
  return bank ? `VA ${bank}` : 'VA'
})

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
  const publicCfg: any = runtimeConfig.public as any
  const supportRaw = String(publicCfg?.adminWhatsapp ?? publicCfg?.admin_whatsapp ?? publicCfg?.ADMIN_WHATSAPP ?? '').trim()
  const waBase = String(publicCfg?.whatsappBaseUrl ?? publicCfg?.whatsapp_base_url ?? publicCfg?.WHATSAPP_BASE_URL ?? 'https://wa.me').trim()
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

interface SnapPayResult {
  order_id: string
}

interface SnapInstance {
  pay: (token: string, options: {
    onSuccess: (result: SnapPayResult) => void
    onPending: (result: SnapPayResult) => void
    onError: (result: SnapPayResult) => void
    onClose: () => void
  }) => void
}

declare global {
  interface Window {
    snap?: SnapInstance
  }
}

const snapToken = computed(() => {
  const token = transactionDetails.value?.snap_token
  return (typeof token === 'string' && token.trim() !== '') ? token.trim() : null
})

const showSnapPaySection = computed(() => {
  if (snapToken.value == null)
    return false
  return finalStatus.value === 'UNKNOWN' || finalStatus.value === 'PENDING'
})

const isPayingWithSnap = ref(false)

async function openSnapPayment() {
  if (isPayingWithSnap.value)
    return
  const token = snapToken.value
  if (!token) {
    addSnackbar({ type: 'warning', title: 'Tidak Tersedia', text: 'Token pembayaran Snap tidak tersedia.' })
    return
  }

  isPayingWithSnap.value = true
  try {
    await ensureMidtransReady()
    if (!window.snap) {
      throw new Error('Snap.js siap, tetapi window.snap tidak tersedia.')
    }

    // snap.pay is callback-based (non-async). Keep loading state until one of callbacks fires.
    window.snap.pay(token, {
      onSuccess: async (result) => {
        try {
          const oid = (result?.order_id || orderId.value || '').toString()
          if (oid)
            await router.push({ path: '/payment/status', query: { order_id: oid, t: statusTokenFromQuery.value ?? undefined } })
          await refreshStatus()
        }
        finally {
          isPayingWithSnap.value = false
        }
      },
      onPending: async (result) => {
        try {
          const oid = (result?.order_id || orderId.value || '').toString()
          if (oid)
            await router.push({ path: '/payment/status', query: { order_id: oid, t: statusTokenFromQuery.value ?? undefined } })
          await refreshStatus()
        }
        finally {
          isPayingWithSnap.value = false
        }
      },
      onError: async (result) => {
        try {
          const oid = (result?.order_id || orderId.value || '').toString()
          addSnackbar({ type: 'error', title: 'Gagal', text: 'Pembayaran gagal diproses. Silakan coba lagi.' })
          if (oid)
            await router.push({ path: '/payment/status', query: { order_id: oid, t: statusTokenFromQuery.value ?? undefined } })
          await refreshStatus()
        }
        finally {
          isPayingWithSnap.value = false
        }
      },
      onClose: async () => {
        try {
          addSnackbar({ type: 'info', title: 'Dibatalkan', text: 'Jendela pembayaran ditutup.' })
          const oid = (orderId.value || '').toString()
          if (oid)
            await cancelTransactionSilently(oid)
          await refreshStatus()
        }
        finally {
          isPayingWithSnap.value = false
        }
      },
    })
  }
  catch (err: any) {
    const msg = err?.message || 'Gagal membuka pembayaran Snap.'
    addSnackbar({ type: 'error', title: 'Gagal', text: msg })
    isPayingWithSnap.value = false
  }
}

const qrValue = computed(() => transactionDetails.value?.qr_code_url ?? '')
const showQrCode = computed(() => {
  if (finalStatus.value !== 'PENDING' || qrValue.value === '')
    return false
  // Don't show QR when we already have VA/echannel instructions.
  if (transactionDetails.value?.va_number)
    return false
  if (transactionDetails.value?.payment_code && transactionDetails.value?.biller_code)
    return false
  return true
})
const qrSize = computed(() => (isMobile.value ? 220 : 280))

const showEchannel = computed(() => {
  if (finalStatus.value !== 'PENDING' || transactionDetails.value == null)
    return false
  const pm = paymentMethod.value?.toLowerCase()
  return pm === 'echannel' && transactionDetails.value.payment_code != null && transactionDetails.value.biller_code != null
})

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

const qrisInstructions = computed(() => {
  return [
    'Buka aplikasi pembayaran (BCA, Mandiri, GoPay, OVO, dll).',
    'Pilih menu Scan QR.',
    'Pindai QR Code di atas atau download QR lalu unggah dari galeri Anda.',
    'Periksa detail pembayaran dan konfirmasi.',
  ]
})

const appDeeplinkInstructions = computed(() => {
  const appName = deeplinkAppName.value
  if (appName === 'GoPay') {
    return [
      'Klik tombol "Buka Aplikasi GoPay" di bawah.',
      'Aplikasi Gojek/GoPay akan terbuka otomatis (jika tersedia di perangkat Anda).',
      'Periksa nominal tagihan dan klik konfirmasi bayar.',
      'Masukkan PIN GoPay Anda untuk menyelesaikan transaksi.',
    ]
  }
  if (appName === 'ShopeePay') {
    return [
      'Klik tombol "Buka ShopeePay" di bawah.',
      'Aplikasi Shopee akan terbuka otomatis (jika tersedia di perangkat Anda).',
      'Buka menu ShopeePay dan konfirmasi pembayaran.',
      'Masukkan PIN ShopeePay Anda untuk menyelesaikan transaksi.',
    ]
  }
  return []
})

function openAppDeeplink() {
  const url = appDeeplinkUrl.value
  if (!url)
    return
  // Use user gesture to maximize chance mobile browsers allow app redirect.
  window.location.href = url
}

definePageMeta({ layout: 'blank' })
useHead({
  title: computed(() => `Status: ${alertTitle.value}`),
  bodyAttrs: {
    style: 'overflow-x: hidden;',
  },
})
</script>

<template>
  <v-container fluid class="fill-height bg-background pa-0 ma-0 finish-no-x">
    <v-row justify="center" align="center" class="fill-height py-md-10 py-6 px-4">
      <v-col cols="12" class="mx-auto finish-max">
        <div v-if="isLoading && !transactionDetails" class="text-center pa-10">
          <v-progress-circular indeterminate color="primary" size="64" width="6" />
          <p class="text-h6 mt-8 text-medium-emphasis font-weight-regular">
            Memeriksa Status Transaksi Anda...
          </p>
        </div>

        <v-card v-else-if="fetchError" variant="tonal" color="error" class="mx-auto rounded-xl pa-2">
          <v-card-text class="text-center pa-6">
            <v-icon size="56" class="mb-4" color="error" icon="tabler-alert-octagon" />
            <h2 class="text-h5 font-weight-bold mb-3">
              Gagal Memuat Transaksi
            </h2>
            <p class="text-body-1 mb-6 text-medium-emphasis">
              {{ fetchError }}
            </p>
            <v-btn color="primary" variant="flat" size="large" @click="goToSelectPackage">
              <v-icon start icon="tabler-arrow-left" />Kembali ke Pilihan Paket
            </v-btn>
          </v-card-text>
        </v-card>

        <v-card v-else-if="transactionDetails" variant="flat" border class="mx-auto finish-card overflow-hidden bg-surface elevation-12">
          <div class="px-sm-8 px-6 pt-10 pb-6 text-center">
            <v-avatar size="80" :color="alertType" variant="tonal" class="mb-5">
              <v-icon :icon="alertIcon" :color="alertType" size="38" />
            </v-avatar>

            <h1 class="text-h5 font-weight-bold mb-2 text-high-emphasis">
              {{ alertTitle }}
            </h1>

            <p class="text-body-1 text-medium-emphasis" style="line-height: 1.7;">
              {{ detailMessage }}
            </p>

            <div class="d-flex justify-center flex-wrap mt-5" style="gap: 10px;">
              <v-chip :color="alertType" variant="tonal" class="font-weight-bold">
                {{ finalStatus }}
              </v-chip>
              <v-chip v-if="paymentMethodBadgeLabel" color="primary" variant="tonal" class="font-weight-medium">
                {{ paymentMethodBadgeLabel }}
              </v-chip>
            </div>

            <p v-if="finalStatus === 'SUCCESS'" class="text-body-2 text-medium-emphasis mt-4 mb-0">
              Silakan sambungkan ulang WiFi jika belum aktif.
            </p>
          </div>

          <v-divider />

          <v-card-text class="pa-0">
            <div class="px-sm-8 px-6 py-6">
              <div v-if="userName" class="d-flex flex-column flex-sm-row justify-space-between align-start align-sm-center mb-3 finish-kv" style="gap: 6px;">
                <span class="text-body-2 text-medium-emphasis">Nama Pengguna</span>
                <span class="font-weight-semibold break-anywhere">{{ userName }}</span>
              </div>

              <div class="d-flex flex-column flex-sm-row justify-space-between align-start align-sm-center mb-3 finish-kv" style="gap: 6px;">
                <span class="text-body-2 text-medium-emphasis">Nomor</span>
                <span class="font-weight-semibold break-anywhere">{{ displayHotspotUsername }}</span>
              </div>

              <div class="d-flex flex-column flex-sm-row justify-space-between align-start align-sm-center mb-3 finish-kv" style="gap: 6px;">
                <span class="text-body-2 text-medium-emphasis">Order ID</span>
                <span class="font-weight-bold text-primary break-anywhere">{{ transactionDetails.midtrans_order_id }}</span>
              </div>

              <div v-if="transactionDetails.midtrans_transaction_id" class="d-flex flex-column flex-sm-row justify-space-between align-start align-sm-center mb-3 finish-kv" style="gap: 6px;">
                <span class="text-body-2 text-medium-emphasis">ID Pembayaran</span>
                <span class="font-weight-bold font-mono break-anywhere">{{ transactionDetails.midtrans_transaction_id }}</span>
              </div>

              <div class="d-flex flex-column flex-sm-row justify-space-between align-start align-sm-center mb-3 finish-kv" style="gap: 6px;">
                <span class="text-body-2 text-medium-emphasis">Paket</span>
                <span class="font-weight-semibold break-anywhere">{{ packageName }}</span>
              </div>

              <div v-if="debtNote" class="d-flex flex-column flex-sm-row justify-space-between align-start align-sm-center mb-3 finish-kv" style="gap: 6px;">
                <span class="text-body-2 text-medium-emphasis">Catatan</span>
                <span class="font-weight-semibold break-anywhere">{{ debtNote }}</span>
              </div>

              <div class="d-flex flex-column flex-sm-row justify-space-between align-start align-sm-center" style="gap: 6px;">
                <span class="text-body-2 text-medium-emphasis">Total Tagihan</span>
                <span class="text-h6 font-weight-bold" :class="finalStatus === 'SUCCESS' ? 'text-success' : 'text-warning'">
                  {{ formatCurrency(transactionDetails.amount) }}
                </span>
              </div>

              <v-alert
                v-if="statusInfoBox"
                :type="statusInfoBox.type"
                variant="tonal"
                density="comfortable"
                class="mt-6"
                :icon="statusInfoBox.icon"
              >
                <div class="font-weight-bold mb-1">{{ statusInfoBox.title }}</div>
                <div class="text-body-2">{{ statusInfoBox.text }}</div>
              </v-alert>

              <v-alert
                v-if="canDownloadInvoice"
                type="info"
                variant="tonal"
                density="compact"
                class="mt-6"
              >
                <div class="d-flex align-center" style="gap: 12px;">
                  <div class="flex-grow-1">
                    Invoice PDF juga dikirim otomatis melalui WhatsApp setelah pembayaran berhasil.
                  </div>
                  <v-tooltip location="top" text="Unduh Invoice (PDF)">
                    <template #activator="{ props: tooltipProps }">
                      <v-btn
                        v-bind="tooltipProps"
                        icon="tabler-file-download"
                        variant="text"
                        color="success"
                        size="small"
                        :loading="isDownloadingInvoice"
                        :disabled="isDownloadingInvoice"
                        @click="downloadInvoice"
                      />
                    </template>
                  </v-tooltip>
                </div>
              </v-alert>

              <v-alert
                v-if="showSnapPaySection"
                type="info"
                variant="tonal"
                density="comfortable"
                class="mt-6"
              >
                <div class="d-flex flex-column flex-sm-row align-start align-sm-center" style="gap: 12px;">
                  <div class="flex-grow-1">
                    Lanjutkan pembayaran dengan membuka halaman pembayaran Midtrans.
                  </div>
                  <v-btn
                    color="primary"
                    :loading="isPayingWithSnap"
                    :disabled="isPayingWithSnap"
                    @click="openSnapPayment"
                  >
                    Bayar
                  </v-btn>
                </div>
              </v-alert>
            </div>
          </v-card-text>

          <div v-if="finalStatus === 'PENDING' && showSpecificPendingInstructions" class="px-sm-6 px-4 pb-6 pt-3">
            <v-divider class="mb-6" />
            <h3 class="text-h6 font-weight-bold mb-5 text-center text-high-emphasis">
              Instruksi Pembayaran
            </h3>

            <div v-if="transactionDetails.va_number" class="mb-4">
              <v-text-field
                :model-value="transactionDetails.va_number"
                :label="vaNumberLabel"
                readonly
                variant="outlined"
                density="comfortable"
                hide-details
                class="finish-big-input font-weight-bold"
              >
                <template #append-inner>
                  <v-tooltip location="top" :text="copySuccess === 'Nomor VA' ? 'Berhasil Disalin!' : 'Salin Nomor VA'">
                    <template #activator="{ props: tooltipProps }">
                      <v-btn
                        v-bind="tooltipProps"
                        :color="copySuccess === 'Nomor VA' ? 'success' : ''"
                        :icon="copySuccess === 'Nomor VA' ? 'tabler-checks' : 'tabler-copy'"
                        variant="text"
                        @click="copyToClipboard(transactionDetails?.va_number, 'Nomor VA')"
                      />
                    </template>
                  </v-tooltip>
                </template>
              </v-text-field>

              <v-alert type="info" variant="tonal" density="compact" class="mt-4 text-start">
                <div class="font-weight-medium mb-2">{{ vaInstructionTitle }}</div>
                <ol class="text-body-2 ps-4 mb-0">
                  <li v-for="(step, idx) in vaInstructions" :key="`va-step-${idx}`">{{ step }}</li>
                </ol>
              </v-alert>
            </div>

            <div v-else-if="showEchannel" class="mb-4">
              <p class="text-body-1 font-weight-medium mb-2 text-medium-emphasis">
                Mandiri Bill Payment
              </p>

              <v-row>
                <v-col cols="12" sm="6">
                  <v-text-field
                    :model-value="transactionDetails.payment_code"
                    label="Bill Key"
                    readonly
                    variant="outlined"
                    density="comfortable"
                    hide-details
                    class="finish-big-input font-weight-bold"
                  >
                    <template #append-inner>
                      <v-tooltip location="top" :text="copySuccess === 'Bill Key' ? 'Berhasil Disalin!' : 'Salin Bill Key'">
                        <template #activator="{ props: tooltipProps }">
                          <v-btn
                            v-bind="tooltipProps"
                            :color="copySuccess === 'Bill Key' ? 'success' : ''"
                            :icon="copySuccess === 'Bill Key' ? 'tabler-checks' : 'tabler-copy'"
                            variant="text"
                            @click="copyToClipboard(transactionDetails?.payment_code, 'Bill Key')"
                          />
                        </template>
                      </v-tooltip>
                    </template>
                  </v-text-field>
                </v-col>

                <v-col cols="12" sm="6">
                  <v-text-field
                    :model-value="transactionDetails.biller_code"
                    label="Biller Code"
                    readonly
                    variant="outlined"
                    density="comfortable"
                    hide-details
                    class="finish-big-input font-weight-bold"
                  >
                    <template #append-inner>
                      <v-tooltip location="top" :text="copySuccess === 'Biller Code' ? 'Berhasil Disalin!' : 'Salin Biller Code'">
                        <template #activator="{ props: tooltipProps }">
                          <v-btn
                            v-bind="tooltipProps"
                            :color="copySuccess === 'Biller Code' ? 'success' : ''"
                            :icon="copySuccess === 'Biller Code' ? 'tabler-checks' : 'tabler-copy'"
                            variant="text"
                            @click="copyToClipboard(transactionDetails?.biller_code, 'Biller Code')"
                          />
                        </template>
                      </v-tooltip>
                    </template>
                  </v-text-field>
                </v-col>
              </v-row>

              <v-alert type="info" variant="tonal" density="comfortable" class="mt-4 text-start">
                <div class="font-weight-bold mb-1">Cara bayar Mandiri Bill Payment</div>
                <ol class="text-body-2 ps-4 mb-0">
                  <li>Buka aplikasi Livin’/Mandiri.</li>
                  <li>Pilih Bayar → Multi Payment/Provider.</li>
                  <li>Masukkan Bill Key &amp; Biller Code di atas, lalu konfirmasi.</li>
                  <li>Kembali ke halaman ini dan klik “Cek Status Pembayaran”.</li>
                </ol>
              </v-alert>
            </div>

            <div v-else-if="showAppInstructions" class="mb-4">
              <v-alert type="info" variant="tonal" density="comfortable" class="text-start">
                <div class="font-weight-bold mb-1">Instruksi {{ deeplinkAppName }}</div>
                <ol class="text-body-2 ps-4 mb-0">
                  <li v-for="(step, idx) in appDeeplinkInstructions" :key="`deeplink-step-${idx}`">{{ step }}</li>
                </ol>
              </v-alert>
            </div>

            <div v-else-if="showQrCode" class="mb-4 text-center">
              <p class="text-body-1 font-weight-medium mb-3 text-medium-emphasis">
                Scan QR Code Menggunakan Aplikasi Pembayaran Anda
              </p>
              <v-sheet border rounded="lg" class="d-inline-block pa-3 mx-auto bg-white">
                <v-img
                  :src="qrViewUrl"
                  :width="qrSize"
                  :height="qrSize"
                  contain
                >
                  <template #placeholder>
                    <v-skeleton-loader type="image" :width="qrSize" :height="qrSize" />
                  </template>
                </v-img>
              </v-sheet>

              <div class="d-flex justify-center mt-4">
                <v-btn
                  color="primary"
                  variant="tonal"
                  prepend-icon="tabler-file-download"
                  :href="qrDownloadUrl"
                  target="_blank"
                  :disabled="qrDownloadUrl === ''"
                >
                  Download QR
                </v-btn>
              </div>

              <v-alert type="info" variant="tonal" density="comfortable" class="mt-6 text-start">
                <div class="font-weight-bold mb-1">Cara Pembayaran (QRIS)</div>
                <ol class="text-body-2 ps-4 mb-0">
                  <li v-for="(step, idx) in qrisInstructions" :key="`qris-step-${idx}`">{{ step }}</li>
                </ol>
              </v-alert>

              <p v-if="showAppDeeplinkButton" class="text-caption text-medium-emphasis mt-4 mb-0">
                Jika QR tidak terbaca, Anda juga bisa mencoba tombol “Buka {{ deeplinkAppName }}” di bawah.
              </p>
            </div>
          </div>

          <v-divider />
          <div class="px-sm-8 px-6 pb-10 pt-6 d-flex flex-column" style="gap: 14px;">
            <!-- PENDING actions -->
            <template v-if="finalStatus === 'PENDING'">
              <v-btn
                v-if="showAppDeeplinkButton"
                block
                size="large"
                rounded="lg"
                color="success"
                variant="flat"
                prepend-icon="tabler-external-link"
                @click="openAppDeeplink"
              >
                Buka {{ deeplinkAppName }}
              </v-btn>

              <v-btn
                v-else-if="showQrCode"
                block
                size="large"
                rounded="lg"
                color="primary"
                variant="flat"
                prepend-icon="tabler-download"
                :href="qrDownloadUrl"
                target="_blank"
                :disabled="qrDownloadUrl === ''"
              >
                Download QR Code
              </v-btn>

              <v-btn
                v-else
                block
                size="large"
                rounded="lg"
                color="primary"
                variant="flat"
                prepend-icon="tabler-refresh"
                :disabled="isRefreshing"
                @click="refreshStatus"
              >
                Cek Status Pembayaran
              </v-btn>

              <v-btn
                v-if="showAppDeeplinkButton || showQrCode"
                block
                size="large"
                rounded="lg"
                color="secondary"
                variant="text"
                class="text-medium-emphasis"
                prepend-icon="tabler-refresh"
                :disabled="isRefreshing"
                @click="refreshStatus"
              >
                Cek Status Pembayaran
              </v-btn>
              <v-btn
                v-else
                block
                size="large"
                rounded="lg"
                color="secondary"
                variant="text"
                class="text-medium-emphasis"
                prepend-icon="tabler-shopping-cart-plus"
                @click="goToSelectPackage"
              >
                Buat Pesanan Baru
              </v-btn>
            </template>

            <!-- SUCCESS actions -->
            <template v-else-if="finalStatus === 'SUCCESS'">
              <v-btn
                block
                size="large"
                rounded="lg"
                color="primary"
                variant="flat"
                prepend-icon="tabler-layout-dashboard"
                @click="goToDashboard"
              >
                Kembali ke Dashboard
              </v-btn>

              <v-btn
                block
                size="large"
                rounded="lg"
                color="secondary"
                variant="text"
                class="text-medium-emphasis"
                prepend-icon="tabler-history"
                @click="router.push('/riwayat')"
              >
                Lihat Riwayat Transaksi
              </v-btn>

            </template>

            <!-- CANCELLED actions -->
            <template v-else-if="finalStatus === 'CANCELLED'">
              <v-btn
                block
                size="large"
                rounded="lg"
                color="primary"
                variant="flat"
                prepend-icon="tabler-shopping-cart-plus"
                @click="goToSelectPackage"
              >
                Buat Pesanan Baru
              </v-btn>

              <v-btn
                block
                size="large"
                rounded="lg"
                color="secondary"
                variant="text"
                class="text-medium-emphasis"
                prepend-icon="tabler-arrow-left"
                @click="goToSelectPackage"
              >
                Kembali ke Beranda
              </v-btn>
            </template>

            <!-- FAILED/EXPIRED/ERROR/UNKNOWN actions -->
            <template v-else>
              <v-btn
                block
                size="large"
                rounded="lg"
                color="primary"
                variant="flat"
                prepend-icon="tabler-refresh"
                @click="goToSelectPackage"
              >
                Ulangi Pembayaran
              </v-btn>

              <v-btn
                v-if="supportWaUrl"
                block
                size="large"
                rounded="lg"
                color="secondary"
                variant="text"
                class="text-medium-emphasis"
                prepend-icon="tabler-brand-whatsapp"
                @click="openSupportWhatsApp"
              >
                Hubungi Bantuan
              </v-btn>
              <v-btn
                v-else
                block
                size="large"
                rounded="lg"
                color="secondary"
                variant="text"
                class="text-medium-emphasis"
                prepend-icon="tabler-arrow-left"
                @click="goToSelectPackage"
              >
                Kembali
              </v-btn>
            </template>
          </div>
        </v-card>
      </v-col>
    </v-row>
  </v-container>
</template>

<style scoped>
.font-mono { font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, Courier, monospace; }

.finish-no-x {
  overflow-x: hidden;
}

.finish-kv {
  min-width: 0;
}

.break-anywhere {
  overflow-wrap: anywhere;
  word-break: break-word;
  min-width: 0;
  max-width: 100%;
}

.finish-big-input :deep(.v-field--variant-outlined .v-field__input) {
  font-size: 1.1rem !important;
  line-height: 1.4 !important;
}

.finish-max {
  max-width: 520px;
}

.finish-card {
  border-radius: 16px;
}

@media (max-width: 600px) {
  .finish-max {
    max-width: 100%;
  }

  .finish-big-input :deep(.v-field--variant-outlined .v-field__input) {
    font-size: 1.02rem !important;
  }
}
</style>
