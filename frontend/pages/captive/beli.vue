<script setup lang="ts">
import type { PackagePublic as Package } from '~/types/package'
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

type PaymentMethod = 'qris' | 'gopay' | 'shopeepay' | 'va'
type VaBank = 'bca' | 'bni' | 'bri' | 'mandiri' | 'permata' | 'cimb'

interface InitiateResponse {
  order_id?: string
  snap_token?: string | null
  redirect_url?: string | null
  provider_mode?: 'snap' | 'core_api'
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

definePageMeta({
  layout: 'blank',
  auth: false,
  public: true,
})

useHead({ title: 'Beli Paket (Captive)' })

const { $api } = useNuxtApp()
const { ensureMidtransReady } = useMidtransSnap()
const router = useRouter()
const authStore = useAuthStore()
const settingsStore = useSettingsStore()
const { isLoggedIn, user } = storeToRefs(authStore)
const { add: addSnackbar } = useSnackbar()

const packagesRequest = useFetch<PackagesApiResponse>('/packages', {
  key: 'captivePackages',
  lazy: true,
  server: true,
  $fetch: $api,
})

const { pending: isLoadingPackages, error: fetchPackagesError, refresh: refreshPackages } = packagesRequest
const packageApiResponse = packagesRequest.data as Ref<PackagesApiResponse | null>
const packages = computed(() => (packageApiResponse.value?.data ?? []))

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
  return packages.value.find(p => p.id === pendingPaymentPackageId.value) ?? null
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
  return isLoggedIn.value && user.value?.is_active === true && user.value.approval_status === 'APPROVED'
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
        onSuccess: (result: SnapPayResult) => router.push(`/payment/status?status=success&order_id=${result.order_id}`),
        onPending: (result: SnapPayResult) => router.push(`/payment/status?status=pending&order_id=${result.order_id}`),
        onError: (result: SnapPayResult) => router.push(`/payment/status?status=error&order_id=${result.order_id}`),
        onClose: () => {
          if (typeof initiatedOrderId === 'string' && initiatedOrderId !== '') {
            void $api(`/transactions/${encodeURIComponent(initiatedOrderId)}/cancel`, { method: 'POST' }).catch(() => {})
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
      await router.push(`/payment/status?order_id=${encodeURIComponent(initiatedOrderId)}`)
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
  if (pkg?.id == null || pkg.is_active !== true || isInitiatingPayment.value != null)
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
  if (authStore.initialAuthCheckDone !== true) {
    await authStore.initializeAuth()
  }
})
</script>

<template>
  <v-container fluid class="pa-0 ma-0 bg-grey-lighten-5 full-height-container">
    <v-col cols="12" style="max-width: 1200px;" class="mx-auto">
      <v-container fluid class="py-6 px-lg-10 px-md-6 px-sm-4">
        <h1 class="text-h4 text-sm-h3 font-weight-bold mb-2 text-center text-grey-darken-3">
          BELI PAKET HOTSPOT
        </h1>
        <p class="text-center text-medium-emphasis mb-6">
          Pilih paket untuk melanjutkan pembayaran melalui Midtrans.
        </p>

      </v-container>

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

      <v-row class="ma-0" align="start" justify="center">
        <v-col cols="12">
          <v-row v-if="isLoadingPackages" justify="center" dense class="px-lg-8 px-md-4 px-sm-2">
            <v-col v-for="n in 4" :key="`skel-captive-${n}`" cols="12" sm="6" md="4" lg="3">
              <v-skeleton-loader type="image, article, actions" height="300" />
            </v-col>
          </v-row>

          <v-row v-else-if="fetchPackagesError" justify="center" class="px-lg-8 px-md-4 px-sm-2">
            <v-col cols="12" md="8" lg="6">
              <v-alert type="error" title="Gagal Memuat Paket" variant="tonal" prominent>
                <p class="mb-4">
                  Tidak dapat mengambil daftar paket.
                </p>
                <v-btn color="error" @click="refreshPackages">
                  Coba Lagi
                </v-btn>
              </v-alert>
            </v-col>
          </v-row>

          <div v-else class="px-lg-8 px-md-4 px-sm-2">
            <v-row v-if="packages.length > 0" dense justify="center">
              <v-col v-for="pkg in packages" :key="pkg.id" cols="12" sm="6" md="4" lg="3" class="pa-2 d-flex">
                <v-card
                  class="d-flex flex-column flex-grow-1"
                  variant="outlined"
                  hover
                  rounded="lg"
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
                    <p v-if="pkg.description" class="text-caption text-medium-emphasis mt-3 px-1">
                      {{ pkg.description }}
                    </p>
                  </v-card-text>

                  <v-card-actions class="pa-4 mt-auto">
                    <v-btn
                      block
                      color="primary"
                      variant="flat"
                      size="large"
                      :disabled="pkg.is_active !== true || isInitiatingPayment != null"
                      :loading="isInitiatingPayment === pkg.id"
                      @click.stop="handlePackageSelection(pkg)"
                    >
                      {{ pkg.is_active === true ? 'Bayar Sekarang' : 'Tidak Tersedia' }}
                    </v-btn>
                  </v-card-actions>
                </v-card>
              </v-col>
            </v-row>
            <v-row v-else justify="center">
              <v-col cols="12" md="8" lg="6">
                <v-alert type="info" variant="tonal" prominent>
                  Tidak ada paket aktif yang tersedia saat ini.
                </v-alert>
              </v-col>
            </v-row>
          </div>
        </v-col>
      </v-row>
    </v-col>
  </v-container>
</template>

<style scoped>
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
</style>
