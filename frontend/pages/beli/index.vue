<script setup lang="ts">
import type { VForm } from 'vuetify/components'
// Mengimpor tipe data `PackagePublic` yang sudah benar dari backend
import type { PackagePublic as Package } from '~/types/package'
import { useFetch, useNuxtApp } from '#app'
import { storeToRefs } from 'pinia'
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '~/store/auth'
import { normalize_to_e164 } from '~/utils/formatters'

// --- STRUKTUR DATA DISESUAIKAN DENGAN RESPON API BACKEND ---
// Interface ini diubah untuk mencocokkan struktur JSON dari backend (`"data": [...]`)
interface PackagesApiResponse {
  data: Package[]
  success: boolean
  message: string
}
// --- AKHIR PENYESUAIAN STRUKTUR DATA ---

const authStore = useAuthStore()
const router = useRouter()
const route = useRoute()
const { $api } = useNuxtApp()
const { ensureMidtransReady } = useMidtransSnap()

const { isLoggedIn, user, loadingUser } = storeToRefs(authStore)

interface FocusableField { focus: () => void }

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

// --- PERBAIKAN PADA FUNGSI FETCH ---
// DIPERBAIKI: Memberikan nilai default `ref(null)` untuk `fetchPackagesError`
// untuk memastikan variabel ini selalu terdefinisi sebagai ref, bahkan jika `useApiFetch` tidak mengembalikan properti `error`.
const packagesRequest = useFetch<PackagesApiResponse>('/packages', {
  key: 'publicPackages',
  lazy: true,
  server: true,
  $fetch: $api,
})

const { pending: isLoadingPackages, error: fetchPackagesError, refresh: refreshPackages } = packagesRequest
const packageApiResponse = packagesRequest.data as Ref<PackagesApiResponse | null>

const packages = computed(() => (packageApiResponse.value?.data ?? []))
// --- AKHIR PERBAIKAN ---

// State untuk dialog, formulir, pembayaran, dan notifikasi
const showContactDialog = ref(false)
const isContactFormValid = ref(false)
const contactFormRef = ref<InstanceType<typeof VForm> | null>(null)
const fullNameInput = ref('')
const phoneNumberInput = ref('')
const fullNameInputRef = ref<FocusableField | null>(null)
const isCheckingUser = ref(false)
const contactSubmitError = ref<string | null>(null)
const selectedPackageId = ref<string | null>(null)
const isInitiatingPayment = ref<string | null>(null)
const isHydrated = ref(false)
const hasAutoInitiatedDebt = ref(false)

const snackbarVisible = ref(false)
const snackbarText = ref('')
const snackbarColor = ref<'error' | 'success' | 'info' | 'warning'>('info')
const snackbarTimeout = ref(5000)

// DIPERBAIKI: Menyederhanakan `watch` untuk penanganan galat yang lebih bersih dan standar.
watch(fetchPackagesError, (newError) => {
  // Memeriksa jika `newError` (nilai dari ref `fetchPackagesError`) ada (tidak null)
  if (newError && newError.statusCode !== 401 && newError.statusCode !== 403) {
    const messageFromServer = (newError as any)?.data?.message
    const errorMessage = (typeof messageFromServer === 'string' && messageFromServer)
      ? messageFromServer
      : 'Gagal memuat daftar paket.'
    showSnackbar(`Gagal memuat daftar paket: ${errorMessage}`, 'error')
  }
})

// Fungsi utilitas dan aturan validasi (tidak ada perubahan)
function showSnackbar(text: string, color: 'error' | 'success' | 'info' | 'warning' = 'info', timeout = 5000) {
  snackbarText.value = text
  snackbarColor.value = color
  snackbarTimeout.value = timeout
  snackbarVisible.value = true
}

const nameRules = [
  (v: string) => (v != null && v.trim() !== '') || 'Nama Lengkap wajib diisi.',
  (v: string) => (v != null && v.trim().length >= 2) || 'Nama minimal 2 karakter.',
]
const phoneRules = [
  (v: string) => (v != null && v.trim() !== '') || 'Nomor WhatsApp wajib diisi.',
  (v: string) => {
    try {
      normalize_to_e164(v)
      return true
    }
    catch (error: any) {
      return error instanceof Error && error.message !== ''
        ? error.message
        : 'Format nomor tidak valid. Gunakan format +<kodeNegara><nomor> atau format lokal 08...'
    }
  },
]

