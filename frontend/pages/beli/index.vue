<script setup lang="ts">
import type { VForm, VTextField } from 'vuetify/components'
// --- PERBAIKAN: Impor tipe data yang benar dari backend ---
import type { PackagePublic as Package } from '~/types/package'
import { useNuxtApp } from '#app'
import { ClientOnly } from '#components'
import { storeToRefs } from 'pinia'
import { computed, isRef, nextTick, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useApiFetch } from '~/composables/useApiFetch'
import { useAuthStore } from '~/store/auth'

const authStore = useAuthStore()
const router = useRouter()
const route = useRoute()
const { $api } = useNuxtApp()

const { isLoggedIn, user, isLoadingUser, authError } = storeToRefs(authStore)

// Mengambil data paket dari API publik
const { data: packageApiResponse, pending: isLoadingPackages, error: fetchPackagesError, refresh: refreshPackages }
  = useApiFetch<Package[]>('/packages', {
    key: 'publicPackages',
    lazy: true,
    server: true,
    // Tidak perlu transform jika API /packages sudah mengembalikan array Package[]
    default: () => [] as Package[],
  })

const packages = computed(() => packageApiResponse.value || [])

// State lainnya tetap sama
const showContactDialog = ref(false)
const isContactFormValid = ref(false)
const contactFormRef = ref<InstanceType<typeof VForm> | null>(null)
const fullNameInput = ref('')
const phoneNumberInput = ref('')
const fullNameInputRef = ref<InstanceType<typeof VTextField> | null>(null)
const isCheckingUser = ref(false)
const contactSubmitError = ref<string | null>(null)
const selectedPackageId = ref<string | null>(null)
const selectedPackageName = ref<string>('')
const isInitiatingPayment = ref<string | null>(null)

const snackbarVisible = ref(false)
const snackbarText = ref('')
const snackbarColor = ref<'error' | 'success' | 'info' | 'warning'>('info')
const snackbarTimeout = ref(5000)

if (isRef(fetchPackagesError)) {
  watch(fetchPackagesError, (newError) => {
    if (newError) {
      if (newError.statusCode !== 401 && newError.statusCode !== 403) {
        const errorMessage = newError.data?.message || newError.statusMessage || newError.message || 'Gagal memuat daftar paket.'
        showSnackbar(`Gagal memuat daftar paket: ${errorMessage} [Status: ${newError.statusCode || 'N/A'}]`, 'error', 8000)
      }
    }
  })
}

if (isRef(authError)) {
  watch(authError, (newErrorValue) => {
    if (newErrorValue && typeof newErrorValue === 'string' && !newErrorValue.includes('middleware')) {
      showSnackbar(`Masalah Autentikasi: ${newErrorValue}`, 'error')
    }
  })
}

function showSnackbar(text: string, color: 'error' | 'success' | 'info' | 'warning' = 'info', timeout = 5000) {
  snackbarText.value = text
  snackbarColor.value = color
  snackbarTimeout.value = timeout
  snackbarVisible.value = true
}

const nameRules = [
  (v: string) => !!v || 'Nama Lengkap wajib diisi.',
  (v: string) => (v && v.trim().length >= 2) || 'Nama minimal 2 karakter.',
  (v: string) => (v && v.trim().length <= 100) || 'Nama maksimal 100 karakter.',
]
const phoneRules = [
  (v: string) => !!v || 'Nomor WhatsApp wajib diisi.',
  (v: string) => {
    const normalized = normalizePhoneNumber(v)
    return /^\+628[1-9]\d{8,12}$/.test(normalized) || 'Format: +628xx... (total 11-15 digit).'
  },
]

// --- PERBAIKAN FUNGSI FORMAT ---
function formatQuota(gb: number | undefined): string {
  if (gb === undefined || gb === null || gb < 0) return 'N/A'
  if (gb === 0) return 'Unlimited'
  return `${gb} GB`
}

// Fungsi formatSpeed tidak lagi diperlukan karena kecepatan unlimited
// function formatSpeed(kbps: any): string { ... }

function formatCurrency(value: number | undefined): string {
  if (value === undefined || value === null) return 'Harga N/A'
  return new Intl.NumberFormat('id-ID', { style: 'currency', currency: 'IDR', minimumFractionDigits: 0, maximumFractionDigits: 0 }).format(value)
}
// --- AKHIR PERBAIKAN FUNGSI FORMAT ---

