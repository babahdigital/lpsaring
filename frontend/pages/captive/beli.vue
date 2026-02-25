<script setup lang="ts">
import type { PackagePublic as Package } from '~/types/package'
import type {
  PaymentMethodContract,
  TransactionInitiateResponseContract,
  VaBankContract,
} from '~/types/api/contracts'
import { useFetch, useNuxtApp } from '#app'
import { storeToRefs } from 'pinia'
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useSnackbar } from '~/composables/useSnackbar'
import { useAuthStore } from '~/store/auth'
import { useSettingsStore } from '~/store/settings'

interface PackagesApiResponse {
  data: Package[]
  success: boolean
  message: string
}

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

definePageMeta({
  layout: 'blank',
  auth: false,
  public: true,
})

useHead({ title: 'Beli Paket (Captive)' })

const { $api } = useNuxtApp()
const { ensureMidtransReady } = useMidtransSnap()
const runtimeConfig = useRuntimeConfig()
const merchantBrandBase = computed(() => {
  const raw = String(runtimeConfig.public.merchantLogo ?? runtimeConfig.public.merchantName ?? 'LPSaring').trim()
  if (raw === '')
    return 'LPSaring'
  return raw.replace(/\s*net$/i, '').trim() || 'LPSaring'
})
const router = useRouter()
const authStore = useAuthStore()
const settingsStore = useSettingsStore()
const { isLoggedIn, user } = storeToRefs(authStore)
const { add: addSnackbar } = useSnackbar()

const packagesRequest = useFetch<PackagesApiResponse>('/packages', {
  key: 'captivePackages',
  lazy: false,
  server: true,
  $fetch: $api,
})

const { pending: isLoadingPackages, error: fetchPackagesError, refresh: refreshPackages } = packagesRequest
const packageApiResponse = packagesRequest.data as Ref<PackagesApiResponse | null>
const packages = computed(() => (packageApiResponse.value?.data ?? []))
const isHydrated = ref(false)
const isRenderHydrated = computed(() => isHydrated.value === true)
const isLoggedInForRender = computed(() => isRenderHydrated.value ? isLoggedIn.value === true : false)
const userForRender = computed(() => (isRenderHydrated.value ? user.value : null))
const isDemoModeEnabled = computed(() => {
  if (!isRenderHydrated.value)
    return false
  return isLoggedInForRender.value === true && userForRender.value?.is_demo_user === true
})

function isTestingPackage(pkg: Package): boolean {
  return String(pkg?.name ?? '').trim().toLowerCase().includes('testing')
}

function isDemoDisabledPackage(pkg: Package): boolean {
  return isDemoModeEnabled.value === true && !isTestingPackage(pkg)
}

function canPurchasePackage(pkg: Package): boolean {
  return pkg.is_active === true || (isDemoModeEnabled.value === true && isTestingPackage(pkg))
}

function isPackageSelectable(pkg: Package): boolean {
  return canPurchasePackage(pkg) && !isDemoDisabledPackage(pkg)
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
  return 'Bayar Sekarang'
}

const visiblePackages = computed(() => {
  return packages.value.filter((pkg) => {
    if (pkg.is_active === true)
      return true
    return isDemoModeEnabled.value === true && isTestingPackage(pkg)
  })
})

const featuredPackageId = computed(() => {
  const firstPurchasable = visiblePackages.value.find(pkg => isPackageSelectable(pkg))
  return firstPurchasable?.id ?? null
})

const isInitiatingPayment = ref<string | null>(null)

const showPaymentMethodDialog = ref(false)
const pendingPaymentPackageId = ref<string | null>(null)

const selectedPaymentMethod = ref<PaymentMethod>('qris')
const selectedVaBank = ref<VaBank>('bni')
const vaBankItems = [
  { title: 'BCA', value: 'bca' },
  { title: 'BNI', value: 'bni' },
  { title: 'BRI', value: 'bri' },
  { title: 'Mandiri', value: 'mandiri' },
  { title: 'Permata', value: 'permata' },
  { title: 'CIMB Niaga', value: 'cimb' },
] as const

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
  { value: 'qris' as const, title: 'QRIS', subtitle: 'Scan QR dari aplikasi pembayaran', icon: 'tabler-qrcode' },
  { value: 'gopay' as const, title: 'GoPay', subtitle: 'Buka GoPay / scan QR jika tersedia', icon: 'tabler-wallet' },
  { value: 'shopeepay' as const, title: 'ShopeePay', subtitle: 'Buka ShopeePay / scan QR jika tersedia', icon: 'tabler-wallet' },
  { value: 'va' as const, title: 'Transfer Virtual Account', subtitle: 'Pilih bank, lalu transfer via VA', icon: 'tabler-building-bank' },
] as const

