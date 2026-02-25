<script setup lang="ts">
import type { PackagePublic } from '~/types/package'
import { useFetch, useNuxtApp } from '#app'

interface PackagesApiResponse {
  data: PackagePublic[]
  success: boolean
  message: string
}

definePageMeta({
  layout: 'blank',
  public: true,
})

useHead({ title: 'Merchant Center - Babah Digital' })

const { $api } = useNuxtApp()
const {
  merchantName,
  merchantBusinessType,
  merchantAddress,
  supportEmail,
  supportWhatsAppFormatted,
  supportWhatsAppHref,
} = useMerchantProfile()

const packagesRequest = useFetch<PackagesApiResponse>('/packages', {
  key: 'merchantCenterPackages',
  server: true,
  lazy: true,
  $fetch: $api,
})

const { pending: isLoadingPackages, error: fetchPackagesError, refresh: refreshPackages } = packagesRequest
const packageApiResponse = packagesRequest.data as Ref<PackagesApiResponse | null>
const packages = computed(() => packageApiResponse.value?.data ?? [])

function formatRupiah(value: number | null | undefined): string {
  const parsed = Number(value ?? 0)
  return new Intl.NumberFormat('id-ID', {
    style: 'currency',
    currency: 'IDR',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(Number.isFinite(parsed) ? parsed : 0)
}

function formatQuota(gb: number | null | undefined): string {
  const parsed = Number(gb ?? 0)
  if (!Number.isFinite(parsed) || parsed <= 0)
    return 'Sesuai paket'

  return `${parsed.toLocaleString('id-ID', { maximumFractionDigits: 2 })} GB`
}
</script>

<template>
  <div class="merchant-center-page">
    <VContainer class="py-6 py-md-10">
      <VCard class="merchant-hero mb-6" rounded="xl">
        <VCardText class="pa-6 pa-md-8">
          <div class="d-flex flex-column flex-md-row align-start align-md-center justify-space-between ga-4">
            <div>
              <p class="text-overline mb-2 text-white">Merchant Center</p>
              <h1 class="text-h4 text-md-h3 font-weight-bold text-white mb-2">
                {{ merchantName }}
              </h1>
              <p class="text-body-1 text-white mb-0 opacity-90">
                Informasi merchant resmi untuk kebutuhan verifikasi pembayaran dan referensi pelanggan.
              </p>
            </div>

            <div class="d-flex flex-wrap ga-2">
              <VBtn variant="flat" color="white" to="/merchant-center/privacy">
                Privacy Policy
              </VBtn>
              <VBtn variant="outlined" color="white" to="/merchant-center/terms">
                Terms of Service
              </VBtn>
            </div>
          </div>
        </VCardText>
      </VCard>

      <VRow>
        <VCol cols="12" md="8">
          <VCard rounded="xl" class="mb-6">
            <VCardItem>
              <VCardTitle class="text-h6">Produk & Harga (Rupiah)</VCardTitle>
              <VCardSubtitle>Data paket ditarik dinamis dari sistem aktif.</VCardSubtitle>
            </VCardItem>

            <VCardText>
              <VRow v-if="isLoadingPackages" dense>
                <VCol v-for="n in 3" :key="`pkg-skeleton-${n}`" cols="12" md="6">
                  <VSkeletonLoader type="card" />
                </VCol>
              </VRow>

              <VAlert v-else-if="fetchPackagesError" type="warning" variant="tonal" class="mb-2">
                Gagal memuat paket dari server.
                <VBtn class="ms-2" size="small" variant="text" @click="refreshPackages()">
                  Coba Lagi
                </VBtn>
              </VAlert>

              <VAlert v-else-if="packages.length === 0" type="info" variant="tonal">
                Belum ada paket aktif yang dipublikasikan saat ini.
              </VAlert>

              <VRow v-else dense>
                <VCol
                  v-for="pkg in packages"
                  :key="pkg.id"
                  cols="12"
                  md="6"
                  class="d-flex"
                >
                  <VCard variant="outlined" class="w-100 package-card" rounded="lg">
                    <VCardText>
                      <div class="d-flex align-start justify-space-between mb-2 ga-3">
                        <h3 class="text-subtitle-1 font-weight-bold mb-0">
                          {{ pkg.name }}
                        </h3>
                        <VChip size="small" color="primary" variant="tonal">
                          {{ pkg.duration_days }} Hari
                        </VChip>
                      </div>

                      <p class="text-h6 font-weight-bold text-primary mb-1">
                        {{ formatRupiah(pkg.price) }}
                      </p>
                      <p class="text-body-2 mb-2">
                        Kuota: {{ formatQuota(pkg.data_quota_gb) }}
                      </p>
                      <p class="text-body-2 text-medium-emphasis mb-0">
                        {{ pkg.description || 'Paket internet digital dengan aktivasi otomatis setelah pembayaran berhasil.' }}
                      </p>
                    </VCardText>
                  </VCard>
                </VCol>
              </VRow>
            </VCardText>
          </VCard>
        </VCol>

        <VCol cols="12" md="4">
          <VCard rounded="xl" class="mb-6" variant="outlined">
            <VCardItem>
              <VCardTitle class="text-h6">Informasi Merchant</VCardTitle>
            </VCardItem>
            <VCardText>
              <p class="mb-2"><strong>Nama:</strong> {{ merchantName }}</p>
              <p class="mb-2"><strong>Bidang:</strong> {{ merchantBusinessType }}</p>
              <p class="mb-2"><strong>Alamat:</strong> {{ merchantAddress || '-' }}</p>
              <p class="mb-2">
                <strong>Email CS:</strong>
                <a v-if="supportEmail" :href="`mailto:${supportEmail}`">{{ supportEmail }}</a>
                <span v-else>-</span>
              </p>
              <p class="mb-0">
                <strong>WhatsApp CS:</strong>
                <a v-if="supportWhatsAppHref" :href="supportWhatsAppHref" target="_blank" rel="noopener noreferrer">
                  {{ supportWhatsAppFormatted }}
                </a>
                <span v-else>-</span>
              </p>
            </VCardText>
          </VCard>

          <VCard rounded="xl" variant="outlined">
            <VCardItem>
              <VCardTitle class="text-h6">Kebijakan Layanan</VCardTitle>
            </VCardItem>
            <VCardText>
              <ul class="pl-4 mb-3">
                <li>Produk dikirimkan digital secara real-time setelah pembayaran sukses.</li>
                <li>Tidak ada ongkir karena bukan produk fisik.</li>
                <li>Refund hanya untuk kasus pembayaran sukses tetapi layanan gagal masuk.</li>
              </ul>

              <div class="d-flex flex-wrap ga-2">
                <VBtn size="small" color="primary" variant="tonal" to="/merchant-center/privacy">Privacy</VBtn>
                <VBtn size="small" color="primary" variant="tonal" to="/merchant-center/terms">Terms</VBtn>
              </div>
            </VCardText>
          </VCard>
        </VCol>
      </VRow>
    </VContainer>
  </div>
</template>

<style scoped lang="scss">
.merchant-center-page {
  min-block-size: 100vh;
  background: rgb(var(--v-theme-background));
}

.merchant-hero {
  background: linear-gradient(135deg, rgba(var(--v-theme-primary), 1) 0%, rgba(var(--v-theme-primary), 0.72) 100%);
}

.opacity-90 {
  opacity: 0.9;
}

.package-card {
  transition: transform 0.2s ease;
}

.package-card:hover {
  transform: translateY(-2px);
}
</style>