// --- FUNGSI FORMATTING YANG DISEMPURNAKAN ---
function formatQuota(gb: number | undefined): string {
  if (gb === undefined || gb === null || gb < 0)
    return 'N/A'
  if (gb === 0)
    return 'Unlimited'
  return `${gb} GB`
}

function formatCurrency(value: number | undefined): string {
  if (value === undefined || value === null)
    return 'Harga N/A'
  return new Intl.NumberFormat('id-ID', { style: 'currency', currency: 'IDR', minimumFractionDigits: 0, maximumFractionDigits: 0 }).format(value)
}

function formatPricePerDay(price?: number | null, days?: number | null): string {
  if (price == null || days == null || days <= 0)
    return 'N/A'
  const value = Math.round(price / days)
  return new Intl.NumberFormat('id-ID', { style: 'currency', currency: 'IDR', minimumFractionDigits: 0, maximumFractionDigits: 0 }).format(value)
}

function formatPricePerGb(price?: number | null, quotaGb?: number | null): string {
  if (price == null || quotaGb == null || quotaGb <= 0)
    return 'N/A'
  const value = Math.round(price / quotaGb)
  return new Intl.NumberFormat('id-ID', { style: 'currency', currency: 'IDR', minimumFractionDigits: 0, maximumFractionDigits: 0 }).format(value)
}

function normalizePhoneNumber(phone: string | null | undefined): string {
  if (phone == null || phone === '')
    return ''
  try {
    return normalize_to_e164(phone)
  }
  catch {
    return ''
  }
}
// --- AKHIR FUNGSI FORMATTING ---

const userGreeting = computed(() => {
  if (isLoggedIn.value && user.value) {
    const name = user.value.full_name
    const nameToDisplay = (name != null && name.trim() !== '') ? name : (user.value.phone_number ?? '')
    const firstName = nameToDisplay.split(' ')[0] || 'Pengguna'
    return `Halo, ${firstName}!`
  }
  return null
})

const isUserApprovedAndActive = computed(() => {
  return isLoggedIn.value && user.value?.is_active === true && user.value.approval_status === 'APPROVED'
})

function retryFetch() {
  snackbarVisible.value = false
  refreshPackages()
}

function goToLogin() {
  router.push({ path: '/login', query: { redirect: '/beli' } })
}
function goToRegister() {
  router.push({ path: '/register', query: { redirect: '/beli' } })
}
function goToDashboard() {
  router.push('/dashboard')
}

// Logika penanganan event (tidak ada perubahan)
function handlePackageSelection(pkg: Package) {
  if (pkg?.id == null || pkg.is_active !== true || isInitiatingPayment.value != null)
    return
  selectedPackageId.value = pkg.id
  if (!isLoggedIn.value) {
    contactFormRef.value?.reset()
    contactFormRef.value?.resetValidation()
    contactSubmitError.value = null
    showContactDialog.value = true
    nextTick(() => fullNameInputRef.value?.focus())
  }
  else if (!isUserApprovedAndActive.value) {
    let warningMsg = 'Akun Anda belum aktif atau disetujui Admin untuk melakukan pembelian.'
    if (user.value?.approval_status === 'PENDING') {
      warningMsg = 'Akun Anda sedang menunggu persetujuan Admin.'
    }
    else if (user.value?.approval_status === 'REJECTED') {
      warningMsg = 'Pendaftaran akun Anda telah ditolak.'
    }
    showSnackbar(warningMsg, 'warning', 7000)
  }
  else if (user.value?.id != null) {
    initiatePayment(pkg.id)
  }
}

