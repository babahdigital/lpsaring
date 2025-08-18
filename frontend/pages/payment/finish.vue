<script setup lang="ts">
import { format, isValid as isValidDate, parseISO } from 'date-fns'
import { id as dateLocaleId } from 'date-fns/locale'
import { useNuxtApp } from 'nuxt/app'
import QrcodeVue from 'qrcode.vue'
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useDisplay } from 'vuetify'

import { useSnackbar } from '~/composables/useSnackbar'

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
type TransactionStatus = 'SUCCESS' | 'PENDING' | 'FAILED' | 'EXPIRED' | 'CANCELLED' | 'ERROR' | 'UNKNOWN' | 'error'

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

const route = useRoute()
const router = useRouter()
const { $api } = useNuxtApp()
const { add: showGlobalSnackbar } = useSnackbar()
const { smAndDown } = useDisplay()

const transactionDetails = ref<TransactionDetails | null>(null)
const isLoading = ref(true)
const fetchError = ref<string | null>(null)
const copySuccess = ref<string | null>(null)
const errorMessageFromQuery = ref<string | null>(
  typeof route.query.msg === 'string' ? decodeURIComponent(route.query.msg) : null,
)

async function fetchTransactionDetails(orderId: string) {
  isLoading.value = true
  fetchError.value = null
  try {
    const response = await $api<TransactionDetails>(`/transactions/by-order-id/${orderId}`)
    if (response == null || typeof response !== 'object' || response.midtrans_order_id == null || response.status == null)
      throw new Error('Respons API tidak valid atau tidak lengkap.')
    transactionDetails.value = response
  }
  catch (err: any) {
    const status = err.response?.status ?? err.statusCode ?? 'N/A'
    const description = err.data?.message ?? 'Terjadi kesalahan.'
    if (status === 404)
      fetchError.value = `Transaksi dengan Order ID '${orderId}' tidak ditemukan.`
    else
      fetchError.value = `Gagal memuat detail transaksi (Kode: ${status}). ${description}`
    transactionDetails.value = null
  }
  finally {
    isLoading.value = false
  }
}

onMounted(() => {
  const orderIdFromQuery = route.query.order_id as string | undefined
  const statusFromQuery = route.query.status as TransactionStatus | undefined

  if (typeof orderIdFromQuery === 'string' && orderIdFromQuery.trim() !== '') {
    fetchTransactionDetails(orderIdFromQuery.trim())
  }
  else if (statusFromQuery === 'error' && errorMessageFromQuery.value != null) {
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
  if (transactionDetails.value?.status != null && transactionDetails.value.status !== 'UNKNOWN')
    return transactionDetails.value.status
  if (statusFromQuery != null && ['SUCCESS', 'PENDING', 'FAILED', 'EXPIRED', 'CANCELLED', 'ERROR'].includes(statusFromQuery))
    return statusFromQuery
  return transactionDetails.value?.status ?? 'UNKNOWN'
})

const userPhoneNumberRaw = computed(() => transactionDetails.value?.user?.phone_number ?? null)
const userName = computed(() => transactionDetails.value?.user?.full_name ?? 'Pengguna')
const packageName = computed(() => transactionDetails.value?.package?.name ?? 'Paket Tidak Diketahui')
const paymentMethod = computed(() => transactionDetails.value?.payment_method ?? null)
const displayHotspotUsername = computed(() => formatToLocalPhone(userPhoneNumberRaw.value) ?? '-')

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
  catch { return 'Tanggal Invalid' }
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
    default: return 'Status Transaksi Tidak Diketahui'
  }
})

