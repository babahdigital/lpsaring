<script setup lang="ts">
import { definePageMeta, useHead } from '#imports'
import { useNuxtApp } from 'nuxt/app'
import { storeToRefs } from 'pinia'
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import type { PackagePublic as Package } from '~/types/package'

import { useApiFetch } from '~/composables/useApiFetch'
import { useMidtrans } from '~/composables/useMidtrans'
import { useSnackbar } from '~/composables/useSnackbar'
import { useAuthStore } from '~/store/auth'

interface PackagesApiResponse {
  data: Package[]
  success: boolean
  message: string
}

definePageMeta({ layout: 'blank' })
useHead({ title: 'Beli Paket Hotspot' })

const authStore = useAuthStore()
const router = useRouter()
const route = useRoute()
const { $api } = useNuxtApp()
const { add: showGlobalSnackbar } = useSnackbar()

const { pay: midtransPay } = useMidtrans()

const { user } = storeToRefs(authStore)

const { data: packageApiResponse, pending: isLoadingPackages, error: fetchPackagesError = ref(null), refresh: refreshPackages }
  = useApiFetch<PackagesApiResponse>('/packages', {
    key: 'publicPackages',
    lazy: true,
    server: true,
  })

const packages = computed(() => packageApiResponse.value?.data ?? [])

const pageState = computed<'loading' | 'error' | 'empty' | 'success'>(() => {
  if (isLoadingPackages.value)
    return 'loading'
  if (fetchPackagesError.value)
    return 'error'
  if (packages.value.length === 0)
    return 'empty'
  return 'success'
})

const isInitiatingPayment = ref<string | null>(null)

