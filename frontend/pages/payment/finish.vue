<script setup lang="ts">
// Impor komponen Vuetify yang digunakan
import type { VIcon } from 'vuetify/components' // VIcon mungkin tidak perlu eksplisit jika sudah global
import { useNuxtApp } from '#app'
import { ClientOnly } from '#components'
import { format, isValid as isValidDate, parseISO } from 'date-fns'
import { id as dateLocaleId } from 'date-fns/locale'
import QrcodeVue from 'qrcode.vue'
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

// --- Interface Data ---
interface PackageDetails { id: string, name: string, description?: string | null, price?: number | null, data_quota_mb?: number | null, speed_limit_kbps?: number | null }
interface UserDetails { id: string, phone_number: string, name?: string | null }
type TransactionStatus = 'SUCCESS' | 'PENDING' | 'FAILED' | 'EXPIRED' | 'CANCELLED' | 'ERROR' | 'UNKNOWN'
interface TransactionDetails {
  orderId: string
  transactionId?: string
  status: TransactionStatus
  amount?: number | null
  paymentMethod?: string | null
  transactionTime?: string | null
  paymentTime?: string | null
  expiryTime?: string | null
  midtransTransactionId?: string | null
  package?: PackageDetails | null
  user?: UserDetails | null
  vaNumber?: string | null
  paymentCode?: string | null
  billerCode?: string | null
  qrCodeUrl?: string | null
  // actions?: { name: string, method: string, url: string }[]; // Tidak digunakan di template saat ini
  hotspotUsername?: string | null
  hotspotPassword?: string | null
}

// --- Setup Aplikasi ---
const route = useRoute()
const router = useRouter()
const { $api, $snackbar } = useNuxtApp() // Menggunakan $api dan $snackbar dari NuxtApp

// --- State Komponen ---
const transactionDetails = ref<TransactionDetails | null>(null)
const isLoading = ref(true)
const fetchError = ref<string | null>(null)
const copySuccess = ref<string | null>(null) // Untuk menandai item mana yang berhasil disalin
const errorMessageFromQuery = ref<string | null>(
  route.query.msg ? decodeURIComponent(route.query.msg as string) : null,
)

// --- Fungsi Fetch Data Transaksi ---
async function fetchTransactionDetails(orderId: string) {
  isLoading.value = true
  fetchError.value = null
  // transactionDetails.value = null; // Jangan reset agar data lama tampil saat refresh sampai data baru datang
  try {
    // $api sudah memiliki baseURL: '/api'
    const response = await $api<TransactionDetails>(`/transactions/by-order-id/${orderId}`, {
      method: 'GET',
      // Headers 'Accept' sudah di-default oleh $api
    })
    // Validasi respons yang lebih ketat
    if (!response || typeof response !== 'object' || !response.orderId || !response.status) {
      throw new Error('Respons API tidak valid atau tidak lengkap.')
    }
    transactionDetails.value = response
  }
  catch (err: any) {
    const status = err.response?.status ?? err.statusCode ?? err.data?.status_code ?? 'N/A'
    const responseData = err.data ?? {}
    const description = responseData?.message ?? responseData?.error ?? responseData?.detail ?? err.message ?? 'Terjadi kesalahan.'

    if (status === 404) {
      fetchError.value = `Transaksi dengan Order ID '${orderId}' tidak ditemukan. Pastikan Order ID sudah benar.`
    }
    else {
      fetchError.value = `Gagal memuat detail transaksi (Kode: ${status}). ${description}`
    }
    transactionDetails.value = null // Set null jika ada error fetch
  }
  finally {
    isLoading.value = false
  }
}

