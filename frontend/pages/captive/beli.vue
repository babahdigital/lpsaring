<script setup lang="ts">
import type { PackagePublic as Package } from '~/types/package'
import { useFetch, useNuxtApp } from '#app'
import { storeToRefs } from 'pinia'
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useSnackbar } from '~/composables/useSnackbar'
import { useAuthStore } from '~/store/auth'

interface PackagesApiResponse {
  data: Package[]
  success: boolean
  message: string
}

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

definePageMeta({
  layout: 'blank',
  auth: false,
})

useHead({ title: 'Beli Paket (Captive)' })

const { $api } = useNuxtApp()
const { ensureMidtransReady } = useMidtransSnap()
const router = useRouter()
const authStore = useAuthStore()
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
          addSnackbar({ type: 'info', title: 'Pembayaran', text: 'Anda menutup jendela pembayaran.' })
          isInitiatingPayment.value = null
        },
      })
    }
    else {
      throw new Error('Gagal mendapatkan token pembayaran.')
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

  initiatePayment(pkg.id)
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
