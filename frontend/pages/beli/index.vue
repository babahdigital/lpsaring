<script setup lang="ts">
import type { VForm } from 'vuetify/components'
// Mengimpor tipe data `PackagePublic` yang sudah benar dari backend
import type { PackagePublic as Package } from '~/types/package'
import type {
  PaymentMethodContract,
  TransactionInitiateResponseContract,
  VaBankContract,
} from '~/types/api/contracts'
import { useFetch, useNuxtApp } from '#app'
import { storeToRefs } from 'pinia'
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '~/store/auth'
import { useSettingsStore } from '~/store/settings'
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
const settingsStore = useSettingsStore()
const router = useRouter()
const route = useRoute()
const { $api } = useNuxtApp()
const { ensureMidtransReady } = useMidtransSnap()
const runtimeConfig = useRuntimeConfig()

const { isLoggedIn, user, loadingUser } = storeToRefs(authStore)

interface FocusableField { focus: () => void }

interface SnapPayResult {
  order_id: string
}

type PaymentMethod = PaymentMethodContract
type VaBank = VaBankContract
type InitiateResponse = TransactionInitiateResponseContract

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
  lazy: false,
  server: true,
  $fetch: $api,
})

const { pending: isLoadingPackages, error: fetchPackagesError, refresh: refreshPackages } = packagesRequest
const packageApiResponse = packagesRequest.data as Ref<PackagesApiResponse | null>

const packages = computed(() => (packageApiResponse.value?.data ?? []))
const isRenderHydrated = computed(() => isHydrated.value === true)
const isLoggedInForRender = computed(() => isRenderHydrated.value ? isLoggedIn.value === true : false)
const userForRender = computed(() => (isRenderHydrated.value ? user.value : null))
const loadingUserForRender = computed(() => (isRenderHydrated.value ? loadingUser.value : false))

const isDemoModeEnabled = computed(() => isLoggedInForRender.value === true && userForRender.value?.is_demo_user === true)

function isTestingPackage(pkg: Package): boolean {
  return String(pkg?.name ?? '').trim().toLowerCase().includes('testing')
}

function isDemoDisabledPackage(pkg: Package): boolean {
  return isDemoModeEnabled.value === true && !isTestingPackage(pkg)
}

function canPurchasePackage(pkg: Package): boolean {
  return pkg.is_active === true || (isDemoModeEnabled.value === true && isTestingPackage(pkg))
}

function getPackageDisabledTooltip(pkg: Package): string | null {
  if (isDemoDisabledPackage(pkg))
    return 'Mode demo aktif: hanya paket Testing yang tersedia.'
  if (!canPurchasePackage(pkg))
    return 'Paket ini sedang tidak tersedia.'
  return null
}

function getPackageButtonLabel(pkg: Package): string {
  if (isDemoDisabledPackage(pkg))
    return 'Disable'
  if (!canPurchasePackage(pkg))
    return 'Tidak Tersedia'
  return 'Beli Sekarang'
}

const visiblePackages = computed(() => {
  return packages.value.filter((pkg) => {
    if (pkg.is_active === true)
      return true
    return isDemoModeEnabled.value === true && isTestingPackage(pkg)
  })
})

const featuredPackageId = computed(() => {
  const firstPurchasable = visiblePackages.value.find(pkg => canPurchasePackage(pkg))
  return firstPurchasable?.id ?? null
})
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

const showPaymentMethodDialog = ref(false)
const pendingPaymentPackageId = ref<string | null>(null)

const selectedPaymentMethod = ref<PaymentMethod>('qris')
const selectedVaBank = ref<VaBank>('bni')

function parseCsvList(value: string | null | undefined): string[] {
  const raw = (value ?? '').toString().trim()
  if (raw === '')
    return []
  return Array.from(new Set(raw.split(',').map(p => p.trim().toLowerCase()).filter(Boolean)))
}

const providerMode = computed<'snap' | 'core_api'>(() => {
  const raw = (settingsStore.getSetting('PAYMENT_PROVIDER_MODE', 'snap') ?? 'snap').toString().trim().toLowerCase()
  return raw === 'core_api' ? 'core_api' : 'snap'
})