watch(fetchPackagesError, (newError) => {
  if (newError && newError.statusCode !== 401 && newError.statusCode !== 403) {
    const messageFromServer = (newError as any)?.data?.message
    const errorMessage = (typeof messageFromServer === 'string' && messageFromServer)
      ? messageFromServer
      : 'Gagal memuat daftar paket.'
    showGlobalSnackbar({ type: 'error', title: 'Gagal Memuat', text: errorMessage })
  }
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

const userGreeting = computed(() => {
  if (user.value) {
    const name = user.value.full_name || ''
    const phone = user.value.phone_number || ''
    const nameToDisplay = name.trim() ? name.trim() : phone
    if (nameToDisplay)
      return `Halo, ${nameToDisplay.split(' ')[0]}!`
  }
  return null
})

const isUserApprovedAndActive = computed(() => {
  return user.value?.is_active === true && user.value.approval_status === 'APPROVED'
})

const purchaseDisabledReason = computed(() => {
  if (isUserApprovedAndActive.value)
    return ''
  if (user.value?.approval_status === 'PENDING_APPROVAL')
    return 'Akun Anda sedang menunggu persetujuan Admin.'
  if (user.value?.approval_status === 'REJECTED')
    return 'Pendaftaran akun Anda telah ditolak.'
  return 'Akun Anda belum aktif atau belum disetujui untuk melakukan pembelian.'
})

function retryFetch() {
  refreshPackages()
}

function goToDashboard() {
  router.push('/dashboard')
}

function handlePackageSelection(pkg: Package) {
  if (pkg?.id == null || pkg.is_active !== true || isInitiatingPayment.value != null)
    return
  if (!isUserApprovedAndActive.value) {
    return
  }
  if (user.value?.id != null)
    initiatePayment(pkg.id)
}

async function initiatePayment(packageId: string) {
  isInitiatingPayment.value = packageId
  try {
    const responseData = await $api<{ snap_token: string, order_id: string }>('/transactions/initiate', {
      method: 'POST',
      body: { package_id: packageId },
    })

    if (responseData?.snap_token) {
      await midtransPay(responseData.snap_token, {
        onSuccess: (result: any) => router.push(`/payment/finish?status=success&order_id=${result.order_id}`),
        onPending: (result: any) => router.push(`/payment/finish?status=pending&order_id=${result.order_id}`),
        onError: (result: any) => router.push(`/payment/finish?status=error&order_id=${result.order_id}`),
        onClose: () => {
          if (!router.currentRoute.value.path.startsWith('/payment/finish'))
            showGlobalSnackbar({ type: 'info', title: 'Informasi', text: 'Anda menutup jendela pembayaran.' })
          isInitiatingPayment.value = null
        },
      })
    }
    else {
      throw new Error('Gagal mendapatkan token pembayaran.')
    }
  }
  catch (err: any) {
    const message = err.data?.message || 'Gagal memulai pembayaran.'
    showGlobalSnackbar({ type: 'error', title: 'Gagal', text: message })
    isInitiatingPayment.value = null
  }
}

onMounted(() => {
  const query = route.query
  if (query.action === 'cancelled' && query.order_id) {
    showGlobalSnackbar({ type: 'info', title: 'Dibatalkan', text: `Pembayaran Order ID ${query.order_id} dibatalkan.` })
    router.replace({ query: {} })
  }
  else if (query.action === 'error' && query.order_id) {
    const errorMsg = query.msg ? decodeURIComponent(query.msg as string) : 'Terjadi kesalahan pembayaran'
    showGlobalSnackbar({ type: 'error', title: 'Gagal', text: `Pembayaran Order ID ${query.order_id} gagal: ${errorMsg}`, timeout: 8000 })
    router.replace({ query: {} })
  }
})
</script>

<template>
  <VContainer fluid class="pa-0 ma-0 bg-grey-lighten-5 full-height-container">
    <VCol cols="12" style="max-width: 1300px;" class="mx-auto">
      <VContainer fluid class="py-8 px-lg-12 px-md-6 px-sm-4">
        <h1 class="text-h4 text-sm-h3 font-weight-bold mb-2 text-center text-grey-darken-3 d-flex align-center justify-center">
          <svg xmlns="http://www.w3.org/2000/svg" class="text-primary me-3" width="32" height="32" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" fill="none" stroke-linecap="round" stroke-linejoin="round"><path stroke="none" d="M0 0h24v24H0z" fill="none" /><path d="M6 19m-2 0a2 2 0 1 0 4 0a2 2 0 1 0 -4 0" /><path d="M17 19m-2 0a2 2 0 1 0 4 0a2 2 0 1 0 -4 0" /><path d="M17 17h-11v-14h-2" /><path d="M6 5l14 1l-1 7h-13" /></svg>
          DAFTAR PAKET HOTSPOT
        </h1>
        <div class="text-center mb-6" style="min-height: 40px;">
          <div v-if="userGreeting" class="d-flex justify-center align-center text-body-1 text-medium-emphasis flex-wrap">
            <span class="mr-3">{{ userGreeting }}</span>
            <VBtn v-if="isUserApprovedAndActive" variant="outlined" color="primary" size="small" @click="goToDashboard">
              <svg xmlns="http://www.w3.org/2000/svg" class="me-2" width="18" height="18" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" fill="none" stroke-linecap="round" stroke-linejoin="round"><path stroke="none" d="M0 0h24v24H0z" fill="none" /><path d="M4 4h6v8h-6z" /><path d="M4 16h6v4h-6z" /><path d="M14 12h6v8h-6z" /><path d="M14 4h6v4h-6z" /></svg>
              Ke Panel
            </VBtn>
          </div>
        </div>
      </VContainer>

      <VRow class="ma-0" align="start" justify="center">
        <VCol cols="12">
          <VRow v-if="pageState === 'loading'" justify="center" dense class="px-lg-10 px-md-4 px-sm-2">
            <VCol v-for="n in 4" :key="`skel-pkg-${n}`" cols="12" sm="6" md="4" lg="3">
              <VSkeletonLoader type="image, article, actions" height="320" />
            </VCol>
          </VRow>

          <div v-else-if="pageState === 'error'" class="text-center pa-8">
            <VSheet max-width="500" class="mx-auto pa-8 rounded-xl bg-transparent">
              <svg xmlns="http://www.w3.org/2000/svg" class="text-error mb-5" width="64" height="64" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" fill="none" stroke-linecap="round" stroke-linejoin="round"><path stroke="none" d="M0 0h24v24H0z" fill="none" /><path d="M12 9v4" /><path d="M10.363 3.591l-8.106 13.534a1.914 1.914 0 0 0 1.636 2.871h16.214a1.914 1.914 0 0 0 1.636 -2.87l-8.106 -13.536a1.914 1.914 0 0 0 -3.274 0z" /><path d="M12 16h.01" /></svg>
              <h2 class="text-h5 font-weight-bold mb-3">
                Gagal Memuat Paket
              </h2>
              <p class="text-body-1 text-medium-emphasis mb-6">
                Tidak dapat mengambil daftar paket dari server saat ini. Silakan coba lagi beberapa saat.
              </p>
              <VBtn color="primary" size="large" @click="retryFetch">
                <svg xmlns="http://www.w3.org/2000/svg" class="me-2" width="20" height="20" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" fill="none" stroke-linecap="round" stroke-linejoin="round"><path stroke="none" d="M0 0h24v24H0z" fill="none" /><path d="M20 11a8.1 8.1 0 0 0 -15.5 -2m-.5 -4v4h4" /><path d="M4 13a8.1 8.1 0 0 0 15.5 2m.5 4v-4h-4" /></svg>
                Coba Lagi
              </VBtn>
            </VSheet>
          </div>

          <div v-else-if="pageState === 'empty'" class="text-center pa-8">
            <VSheet max-width="500" class="mx-auto pa-8 rounded-xl bg-transparent">
              <svg xmlns="http://www.w3.org/2000/svg" class="text-grey-lighten-1 mb-5" width="64" height="64" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" fill="none" stroke-linecap="round" stroke-linejoin="round"><path stroke="none" d="M0 0h24v24H0z" fill="none" /><path d="M8.312 4.312l8.688 8.688" /><path d="M16 16l-4.43 -4.43" /><path d="M12.48 8.48l-2.58 2.58" /><path d="M12 3l.329 .556" /><path d="M16.126 4.36l.243 .432" /><path d="M19.636 7.364l.244 .434" /><path d="M20.985 11.213l.015 .587" /><path d="M4.364 7.364l-.244 .434" /><path d="M3.015 11.213l-.015 .587" /><path d="M7.874 4.36l-.243 .432" /><path d="M12 21a9 9 0 0 0 8.985 -8.213" /><path d="M3 12a9 9 0 0 0 .015 8.213" /></svg>
              <h2 class="text-h5 font-weight-bold mb-3 text-grey-darken-2">
                Belum Ada Paket Tersedia
              </h2>
              <p class="text-body-1 text-medium-emphasis mb-6">
                Saat ini belum ada paket hotspot yang aktif. Silakan cek kembali nanti.
              </p>
              <VBtn color="grey-darken-1" variant="text" @click="retryFetch">
                <svg xmlns="http://www.w3.org/2000/svg" class="me-2" width="20" height="20" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" fill="none" stroke-linecap="round" stroke-linejoin="round"><path stroke="none" d="M0 0h24v24H0z" fill="none" /><path d="M20 11a8.1 8.1 0 0 0 -15.5 -2m-.5 -4v4h4" /><path d="M4 13a8.1 8.1 0 0 0 15.5 2m.5 4v-4h-4" /></svg>
                Refresh Halaman
              </VBtn>
            </VSheet>
          </div>

          <div v-else-if="pageState === 'success'" class="px-lg-10 px-md-4 px-sm-2">
            <VRow dense justify="center">
              <VCol v-for="pkg in packages" :key="pkg.id" cols="12" sm="6" md="4" lg="3" class="pa-2 d-flex">
                <VTooltip :text="purchaseDisabledReason" :disabled="isUserApprovedAndActive" location="top center">
                  <template #activator="{ props: tooltipProps }">
                    <VCard
                      v-bind="tooltipProps"
                      class="d-flex flex-column flex-grow-1"
                      variant="outlined" hover rounded="lg"
                      :disabled="pkg.is_active !== true || isInitiatingPayment != null || !isUserApprovedAndActive"
                      @click="handlePackageSelection(pkg)"
                    >
                      <VCardItem class="text-left">
                        <VCardTitle class="text-h6 text-wrap font-weight-bold mb-2">
                          {{ pkg.name }}
                        </VCardTitle>
                        <VCardSubtitle class="text-h5 font-weight-bold text-primary">
                          {{ formatCurrency(pkg.price) }}
                        </VCardSubtitle>
                      </VCardItem>

                      <VCardText class="flex-grow-1 py-2 text-left">
                        <VList lines="one" density="compact" bg-color="transparent" class="py-0">
                          <VListItem>
                            <template #prepend>
                              <div class="me-2 d-flex align-center" style="width: 20px; height: 20px;">
                                <svg xmlns="http://www.w3.org/2000/svg" class="text-info" width="20" height="20" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" fill="none" stroke-linecap="round" stroke-linejoin="round"><path stroke="none" d="M0 0h24v24H0z" fill="none" /><path d="M12 6m-8 0c0 1.657 3.582 3 8 3s8 -1.343 8 -3s-3.582 -3 -8 -3s-8 1.343 -8 3" /><path d="M4 6v6c0 1.657 3.582 3 8 3s8 -1.343 8 -3v-6" /><path d="M4 12v6c0 1.657 3.582 3 8 3s8 -1.343 8 -3v-6" /></svg>
                              </div>
                            </template>
                            <VListItemTitle class="text-body-2">
                              Kuota: <span class="font-weight-medium">{{ formatQuota(pkg.data_quota_gb) }}</span>
                            </VListItemTitle>
                          </VListItem>
                          <VListItem>
                            <template #prepend>
                              <div class="me-2 d-flex align-center" style="width: 20px; height: 20px;">
                                <svg xmlns="http://www.w3.org/2000/svg" class="text-warning" width="20" height="20" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" fill="none" stroke-linecap="round" stroke-linejoin="round"><path stroke="none" d="M0 0h24v24H0z" fill="none" /><path d="M12 12m-9 0a9 9 0 1 0 18 0a9 9 0 1 0 -18 0" /><path d="M12 12l3.5 0" /><path d="M12 7v5" /></svg>
                              </div>
                            </template>
                            <VListItemTitle class="text-body-2">
                              Aktif: <span class="font-weight-medium">{{ pkg.duration_days }} Hari</span>
                            </VListItemTitle>
                          </VListItem>
                        </VList>
                        <p v-if="pkg.description" class="text-caption text-medium-emphasis mt-3 px-1">
                          {{ pkg.description }}
                        </p>
                      </VCardText>

                      <VCardActions class="pa-4 mt-auto">
                        <VBtn
                          block color="primary" variant="flat" size="large"
                          :disabled="pkg.is_active !== true || isInitiatingPayment != null || !isUserApprovedAndActive"
                          :loading="isInitiatingPayment === pkg.id"
                          @click.stop="handlePackageSelection(pkg)"
                        >
                          <svg xmlns="http://www.w3.org/2000/svg" class="me-2" width="20" height="20" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" fill="none" stroke-linecap="round" stroke-linejoin="round"><path stroke="none" d="M0 0h24v24H0z" fill="none" /><path d="M4 19a2 2 0 1 0 4 0a2 2 0 1 0 -4 0" /><path d="M12.5 17h-6.5v-14h-2" /><path d="M6 5l14 1l-.86 6.017m-2.64 .983h-10.5" /><path d="M16 19h6" /><path d="M19 16v6" /></svg>
                          {{ pkg.is_active === true ? 'Beli Sekarang' : 'Tidak Tersedia' }}
                        </VBtn>
                      </VCardActions>
                    </VCard>
                  </template>
                </VTooltip>
              </VCol>
            </VRow>
          </div>
        </VCol>
      </VRow>
    </VCol>
  </VContainer>
</template>

<style scoped>
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