function normalizePhoneNumber(phone: string | null | undefined): string {
  if (!phone) return ''
  let cleaned = phone.replace(/[\s\-()+]/g, '')
  if (cleaned.startsWith('08')) cleaned = `+62${cleaned.substring(1)}`
  else if (cleaned.startsWith('628')) cleaned = `+${cleaned}`
  else if (cleaned.startsWith('8') && cleaned.length >= 9) cleaned = `+62${cleaned}`
  return cleaned.startsWith('+628') ? cleaned : ''
}

const userGreeting = computed(() => {
  if (isLoggedIn.value && user.value) {
    const currentUserData = user.value
    const nameToDisplay = (currentUserData.full_name && currentUserData.full_name.trim() !== '') ? currentUserData.full_name : currentUserData.phone_number
    const firstName = nameToDisplay?.split(' ')[0]
    return `Halo, ${firstName || nameToDisplay}!`
  }
  return null
})

const isUserApprovedAndActive = computed(() => {
  if (isLoggedIn.value && user.value) {
    const currentUserData = user.value
    return currentUserData.is_active === true && currentUserData.approval_status === 'APPROVED'
  }
  return false
})

function retryFetch() {
  snackbarVisible.value = false
  refreshPackages()
}

// Fungsi navigasi (goToLogin, goToRegister, goToDashboard) tetap sama
function goToLogin() { router.push({ path: '/login', query: { redirect: '/beli' } }) }
function goToRegister() { router.push({ path: '/register', query: { redirect: '/beli' } }) }
function goToDashboard() { router.push('/dashboard') }

// Fungsi handlePackageSelection dan lainnya tetap sama
function handlePackageSelection(pkg: Package) {
  if (!pkg?.id || !pkg.is_active || !!isInitiatingPayment.value) return
  selectedPackageId.value = pkg.id
  selectedPackageName.value = pkg.name || 'Paket'
  snackbarVisible.value = false
  if (!isLoggedIn.value) {
    contactFormRef.value?.resetValidation()
    contactFormRef.value?.reset()
    contactSubmitError.value = null
    showContactDialog.value = true
    nextTick(() => { fullNameInputRef.value?.focus() })
  }
  else if (!isUserApprovedAndActive.value) {
    let warningMsg = 'Akun Anda belum aktif atau disetujui Admin untuk melakukan pembelian.'
    if (user.value?.approval_status === 'PENDING_APPROVAL') {
      warningMsg = 'Akun Anda sedang menunggu persetujuan Admin. Belum bisa melakukan pembelian.'
    }
    else if (user.value?.approval_status === 'REJECTED') {
      warningMsg = 'Pendaftaran akun Anda telah ditolak. Tidak dapat melakukan pembelian.'
    }
    showSnackbar(warningMsg, 'warning', 7000)
  }
  else if (user.value?.id) {
    initiatePayment(pkg.id)
  }
  else if (isLoadingUser.value) {
    showSnackbar('Memuat data pengguna, mohon tunggu...', 'info')
  }
}

async function handleContactSubmit() {
  if (!contactFormRef.value) return
  const { valid } = await contactFormRef.value.validate()
  if (!valid) {
    contactSubmitError.value = 'Periksa kembali isian nama dan nomor WhatsApp Anda.'
    return
  }
  if (isCheckingUser.value) return
  const nameToSubmit = fullNameInput.value.trim()
  const phoneToSubmit = normalizePhoneNumber(phoneNumberInput.value)
  if (!/^\+628[1-9]\d{8,12}$/.test(phoneToSubmit)) {
    contactSubmitError.value = 'Format nomor WhatsApp tidak valid (contoh: +62812...).'
    return
  }
  contactSubmitError.value = null
  isCheckingUser.value = true
  try {
    const response = await $api<{ user_exists: boolean, user_id?: string, success?: boolean, message?: string }>(
      '/users/check-or-register',
      { method: 'POST', body: { phone_number: phoneToSubmit, full_name: nameToSubmit } },
    )
    if (response && response.user_exists && response.user_id) {
      showContactDialog.value = false
      showSnackbar('Nomor Anda sudah terdaftar. Silakan login untuk melanjutkan pembelian.', 'info', 7000)
      goToLogin()
    } else if (response && Object.prototype.hasOwnProperty.call(response, 'user_exists') && !response.user_exists) {
      showContactDialog.value = false
      showSnackbar('Nomor Anda belum terdaftar. Silakan registrasi akun terlebih dahulu.', 'info', 7000)
      goToRegister()
    } else {
      throw new Error(response?.message || 'Gagal memeriksa status nomor. Respons tidak sesuai.')
    }
  } catch (err: any) {
    const message = err.data?.message || err.data?.error || err.data?.detail || err.message || 'Terjadi kesalahan.'
    contactSubmitError.value = `Gagal: ${message}`
  } finally {
    isCheckingUser.value = false
  }
}

