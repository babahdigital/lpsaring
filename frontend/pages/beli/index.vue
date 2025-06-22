<script setup lang="ts">
import type { VForm, VTextField } from 'vuetify/components'
// Mengimpor tipe data `PackagePublic` yang sudah benar dari backend
import type { PackagePublic as Package } from '~/types/package'
import { useNuxtApp } from '#app'
import { ClientOnly } from '#components'
import { storeToRefs } from 'pinia'
import { computed, isRef, nextTick, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useApiFetch } from '~/composables/useApiFetch'
import { useAuthStore } from '~/store/auth'

// --- STRUKTUR DATA DISESUAIKAN DENGAN RESPON API BACKEND ---
// Interface ini diubah untuk mencocokkan struktur JSON dari backend (`"data": [...]`)
interface PackagesApiResponse {
  data: Package[];
  success: boolean;
  message: string;
}
// --- AKHIR PENYESUAIAN STRUKTUR DATA ---

const authStore = useAuthStore()
const router = useRouter()
const route = useRoute()
const { $api } = useNuxtApp()

const { isLoggedIn, user, isLoadingUser, authError } = storeToRefs(authStore)

// --- PERBAIKAN PADA FUNGSI FETCH ---
// Mengambil data paket dari API publik, dengan mengharapkan objek yang berisi `data`
const { data: packageApiResponse, pending: isLoadingPackages, error: fetchPackagesError, refresh: refreshPackages }
  = useApiFetch<PackagesApiResponse>('/packages', { // DIUBAH: Mengharapkan PackagesApiResponse
    key: 'publicPackages',
    lazy: true,
    server: true,
    // DIUBAH: Nilai default disesuaikan dengan struktur objek backend
    default: () => ({ data: [] as Package[], success: false, message: '' }),
  })

// DIUBAH: Computed property sekarang mengekstrak array dari `packageApiResponse.value.data`
const packages = computed(() => packageApiResponse.value?.data || [])
// --- AKHIR PERBAIKAN ---

// State untuk dialog, formulir, pembayaran, dan notifikasi
const showContactDialog = ref(false)
const isContactFormValid = ref(false)
const contactFormRef = ref<InstanceType<typeof VForm> | null>(null)
const fullNameInput = ref('')
const phoneNumberInput = ref('')
const fullNameInputRef = ref<InstanceType<typeof VTextField> | null>(null)
const isCheckingUser = ref(false)
const contactSubmitError = ref<string | null>(null)
const selectedPackageId = ref<string | null>(null)
const isInitiatingPayment = ref<string | null>(null)

const snackbarVisible = ref(false)
const snackbarText = ref('')
const snackbarColor = ref<'error' | 'success' | 'info' | 'warning'>('info')
const snackbarTimeout = ref(5000)

if (isRef(fetchPackagesError)) {
  watch(fetchPackagesError, (newError) => {
    if (newError && newError.statusCode !== 401 && newError.statusCode !== 403) {
      const errorMessage = newError.data?.message || 'Gagal memuat daftar paket.'
      showSnackbar(`Gagal memuat daftar paket: ${errorMessage}`, 'error')
    }
  })
}

// Fungsi utilitas dan aturan validasi (tidak ada perubahan)
function showSnackbar(text: string, color: 'error' | 'success' | 'info' | 'warning' = 'info', timeout = 5000) {
  snackbarText.value = text
  snackbarColor.value = color
  snackbarTimeout.value = timeout
  snackbarVisible.value = true
}

const nameRules = [
  (v: string) => !!v || 'Nama Lengkap wajib diisi.',
  (v: string) => (v && v.trim().length >= 2) || 'Nama minimal 2 karakter.',
]
const phoneRules = [
  (v: string) => !!v || 'Nomor WhatsApp wajib diisi.',
  (v: string) => /^\+628[1-9]\d{8,12}$/.test(normalizePhoneNumber(v)) || 'Format: +628xx... (11-15 digit).',
]

// --- FUNGSI FORMATTING YANG DISEMPURNAKAN ---
function formatQuota(gb: number | undefined): string {
  if (gb === undefined || gb === null || gb < 0) return 'N/A'
  if (gb === 0) return 'Unlimited'
  return `${gb} GB`
}