// --- Lifecycle Hook ---
onMounted(() => {
  const orderIdFromQuery = route.query.order_id as string | undefined
  const statusFromQuery = route.query.status as TransactionStatus | undefined

  if (orderIdFromQuery && typeof orderIdFromQuery === 'string' && orderIdFromQuery.trim() !== '') {
    fetchTransactionDetails(orderIdFromQuery.trim())
  }
  else if (statusFromQuery === 'error' && errorMessageFromQuery.value) {
    // Jika ada status=error dan pesan dari query, tampilkan itu
    fetchError.value = `Pembayaran Gagal: ${errorMessageFromQuery.value}`
    isLoading.value = false
  }
  else {
    // Jika tidak ada order_id, ini adalah kondisi error
    fetchError.value = 'Order ID tidak valid atau tidak ditemukan dalam parameter URL.'
    isLoading.value = false
  }
})

// --- Computed Properties ---
const finalStatus = computed((): TransactionStatus => {
  const statusFromQuery = route.query.status as TransactionStatus | undefined
  if (transactionDetails.value?.status && transactionDetails.value.status !== 'UNKNOWN') {
    return transactionDetails.value.status
  }
  if (statusFromQuery && ['SUCCESS', 'PENDING', 'FAILED', 'EXPIRED', 'CANCELLED', 'ERROR'].includes(statusFromQuery)) {
    return statusFromQuery
  }
  return transactionDetails.value?.status || 'UNKNOWN'
})

const userPhoneNumberRaw = computed(() => transactionDetails.value?.user?.phone_number || null)
const userName = computed(() => transactionDetails.value?.user?.name || 'Pengguna')
const packageName = computed(() => transactionDetails.value?.package?.name || 'Paket Tidak Diketahui')
const paymentMethod = computed(() => transactionDetails.value?.paymentMethod || null)
const displayHotspotUsername = computed(() => transactionDetails.value?.hotspotUsername || formatToLocalPhone(userPhoneNumberRaw.value) || '-')

// --- Helper Pemformatan ---
function formatToLocalPhone(phoneNumber?: string | null): string {
  if (!phoneNumber)
    return '-'
  const cleaned = phoneNumber.replace(/\D/g, '')
  if (cleaned.startsWith('62'))
    return `0${cleaned.substring(2)}`
  if (cleaned.startsWith('08') && cleaned.length >= 9)
    return cleaned
  return phoneNumber
}

function formatDate(isoString?: string | null): string {
  if (!isoString || typeof isoString !== 'string')
    return '-'
  try {
    const parsedDate = parseISO(isoString)
    if (!isValidDate(parsedDate))
      throw new Error('Invalid date parsed')
    return format(parsedDate, 'iiii, dd MMMM yyyy, HH:mm \'WITA\'', { locale: dateLocaleId })
  }
  catch (e) {
    console.error(`[formatDate] Error parsing/formatting date string "${isoString}":`, e)
    return 'Tanggal Invalid'
  }
}

function formatCurrency(value?: number | null): string {
  if (value === null || value === undefined)
    return 'Rp -'
  const numericValue = Number(value)
  if (Number.isNaN(numericValue))
    return 'Rp -'
  return new Intl.NumberFormat('id-ID', { style: 'currency', currency: 'IDR', minimumFractionDigits: 0, maximumFractionDigits: 0 }).format(numericValue)
}

// --- Properti Dinamis Vuetify ---
const alertType = computed((): 'success' | 'warning' | 'error' | 'info' => {
  switch (finalStatus.value) {
    case 'SUCCESS': return 'success'
    case 'PENDING': return 'warning'
    case 'FAILED': return 'error'
    case 'EXPIRED': return 'error'
    case 'ERROR': return 'error'
    case 'CANCELLED': return 'info'
    default: return 'info' // Untuk UNKNOWN atau status lain
  }
})