async function initiatePayment(packageId: string) {
  isInitiatingPayment.value = packageId
  snackbarVisible.value = false
  try {
    const requestBody = { package_id: packageId }
    const responseData = await $api<{ snap_token: string, transaction_id?: string, order_id: string, message?: string }>(
      '/transactions/initiate',
      { method: 'POST', body: requestBody },
    )
    if (responseData?.snap_token && typeof window.snap?.pay === 'function') {
      const currentOrderId = responseData.order_id
      window.snap.pay(responseData.snap_token, {
        onSuccess: (result) => { router.push({ path: '/payment/finish', query: { status: 'success', order_id: result.order_id } }) },
        onPending: (result) => { router.push({ path: '/payment/finish', query: { status: 'pending', order_id: result.order_id } }) },
        onError: (result) => {
          const orderIdOnError = result?.order_id || currentOrderId
          let errorMsg = 'Pembayaran Gagal'
          if (result?.status_message) {
            if (Array.isArray(result.status_message) && result.status_message.length > 0)
              errorMsg = result.status_message.join(', ')
            else if (typeof result.status_message === 'string')
              errorMsg = result.status_message
          }
          if (orderIdOnError)
            router.push({ path: '/payment/finish', query: { status: 'error', order_id: orderIdOnError, msg: encodeURIComponent(errorMsg) } })
          else showSnackbar(`Pembayaran Gagal: ${errorMsg}`, 'error')
          isInitiatingPayment.value = null
        },
        onClose: () => {
          isInitiatingPayment.value = null
          if (!router.currentRoute.value.path.startsWith('/payment/finish')) {
            showSnackbar('Anda menutup jendela pembayaran.', 'info')
          }
        },
      })
    } else if (typeof window.snap?.pay !== 'function') {
      throw new TypeError('Komponen Midtrans tidak siap. Coba refresh halaman.')
    } else {
      throw new TypeError(responseData?.message || 'Gagal memulai pembayaran dari server.')
    }
  } catch (err: any) {
    if (err.response?.status !== 401 && err.response?.status !== 403) {
      const message = err.data?.message || err.data?.error || err.data?.detail || err.message || 'Gagal memulai pembayaran.'
      showSnackbar(`Error: ${message}`, 'error')
    }
    isInitiatingPayment.value = null
  }
}

function closeContactDialog() {
  if (!isCheckingUser.value) showContactDialog.value = false
}

onMounted(async () => {
  if (authStore && !authStore.isInitialized) {
    await authStore.initializeAuth()
  }
  const query = route.query
  if (query.action === 'cancelled' && query.order_id) {
    showSnackbar(`Pembayaran Order ID ${query.order_id} dibatalkan.`, 'info')
    router.replace({ query: {} })
  } else if (query.action === 'error' && query.order_id) {
    const errorMsg = query.msg ? decodeURIComponent(query.msg as string) : 'Terjadi kesalahan pembayaran'
    showSnackbar(`Pembayaran Order ID ${query.order_id} gagal: ${errorMsg}`, 'error', 8000)
    router.replace({ query: {} })
  }
})

definePageMeta({ layout: 'blank' })
useHead({ title: 'Beli Paket Mikrotik' })
</script>