async function handleContactSubmit() {
  if (contactFormRef.value == null)
    return
  const { valid } = await contactFormRef.value.validate()
  if (valid !== true)
    return
  isCheckingUser.value = true
  contactSubmitError.value = null
  try {
    const phoneToSubmit = normalizePhoneNumber(phoneNumberInput.value)
    const response = await $api<{ user_exists: boolean }>('/users/check-or-register', {
      method: 'POST',
      body: { phone_number: phoneToSubmit, full_name: fullNameInput.value.trim() },
    })
    showContactDialog.value = false
    if (response.user_exists === true) {
      showSnackbar('Nomor Anda sudah terdaftar. Silakan login.', 'info')
      goToLogin()
    }
    else {
      showSnackbar('Nomor Anda belum terdaftar. Silakan registrasi.', 'info')
      goToRegister()
    }
  }
  catch (err: any) {
    let errorMessage = 'Terjadi kesalahan.'
    if (err != null && typeof err.data === 'object' && err.data != null) {
      const message = err.data.message
      if (typeof message === 'string' && message.length > 0) {
        errorMessage = message
      }
    }
    contactSubmitError.value = errorMessage
  }
  finally {
    isCheckingUser.value = false
  }
}

async function initiatePayment(packageId: string) {
  isInitiatingPayment.value = packageId
  try {
    try {
      await ensureMidtransReady()
    }
    catch (error) {
      const fallbackMessage = error instanceof Error && error.message
        ? error.message
        : 'Gagal memuat Midtrans Snap.'
      throw new Error(fallbackMessage)
    }
    if (window.snap == null) {
      throw new Error('Midtrans belum siap. Silakan coba beberapa saat lagi.')
    }
    const responseData = await $api<{ snap_token: string, order_id: string }>('/transactions/initiate', {
      method: 'POST',
      body: { package_id: packageId },
    })
    const initiatedOrderId = responseData?.order_id
    if ((responseData?.snap_token != null && responseData.snap_token !== '') && window.snap != null) {
      window.snap.pay(responseData.snap_token, {
        onSuccess: (result: SnapPayResult) => router.push(`/payment/finish?status=success&order_id=${result.order_id}`),
        onPending: (result: SnapPayResult) => router.push(`/payment/finish?status=pending&order_id=${result.order_id}`),
        onError: (result: SnapPayResult) => router.push(`/payment/finish?status=error&order_id=${result.order_id}`),
        onClose: () => {
          if (typeof initiatedOrderId === 'string' && initiatedOrderId !== '') {
            void $api(`/transactions/${encodeURIComponent(initiatedOrderId)}/cancel`, { method: 'POST' }).catch(() => {})
          }
          if (router.currentRoute.value.path.startsWith('/payment/finish') !== true) {
            showSnackbar('Anda menutup jendela pembayaran.', 'info')
          }
          isInitiatingPayment.value = null
        },
      })
    }
    else { throw new Error('Gagal mendapatkan token pembayaran.') }
  }
  catch (err: any) {
    let errorMessage = 'Gagal memulai pembayaran.'
    if (err != null && typeof err.data === 'object' && err.data != null) {
      const message = err.data.message
      if (typeof message === 'string' && message.length > 0) {
        errorMessage = message
      }
    }
    showSnackbar(errorMessage, 'error')
    isInitiatingPayment.value = null
  }
}

async function initiateDebtSettlementPayment() {
  if (isInitiatingPayment.value != null)
    return
  isInitiatingPayment.value = 'debt'
  try {
    try {
      await ensureMidtransReady()
    }
    catch (error) {
      const fallbackMessage = error instanceof Error && error.message
        ? error.message
        : 'Gagal memuat Midtrans Snap.'
      throw new Error(fallbackMessage)
    }
    if (window.snap == null)
      throw new Error('Midtrans belum siap. Silakan coba beberapa saat lagi.')

    const responseData = await $api<{ snap_token: string, order_id: string }>('/transactions/debt/initiate', {
      method: 'POST',
    })
    const initiatedOrderId = responseData?.order_id

    if ((responseData?.snap_token != null && responseData.snap_token !== '') && window.snap != null) {
      window.snap.pay(responseData.snap_token, {
        onSuccess: (result: SnapPayResult) => router.push(`/payment/finish?status=success&order_id=${result.order_id}`),
        onPending: (result: SnapPayResult) => router.push(`/payment/finish?status=pending&order_id=${result.order_id}`),
        onError: (result: SnapPayResult) => router.push(`/payment/finish?status=error&order_id=${result.order_id}`),
        onClose: () => {
          if (typeof initiatedOrderId === 'string' && initiatedOrderId !== '') {
            void $api(`/transactions/${encodeURIComponent(initiatedOrderId)}/cancel`, { method: 'POST' }).catch(() => {})
          }
          if (router.currentRoute.value.path.startsWith('/payment/finish') !== true)
            showSnackbar('Anda menutup jendela pembayaran.', 'info')
          isInitiatingPayment.value = null
        },
      })
    }
    else {
      throw new Error('Gagal mendapatkan token pembayaran.')
    }
  }
  catch (err: any) {
    let errorMessage = 'Gagal memulai pembayaran.'
    if (err != null && typeof err.data === 'object' && err.data != null) {
      const message = err.data.message
      if (typeof message === 'string' && message.length > 0)
        errorMessage = message
    }
    showSnackbar(errorMessage, 'error', 8000)
    isInitiatingPayment.value = null
  }
}