const availablePaymentMethodItems = computed(() => {
  if (providerMode.value === 'core_api') {
    const enabled = new Set(coreApiEnabledMethods.value)
    return allPaymentMethodItems.filter(i => enabled.has(i.value))
  }
  return allPaymentMethodItems.filter(i => i.value !== 'shopeepay')
})

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

watch(fetchPackagesError, (newError) => {
  if (newError) {
    const messageFromServer = (newError as any)?.data?.message
    const errorMessage = (typeof messageFromServer === 'string' && messageFromServer)
      ? messageFromServer
      : 'Gagal memuat daftar paket.'
    addSnackbar({ type: 'error', title: 'Paket', text: errorMessage })
  }
})

const isUserApprovedAndActive = computed(() => {
  return isLoggedInForRender.value && userForRender.value?.is_active === true && userForRender.value.approval_status === 'APPROVED'
})

const userGreeting = computed(() => {
  if (isLoggedInForRender.value && userForRender.value) {
    const name = userForRender.value.full_name
    const nameToDisplay = (name != null && name.trim() !== '') ? name : (userForRender.value.phone_number ?? '')
    const firstName = nameToDisplay.split(' ')[0] || 'Pengguna'
    return `Halo, ${firstName}!`
  }
  return null
})

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

function goToLogin() {
  router.push({ path: '/captive', query: { redirect: '/captive/beli' } })
}

function getMidtransLoadErrorMessage(): string | null {
  const globalWindow = window as typeof window & {
    __midtransSnapLastError?: string
  }
  if (typeof globalWindow.__midtransSnapLastError === 'string' && globalWindow.__midtransSnapLastError.length > 0)
    return globalWindow.__midtransSnapLastError
  return null
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
      try {
        await ensureMidtransReady()
      }
      catch (error) {
        const snapErrorMessage = getMidtransLoadErrorMessage()
        const fallbackMessage = error instanceof Error && error.message ? error.message : 'Gagal memuat Midtrans Snap.'
        throw new Error(snapErrorMessage ?? fallbackMessage)
      }

      if (window.snap == null) {
        const snapErrorMessage = getMidtransLoadErrorMessage()
        throw new Error(snapErrorMessage ?? 'Midtrans belum siap. Silakan coba beberapa saat lagi.')
      }

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
          addSnackbar({ type: 'info', title: 'Pembayaran', text: 'Anda menutup jendela pembayaran.' })
          isInitiatingPayment.value = null
        },
      })
    }
    else if (provider === 'core_api' && (selectedPaymentMethod.value === 'gopay' || selectedPaymentMethod.value === 'shopeepay') && redirectUrl) {
      isInitiatingPayment.value = null
      window.location.href = redirectUrl
    }
    else if (typeof initiatedOrderId === 'string' && initiatedOrderId.trim() !== '') {
      await router.push(`/payment/status?order_id=${encodeURIComponent(initiatedOrderId)}${statusToken ? `&t=${encodeURIComponent(statusToken)}` : ''}`)
      isInitiatingPayment.value = null
    }
    else {
      throw new Error('Gagal memulai pembayaran (Order ID tidak tersedia).')
    }
  }
  catch (err: any) {
    const statusCode = err?.response?.status ?? err?.statusCode
    const message = err?.data?.message
    let fallback = 'Gagal memulai pembayaran.'
    if (statusCode === 401)
      fallback = 'Silakan login terlebih dahulu untuk membeli paket.'
    else if (statusCode === 403)
      fallback = 'Akun Anda belum aktif atau belum disetujui Admin.'
    const runtimeMessage = typeof err?.message === 'string' && err.message ? err.message : null
    addSnackbar({ type: 'error', title: 'Pembayaran', text: typeof message === 'string' && message ? message : (runtimeMessage ?? fallback) })
    isInitiatingPayment.value = null
  }
}

function handlePackageSelection(pkg: Package) {
  if (pkg?.id == null || isInitiatingPayment.value != null)
    return

  if (isDemoDisabledPackage(pkg)) {
    addSnackbar({ type: 'warning', title: 'Mode Demo', text: 'Mode demo aktif: hanya paket Testing yang bisa dipilih.' })
    return
  }

  if (!canPurchasePackage(pkg))
    return

  if (!isLoggedIn.value) {
    addSnackbar({ type: 'warning', title: 'Login', text: 'Silakan login terlebih dahulu untuk membeli paket.' })
    goToLogin()
    return
  }

  if (!isUserApprovedAndActive.value) {
    addSnackbar({ type: 'warning', title: 'Akun', text: 'Akun Anda belum aktif atau belum disetujui Admin.' })
    return
  }

  openPaymentMethodDialog(pkg.id)
}