const detailMessage = computed((): string => {
  if (finalStatus.value === 'ERROR' && errorMessageFromQuery.value != null && transactionDetails.value == null)
    return errorMessageFromQuery.value

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
      return `Mohon selesaikan pembayaran sebelum ${formatDate(transactionDetails.value?.expiry_time)} menggunakan instruksi di bawah ini.`
    case 'FAILED':
      return `Pembayaran untuk transaksi ${transactionDetails.value?.midtrans_order_id ?? ''} telah gagal. Silakan coba untuk memesan ulang.`
    case 'EXPIRED':
      return `Batas waktu pembayaran untuk transaksi ${transactionDetails.value?.midtrans_order_id ?? ''} telah terlewati. Silakan coba untuk memesan ulang.`
    case 'CANCELLED':
      return `Transaksi ${transactionDetails.value?.midtrans_order_id ?? ''} telah dibatalkan.`
    case 'ERROR':
      return 'Terjadi kesalahan pada proses pembayaran. Jika Anda merasa ini adalah kesalahan sistem, silakan hubungi administrator.'
    default:
      return 'Status transaksi ini belum dapat dipastikan. Sistem kami sedang melakukan pengecekan lebih lanjut.'
  }
})

async function copyToClipboard(textToCopy: string | undefined | null, type: string) {
  if (textToCopy == null || navigator.clipboard == null) {
    showGlobalSnackbar({ type: 'error', title: 'Gagal', text: 'Gagal menyalin: Fitur tidak didukung oleh browser Anda.' })
    return
  }
  try {
    await navigator.clipboard.writeText(textToCopy)
    copySuccess.value = type
    showGlobalSnackbar({ type: 'success', title: 'Berhasil', text: `${type} berhasil disalin ke clipboard!` })
    setTimeout(() => {
      copySuccess.value = null
    }, 2500)
  }
  catch {
    showGlobalSnackbar({ type: 'error', title: 'Gagal', text: `Gagal menyalin ${type}.` })
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
    if (!bankCode)
      return 'Bank'
    const bankMap: { [key: string]: string } = { bca: 'BCA', bni: 'BNI', bri: 'BRI', cimb: 'CIMB Niaga', permata: 'Bank Permata', mandiri: 'Mandiri', bsi: 'BSI' }
    return bankMap[bankCode] ?? bankCode.toUpperCase()
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
  if (finalStatus.value !== 'PENDING' || transactionDetails.value == null)
    return false
  const td = transactionDetails.value
  const pm = td.payment_method?.toLowerCase()
  const hasVa = td.va_number != null && (pm?.includes('_va') === true || pm === 'bank_transfer')
  const hasEchannel = td.payment_code != null && td.biller_code != null && pm === 'echannel'
  const hasQr = td.qr_code_url != null && (pm === 'qris' || pm === 'gopay' || pm === 'shopeepay')
  return hasVa || hasEchannel || hasQr
})

const qrValue = computed(() => transactionDetails.value?.qr_code_url ?? '')
const showQrCode = computed(() => {
  if (finalStatus.value !== 'PENDING' || qrValue.value === '')
    return false
  const pm = paymentMethod.value?.toLowerCase()
  return pm === 'qris' || pm === 'gopay' || pm === 'shopeepay'
})
const qrSize = computed(() => smAndDown.value ? 200 : 250)

definePageMeta({
  layout: 'blank',
  auth: false, // Halaman ini harus bisa diakses dari captive browser tanpa auth check
})
useHead({ title: computed(() => `Status: ${alertTitle.value}`) })
</script>

