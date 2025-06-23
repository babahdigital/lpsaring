<script setup lang="ts">
import type { VIcon } from 'vuetify/components'
import { useNuxtApp } from '#app'
import { ClientOnly } from '#components'
import { format, isValid as isValidDate, parseISO } from 'date-fns'
import { id as dateLocaleId } from 'date-fns/locale'
import QrcodeVue from 'qrcode.vue'
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

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
  amount?: number | null
  payment_method?: string | null
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
const { $api, $snackbar } = useNuxtApp()

const transactionDetails = ref<TransactionDetails | null>(null)
const isLoading = ref(true)
const fetchError = ref<string | null>(null)
const copySuccess = ref<string | null>(null)
const errorMessageFromQuery = ref<string | null>(
  route.query.msg ? decodeURIComponent(route.query.msg as string) : null,
)

async function fetchTransactionDetails(orderId: string) {
  isLoading.value = true
  fetchError.value = null
  try {
    const response = await $api<TransactionDetails>(`/transactions/by-order-id/${orderId}`)
    if (!response || typeof response !== 'object' || !response.midtrans_order_id || !response.status) {
      throw new Error('Respons API tidak valid atau tidak lengkap.')
    }
    transactionDetails.value = response
  }
  catch (err: any) {
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
  }
}

onMounted(() => {
  const orderIdFromQuery = route.query.order_id as string | undefined
  const statusFromQuery = route.query.status as TransactionStatus | undefined

  if (orderIdFromQuery && orderIdFromQuery.trim() !== '') {
    fetchTransactionDetails(orderIdFromQuery.trim())
  }
  else if (statusFromQuery === 'error' && errorMessageFromQuery.value) {
    fetchError.value = `Pembayaran Gagal: ${errorMessageFromQuery.value}`
    isLoading.value = false
  }
  else {
    fetchError.value = 'Order ID tidak valid atau tidak ditemukan.'
    isLoading.value = false
  }
})

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
const userName = computed(() => transactionDetails.value?.user?.full_name || 'Pengguna')
const packageName = computed(() => transactionDetails.value?.package?.name || 'Paket Tidak Diketahui')
const paymentMethod = computed(() => transactionDetails.value?.payment_method || null)
const displayHotspotUsername = computed(() => formatToLocalPhone(userPhoneNumberRaw.value) || '-')

function formatToLocalPhone(phoneNumber?: string | null): string {
  if (!phoneNumber)
    return '-'
  const cleaned = phoneNumber.replace(/\D/g, '')
  if (cleaned.startsWith('62'))
    return `0${cleaned.substring(2)}`
  return phoneNumber
}

function formatDate(isoString?: string | null): string {
  if (!isoString)
    return '-'
  try {
    const parsedDate = parseISO(isoString)
    if (!isValidDate(parsedDate))
      throw new Error('Invalid date')
    return format(parsedDate, 'iiii, dd MMMM yyyy, HH:mm \'WITA\'', { locale: dateLocaleId })
  }
  catch {
    return 'Tanggal Invalid'
  }
}

function formatCurrency(value?: number | null): string {
  if (value === null || value === undefined)
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
    case 'SUCCESS': return 'Pembayaran Berhasil!'
    case 'PENDING': return 'Menunggu Pembayaran'
    case 'FAILED': return 'Pembayaran Gagal'
    case 'EXPIRED': return 'Waktu Pembayaran Habis'
    case 'CANCELLED': return 'Transaksi Dibatalkan'
    case 'ERROR': return 'Terjadi Kesalahan Pembayaran'
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
  const safePackageName = packageName.value || 'paket yang dipilih'
  const safeUsername = displayHotspotUsername.value || 'akun Anda'
  const safePhoneNumber = formatToLocalPhone(userPhoneNumberRaw.value) || 'nomor Anda'

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
      return `Selesaikan pembayaran sebelum ${formatDate(transactionDetails.value?.expiry_time)} menggunakan instruksi di bawah.`
    case 'FAILED':
      return `Pembayaran untuk transaksi ${transactionDetails.value?.midtrans_order_id || ''} gagal. Silakan coba pesan ulang.`
    case 'EXPIRED':
      return `Batas waktu pembayaran untuk transaksi ${transactionDetails.value?.midtrans_order_id || ''} telah terlewati. Silakan pesan ulang.`
    case 'CANCELLED':
      return `Transaksi ${transactionDetails.value?.midtrans_order_id || ''} telah dibatalkan.`
    case 'ERROR':
      return `Terjadi kesalahan pada proses pembayaran. Jika Anda merasa ini adalah kesalahan sistem, silakan hubungi admin.`
    default:
      return 'Status transaksi ini belum dapat dipastikan. Sistem sedang melakukan pengecekan.'
  }
})

async function copyToClipboard(textToCopy: string | undefined | null, type: string) {
  if (!textToCopy || !navigator.clipboard) {
    $snackbar.add({ type: 'error', text: 'Gagal menyalin: Fitur tidak didukung.' })
    return
  }
  try {
    await navigator.clipboard.writeText(textToCopy)
    copySuccess.value = type
    $snackbar.add({ type: 'success', text: `${type} berhasil disalin!` })
    setTimeout(() => { copySuccess.value = null }, 2500)
  }
  catch {
    $snackbar.add({ type: 'error', text: `Gagal menyalin ${type}.` })
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
    const bankMap: { [key: string]: string } = { bca: 'BCA', bni: 'BNI', bri: 'BRI', cimb: 'CIMB Niaga', permata: 'Bank Permata', mandiri: 'Mandiri', bsi: 'BSI' }
    return bankMap[bankCode] || bankCode.toUpperCase()
  }
  return paymentMethodValue.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())
}