const alertTitle = computed((): string => {
  if (finalStatus.value === 'ERROR' && errorMessageFromQuery.value && !transactionDetails.value) { // Hanya jika fetch gagal dan ada msg
    return `Pembayaran Gagal`
  }
  switch (finalStatus.value) {
    case 'SUCCESS': return 'Pembayaran Berhasil!'
    case 'PENDING': return 'Menunggu Pembayaran'
    case 'FAILED': return 'Pembayaran Gagal'
    case 'EXPIRED': return 'Waktu Pembayaran Habis'
    case 'CANCELLED': return 'Transaksi Dibatalkan'
    case 'ERROR': return 'Terjadi Kesalahan Pembayaran' // Pesan generik jika API mengembalikan ERROR
    default: return 'Status Transaksi Tidak Diketahui'
  }
})

const alertIcon = computed((): string => {
  switch (finalStatus.value) {
    case 'SUCCESS': return 'mdi-check-circle-outline'
    case 'PENDING': return 'mdi-clock-fast'
    case 'FAILED': return 'mdi-close-circle-outline'
    case 'EXPIRED': return 'mdi-timer-sand-complete'
    case 'CANCELLED': return 'mdi-cancel'
    case 'ERROR': return 'mdi-alert-circle-outline'
    default: return 'mdi-help-circle-outline'
  }
})

const detailMessage = computed((): string => {
  if (finalStatus.value === 'ERROR' && errorMessageFromQuery.value && !transactionDetails.value) {
    return errorMessageFromQuery.value
  }
  const безопасныйПакетИмя = packageName.value || 'paket yang dipilih'
  const безопасныйИмяПользователя = displayHotspotUsername.value || 'akun Anda'
  const безопасныйНомерТелефона = formatToLocalPhone(userPhoneNumberRaw.value) || 'nomor Anda'

  switch (finalStatus.value) {
    case 'SUCCESS':
      return `Aktivasi ${безопасныйПакетИмя} untuk ${безопасныйИмяПользователя} (${userName.value}) berhasil. Kredensial login (jika ini pembelian pertama) akan atau sudah dikirim via WhatsApp ke ${безопасныйНомерТелефона}.`
    case 'PENDING':
      return `Selesaikan pembayaran sebelum ${formatDate(transactionDetails.value?.expiryTime)} menggunakan instruksi di bawah. Status akan diperbarui otomatis setelah pembayaran terkonfirmasi.`
    case 'FAILED':
      return `Pembayaran untuk transaksi ${transactionDetails.value?.orderId || ''} gagal. Silakan coba pesan ulang atau gunakan metode pembayaran lain.`
    case 'EXPIRED':
      return `Batas waktu pembayaran untuk transaksi ${transactionDetails.value?.orderId || ''} pada ${formatDate(transactionDetails.value?.expiryTime)} telah terlewati. Silakan pesan ulang.`
    case 'CANCELLED':
      return `Transaksi ${transactionDetails.value?.orderId || ''} telah dibatalkan.`
    case 'ERROR':
      return `Terjadi kesalahan pada proses pembayaran transaksi ${transactionDetails.value?.orderId || ''}. Jika Anda merasa ini adalah kesalahan sistem, silakan hubungi admin.`
    default:
      return 'Status transaksi ini belum dapat dipastikan. Sistem sedang melakukan pengecekan atau menunggu konfirmasi akhir.'
  }
})

// --- Helper Fungsi UI ---
async function copyToClipboard(textToCopy: string | undefined | null, type: string) {
  if (!textToCopy || !navigator.clipboard) {
    if ($snackbar) {
      $snackbar.add({ type: 'error', text: 'Gagal menyalin: Fitur tidak didukung browser ini.' })
    }
    else {
      console.error('Gagal menyalin: Fitur clipboard tidak tersedia.')
    }
    return
  }
  try {
    await navigator.clipboard.writeText(textToCopy)
    copySuccess.value = type // Tandai tipe apa yang berhasil disalin
    if ($snackbar) {
      $snackbar.add({ type: 'success', text: `${type} berhasil disalin!` })
    }
    setTimeout(() => {
      copySuccess.value = null // Reset setelah beberapa saat
    }, 2500)
  }
  catch (err) {
    if ($snackbar) {
      $snackbar.add({ type: 'error', text: `Gagal menyalin ${type}.` })
    }
    else {
      console.error(`Gagal menyalin ${type}:`, err)
    }
  }
}