<template>
  <VContainer fluid class="fill-height bg-surface pa-0 ma-0">
    <VRow justify="center" align="center" class="fill-height py-md-8 py-4 px-4">
      <VCol cols="12" sm="11" md="9" lg="7" xl="5" class="mx-auto">
        <div v-if="isLoading" class="text-center pa-10">
          <VProgressCircular indeterminate color="primary" size="64" width="6" />
          <p class="text-h6 mt-8 text-medium-emphasis font-weight-regular">
            Memeriksa Status Transaksi Anda...
          </p>
        </div>

        <VCard v-else-if="fetchError" variant="tonal" color="error" class="mx-auto rounded-xl pa-2">
          <VCardText class="text-center pa-6">
            <!-- ICON UPDATE: plug-connected-x -->
            <svg xmlns="http://www.w3.org/2000/svg" class="mb-4 text-error" width="64" height="64" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" fill="none" stroke-linecap="round" stroke-linejoin="round"><path stroke="none" d="M0 0h24v24H0z" fill="none" /><path d="M20 12l-8 -8l-8 8" /><path d="M4 12v-2a2 2 0 0 1 2 -2h12a2 2 0 0 1 2 2v2" /><path d="M14 13l-2 2" /><path d="M10 13l2 2" /><path d="M12 18v4" /><path d="M10 22h4" /></svg>
            <h2 class="text-h5 font-weight-bold mb-3">
              Gagal Memuat Transaksi
            </h2>
            <p class="text-body-1 mb-6 text-medium-emphasis">
              {{ fetchError }}
            </p>
            <VBtn color="primary" variant="flat" size="large" @click="goToSelectPackage">
              <!-- ICON UPDATE: arrow-back-up -->
              <svg xmlns="http://www.w3.org/2000/svg" class="me-2" width="20" height="20" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" fill="none" stroke-linecap="round" stroke-linejoin="round"><path stroke="none" d="M0 0h24v24H0z" fill="none" /><path d="M9 14l-4 -4l4 -4" /><path d="M5 10h11a4 4 0 1 1 0 8h-1" /></svg>
              Kembali ke Pilihan Paket
            </VBtn>
          </VCardText>
        </VCard>

        <VCard v-else-if="transactionDetails" variant="flat" border class="mx-auto rounded-xl overflow-hidden">
          <VAlert
            :type="alertType"
            variant="flat"
            class="pa-6 text-center"
            :title="alertTitle"
            :text="detailMessage"
            prominent
            tile
          />

          <VCardText class="pa-0">
            <VList lines="two" density="comfortable" class="py-2 bg-transparent">
              <VListItem class="px-sm-6 px-4">
                <template #prepend>
                  <!-- ICON UPDATE: hash -->
                  <div class="mr-5">
                    <svg xmlns="http://www.w3.org/2000/svg" class="text-medium-emphasis" width="24" height="24" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" fill="none" stroke-linecap="round" stroke-linejoin="round"><path stroke="none" d="M0 0h24v24H0z" fill="none" /><path d="M5 9l14 0" /><path d="M5 15l14 0" /><path d="M11 4l-4 16" /><path d="M17 4l-4 16" /></svg>
                  </div>
                </template>
                <VListItemTitle class="font-weight-bold">
                  {{ transactionDetails.midtrans_order_id }}
                </VListItemTitle>
                <VListItemSubtitle class="text-medium-emphasis">
                  Order ID
                </VListItemSubtitle>
              </VListItem>

              <VDivider v-if="transactionDetails.midtrans_transaction_id" class="mx-6 my-1" />

              <VListItem v-if="transactionDetails.midtrans_transaction_id" class="px-sm-6 px-4">
                <template #prepend>
                  <!-- ICON UPDATE: scan -->
                  <div class="mr-5">
                    <svg xmlns="http://www.w3.org/2000/svg" class="text-medium-emphasis" width="24" height="24" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" fill="none" stroke-linecap="round" stroke-linejoin="round"><path stroke="none" d="M0 0h24v24H0z" fill="none" /><path d="M4 7v-1a2 2 0 0 1 2 -2h2" /><path d="M4 17v1a2 2 0 0 0 2 2h2" /><path d="M16 4h2a2 2 0 0 1 2 2v1" /><path d="M16 20h2a2 2 0 0 0 2 -2v-1" /><path d="M5 12l14 0" /></svg>
                  </div>
                </template>
                <VListItemTitle class="font-weight-bold font-mono">
                  {{ transactionDetails.midtrans_transaction_id }}
                </VListItemTitle>
                <VListItemSubtitle class="text-medium-emphasis">
                  ID Pembayaran
                </VListItemSubtitle>
              </VListItem>

              <VDivider class="mx-6 my-1" />

              <VListItem class="px-sm-6 px-4">
                <template #prepend>
                  <!-- ICON UPDATE: package -->
                  <div class="mr-5">
                    <svg xmlns="http://www.w3.org/2000/svg" class="text-medium-emphasis" width="24" height="24" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" fill="none" stroke-linecap="round" stroke-linejoin="round"><path stroke="none" d="M0 0h24v24H0z" fill="none" /><path d="M12 3l8 4.5l0 9l-8 4.5l-8 -4.5l0 -9l8 -4.5" /><path d="M12 12l8 -4.5" /><path d="M12 12l0 9" /><path d="M12 12l-8 -4.5" /><path d="M16 5.25l-8 4.5" /></svg>
                  </div>
                </template>
                <VListItemTitle class="font-weight-bold">
                  {{ packageName }}
                </VListItemTitle>
                <VListItemSubtitle class="text-medium-emphasis">
                  Paket yang Dibeli
                </VListItemSubtitle>
              </VListItem>

              <VDivider class="mx-6 my-1" />

              <VListItem class="px-sm-6 px-4">
                <template #prepend>
                  <!-- ICON UPDATE: receipt-2 -->
                  <div class="mr-5">
                    <svg xmlns="http://www.w3.org/2000/svg" class="text-medium-emphasis" width="24" height="24" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" fill="none" stroke-linecap="round" stroke-linejoin="round"><path stroke="none" d="M0 0h24v24H0z" fill="none" /><path d="M5 21v-16a2 2 0 0 1 2 -2h10a2 2 0 0 1 2 2v16l-3 -2l-2 2l-2 -2l-2 2l-2 -2l-3 2" /><path d="M14 8h-2.5a1.5 1.5 0 0 0 0 3h1.5a1.5 1.5 0 0 1 0 3h-2.5" /><path d="M12 14v1" /><path d="M12 7v1" /></svg>
                  </div>
                </template>
                <VListItemTitle class="text-h6 font-weight-bold text-success">
                  {{ formatCurrency(transactionDetails.amount) }}
                </VListItemTitle>
                <VListItemSubtitle class="text-medium-emphasis">
                  Total Tagihan
                </VListItemSubtitle>
              </VListItem>
            </VList>
          </VCardText>

          <div v-if="finalStatus === 'PENDING' && showSpecificPendingInstructions" class="px-sm-6 px-4 pb-6 pt-3">
            <VDivider class="mb-6" />
            <h3 class="text-h6 font-weight-bold mb-5 text-center text-high-emphasis">
              Instruksi Pembayaran
            </h3>

            <div v-if="transactionDetails.va_number" class="mb-4">
              <p class="text-body-1 font-weight-medium mb-2 text-medium-emphasis">
                {{ getBankNameFromVA(paymentMethod) }} Virtual Account
              </p>
              <VTextField
                :model-value="transactionDetails.va_number"
                label="Nomor Virtual Account"
                readonly
                variant="outlined"
                density="comfortable"
                hide-details
                class="font-weight-bold text-h6"
              >
                <template #append-inner>
                  <VTooltip location="top" :text="copySuccess === 'Nomor VA' ? 'Berhasil Disalin!' : 'Salin Nomor VA'">
                    <template #activator="{ props: tooltipProps }">
                      <VBtn
                        v-bind="tooltipProps"
                        :color="copySuccess === 'Nomor VA' ? 'success' : ''"
                        variant="text"
                        @click="copyToClipboard(transactionDetails?.va_number, 'Nomor VA')"
                      >
                        <!-- ICON UPDATE: check vs copy -->
                        <svg v-if="copySuccess === 'Nomor VA'" xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" fill="none" stroke-linecap="round" stroke-linejoin="round"><path stroke="none" d="M0 0h24v24H0z" fill="none" /><path d="M5 12l5 5l10 -10" /></svg>
                        <svg v-else xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" fill="none" stroke-linecap="round" stroke-linejoin="round"><path stroke="none" d="M0 0h24v24H0z" fill="none" /><path d="M7 7h-1a2 2 0 0 0 -2 2v9a2 2 0 0 0 2 2h9a2 2 0 0 0 2 -2v-1" /><path d="M10 14h-1a2 2 0 0 1 -2 -2v-9a2 2 0 0 1 2 -2h9a2 2 0 0 1 2 2v1" /><path d="M13 10h7" /><path d="M13 13h7" /><path d="M13 16h7" /></svg>
                      </VBtn>
                    </template>
                  </VTooltip>
                </template>
              </VTextField>
            </div>

            <div v-else-if="showQrCode" class="mb-4 text-center">
              <p class="text-body-1 font-weight-medium mb-3 text-medium-emphasis">
                Scan QR Code Menggunakan Aplikasi Pembayaran Anda
              </p>
              <VSheet border rounded="lg" class="d-inline-block pa-3 mx-auto bg-white">
                <QrcodeVue :value="qrValue" :size="qrSize" level="H" render-as="svg" />
              </VSheet>
            </div>
          </div>

          <VDivider />
          <VCardActions class="pa-4 bg-surface-variant">
            <div class="d-flex flex-column ga-3" style="width: 100%;">
              <VBtn
                v-if="['FAILED', 'EXPIRED', 'CANCELLED', 'ERROR', 'UNKNOWN'].includes(finalStatus)"
                color="primary" variant="tonal" size="large" rounded="lg"
                @click="goToSelectPackage"
              >
                <!-- ICON UPDATE: shopping-cart-plus -->
                <svg xmlns="http://www.w3.org/2000/svg" class="me-2" width="20" height="20" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" fill="none" stroke-linecap="round" stroke-linejoin="round"><path stroke="none" d="M0 0h24v24H0z" fill="none" /><path d="M4 19a2 2 0 1 0 4 0a2 2 0 1 0 -4 0" /><path d="M12.5 17h-6.5v-14h-2" /><path d="M6 5l14 1l-.86 6.017m-2.64 .983h-10.5" /><path d="M16 19h6" /><path d="M19 16v6" /></svg>
                Pesan Paket Baru
              </VBtn>
              <VBtn
                v-if="finalStatus === 'SUCCESS'"
                color="primary" variant="tonal" size="large" rounded="lg"
                @click="goToDashboard"
              >
                <!-- ICON UPDATE: layout-dashboard -->
                <svg xmlns="http://www.w3.org/2000/svg" class="me-2" width="20" height="20" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" fill="none" stroke-linecap="round" stroke-linejoin="round"><path stroke="none" d="M0 0h24v24H0z" fill="none" /><path d="M4 4h6v8h-6z" /><path d="M4 16h6v4h-6z" /><path d="M14 12h6v8h-6z" /><path d="M14 4h6v4h-6z" /></svg>
                Buka Dashboard
              </VBtn>
              <VBtn
                v-if="finalStatus === 'PENDING'"
                variant="text" size="large" rounded="lg"
                :loading="isLoading"
                @click="fetchTransactionDetails(transactionDetails.midtrans_order_id)"
              >
                <!-- ICON UPDATE: refresh -->
                <svg xmlns="http://www.w3.org/2000/svg" class="me-2" width="20" height="20" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" fill="none" stroke-linecap="round" stroke-linejoin="round"><path stroke="none" d="M0 0h24v24H0z" fill="none" /><path d="M20 11a8.1 8.1 0 0 0 -15.5 -2m-.5 -4v4h4" /><path d="M4 13a8.1 8.1 0 0 0 15.5 2m.5 4v-4h-4" /></svg>
                Cek Ulang Status Pembayaran
              </VBtn>
            </div>
          </VCardActions>
        </VCard>
      </VCol>
    </VRow>
  </VContainer>
</template>

<style scoped>
.font-mono { font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, Courier, monospace; }
.v-text-field .v-field--variant-outlined .v-field__input {
  font-size: 1.25rem !important;
}
</style>