function closeContactDialog() {
  if (isCheckingUser.value !== true)
    showContactDialog.value = false
}

onMounted(async () => {
  isHydrated.value = true
  if (authStore.initialAuthCheckDone !== true) {
    await authStore.initializeAuth()
  }

  // Jika pengguna datang dari tombol "Lunasi" di dashboard, otomatis buka pembayaran
  // untuk paket termurah (backend sudah order_by price).
  if (route.query?.intent === 'debt' && hasAutoInitiatedDebt.value !== true) {
    hasAutoInitiatedDebt.value = true

    if (!isLoggedIn.value) {
      showSnackbar('Silakan login terlebih dulu untuk melunasi tunggakan.', 'warning', 6000)
    }
    else if (!isUserApprovedAndActive.value) {
      showSnackbar('Akun Anda belum aktif atau belum disetujui Admin untuk melakukan pembayaran.', 'warning', 7000)
    }
    else {
      try {
        showSnackbar('Membuka pembayaran pelunasan tunggakan…', 'info', 4500)
        await initiateDebtSettlementPayment()
      }
      catch {
        showSnackbar('Gagal memulai pembayaran pelunasan tunggakan.', 'error', 7000)
      }
    }

    // Bersihkan query agar tidak auto-trigger lagi saat refresh.
    const nextQuery = { ...(route.query as Record<string, any>) }
    delete nextQuery.intent
    router.replace({ query: nextQuery })
  }

  const query = route.query
  if (query.action === 'cancelled' && (query.order_id != null && query.order_id !== '')) {
    showSnackbar(`Pembayaran Order ID ${query.order_id} dibatalkan.`, 'info')
    router.replace({ query: {} })
  }
  else if (query.action === 'error' && (query.order_id != null && query.order_id !== '')) {
    const errorMsg = (query.msg != null && query.msg !== '') ? decodeURIComponent(query.msg as string) : 'Terjadi kesalahan pembayaran'
    showSnackbar(`Pembayaran Order ID ${query.order_id} gagal: ${errorMsg}`, 'error', 8000)
    router.replace({ query: {} })
  }
})

definePageMeta({ layout: 'blank' })
useHead({ title: 'Beli Paket Hotspot' })
</script>