function getBankNameFromVA(paymentMethodValue?: string | null): string {
  if (!paymentMethodValue)
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
    return bankMap[bankCode] || bankCode.toUpperCase()
  }
  return paymentMethodValue.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase()) // Kapitalisasi setiap kata
}

function getEchannelBankName(billerCodeValue?: string | null): string {
  if (billerCodeValue === '70012')
    return 'Mandiri' // Untuk Midtrans
  return 'Bank'
}

// --- Watcher ---
// Watcher ini bisa digunakan untuk polling status PENDING jika diperlukan di masa depan.
watch(() => transactionDetails.value?.status, (newStatus) => {
  if (newStatus === 'PENDING' && transactionDetails.value) {
    // Logika polling bisa ditambahkan di sini jika ingin auto-refresh status PENDING
  }
}, { immediate: false })

// --- Navigasi ---
const goToSelectPackage = () => router.push({ path: '/beli' })
const goToDashboard = () => router.push({ path: '/dashboard' }) // Tombol ke dashboard untuk status SUCCESS

// --- Logika Tampilan Instruksi Pending ---
const showSpecificPendingInstructions = computed(() => {
  if (finalStatus.value !== 'PENDING' || !transactionDetails.value)
    return false
  const td = transactionDetails.value
  const pm = td.paymentMethod?.toLowerCase()
  const hasVa = !!td.vaNumber && td.vaNumber.trim() !== '' && (pm?.includes('_va') || pm === 'bank_transfer')
  const hasEchannel = !!td.paymentCode && !!td.billerCode && pm === 'echannel'
  const hasQr = !!td.qrCodeUrl && td.qrCodeUrl.trim() !== '' && (pm === 'qris' || pm === 'gopay' || pm === 'shopeepay')
  return hasVa || hasEchannel || hasQr
})

const pendingInstructionFallbackMessage = computed(() => {
  if (finalStatus.value !== 'PENDING' || showSpecificPendingInstructions.value || !transactionDetails.value)
    return ''
  const pm = paymentMethod.value?.toLowerCase()
  if (pm === 'credit_card')
    return 'Pembayaran Kartu Kredit sedang diproses atau menunggu otentikasi (3D Secure). Status akan diperbarui otomatis.'
  return `Pembayaran sedang diproses menggunakan ${transactionDetails.value.paymentMethod?.replace(/_/g, ' ') || 'metode yang dipilih'}. Silakan tunggu konfirmasi atau ikuti instruksi yang mungkin telah Anda terima.`
})

const qrValue = computed(() => transactionDetails.value?.qrCodeUrl ?? '')
const showQrCode = computed(() => {
  if (finalStatus.value !== 'PENDING' || !qrValue.value || qrValue.value.trim() === '')
    return false
  const pm = paymentMethod.value?.toLowerCase()
  return (pm === 'qris' || pm === 'gopay' || pm === 'shopeepay')
})
const isQrUrl = computed(() => qrValue.value.startsWith('http') || qrValue.value.startsWith('data:image'))
const qrSize = ref(220)

definePageMeta({ layout: 'blank' })
useHead({ title: 'Detail Transaksi' })
</script>