function formatCurrency(value: number | undefined): string {
  if (value === undefined || value === null) return 'Harga N/A'
  return new Intl.NumberFormat('id-ID', { style: 'currency', currency: 'IDR', minimumFractionDigits: 0, maximumFractionDigits: 0 }).format(value)
}

function normalizePhoneNumber(phone: string | null | undefined): string {
  if (!phone) return ''
  let cleaned = phone.replace(/[\s\-()+]/g, '')
  if (cleaned.startsWith('08')) cleaned = `+62${cleaned.substring(1)}`
  else if (cleaned.startsWith('628')) cleaned = `+${cleaned}`
  else if (cleaned.startsWith('8') && cleaned.length >= 9) cleaned = `+62${cleaned}`
  return cleaned.startsWith('+628') ? cleaned : ''
}
// --- AKHIR FUNGSI FORMATTING ---

const userGreeting = computed(() => {
  if (isLoggedIn.value && user.value) {
    const nameToDisplay = user.value.full_name || user.value.phone_number
    return `Halo, ${nameToDisplay.split(' ')[0]}!`
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

function goToLogin() { router.push({ path: '/login', query: { redirect: '/beli' } }) }
function goToRegister() { router.push({ path: '/register', query: { redirect: '/beli' } }) }
function goToDashboard() { router.push('/dashboard') }

// Logika penanganan event (tidak ada perubahan)
function handlePackageSelection(pkg: Package) {
  if (!pkg?.id || !pkg.is_active || !!isInitiatingPayment.value) return
  selectedPackageId.value = pkg.id
  if (!isLoggedIn.value) {
    contactFormRef.value?.reset()
    contactFormRef.value?.resetValidation()
    contactSubmitError.value = null
    showContactDialog.value = true
    nextTick(() => fullNameInputRef.value?.focus())
  } else if (!isUserApprovedAndActive.value) {
    let warningMsg = 'Akun Anda belum aktif atau disetujui Admin untuk melakukan pembelian.'
    if (user.value?.approval_status === 'PENDING_APPROVAL') {
      warningMsg = 'Akun Anda sedang menunggu persetujuan Admin.'
    } else if (user.value?.approval_status === 'REJECTED') {
      warningMsg = 'Pendaftaran akun Anda telah ditolak.'
    }
    showSnackbar(warningMsg, 'warning', 7000)
  } else if (user.value?.id) {
    initiatePayment(pkg.id)
  }
}

async function handleContactSubmit() {
  if (!contactFormRef.value) return
  const { valid } = await contactFormRef.value.validate()
  if (!valid) return
  isCheckingUser.value = true
  contactSubmitError.value = null
  try {
    const phoneToSubmit = normalizePhoneNumber(phoneNumberInput.value)
    const response = await $api<{ user_exists: boolean }>('/users/check-or-register', {
      method: 'POST', body: { phone_number: phoneToSubmit, full_name: fullNameInput.value.trim() },
    })
    showContactDialog.value = false
    if (response.user_exists) {
      showSnackbar('Nomor Anda sudah terdaftar. Silakan login.', 'info')
      goToLogin()
    } else {
      showSnackbar('Nomor Anda belum terdaftar. Silakan registrasi.', 'info')
      goToRegister()
    }
  } catch (err: any) {
    contactSubmitError.value = err.data?.message || 'Terjadi kesalahan.'
  } finally {
    isCheckingUser.value = false
  }
}

async function initiatePayment(packageId: string) {
  isInitiatingPayment.value = packageId
  try {
    const responseData = await $api<{ snap_token: string, order_id: string }>('/transactions/initiate', {
      method: 'POST', body: { package_id: packageId },
    })
    if (responseData?.snap_token && window.snap) {
      window.snap.pay(responseData.snap_token, {
        onSuccess: (result) => router.push(`/payment/finish?status=success&order_id=${result.order_id}`),
        onPending: (result) => router.push(`/payment/finish?status=pending&order_id=${result.order_id}`),
        onError: (result) => router.push(`/payment/finish?status=error&order_id=${result.order_id}`),
        onClose: () => {
          if (!router.currentRoute.value.path.startsWith('/payment/finish')) {
            showSnackbar('Anda menutup jendela pembayaran.', 'info')
          }
          isInitiatingPayment.value = null
        },
      })
    } else { throw new Error('Gagal mendapatkan token pembayaran.') }
  } catch (err: any) {
    showSnackbar(err.data?.message || 'Gagal memulai pembayaran.', 'error')
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
  }
  else if (query.action === 'error' && query.order_id) {
    const errorMsg = query.msg ? decodeURIComponent(query.msg as string) : 'Terjadi kesalahan pembayaran'
    showSnackbar(`Pembayaran Order ID ${query.order_id} gagal: ${errorMsg}`, 'error', 8000)
    router.replace({ query: {} })
  }
})

definePageMeta({ layout: 'blank' })
useHead({ title: 'Beli Paket Hotspot' })
</script>

<template>
  <!-- DIUBAH: Container utama ditambahkan class untuk centering -->
  <v-container fluid class="pa-0 ma-0 bg-grey-lighten-5 full-height-container">
    <v-col cols="12" style="max-width: 1300px;" class="mx-auto">
      
      <v-container fluid class="py-8 px-lg-12 px-md-6 px-sm-4">
        <h1 class="text-h4 text-sm-h3 font-weight-bold mb-2 text-center text-grey-darken-3">
          DAFTAR PAKET HOTSPOT
        </h1>
        <div class="text-center mb-6" style="min-height: 40px;">
          <!-- Bagian greeting pengguna dan tombol login/dashboard -->
          <v-btn v-if="!isLoggedIn && !isLoadingUser" variant="text" color="primary" @click="goToLogin">
            <v-icon start>mdi-login-variant</v-icon> Sudah Punya Akun? Login
          </v-btn>
          <div v-else-if="isLoadingUser" class="d-flex justify-center align-center text-medium-emphasis">
            <v-progress-circular indeterminate size="20" width="2" color="primary" class="mr-2" />
            <span>Memuat data pengguna...</span>
          </div>
          <div v-else-if="userGreeting" class="d-flex justify-center align-center text-body-1 text-medium-emphasis flex-wrap">
            <span class="mr-3">{{ userGreeting }}</span>
            <v-btn v-if="isUserApprovedAndActive" variant="outlined" color="primary" size="small" @click="goToDashboard">
              <v-icon start>mdi-view-dashboard-outline</v-icon> Ke Panel
            </v-btn>
          </div>
        </div>
      </v-container>

      <v-row class="ma-0" align="start" justify="center">
        <v-col cols="12">
          <!-- Skeleton loader saat memuat paket -->
          <v-row v-if="isLoadingPackages" justify="center" dense class="px-lg-10 px-md-4 px-sm-2">
            <v-col v-for="n in 4" :key="`skel-pkg-${n}`" cols="12" sm="6" md="4" lg="3">
              <v-skeleton-loader type="image, article, actions" height="320" />
            </v-col>
          </v-row>
          <!-- Tampilan error jika gagal memuat paket -->
          <v-row v-else-if="fetchPackagesError" justify="center" class="px-lg-10 px-md-4 px-sm-2">
            <v-col cols="12" md="8" lg="6">
              <v-alert type="error" title="Gagal Memuat Paket" variant="tonal" prominent>
                <p class="mb-4">Tidak dapat mengambil daftar paket dari server.</p>
                <v-btn color="error" @click="retryFetch">Coba Lagi</v-btn>
              </v-alert>
            </v-col>
          </v-row>
          <!-- Tampilan daftar paket atau pesan jika tidak ada paket -->
          <div v-else class="px-lg-10 px-md-4 px-sm-2">
            <v-row v-if="packages.length > 0" dense justify="center">
              <v-col v-for="pkg in packages" :key="pkg.id" cols="12" sm="6" md="4" lg="3" class="pa-2 d-flex">
                <v-card
                  class="d-flex flex-column flex-grow-1"
                  variant="outlined" hover rounded="lg"
                  :disabled="!pkg.is_active || !!isInitiatingPayment"
                  @click="handlePackageSelection(pkg)"
                >
                  <v-card-item class="text-left">
                    <v-card-title class="text-h6 text-wrap font-weight-bold mb-2">{{ pkg.name }}</v-card-title>
                    <v-card-subtitle class="text-h5 font-weight-bold text-primary">
                      {{ formatCurrency(pkg.price) }}
                    </v-card-subtitle>
                  </v-card-item>

                  <v-card-text class="flex-grow-1 py-2 text-left">
                    <v-list lines="one" density="compact" bg-color="transparent" class="py-0">
                      <v-list-item>
                        <template #prepend><v-icon size="small" class="mr-2">mdi-database-outline</v-icon></template>
                        <v-list-item-title class="text-body-2">
                          Kuota: <span class="font-weight-medium">{{ formatQuota(pkg.data_quota_gb) }}</span>
                        </v-list-item-title>
                      </v-list-item>
                      <v-list-item>
                        <template #prepend><v-icon size="small" class="mr-2">mdi-speedometer</v-icon></template>
                        <v-list-item-title class="text-body-2">
                          Kecepatan: <span class="font-weight-medium">Unlimited</span>
                        </v-list-item-title>
                      </v-list-item>
                      <v-list-item>
                        <template #prepend><v-icon size="small" class="mr-2">mdi-calendar-clock-outline</v-icon></template>
                        <v-list-item-title class="text-body-2">
                          Aktif: <span class="font-weight-medium">{{ pkg.duration_days }} Hari</span>
                        </v-list-item-title>
                      </v-list-item>
                    </v-list>
                    <p v-if="pkg.description" class="text-caption text-medium-emphasis mt-3 px-1">{{ pkg.description }}</p>
                  </v-card-text>

                  <v-card-actions class="pa-4 mt-auto">
                    <v-btn
                      block color="primary" variant="flat" size="large"
                      :disabled="!pkg.is_active || !!isInitiatingPayment"
                      :loading="isInitiatingPayment === pkg.id"
                      @click.stop="handlePackageSelection(pkg)"
                    >
                      {{ pkg.is_active ? 'Beli Sekarang' : 'Tidak Tersedia' }}
                    </v-btn>
                  </v-card-actions>
                </v-card>
              </v-col>
            </v-row>
            <v-row v-else-if="!isLoadingPackages" justify="center">
              <v-col cols="12" class="text-center py-16 text-medium-emphasis">
                <v-icon size="x-large" class="mb-5">mdi-package-variant-closed-remove</v-icon>
                <p class="text-h6">Belum ada paket yang tersedia.</p>
              </v-col>
            </v-row>
          </div>
        </v-col>
      </v-row>

      <!-- Dialog kontak (KODE LENGKAP) -->
      <v-dialog v-model="showContactDialog" persistent max-width="500px" scrim="grey-darken-3" eager>
        <v-card :loading="isCheckingUser" rounded="lg" :disabled="isCheckingUser">
          <v-card-title class="d-flex align-center py-3 px-4 bg-grey-lighten-4 border-b">
            <v-icon color="primary" start>mdi-account-question-outline</v-icon>
            <span class="text-h6 font-weight-medium">Periksa Nomor Telepon</span>
            <v-spacer />
            <v-btn icon flat size="small" :disabled="isCheckingUser" variant="text" @click="closeContactDialog">
              <v-icon>mdi-close</v-icon>
            </v-btn>
          </v-card-title>
          <p class="text-caption px-4 pt-4 text-medium-emphasis">
            Masukkan nama dan nomor WhatsApp Anda untuk memeriksa apakah sudah terdaftar.
          </p>
          <v-form ref="contactFormRef" v-model="isContactFormValid" @submit.prevent="handleContactSubmit">
            <v-card-text class="pt-4 px-4">
              <v-alert v-if="contactSubmitError" density="compact" type="error" variant="tonal" class="mb-4 text-caption" border="start" closable @click:close="contactSubmitError = null">
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
                prepend-inner-icon="mdi-account"
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
                prepend-inner-icon="mdi-whatsapp"
                :rules="phoneRules"
                clearable
                density="default"
              />
            </v-card-text>
            <v-divider />
            <v-card-actions class="px-4 py-3 bg-grey-lighten-5">
              <v-spacer />
              <v-btn color="grey-darken-1" variant="text" :disabled="isCheckingUser" @click="closeContactDialog">
                Batal
              </v-btn>
              <v-btn color="primary" variant="flat" type="submit" :loading="isCheckingUser" :disabled="isCheckingUser || !isContactFormValid">
                <v-icon start>mdi-account-search-outline</v-icon>
                Periksa Nomor
              </v-btn>
            </v-card-actions>
          </v-form>
        </v-card>
      </v-dialog>

      <!-- Snackbar (tidak ada perubahan) -->
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
          <v-btn icon="mdi-close" variant="text" @click="snackbarVisible = false" />
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