<template>
  <v-container fluid class="pa-0 ma-0 bg-grey-lighten-5 full-height-container">
    <v-col cols="12" style="max-width: 1300px;" class="mx-auto">
      <v-container fluid class="py-8 px-lg-12 px-md-6 px-sm-4">
        <h1 class="text-h4 text-sm-h3 font-weight-bold mb-2 text-center text-grey-darken-3">
          DAFTAR PAKET HOTSPOT
        </h1>
        <div class="text-center mb-6" style="min-height: 40px;">
          <v-btn v-if="!isLoggedIn && !loadingUser" variant="text" color="primary" @click="goToLogin">
            <v-icon start icon="tabler-login" /> Sudah Punya Akun? Login
          </v-btn>
          <div v-else-if="loadingUser" class="d-flex justify-center align-center text-medium-emphasis">
            <v-progress-circular indeterminate size="20" width="2" color="primary" class="mr-2" />
            <span>Memuat data pengguna...</span>
          </div>
          <div v-else-if="userGreeting != null" class="d-flex justify-center align-center text-body-1 text-medium-emphasis flex-wrap">
            <span class="mr-3">{{ userGreeting }}</span>
            <v-btn v-if="isUserApprovedAndActive" variant="outlined" color="primary" size="small" @click="goToDashboard">
              <v-icon start icon="tabler-layout-dashboard" /> Ke Panel
            </v-btn>
          </div>
        </div>
      </v-container>

      <v-row class="ma-0" align="start" justify="center">
        <v-col cols="12">
          <v-row v-if="isLoadingPackages" justify="center" dense class="px-lg-10 px-md-4 px-sm-2">
            <v-col v-for="n in 4" :key="`skel-pkg-${n}`" cols="12" sm="6" md="4" lg="3">
              <v-skeleton-loader type="image, article, actions" height="320" />
            </v-col>
          </v-row>
          <v-row v-else-if="fetchPackagesError" justify="center" class="px-lg-10 px-md-4 px-sm-2">
            <v-col cols="12" md="8" lg="6">
              <v-alert type="error" title="Gagal Memuat Paket" variant="tonal" prominent>
                <p class="mb-4">
                  Tidak dapat mengambil daftar paket dari server.
                </p>
                <v-btn color="error" @click="retryFetch">
                  Coba Lagi
                </v-btn>
              </v-alert>
            </v-col>
          </v-row>
          <div v-else class="px-lg-10 px-md-4 px-sm-2">
            <v-row v-if="packages.length > 0" dense justify="center">
              <v-col v-for="pkg in packages" :key="pkg.id" cols="12" sm="6" md="4" lg="3" class="pa-2 d-flex">
                <v-card
                  class="d-flex flex-column flex-grow-1"
                  variant="outlined" hover rounded="lg"
                  :disabled="pkg.is_active !== true || isInitiatingPayment != null"
                  @click="handlePackageSelection(pkg)"
                >
                  <v-card-item class="text-left">
                    <v-card-title class="text-h6 text-wrap font-weight-bold mb-2">
                      {{ pkg.name }}
                    </v-card-title>
                    <v-card-subtitle class="text-h5 font-weight-bold text-primary">
                      {{ formatCurrency(pkg.price) }}
                    </v-card-subtitle>
                  </v-card-item>

                  <v-card-text class="flex-grow-1 py-2 text-left">
                    <v-list lines="one" density="compact" bg-color="transparent" class="py-0">
                      <v-list-item>
                        <template #prepend>
                          <v-icon icon="tabler-database" size="small" class="mr-2" />
                        </template>
                        <v-list-item-title class="text-body-2">
                          Kuota: <span class="font-weight-medium">{{ formatQuota(pkg.data_quota_gb) }}</span>
                        </v-list-item-title>
                      </v-list-item>
                      <v-list-item>
                        <template #prepend>
                          <v-icon icon="tabler-gauge" size="small" class="mr-2" />
                        </template>
                        <v-list-item-title class="text-body-2">
                          Kecepatan: <span class="font-weight-medium">Unlimited</span>
                        </v-list-item-title>
                      </v-list-item>
                      <v-list-item>
                        <template #prepend>
                          <v-icon icon="tabler-calendar-time" size="small" class="mr-2" />
                        </template>
                        <v-list-item-title class="text-body-2">
                          Aktif: <span class="font-weight-medium">{{ pkg.duration_days }} Hari</span>
                        </v-list-item-title>
                      </v-list-item>
                      <v-list-item>
                        <template #prepend>
                          <v-icon icon="tabler-receipt" size="small" class="mr-2" />
                        </template>
                        <v-list-item-title class="text-body-2">
                          Harga / Hari: <span class="font-weight-medium">{{ formatPricePerDay(pkg.price, pkg.duration_days) }}</span>
                        </v-list-item-title>
                      </v-list-item>
                      <v-list-item>
                        <template #prepend>
                          <v-icon icon="tabler-math-function" size="small" class="mr-2" />
                        </template>
                        <v-list-item-title class="text-body-2">
                          Harga / GB: <span class="font-weight-medium">{{ formatPricePerGb(pkg.price, pkg.data_quota_gb) }}</span>
                        </v-list-item-title>
                      </v-list-item>
                    </v-list>
                    <p v-if="pkg.description != null && pkg.description !== ''" class="text-caption text-medium-emphasis mt-3 px-1">
                      {{ pkg.description }}
                    </p>
                  </v-card-text>

                  <v-card-actions class="pa-4 mt-auto">
                    <v-btn
                      block color="primary" variant="flat" size="large"
                      :disabled="pkg.is_active !== true || isInitiatingPayment != null"
                      :loading="isInitiatingPayment === pkg.id"
                      @click.stop="handlePackageSelection(pkg)"
                    >
                      {{ pkg.is_active === true ? 'Beli Sekarang' : 'Tidak Tersedia' }}
                    </v-btn>
                  </v-card-actions>
                </v-card>
              </v-col>
            </v-row>
            <v-row v-else-if="!isLoadingPackages" justify="center">
              <v-col cols="12" class="text-center py-16 text-medium-emphasis">
                <v-icon icon="tabler-package-off" size="x-large" class="mb-5" />
                <p class="text-h6">
                  Belum ada paket yang tersedia.
                </p>
              </v-col>
            </v-row>
          </div>
        </v-col>
      </v-row>

      <v-dialog v-if="isHydrated" v-model="showContactDialog" persistent max-width="500px" scrim="grey-darken-3" eager>
        <v-card :loading="isCheckingUser" rounded="lg" :disabled="isCheckingUser">
          <v-card-title class="d-flex align-center py-3 px-4 bg-grey-lighten-4 border-b">
            <v-icon icon="tabler-user-question" color="primary" start />
            <span class="text-h6 font-weight-medium">Periksa Nomor Telepon</span>
            <v-spacer />
            <v-btn icon="tabler-x" flat size="small" :disabled="isCheckingUser === true" variant="text" @click="closeContactDialog" />
          </v-card-title>
          <p class="text-caption px-4 pt-4 text-medium-emphasis">
            Masukkan nama dan nomor WhatsApp Anda untuk memeriksa apakah sudah terdaftar.
          </p>
          <v-form ref="contactFormRef" v-model="isContactFormValid" @submit.prevent="handleContactSubmit">
            <v-card-text class="pt-4 px-4">
              <v-alert v-if="contactSubmitError != null" density="compact" type="error" variant="tonal" class="mb-4 text-caption" border="start" closable @click:close="contactSubmitError = null">
                {{ contactSubmitError }}
              </v-alert>
              <v-text-field
                ref="fullNameInputRef"
                v-model.trim="fullNameInput"
                label="Nama Lengkap Anda"
                placeholder="Nama sesuai identitas"
                required
                variant="outlined"
                class="mb-4"
                :disabled="isCheckingUser"
                hide-details="auto"
                prepend-inner-icon="tabler-user"
                :rules="nameRules"
                clearable
                autofocus
                density="default"
              />
              <v-text-field
                v-model.trim="phoneNumberInput"
                label="Nomor WhatsApp Aktif"
                placeholder="Contoh: 081234567890"
                required
                type="tel"
                variant="outlined"
                class="mb-1"
                :disabled="isCheckingUser"
                hide-details="auto"
                prepend-inner-icon="tabler-brand-whatsapp"
                :rules="phoneRules"
                clearable
                density="default"
              />
            </v-card-text>
            <v-divider />
            <v-card-actions class="px-4 py-3 bg-grey-lighten-5">
              <v-spacer />
              <v-btn color="grey-darken-1" variant="text" :disabled="isCheckingUser === true" @click="closeContactDialog">
                Batal
              </v-btn>
              <v-btn color="primary" variant="flat" type="submit" :loading="isCheckingUser" :disabled="isCheckingUser === true || isContactFormValid !== true">
                <v-icon icon="tabler-user-search" start />
                Periksa Nomor
              </v-btn>
            </v-card-actions>
          </v-form>
        </v-card>
      </v-dialog>

      <v-snackbar
        v-model="snackbarVisible"
        :color="snackbarColor"
        location="bottom center"
        variant="elevated"
        :timeout="snackbarTimeout"
        multi-line
      >
        {{ snackbarText }}
        <template #actions>
          <v-btn icon="tabler-x" variant="text" @click="snackbarVisible = false" />
        </template>
      </v-snackbar>
    </v-col>
  </v-container>
</template>

<style scoped>
/* DIUBAH: Penambahan style untuk centering halaman penuh */
.full-height-container {
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  min-height: 100vh;
  text-align: center;
}

.v-card:hover:not([disabled]) {
  border-color: rgba(var(--v-theme-primary), 0.6);
  box-shadow: 0 6px 14px rgba(var(--v-theme-primary), 0.1);
}
.v-list-item {
  padding-inline: 0px !important;
}
</style>