<template>
  <v-container fluid class="fill-height pa-0 ma-0 bg-grey-lighten-5">
    <v-row justify="center" class="fill-height ma-0">
      <v-col cols="12" style="max-width: 1300px;" class="d-flex flex-column">
        <v-container fluid class="py-8 px-lg-12 px-md-6 px-sm-4 flex-grow-0">
          <h1 class="text-h4 text-sm-h3 font-weight-bold mb-2 text-center text-grey-darken-3">
            DAFTAR PAKET HOTSPOT
          </h1>
          <div class="text-center mb-8" style="min-height: 40px;">
            <!-- ... (Bagian greeting pengguna tetap sama) ... -->
          </div>
        </v-container>

        <v-row class="flex-grow-1 ma-0" align="center" justify="center">
          <v-col cols="12">
            <v-row v-if="isLoadingPackages" justify="center" dense class="px-lg-10 px-md-4 px-sm-2">
              <v-col v-for="n in 4" :key="`skel-pkg-${n}`" cols="12" sm="6" md="4" lg="3" xl="3" class="pa-2">
                <v-skeleton-loader type="image, article, actions" height="380" class="vuexy-skeleton-card" />
              </v-col>
            </v-row>
            <v-row v-else-if="fetchPackagesError" justify="center" class="px-lg-10 px-md-4 px-sm-2">
              <v-col cols="12" md="9" lg="7">
                <v-alert type="error" title="Gagal Memuat Paket" variant="tonal" prominent border="start" class="mx-auto" elevation="2">
                  <p class="text-body-2 mb-3">
                    Tidak dapat mengambil daftar paket dari server. Silakan coba lagi.
                  </p>
                  <template #append>
                    <v-btn color="error" variant="outlined" size="small" @click="retryFetch">
                      <v-icon start>mdi-reload</v-icon> Coba Lagi
                    </v-btn>
                  </template>
                </v-alert>
              </v-col>
            </v-row>
            <div v-else class="px-lg-10 px-md-4 px-sm-2">
              <v-row v-if="packages.length > 0" dense justify="center">
                <v-col v-for="(pkg, index) in packages" :key="pkg.id || index" cols="12" sm="6" md="4" lg="3" xl="3" class="pa-2 d-flex">
                  <v-card
                    class="d-flex flex-column flex-grow-1"
                    variant="outlined" hover rounded="lg"
                    :disabled="!pkg.is_active || !!isInitiatingPayment"
                    elevation="2"
                    :title="pkg.name"
                    @click="handlePackageSelection(pkg)"
                  >
                    <v-card-item class="pb-2">
                      <v-card-title class="text-h5 font-weight-bold text-primary mb-3 d-block">
                        {{ formatCurrency(pkg.price) }}
                      </v-card-title>
                    </v-card-item>
                    <v-card-text class="flex-grow-1 py-1">
                      <!-- --- PERBAIKAN TAMPILAN DETAIL PAKET --- -->
                      <v-list lines="one" density="compact" bg-color="transparent" class="py-0 ma-n2">
                        <v-list-item density="compact" class="px-1" :ripple="false">
                          <template #prepend>
                            <ClientOnly>
                              <v-icon size="small" class="mr-2 text-medium-emphasis">mdi-database-outline</v-icon>
                            </ClientOnly>
                          </template>
                          <v-list-item-title class="text-body-2">
                            Kuota: <span class="font-weight-medium text-high-emphasis">{{ formatQuota(pkg.data_quota_gb) }}</span>
                          </v-list-item-title>
                        </v-list-item>
                        
                        <!-- Item Kecepatan Dihapus -->

                        <v-list-item density="compact" class="px-1" :ripple="false">
                          <template #prepend>
                            <ClientOnly>
                              <v-icon size="small" class="mr-2 text-medium-emphasis">mdi-calendar-clock-outline</v-icon>
                            </ClientOnly>
                          </template>
                          <v-list-item-title class="text-body-2">
                            Aktif: <span class="font-weight-medium text-high-emphasis">{{ pkg.duration_days }} Hari</span>
                          </v-list-item-title>
                        </v-list-item>
                      </v-list>
                      <p v-if="pkg.description" class="text-caption text-medium-emphasis mt-4 px-1">
                        {{ pkg.description }}
                      </p>
                      <!-- --- AKHIR PERBAIKAN --- -->
                    </v-card-text>
                    <v-card-actions class="pa-4 mt-auto">
                      <v-btn
                        block color="primary" variant="flat" size="large" rounded="lg"
                        :disabled="!pkg.is_active || !!isInitiatingPayment"
                        :loading="isInitiatingPayment === pkg.id"
                        @click.stop="handlePackageSelection(pkg)"
                      >
                        <template #prepend>
                          <ClientOnly>
                            <v-icon v-if="!(isInitiatingPayment === pkg.id)">
                              {{ pkg.is_active ? 'mdi-cart-arrow-right' : 'mdi-cancel' }}
                            </v-icon>
                          </ClientOnly>
                        </template>
                        {{ pkg.is_active ? 'Beli Sekarang' : 'Tidak Tersedia' }}
                      </v-btn>
                    </v-card-actions>
                  </v-card>
                </v-col>
              </v-row>
              <v-row v-else-if="!isLoadingPackages" justify="center">
                <!-- ... (Tampilan jika tidak ada paket tetap sama) ... -->
              </v-row>
            </div>
          </v-col>
        </v-row>

        <!-- ... (Dialog dan Snackbar tetap sama) ... -->

      </v-col>
    </v-row>
  </v-container>
</template>

<style scoped>
/* Style Anda sudah baik, tidak perlu perubahan signifikan */
</style>