onMounted(async () => {
  isHydrated.value = true
  if (authStore.initialAuthCheckDone !== true) {
    await authStore.initializeAuth()
  }
})
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
            {{ merchantBrandBase }}<span class="text-primary">Net</span>
          </div>
        </div>

        <div class="d-flex align-center ga-2 ga-sm-3">
          <template v-if="isLoggedInForRender && userGreeting != null">
            <div class="text-right d-none d-md-flex flex-column">
              <span class="text-body-2 font-weight-bold line-height-1">{{ userGreeting }}</span>
              <span class="text-caption text-medium-emphasis line-height-1">{{ isUserApprovedAndActive ? 'User Aktif' : 'Menunggu Aktivasi' }}</span>
            </div>
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
        <p class="text-body-1 text-sm-h6 text-medium-emphasis package-hero-subtitle">
          Dapatkan akses internet super cepat. Pilih paket yang sesuai dengan kebutuhan aktivitas digital Anda hari ini.
        </p>
      </div>

      <v-dialog v-model="showPaymentMethodDialog" max-width="560px" scrim="grey-darken-3" eager>
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
                      <div class="text-body-1 font-weight-medium">{{ item.title }}</div>
                      <div class="text-caption text-medium-emphasis">{{ item.subtitle }}</div>
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

      <v-row v-if="isLoadingPackages" dense>
        <v-col v-for="n in 6" :key="`skel-captive-${n}`" cols="12" sm="6" md="4" lg="3">
          <v-skeleton-loader class="beli-skeleton" type="heading, paragraph, paragraph, button" />
        </v-col>
      </v-row>

      <v-row v-else-if="fetchPackagesError" justify="center">
        <v-col cols="12" md="8" lg="6">
          <v-alert type="error" title="Gagal Memuat Paket" variant="tonal" prominent>
            <p class="mb-4">Tidak dapat mengambil daftar paket.</p>
            <v-btn color="error" @click="refreshPackages">Coba Lagi</v-btn>
          </v-alert>
        </v-col>
      </v-row>

      <v-row v-else-if="visiblePackages.length > 0" class="package-grid">
        <v-col v-for="pkg in visiblePackages" :key="pkg.id" cols="12" sm="6" md="4" lg="3" class="package-grid-col d-flex">
          <v-tooltip :disabled="isDemoDisabledPackage(pkg) !== true" location="top" max-width="280">
            <template #activator="{ props }">
              <div v-bind="props" class="w-100 d-flex">
                <v-card
                  class="package-card d-flex flex-column flex-grow-1"
                  :class="{
                    'package-card--featured': pkg.id === featuredPackageId,
                    'package-card--available': isPackageSelectable(pkg),
                    'package-card--disabled': !isPackageSelectable(pkg),
                  }"
                  rounded="lg"
                  :disabled="!canPurchasePackage(pkg) || isInitiatingPayment != null || isDemoDisabledPackage(pkg)"
                  @click="handlePackageSelection(pkg)"
                >
                  <v-card-item class="package-card-head pb-1">
                    <v-chip
                      v-if="isPackageSelectable(pkg)"
                      color="primary"
                      size="x-small"
                      variant="flat"
                      class="mb-3 font-weight-bold package-status-chip"
                    >
                      Tersedia
                    </v-chip>
                    <v-card-title class="text-h6 font-weight-bold text-wrap px-0 mb-2 text-center package-title">
                      {{ pkg.name }}
                    </v-card-title>
                    <v-card-subtitle class="text-h4 font-weight-bold text-primary px-0 opacity-100 text-center package-price">
                      {{ formatCurrency(pkg.price) }}
                    </v-card-subtitle>
                  </v-card-item>

                  <v-card-text class="pt-0 pb-2 flex-grow-1">
                    <div class="package-detail-wrap pa-3 rounded-lg mb-4">
                      <div class="package-detail-row d-flex align-center mb-2">
                        <v-icon icon="tabler-circle-check" size="18" color="success" class="mr-2" />
                        <span class="text-body-2">Kuota: <span class="font-weight-bold">{{ formatQuota(pkg.data_quota_gb) }}</span></span>
                      </div>
                      <div class="package-detail-row d-flex align-center mb-2">
                        <v-icon icon="tabler-circle-check" size="18" color="success" class="mr-2" />
                        <span class="text-body-2">Kecepatan: <span class="font-weight-bold">Unlimited</span></span>
                      </div>
                      <div class="package-detail-row d-flex align-center">
                        <v-icon icon="tabler-circle-check" size="18" color="success" class="mr-2" />
                        <span class="text-body-2">Aktif: <span class="font-weight-bold">{{ pkg.duration_days }} Hari</span></span>
                      </div>
                    </div>

                    <div class="package-metrics">
                      <div class="package-metric-row d-flex align-center justify-space-between py-1">
                        <span class="text-body-2 text-medium-emphasis d-flex align-center">
                          <v-icon icon="tabler-receipt" size="17" class="mr-2" />
                          Harga / Hari
                        </span>
                        <span class="text-body-2 font-weight-bold">{{ formatPricePerDay(pkg.price, pkg.duration_days) }}</span>
                      </div>
                      <div class="package-metric-row d-flex align-center justify-space-between py-1">
                        <span class="text-body-2 text-medium-emphasis d-flex align-center">
                          <v-icon icon="tabler-chart-pie" size="17" class="mr-2" />
                          Harga / GB
                        </span>
                        <span class="text-body-2 font-weight-bold">{{ formatPricePerGb(pkg.price, pkg.data_quota_gb) }}</span>
                      </div>
                    </div>

                    <p v-if="pkg.description" class="text-caption text-medium-emphasis mt-3 mb-0">
                      {{ pkg.description }}
                    </p>
                  </v-card-text>

                  <v-card-actions class="pa-4 pt-2 mt-auto">
                    <v-btn
                      block
                      color="primary"
                      variant="flat"
                      size="large"
                      class="package-action-btn"
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
            Tidak ada paket aktif yang tersedia saat ini.
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
          <NuxtLink class="footer-link" :to="{ path: '/merchant-center/privacy', query: { from: 'beli' } }">
            Privacy
          </NuxtLink>
          <NuxtLink class="footer-link" :to="{ path: '/merchant-center/terms', query: { from: 'beli' } }">
            Syarat & Ketentuan
          </NuxtLink>
        </div>
      </div>
    </footer>
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
  backdrop-filter: blur(8px);
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
  position: relative;
  overflow: visible;
  border: 1px solid rgba(var(--v-border-color), 0.34);
  background: rgba(var(--v-theme-surface), 0.96);
  width: 100%;
  max-width: 332px;
  margin-inline: auto;
  min-height: 100%;
  transition: all 0.22s ease;
}