const coreApiEnabledMethods = computed<PaymentMethod[]>(() => {
  const parsed = parseCsvList(settingsStore.getSetting('CORE_API_ENABLED_PAYMENT_METHODS', 'qris,gopay,va'))
  const allowed: PaymentMethod[] = ['qris', 'gopay', 'shopeepay', 'va']
  const enabled = allowed.filter(m => parsed.includes(m))
  return enabled.length > 0 ? enabled : ['qris', 'gopay', 'va']
})

const coreApiEnabledVaBanks = computed<VaBank[]>(() => {
  const parsed = parseCsvList(settingsStore.getSetting('CORE_API_ENABLED_VA_BANKS', 'bca,bni,bri,mandiri,permata,cimb'))
  const allowed: VaBank[] = ['bca', 'bni', 'bri', 'mandiri', 'permata', 'cimb']
  const enabled = allowed.filter(b => parsed.includes(b))
  return enabled.length > 0 ? enabled : allowed
})

const allPaymentMethodItems = [
  {
    value: 'qris' as const,
    title: 'QRIS',
    subtitle: 'Scan QR dari aplikasi pembayaran',
    icon: 'tabler-qrcode',
  },
  {
    value: 'gopay' as const,
    title: 'GoPay',
    subtitle: 'Buka GoPay / scan QR jika tersedia',
    icon: 'tabler-wallet',
  },
  {
    value: 'shopeepay' as const,
    title: 'ShopeePay',
    subtitle: 'Buka ShopeePay / scan QR jika tersedia',
    icon: 'tabler-wallet',
  },
  {
    value: 'va' as const,
    title: 'Transfer Virtual Account',
    subtitle: 'Pilih bank, lalu transfer via VA',
    icon: 'tabler-building-bank',
  },
] as const

const availablePaymentMethodItems = computed(() => {
  if (providerMode.value === 'core_api') {
    const enabled = new Set(coreApiEnabledMethods.value)
    return allPaymentMethodItems.filter(i => enabled.has(i.value))
  }
  // Snap mode: keep existing options to avoid changing behavior.
  return allPaymentMethodItems.filter(i => i.value !== 'shopeepay')
})

const vaBankItems = [
  { title: 'BCA', value: 'bca' },
  { title: 'BNI', value: 'bni' },
  { title: 'BRI', value: 'bri' },
  { title: 'Mandiri', value: 'mandiri' },
  { title: 'Permata', value: 'permata' },
  { title: 'CIMB Niaga', value: 'cimb' },
] as const

const availableVaBankItems = computed(() => {
  if (providerMode.value !== 'core_api')
    return vaBankItems
  const enabled = new Set(coreApiEnabledVaBanks.value)
  return vaBankItems.filter(i => enabled.has(i.value))
})

watch(availablePaymentMethodItems, (items) => {
  const first = items[0]?.value
  if (!first)
    return
  if (!items.some(i => i.value === selectedPaymentMethod.value))
    selectedPaymentMethod.value = first
}, { immediate: true })

watch([selectedPaymentMethod, availableVaBankItems], () => {
  if (selectedPaymentMethod.value !== 'va')
    return
  const items = availableVaBankItems.value
  const first = items[0]?.value
  if (!first)
    return
  if (!items.some(i => i.value === selectedVaBank.value))
    selectedVaBank.value = first
}, { immediate: true })

const selectedPackageForPayment = computed(() => {
  if (pendingPaymentPackageId.value == null)
    return null
  return visiblePackages.value.find(p => p.id === pendingPaymentPackageId.value) ?? null
})

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
  if (isLoggedInForRender.value && userForRender.value) {
    const name = userForRender.value.full_name
    const nameToDisplay = (name != null && name.trim() !== '') ? name : (userForRender.value.phone_number ?? '')
    const firstName = nameToDisplay.split(' ')[0] || 'Pengguna'
    return `Halo, ${firstName}!`
  }
  return null
})