<template>
  <v-container fluid class="fill-height bg-grey-lighten-5 pa-0 ma-0">
    <v-row justify="center" align="center" class="fill-height py-8 px-sm-4 px-2">
      <v-col cols="12" sm="10" md="8" lg="6" xl="5" class="pa-md-4 mx-auto">
        <div v-if="isLoading" class="text-center pa-10">
          <v-progress-circular indeterminate color="primary" size="60" width="5" />
          <p class="text-h6 mt-6 text-medium-emphasis font-weight-regular">
            Memuat Status Transaksi...
          </p>
        </div>

        <v-alert
          v-else-if="fetchError"
          type="error"
          variant="tonal"
          prominent
          border="start"
          class="mx-auto rounded-lg elevation-2 pa-5 text-center"
          max-width="600"
          icon="mdi-alert-octagon-outline"
        >
          <v-alert-title class="text-h6 font-weight-bold mb-2">
            Terjadi Kesalahan
          </v-alert-title>
          <p class="text-body-1">
            {{ fetchError }}
          </p>
          <div class="mt-6">
            <v-btn color="primary" variant="flat" @click="goToSelectPackage">
              <v-icon start>
                mdi-arrow-left
              </v-icon>
              Kembali Pilih Paket
            </v-btn>
          </div>
        </v-alert>

        <v-card v-else-if="transactionDetails" elevation="3" rounded="xl" class="mx-auto overflow-hidden">
          <v-sheet :color="alertType" class="pa-5 text-center vuexy-alert-sheet">
            <v-icon :icon="alertIcon" size="48" class="mb-3" />
            <div class="text-h5 font-weight-bold mb-1">
              {{ alertTitle }}
            </div>
            <p class="text-body-2 mx-auto" style="max-width: 90%; line-height: 1.6;">
              {{ detailMessage }}
            </p>
          </v-sheet>

          <v-list lines="one" density="comfortable" class="py-3 px-1">
            <v-list-item class="px-sm-5 px-3">
              <template #prepend>
                <v-icon size="20" class="mr-4 text-disabled">
                  mdi-pound
                </v-icon>
              </template>
              <v-list-item-title class="text-caption text-medium-emphasis">
                Order ID
              </v-list-item-title>
              <template #append>
                <span class="text-body-2 font-weight-medium font-mono">{{ transactionDetails.orderId }}</span>
              </template>
            </v-list-item>

            <v-list-item v-if="transactionDetails.midtransTransactionId" class="px-sm-5 px-3">
              <template #prepend>
                <v-icon size="20" class="mr-4 text-disabled">
                  mdi-barcode-scan
                </v-icon>
              </template>
              <v-list-item-title class="text-caption text-medium-emphasis">
                ID Pembayaran
              </v-list-item-title>
              <template #append>
                <span class="text-body-2 font-mono">{{ transactionDetails.midtransTransactionId }}</span>
              </template>
            </v-list-item>

            <v-list-item class="px-sm-5 px-3">
              <template #prepend>
                <v-icon size="20" class="mr-4 text-disabled">
                  mdi-package-variant-closed
                </v-icon>
              </template>
              <v-list-item-title class="text-caption text-medium-emphasis">
                Paket
              </v-list-item-title>
              <template #append>
                <span class="text-body-2 font-weight-medium">{{ packageName }}</span>
              </template>
            </v-list-item>

            <v-list-item class="px-sm-5 px-3">
              <template #prepend>
                <v-icon size="20" class="mr-4 text-disabled">
                  mdi-account-circle-outline
                </v-icon>
              </template>
              <v-list-item-title class="text-caption text-medium-emphasis">
                Pengguna
              </v-list-item-title>
              <template #append>
                <span class="text-body-2">{{ userName }} ({{ formatToLocalPhone(userPhoneNumberRaw) }})</span>
              </template>
            </v-list-item>

            <v-list-item class="px-sm-5 px-3">
              <template #prepend>
                <v-icon size="20" class="mr-4 text-disabled">
                  mdi-cash
                </v-icon>
              </template>
              <v-list-item-title class="text-caption text-medium-emphasis">
                Total Tagihan
              </v-list-item-title>
              <template #append>
                <span class="text-body-2 font-weight-bold">{{ formatCurrency(transactionDetails.amount) }}</span>
              </template>
            </v-list-item>

            <v-list-item v-if="paymentMethod" class="px-sm-5 px-3">
              <template #prepend>
                <v-icon size="20" class="mr-4 text-disabled">
                  mdi-credit-card-scan-outline
                </v-icon>
              </template>
              <v-list-item-title class="text-caption text-medium-emphasis">
                Metode Bayar
              </v-list-item-title>
              <template #append>
                <span class="text-body-2 text-capitalize">{{ paymentMethod.replace(/_/g, ' ') }}</span>
              </template>
            </v-list-item>

            <v-list-item class="px-sm-5 px-3">
              <template #prepend>
                <v-icon size="20" class="mr-4 text-disabled">
                  mdi-calendar-clock-outline
                </v-icon>
              </template>
              <v-list-item-title class="text-caption text-medium-emphasis">
                Waktu Pesan
              </v-list-item-title>
              <template #append>
                <span class="text-body-2">{{ formatDate(transactionDetails.transactionTime) }}</span>
              </template>
            </v-list-item>

            <v-list-item v-if="finalStatus === 'SUCCESS' && transactionDetails.paymentTime" class="px-sm-5 px-3">
              <template #prepend>
                <v-icon size="20" class="mr-4 text-success">
                  mdi-calendar-check-outline
                </v-icon>
              </template>
              <v-list-item-title class="text-caption text-medium-emphasis">
                Waktu Bayar
              </v-list-item-title>
              <template #append>
                <span class="text-body-2 text-success font-weight-medium">{{ formatDate(transactionDetails.paymentTime) }}</span>
              </template>
            </v-list-item>

            <v-list-item v-if="['PENDING', 'EXPIRED'].includes(finalStatus) && transactionDetails.expiryTime" class="px-sm-5 px-3">
              <template #prepend>
                <v-icon size="20" :class="finalStatus === 'EXPIRED' ? 'text-error' : 'text-warning'" class="mr-4">
                  mdi-timer-sand
                </v-icon>
              </template>
              <v-list-item-title class="text-caption text-medium-emphasis">
                Batas Pembayaran
              </v-list-item-title>
              <template #append>
                <span :class="finalStatus === 'EXPIRED' ? 'text-error font-weight-bold' : 'text-warning'" class="text-body-2">{{ formatDate(transactionDetails.expiryTime) }}</span>
              </template>
            </v-list-item>
          </v-list>

          <div v-if="finalStatus === 'PENDING'" class="px-5 pb-5 pt-3">
            <v-divider class="mb-5" />
            <p class="text-h6 font-weight-medium mb-4 text-center">
              Instruksi Pembayaran
            </p>

            <div v-if="showSpecificPendingInstructions">
              <div v-if="transactionDetails.vaNumber && (paymentMethod?.toLowerCase().includes('_va') || paymentMethod?.toLowerCase() === 'bank_transfer')" class="mb-5 instruction-section">
                <p class="text-subtitle-1 font-weight-medium mb-2">
                  {{ getBankNameFromVA(paymentMethod) }} Virtual Account
                </p>
                <v-text-field
                  :model-value="transactionDetails.vaNumber"
                  label="Nomor Virtual Account"
                  readonly
                  variant="outlined"
                  density="comfortable"
                  hide-details
                  class="font-weight-bold text-h6 va-number-field"
                  bg-color="grey-lighten-4"
                >
                  <template #append-inner>
                    <v-tooltip location="top" :text="copySuccess === 'Nomor VA' ? 'Tersalin!' : 'Salin Nomor VA'">
                      <template #activator="{ props: tooltipProps }">
                        <v-btn v-bind="tooltipProps" :icon="copySuccess === 'Nomor VA' ? 'mdi-check-all' : 'mdi-content-copy'" variant="text" density="comfortable" @click="copyToClipboard(transactionDetails?.vaNumber, 'Nomor VA')" />
                      </template>
                    </v-tooltip>
                  </template>
                </v-text-field>
                <p class="text-caption mt-2 text-medium-emphasis">
                  Salin nomor di atas dan lakukan pembayaran melalui ATM, Mobile Banking, atau Internet Banking {{ getBankNameFromVA(paymentMethod) }}.
                </p>
              </div>

              <div v-else-if="transactionDetails.paymentCode && transactionDetails.billerCode && paymentMethod === 'echannel'" class="mb-5 instruction-section">
                <p class="text-subtitle-1 font-weight-medium mb-2">
                  {{ getEchannelBankName(transactionDetails.billerCode) }} Bill Payment
                </p>
                <v-sheet border rounded class="pa-4 bg-grey-lighten-4">
                  <div class="d-flex justify-space-between mb-1">
                    <span class="text-body-2 text-medium-emphasis">Penyedia Jasa:</span>
                    <span class="text-body-2 font-weight-medium">Midtrans</span>
                  </div>
                  <div class="d-flex justify-space-between mb-3">
                    <span class="text-body-2 text-medium-emphasis">Kode Perusahaan:</span>
                    <span class="text-body-2 font-weight-medium">{{ transactionDetails.billerCode }}</span>
                  </div>
                  <v-text-field
                    :model-value="transactionDetails.paymentCode"
                    label="Kode Bayar"
                    readonly
                    variant="outlined"
                    density="comfortable"
                    hide-details
                    class="font-weight-bold text-h6 payment-code-field"
                  >
                    <template #append-inner>
                      <v-tooltip location="top" :text="copySuccess === 'Kode Bayar' ? 'Tersalin!' : 'Salin Kode Bayar'">
                        <template #activator="{ props: tooltipProps }">
                          <v-btn v-bind="tooltipProps" :icon="copySuccess === 'Kode Bayar' ? 'mdi-check-all' : 'mdi-content-copy'" variant="text" density="comfortable" @click="copyToClipboard(transactionDetails?.paymentCode, 'Kode Bayar')" />
                        </template>
                      </v-tooltip>
                    </template>
                  </v-text-field>
                </v-sheet>
                <p class="text-caption mt-2 text-medium-emphasis">
                  Gunakan fitur Bill Pay / Multipayment pada {{ getEchannelBankName(transactionDetails.billerCode) }}.
                </p>
              </div>

              <div v-else-if="showQrCode" class="mb-5 text-center instruction-section">
                <p class="text-subtitle-1 font-weight-medium mb-3">
                  Scan QR Code dengan Aplikasi Anda
                </p>
                <v-sheet elevation="0" border rounded class="d-inline-block pa-3 mx-auto bg-white" style="line-height: 0;">
                  <ClientOnly>
                    <img v-if="isQrUrl" :src="qrValue" alt="QR Payment Code" :width="qrSize" :height="qrSize" style="max-width: 100%; height: auto; display: block;">
                    <QrcodeVue v-else :value="qrValue" :size="qrSize" level="H" render-as="svg" />
                  </ClientOnly>
                </v-sheet>
                <p class="text-caption mt-3 text-medium-emphasis px-2">
                  Gunakan aplikasi E-Wallet atau Mobile Banking yang mendukung <strong class="text-uppercase">{{ paymentMethod === 'qris' ? 'QRIS' : paymentMethod?.replace(/_/g, ' ') }}</strong>.
                </p>
              </div>
            </div>
            <div v-else class="text-center text-body-2 text-medium-emphasis my-5 px-3">
              <v-icon size="x-large" class="mb-3 d-block mx-auto text-info">
                mdi-information-outline
              </v-icon>
              <p style="line-height: 1.7;">
                {{ pendingInstructionFallbackMessage }}
              </p>
            </div>
          </div>

          <v-card-actions class="justify-center pa-4 bg-grey-lighten-5 border-t">
            <v-btn
              v-if="['FAILED', 'EXPIRED', 'CANCELLED', 'ERROR', 'UNKNOWN'].includes(finalStatus)"
              color="primary"
              variant="flat"
              rounded="lg"
              class="mx-2"
              @click="goToSelectPackage"
            >
              <v-icon start>
                mdi-cart-plus
              </v-icon>
              Pesan Paket Lain
            </v-btn>
            <v-btn
              v-if="finalStatus === 'SUCCESS'"
              color="primary"
              variant="flat"
              rounded="lg"
              class="mx-2"
              @click="goToDashboard"
            >
              <v-icon start>
                mdi-view-dashboard
              </v-icon>
              Ke Dashboard
            </v-btn>
            <v-btn
              v-if="finalStatus === 'PENDING'"
              color="grey-darken-1"
              variant="text"
              rounded="lg"
              class="mx-2"
              :loading="isLoading"
              @click="fetchTransactionDetails(transactionDetails.orderId)"
            >
              <v-icon start>
                mdi-refresh
              </v-icon>
              Cek Ulang Status
            </v-btn>
          </v-card-actions>
        </v-card>

        <div v-else class="text-center py-16 text-medium-emphasis">
          <v-icon size="64" class="mb-4 text-disabled d-block mx-auto">
            mdi-file-question-outline
          </v-icon>
          <p class="text-h6 mb-2">
            Data Transaksi Tidak Tersedia
          </p>
          <p class="text-body-1 mb-6 mx-auto" style="max-width: 400px;">
            Tidak dapat menampilkan detail transaksi saat ini. Pastikan Order ID sudah benar.
          </p>
          <v-btn color="primary" variant="tonal" @click="goToSelectPackage">
            Kembali Pilih Paket
          </v-btn>
        </div>
      </v-col>
    </v-row>
  </v-container>