function goToSelectPackage() {
  router.push({ path: '/beli' })
}

function goToDashboard() {
  router.push({ path: '/dashboard' })
}

const showSpecificPendingInstructions = computed(() => {
  if (finalStatus.value !== 'PENDING' || !transactionDetails.value)
    return false
  const td = transactionDetails.value
  const pm = td.payment_method?.toLowerCase()
  const hasVa = !!td.va_number && (pm?.includes('_va') || pm === 'bank_transfer')
  const hasEchannel = !!td.payment_code && !!td.biller_code && pm === 'echannel'
  const hasQr = !!td.qr_code_url && (pm === 'qris' || pm === 'gopay' || pm === 'shopeepay')
  return hasVa || hasEchannel || hasQr
})

const qrValue = computed(() => transactionDetails.value?.qr_code_url ?? '')
const showQrCode = computed(() => {
  if (finalStatus.value !== 'PENDING' || !qrValue.value)
    return false
  const pm = paymentMethod.value?.toLowerCase()
  return pm === 'qris' || pm === 'gopay' || pm === 'shopeepay'
})
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
          type="error" variant="tonal" prominent border="start"
          class="mx-auto rounded-lg elevation-2 pa-5 text-center"
          max-width="600" icon="mdi-alert-octagon-outline"
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
              </v-icon>Kembali Pilih Paket
            </v-btn>
          </div>
        </v-alert>

        <v-card v-else-if="transactionDetails" elevation="3" rounded="xl" class="mx-auto overflow-hidden">
          <v-sheet :color="alertType" class="pa-5 text-center text-white">
            <v-icon :icon="alertIcon" size="48" class="mb-3" />
            <div class="text-h5 font-weight-bold mb-1">
              {{ alertTitle }}
            </div>
            <p class="text-body-2 mx-auto" style="max-width: 90%; line-height: 1.6; opacity: 0.9;">
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
                <span class="text-body-2 font-weight-medium font-mono">{{ transactionDetails.midtrans_order_id }}</span>
              </template>
            </v-list-item>
            <v-list-item v-if="transactionDetails.midtrans_transaction_id" class="px-sm-5 px-3">
              <template #prepend>
                <v-icon size="20" class="mr-4 text-disabled">
                  mdi-barcode-scan
                </v-icon>
              </template>
              <v-list-item-title class="text-caption text-medium-emphasis">
                ID Pembayaran
              </v-list-item-title>
              <template #append>
                <span class="text-body-2 font-mono">{{ transactionDetails.midtrans_transaction_id }}</span>
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
          </v-list>

          <div v-if="finalStatus === 'PENDING'" class="px-5 pb-5 pt-3">
            <v-divider class="mb-5" />
            <p class="text-h6 font-weight-medium mb-4 text-center">
              Instruksi Pembayaran
            </p>
            <div v-if="showSpecificPendingInstructions">
              <div v-if="transactionDetails.va_number" class="mb-5">
                <p class="text-subtitle-1 font-weight-medium mb-2">
                  {{ getBankNameFromVA(paymentMethod) }} Virtual Account
                </p>
                <v-text-field
                  :model-value="transactionDetails.va_number" label="Nomor Virtual Account" readonly variant="outlined"
                  density="comfortable" hide-details class="font-weight-bold text-h6"
                >
                  <template #append-inner>
                    <v-tooltip location="top" :text="copySuccess === 'Nomor VA' ? 'Tersalin!' : 'Salin Nomor VA'">
                      <template #activator="{ props: tooltipProps }">
                        <v-btn v-bind="tooltipProps" :icon="copySuccess === 'Nomor VA' ? 'mdi-check-all' : 'mdi-content-copy'" variant="text" @click="copyToClipboard(transactionDetails?.va_number, 'Nomor VA')" />
                      </template>
                    </v-tooltip>
                  </template>
                </v-text-field>
              </div>
              <div v-else-if="showQrCode" class="mb-5 text-center">
                <p class="text-subtitle-1 font-weight-medium mb-3">
                  Scan QR Code
                </p>
                <v-sheet border rounded class="d-inline-block pa-3 mx-auto bg-white">
                  <ClientOnly>
                    <QrcodeVue :value="qrValue" :size="qrSize" level="H" render-as="svg" />
                  </ClientOnly>
                </v-sheet>
              </div>
            </div>
          </div>

          <v-card-actions class="justify-center pa-4 bg-grey-lighten-5 border-t">
            <v-btn
              v-if="['FAILED', 'EXPIRED', 'CANCELLED', 'ERROR', 'UNKNOWN'].includes(finalStatus)"
              color="primary" variant="flat" rounded="lg" @click="goToSelectPackage"
            >
              <v-icon start>
                mdi-cart-plus
              </v-icon> Pesan Paket Lain
            </v-btn>
            <v-btn v-if="finalStatus === 'SUCCESS'" color="primary" variant="flat" rounded="lg" @click="goToDashboard">
              <v-icon start>
                mdi-view-dashboard
              </v-icon> Ke Dashboard
            </v-btn>
            <v-btn v-if="finalStatus === 'PENDING'" color="grey-darken-1" variant="text" rounded="lg" :loading="isLoading" @click="fetchTransactionDetails(transactionDetails.midtrans_order_id)">
              <v-icon start>
                mdi-refresh
              </v-icon> Cek Ulang Status
            </v-btn>
          </v-card-actions>
        </v-card>
      </v-col>
    </v-row>
  </v-container>
</template>

<style scoped>
.font-mono { font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, Courier, monospace; }
</style>