const isUserApprovedAndActive = computed(() => {
  return isLoggedInForRender.value && userForRender.value?.is_active === true && userForRender.value.approval_status === 'APPROVED'
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

function openPaymentMethodDialog(packageId: string) {
  // Snap mode: langsung buka Midtrans Snap (tanpa popup pilih metode)
  if (providerMode.value === 'snap') {
    void initiatePayment(packageId)
    return
  }

  pendingPaymentPackageId.value = packageId
  showPaymentMethodDialog.value = true
}

function closePaymentMethodDialog() {
  showPaymentMethodDialog.value = false
  pendingPaymentPackageId.value = null
}

async function confirmPaymentMethod() {
  if (pendingPaymentPackageId.value == null)
    return
  const packageId = pendingPaymentPackageId.value
  closePaymentMethodDialog()
  await initiatePayment(packageId)
}

// Logika penanganan event (tidak ada perubahan)
function handlePackageSelection(pkg: Package) {
  if (pkg?.id == null || isInitiatingPayment.value != null)
    return

  if (isDemoDisabledPackage(pkg)) {
    showSnackbar('Mode demo aktif: hanya paket Testing yang bisa dipilih.', 'warning', 6000)
    return
  }

  if (!canPurchasePackage(pkg))
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
    openPaymentMethodDialog(pkg.id)
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
    const responseData = await $api<InitiateResponse>('/transactions/initiate', {
      method: 'POST',
      body: {
        package_id: packageId,
        payment_method: selectedPaymentMethod.value,
        va_bank: selectedPaymentMethod.value === 'va' ? selectedVaBank.value : undefined,
      },
    })
    const initiatedOrderId = responseData?.order_id

    const statusToken = (typeof responseData?.status_token === 'string' && responseData.status_token.trim() !== '')
      ? responseData.status_token.trim()
      : null

    const provider = (responseData?.provider_mode ?? providerMode.value) === 'core_api' ? 'core_api' : 'snap'

    const redirectUrl = (typeof responseData?.redirect_url === 'string' && responseData.redirect_url.trim() !== '')
      ? responseData.redirect_url.trim()
      : null

    const snapToken = (typeof responseData?.snap_token === 'string' && responseData.snap_token.trim() !== '')
      ? responseData.snap_token
      : null

    if (snapToken) {
      await ensureMidtransReady()
      if (window.snap == null)
        throw new Error('Midtrans Snap belum siap. Silakan coba beberapa saat lagi.')

      window.snap.pay(snapToken, {
        onSuccess: (result: SnapPayResult) => router.push(`/payment/status?status=success&order_id=${result.order_id}${statusToken ? `&t=${encodeURIComponent(statusToken)}` : ''}`),
        onPending: (result: SnapPayResult) => router.push(`/payment/status?status=pending&order_id=${result.order_id}${statusToken ? `&t=${encodeURIComponent(statusToken)}` : ''}`),
        onError: (result: SnapPayResult) => router.push(`/payment/status?status=error&order_id=${result.order_id}${statusToken ? `&t=${encodeURIComponent(statusToken)}` : ''}`),
        onClose: () => {
          if (typeof initiatedOrderId === 'string' && initiatedOrderId !== '') {
            if (statusToken) {
              void $api(`/transactions/public/${encodeURIComponent(initiatedOrderId)}/cancel?t=${encodeURIComponent(statusToken)}`, { method: 'POST' }).catch(() => {})
            }
            else {
              void $api(`/transactions/${encodeURIComponent(initiatedOrderId)}/cancel`, { method: 'POST' }).catch(() => {})
            }
          }
          if (router.currentRoute.value.path.startsWith('/payment/') !== true) {
            showSnackbar('Anda menutup jendela pembayaran.', 'info')
          }
          isInitiatingPayment.value = null
        },
      })
    }
    else if (provider === 'core_api' && (selectedPaymentMethod.value === 'gopay' || selectedPaymentMethod.value === 'shopeepay') && redirectUrl) {
      // Core API app deeplink: redirect langsung (user gesture) untuk memaksimalkan sukses di mobile.
      isInitiatingPayment.value = null
      window.location.href = redirectUrl
    }
    else if (typeof initiatedOrderId === 'string' && initiatedOrderId.trim() !== '') {
      // Core API mode: proceed to status/instructions page.
      await router.push(`/payment/status?order_id=${encodeURIComponent(initiatedOrderId)}${statusToken ? `&t=${encodeURIComponent(statusToken)}` : ''}`)
      isInitiatingPayment.value = null
    }
    else {
      throw new Error('Gagal memulai pembayaran (Order ID tidak tersedia).')
    }
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
    const responseData = await $api<InitiateResponse>('/transactions/debt/initiate', {
      method: 'POST',
      body: {
        payment_method: selectedPaymentMethod.value,
        va_bank: selectedPaymentMethod.value === 'va' ? selectedVaBank.value : undefined,
      },
    })
    const initiatedOrderId = responseData?.order_id

    const statusToken = (typeof responseData?.status_token === 'string' && responseData.status_token.trim() !== '')
      ? responseData.status_token.trim()
      : null

    const provider = (responseData?.provider_mode ?? providerMode.value) === 'core_api' ? 'core_api' : 'snap'

    const redirectUrl = (typeof responseData?.redirect_url === 'string' && responseData.redirect_url.trim() !== '')
      ? responseData.redirect_url.trim()
      : null

    const snapToken = (typeof responseData?.snap_token === 'string' && responseData.snap_token.trim() !== '')
      ? responseData.snap_token
      : null

    if (snapToken) {
      await ensureMidtransReady()
      if (window.snap == null)
        throw new Error('Midtrans Snap belum siap. Silakan coba beberapa saat lagi.')

      window.snap.pay(snapToken, {
        onSuccess: (result: SnapPayResult) => router.push(`/payment/status?status=success&order_id=${result.order_id}${statusToken ? `&t=${encodeURIComponent(statusToken)}` : ''}`),
        onPending: (result: SnapPayResult) => router.push(`/payment/status?status=pending&order_id=${result.order_id}${statusToken ? `&t=${encodeURIComponent(statusToken)}` : ''}`),
        onError: (result: SnapPayResult) => router.push(`/payment/status?status=error&order_id=${result.order_id}${statusToken ? `&t=${encodeURIComponent(statusToken)}` : ''}`),
        onClose: () => {
          if (typeof initiatedOrderId === 'string' && initiatedOrderId !== '') {
            if (statusToken) {
              void $api(`/transactions/public/${encodeURIComponent(initiatedOrderId)}/cancel?t=${encodeURIComponent(statusToken)}`, { method: 'POST' }).catch(() => {})
            }
            else {
              void $api(`/transactions/${encodeURIComponent(initiatedOrderId)}/cancel`, { method: 'POST' }).catch(() => {})
            }
          }
          if (router.currentRoute.value.path.startsWith('/payment/') !== true)
            showSnackbar('Anda menutup jendela pembayaran.', 'info')
          isInitiatingPayment.value = null
        },
      })
    }
    else if (provider === 'core_api' && (selectedPaymentMethod.value === 'gopay' || selectedPaymentMethod.value === 'shopeepay') && redirectUrl) {
      isInitiatingPayment.value = null
      window.location.href = redirectUrl
    }
    else {
      if (typeof initiatedOrderId === 'string' && initiatedOrderId.trim() !== '') {
        await router.push(`/payment/status?order_id=${encodeURIComponent(initiatedOrderId)}&purpose=debt${statusToken ? `&t=${encodeURIComponent(statusToken)}` : ''}`)
        isInitiatingPayment.value = null
      }
      else {
        throw new Error('Gagal memulai pembayaran (Order ID tidak tersedia).')
      }
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
  <v-container fluid class="pa-0 beli-page">
    <header class="beli-header">
      <div class="beli-shell d-flex align-center justify-space-between py-3 px-4 px-sm-6 px-md-8">
        <div class="d-flex align-center">
          <div class="beli-brand-icon mr-3">
            <v-icon icon="tabler-wifi" color="primary" size="22" />
          </div>
          <div class="text-h6 font-weight-bold">
            Hotspot<span class="text-primary">Net</span>
          </div>
        </div>

        <div class="d-flex align-center ga-2 ga-sm-3">
          <div v-if="loadingUserForRender" class="d-flex align-center text-caption text-medium-emphasis">
            <v-progress-circular indeterminate size="18" width="2" color="primary" class="mr-2" />
            Memuat...
          </div>
          <template v-else-if="isLoggedInForRender && userGreeting != null">
            <div class="text-right d-none d-md-flex flex-column">
              <span class="text-body-2 font-weight-bold line-height-1">{{ userGreeting }}</span>
              <span class="text-caption text-medium-emphasis line-height-1">{{ isUserApprovedAndActive ? 'User Aktif' : 'Menunggu Aktivasi' }}</span>
            </div>
            <v-btn v-if="isUserApprovedAndActive" color="primary" variant="tonal" size="small" @click="goToDashboard">
              <v-icon icon="tabler-layout-dashboard" start />
              Ke Panel
            </v-btn>
          </template>
          <v-btn v-else color="primary" variant="tonal" size="small" @click="goToLogin">
            <v-icon icon="tabler-login" start />
            Login
          </v-btn>
        </div>
      </div>
    </header>

    <main class="beli-shell px-4 px-sm-6 px-md-8 py-10 py-sm-12">
      <div class="text-center mx-auto mb-10" style="max-width: 760px;">
        <v-chip
          :color="isDemoModeEnabled ? 'warning' : 'primary'"
          variant="tonal"
          size="small"
          class="font-weight-bold mb-4"
        >
          {{ isDemoModeEnabled ? 'Mode Demo' : 'Paket Hotspot' }}
        </v-chip>
        <h1 class="text-h4 text-sm-h3 text-md-h2 font-weight-bold mb-3 text-high-emphasis">
          Pilih Paket Internet Anda
        </h1>
        <p class="text-body-1 text-sm-h6 text-medium-emphasis">
          Pilih paket yang sesuai kebutuhan dan lanjutkan pembayaran dengan aman melalui Midtrans.
        </p>
      </div>

      <v-row v-if="isLoadingPackages" dense>
        <v-col v-for="n in 6" :key="`skel-pkg-${n}`" cols="12" sm="6" md="4" lg="3">
          <v-skeleton-loader class="beli-skeleton" type="heading, paragraph, paragraph, button" />
        </v-col>
      </v-row>

      <v-row v-else-if="fetchPackagesError" justify="center">
        <v-col cols="12" md="8" lg="6">
          <v-alert type="error" title="Gagal Memuat Paket" variant="tonal" prominent>
            <p class="mb-4">Tidak dapat mengambil daftar paket dari server.</p>
            <v-btn color="error" @click="retryFetch">Coba Lagi</v-btn>
          </v-alert>
        </v-col>
      </v-row>

      <v-row v-else-if="visiblePackages.length > 0" dense>
        <v-col v-for="pkg in visiblePackages" :key="pkg.id" cols="12" sm="6" md="4" lg="3" class="d-flex">
          <v-tooltip :disabled="isDemoDisabledPackage(pkg) !== true" location="top" max-width="280">
            <template #activator="{ props }">
              <div v-bind="props" class="w-100 d-flex">
                <v-card
                  class="package-card d-flex flex-column flex-grow-1"
                  :class="{
                    'package-card--featured': pkg.id === featuredPackageId,
                    'package-card--disabled': !canPurchasePackage(pkg) || isDemoDisabledPackage(pkg),
                  }"
                  rounded="xl"
                  :disabled="!canPurchasePackage(pkg) || isInitiatingPayment != null || isDemoDisabledPackage(pkg)"
                  @click="handlePackageSelection(pkg)"
                >
                  <v-card-item class="pb-2">
                    <v-chip
                      v-if="pkg.id === featuredPackageId"
                      color="primary"
                      size="x-small"
                      variant="flat"
                      class="mb-3 font-weight-bold"
                    >
                      Tersedia
                    </v-chip>
                    <v-card-title class="text-h6 font-weight-bold text-wrap px-0 mb-1">
                      {{ pkg.name }}
                    </v-card-title>
                    <v-card-subtitle class="text-h5 font-weight-bold text-primary px-0 opacity-100">
                      {{ formatCurrency(pkg.price) }}
                    </v-card-subtitle>
                  </v-card-item>

                  <v-card-text class="pt-0 pb-2 flex-grow-1">
                    <div class="package-detail-wrap pa-3 rounded-lg mb-4">
                      <v-list density="compact" lines="one" bg-color="transparent" class="py-0">
                        <v-list-item class="px-0">
                          <template #prepend><v-icon icon="tabler-database" size="small" class="mr-2" /></template>
                          <v-list-item-title class="text-body-2">Kuota: <span class="font-weight-medium">{{ formatQuota(pkg.data_quota_gb) }}</span></v-list-item-title>
                        </v-list-item>
                        <v-list-item class="px-0">
                          <template #prepend><v-icon icon="tabler-gauge" size="small" class="mr-2" /></template>
                          <v-list-item-title class="text-body-2">Kecepatan: <span class="font-weight-medium">Unlimited</span></v-list-item-title>
                        </v-list-item>
                        <v-list-item class="px-0">
                          <template #prepend><v-icon icon="tabler-calendar-time" size="small" class="mr-2" /></template>
                          <v-list-item-title class="text-body-2">Aktif: <span class="font-weight-medium">{{ pkg.duration_days }} Hari</span></v-list-item-title>
                        </v-list-item>
                      </v-list>
                    </div>

                    <v-list density="compact" lines="one" bg-color="transparent" class="py-0 package-metrics">
                      <v-list-item class="px-0">
                        <template #prepend><v-icon icon="tabler-receipt" size="small" class="mr-2" /></template>
                        <v-list-item-title class="text-body-2">Harga / Hari: <span class="font-weight-medium">{{ formatPricePerDay(pkg.price, pkg.duration_days) }}</span></v-list-item-title>
                      </v-list-item>
                      <v-list-item class="px-0">
                        <template #prepend><v-icon icon="tabler-chart-pie" size="small" class="mr-2" /></template>
                        <v-list-item-title class="text-body-2">Harga / GB: <span class="font-weight-medium">{{ formatPricePerGb(pkg.price, pkg.data_quota_gb) }}</span></v-list-item-title>
                      </v-list-item>
                    </v-list>

                    <p v-if="pkg.description != null && pkg.description !== ''" class="text-caption text-medium-emphasis mt-3 mb-0">
                      {{ pkg.description }}
                    </p>
                  </v-card-text>

                  <v-card-actions class="pa-4 pt-2 mt-auto">
                    <v-btn
                      block
                      color="primary"
                      variant="flat"
                      size="large"
                      :disabled="!canPurchasePackage(pkg) || isInitiatingPayment != null || isDemoDisabledPackage(pkg)"
                      :loading="isInitiatingPayment === pkg.id"
                      @click.stop="handlePackageSelection(pkg)"
                    >
                      {{ getPackageButtonLabel(pkg) }}
                    </v-btn>
                  </v-card-actions>
                </v-card>
              </div>
            </template>
            {{ getPackageDisabledTooltip(pkg) }}
          </v-tooltip>
        </v-col>
      </v-row>

      <v-row v-else justify="center">
        <v-col cols="12" md="8" lg="6">
          <v-alert type="info" variant="tonal" prominent>
            Belum ada paket yang tersedia.
          </v-alert>
        </v-col>
      </v-row>
    </main>

    <footer class="beli-footer mt-auto">
      <div class="beli-shell d-flex flex-column flex-sm-row align-center justify-space-between px-4 px-sm-6 px-md-8 py-5 ga-3">
        <p class="text-caption text-medium-emphasis mb-0 text-center text-sm-left">
          © 2026 {{ runtimeConfig.public.merchantName }}. All rights reserved.
        </p>
        <div class="d-flex align-center ga-4 text-caption">
          <NuxtLink class="footer-link" to="/merchant-center/privacy">
            Privacy
          </NuxtLink>
          <NuxtLink class="footer-link" to="/merchant-center/terms">
            Syarat & Ketentuan
          </NuxtLink>
        </div>
      </div>
    </footer>

      <v-dialog v-if="isHydrated" v-model="showPaymentMethodDialog" max-width="560px" scrim="grey-darken-3" eager>
        <v-card rounded="lg">
          <v-card-title class="d-flex align-center py-3 px-4 bg-grey-lighten-4 border-b">
            <v-icon icon="tabler-credit-card" color="primary" start />
            <span class="text-h6 font-weight-medium">Pilih Metode Pembayaran</span>
            <v-spacer />
            <v-btn icon="tabler-x" flat size="small" variant="text" @click="closePaymentMethodDialog" />
          </v-card-title>

          <v-card-text class="px-4 pt-4">
            <p v-if="selectedPackageForPayment" class="text-caption text-medium-emphasis mb-3">
              Paket: <span class="font-weight-medium">{{ selectedPackageForPayment.name }}</span>
              <span class="mx-1">•</span>
              <span class="font-weight-medium">{{ formatCurrency(selectedPackageForPayment.price) }}</span>
            </p>

            <v-radio-group v-model="selectedPaymentMethod" class="mt-1 payment-method-group">
              <v-radio
                v-for="item in availablePaymentMethodItems"
                :key="item.value"
                :value="item.value"
                class="payment-method-radio"
              >
                <template #label>
                  <div class="d-flex align-center payment-method-label">
                    <v-icon :icon="item.icon" color="primary" />
                    <div class="payment-method-text">
                      <div class="text-body-1 font-weight-medium">
                        {{ item.title }}
                      </div>
                      <div class="text-caption text-medium-emphasis">
                        {{ item.subtitle }}
                      </div>
                    </div>
                  </div>
                </template>
              </v-radio>
            </v-radio-group>

            <v-select
              v-if="selectedPaymentMethod === 'va'"
              v-model="selectedVaBank"
              class="mt-2"
              label="Pilih Bank VA"
              persistent-placeholder
              :items="availableVaBankItems"
              item-title="title"
              item-value="value"
              variant="outlined"
              density="comfortable"
            />
          </v-card-text>

          <v-divider />
          <v-card-actions class="px-4 py-3 bg-grey-lighten-5">
            <v-spacer />
            <v-btn color="grey-darken-1" variant="text" @click="closePaymentMethodDialog">
              Batal
            </v-btn>
            <v-btn
              color="primary"
              variant="flat"
              :disabled="pendingPaymentPackageId == null || isInitiatingPayment != null"
              @click="confirmPaymentMethod"
            >
              Lanjutkan Pembayaran
            </v-btn>
          </v-card-actions>
        </v-card>
      </v-dialog>

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
  </v-container>
</template>

<style scoped>
.beli-page {
  display: flex;
  flex-direction: column;
  min-height: 100vh;
  background: rgb(var(--v-theme-background));
}

.beli-shell {
  width: 100%;
  max-width: 1340px;
  margin: 0 auto;
}

.beli-header {
  position: sticky;
  top: 0;
  z-index: 20;
  border-bottom: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  background: rgba(var(--v-theme-surface), 0.96);
  backdrop-filter: blur(10px);
}

.beli-brand-icon {
  width: 40px;
  height: 40px;
  border-radius: 10px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: rgba(var(--v-theme-primary), 0.12);
}

.package-card {
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  background: rgba(var(--v-theme-surface), 0.7);
  backdrop-filter: blur(8px);
  transition: all 0.22s ease;
}

.package-card--featured {
  border: 2px solid rgba(var(--v-theme-primary), 0.8);
  box-shadow: 0 8px 24px rgba(var(--v-theme-primary), 0.2);
}

.package-card--disabled {
  opacity: 0.66;
}

.package-card:hover:not([disabled]) {
  transform: translateY(-4px);
  border-color: rgba(var(--v-theme-primary), 0.6);
  box-shadow: 0 8px 26px rgba(var(--v-theme-primary), 0.16);
}

.package-detail-wrap {
  background: rgba(var(--v-theme-surface), 0.52);
}

.beli-skeleton {
  border-radius: 16px;
}

.beli-footer {
  border-top: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  background: rgba(var(--v-theme-surface), 0.92);
}

.footer-link {
  color: rgba(var(--v-theme-on-surface), 0.66);
  text-decoration: none;
}

.footer-link:hover {
  color: rgb(var(--v-theme-primary));
}

.v-list-item {
  padding-inline: 0 !important;
}

.payment-method-label {
  gap: 14px;
  padding-block: 10px;
}

.payment-method-text {
  display: flex;
  flex-direction: column;
}

@media (max-width: 600px) {
  .beli-header {
    position: relative;
  }
}

:deep(.payment-method-radio .v-selection-control) {
  min-height: 56px;
}
</style>