</template>

<style scoped>
.font-mono { font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, Courier, monospace; }

.v-list-item {
  padding-top: 0.6rem;
  padding-bottom: 0.6rem;
}
.v-list-item--density-comfortable .v-list-item-title,
.v-list-item--density-comfortable .v-list-item-subtitle,
.v-list-item--density-comfortable .text-body-2,
.v-list-item--density-comfortable .text-caption {
  line-height: 1.5;
}
.v-list-item-title.text-caption {
  font-size: 0.8rem !important;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
}
span.text-body-2 {
  font-size: 0.925rem !important;
}

.vuexy-alert-sheet {
  color: white !important; /* Pastikan teks selalu putih di atas background berwarna */
}
.vuexy-alert-sheet .text-h5 {
  letter-spacing: 0.2px;
}
.vuexy-alert-sheet .text-body-2 {
  opacity: 0.9;
}

.instruction-section {
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 8px;
  padding: 1.25rem;
  background-color: rgba(var(--v-theme-surface-variant), 0.3);
}

.instruction-section .text-subtitle-1 {
  color: rgba(var(--v-theme-on-surface), var(--v-high-emphasis-opacity));
}

.va-number-field:deep(.v-field__input),
.payment-code-field:deep(.v-field__input) {
  font-size: 1.3rem !important; /* Lebih besar untuk nomor penting */
  font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, Courier, monospace;
  letter-spacing: 0.5px;
  text-align: center;
  padding-top: 10px;
  padding-bottom: 10px;
}
.va-number-field:deep(.v-field),
.payment-code-field:deep(.v-field) {
  background-color: #FFFFFF; /* Latar putih agar mudah dibaca */
}

.v-text-field:deep(.v-input__append-inner .v-btn) {
   color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
}
.v-text-field:deep(.v-input__append-inner .v-btn .v-icon) {
   font-size: 20px; /* Sesuaikan ukuran ikon copy */
}

/* Pastikan tema gelap juga terlihat baik */
.theme--dark .instruction-section {
  background-color: rgba(var(--v-theme-surface-variant), 0.5);
}
.theme--dark .va-number-field:deep(.v-field),
.theme--dark .payment-code-field:deep(.v-field) {
  background-color: rgba(var(--v-theme-surface), 0.8);
}
</style>