.package-card--featured {
  border-color: rgba(var(--v-theme-primary), 0.9);
  box-shadow: 0 8px 24px rgba(var(--v-theme-primary), 0.24);
}

.package-card--available {
  border-color: rgba(var(--v-theme-primary), 0.52);
  box-shadow: inset 0 0 0 1px rgba(var(--v-theme-primary), 0.08);
}

.package-card--disabled {
  opacity: 0.66;
}

.package-card:hover:not([disabled]) {
  transform: translateY(-2px);
  border-color: rgba(var(--v-theme-primary), 0.72);
  box-shadow: 0 10px 28px rgba(var(--v-theme-primary), 0.22);
}

.package-detail-wrap {
  border: 1px solid rgba(var(--v-border-color), 0.22);
  background: rgba(var(--v-theme-background), 0.58);
}

.package-status-chip {
  position: absolute;
  top: -12px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 2;
}

.package-card-head {
  padding-top: 1.1rem;
}

.package-title {
  line-height: 1.25;
}

.package-price {
  min-height: 2.2rem;
}

.package-detail-row {
  color: rgba(var(--v-theme-on-surface), 0.95);
}

.package-metrics {
  border-top: 1px solid rgba(var(--v-border-color), 0.22);
  padding-top: 0.5rem;
}

.package-grid {
  margin-inline: -12px;
}

.package-grid-col {
  padding: 12px;
  min-width: 0;
}

.package-hero-subtitle {
  max-width: 40rem;
  margin-inline: auto;
  font-size: clamp(0.92rem, 2.8vw, 1.02rem);
  line-height: 1.65;
}

.beli-skeleton {
  border-radius: 16px;
}

.beli-footer {
  border-top: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  background: rgba(var(--v-theme-surface), 0.96);
}

.package-action-btn {
  border-radius: 12px;
}

.footer-link {
  color: rgba(var(--v-theme-on-surface), 0.66);
  text-decoration: none;
}

.footer-link:hover {
  color: rgb(var(--v-theme-primary));
}

.payment-method-label {
  gap: 14px;
  padding-block: 10px;
}

.payment-method-text {
  display: flex;
  flex-direction: column;
}

:deep(.payment-method-radio .v-selection-control) {
  min-height: 56px;
}

@media (max-width: 600px) {
  .beli-header {
    position: relative;
  }
}
</style>
