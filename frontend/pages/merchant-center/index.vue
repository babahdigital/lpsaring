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
    <VContainer class="py-4 py-sm-6 py-md-10">
      <VCard class="merchant-hero mb-6 mb-sm-8" rounded="0">
        <VCardText class="pa-6 pa-sm-8 pa-md-10">
          <div class="d-flex flex-column flex-md-row align-start align-md-center justify-space-between ga-6">
            <div class="w-100 w-md-auto">
              <p class="hero-overline mb-2">Merchant Center</p>
              <h1 class="hero-title mb-3">
                {{ merchantName }}
              </h1>
              <p class="hero-subtitle mb-0">
                Informasi merchant resmi untuk kebutuhan verifikasi pembayaran dan referensi pelanggan. Berkomitmen memberikan layanan internet terbaik.
              </p>
            </div>

            <div class="hero-actions w-100 w-md-auto">
              <VBtn class="hero-btn" variant="outlined" color="white" to="/merchant-center/privacy" size="large">
                Privacy Policy
              </VBtn>
              <VBtn class="hero-btn" variant="flat" color="white" to="/merchant-center/terms" size="large">
                Terms Of Service
              </VBtn>
            </div>
          </div>
        </VCardText>
      </VCard>

      <VRow class="ga-0" align="start">
        <VCol cols="12" lg="8" class="pe-lg-4">
          <VCard class="surface-card mb-6 mb-lg-0" rounded="0" variant="outlined">
            <VCardText class="pa-6 pa-sm-8">
              <div class="mb-6 mb-sm-8">
                <h2 class="section-title mb-2">Produk & Harga</h2>
                <p class="section-subtitle mb-0">Data paket ditarik dinamis dari sistem aktif. Harga dalam Rupiah (IDR).</p>
              </div>

              <VRow v-if="isLoadingPackages" dense>
                <VCol v-for="n in 4" :key="`pkg-skeleton-${n}`" cols="12" sm="6">
                  <VSkeletonLoader type="card" class="rounded-xl" />
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
                  sm="6"
                  class="d-flex"
                >
                  <VCard variant="outlined" class="w-100 package-card" rounded="0">
                    <VCardText class="pa-5 pa-sm-6 d-flex flex-column h-100">
                      <div class="d-flex align-start justify-space-between mb-4 mb-sm-5 ga-2">
                        <h3 class="text-subtitle-1 font-weight-bold text-white mb-0">
                          {{ pkg.name }}
                        </h3>
                        <VChip size="small" color="primary" variant="tonal" class="font-weight-bold">
                          {{ pkg.duration_days }} Hari
                        </VChip>
                      </div>

                      <div class="mb-4 mb-sm-5">
                        <p class="text-h5 text-sm-h4 font-weight-black text-primary mb-1">
                          {{ formatRupiah(pkg.price) }}
                        </p>
                        <p class="text-caption text-sm-body-2 text-medium-emphasis mb-0">
                          Kuota Utama: <span class="text-white font-weight-bold">{{ formatQuota(pkg.data_quota_gb) }}</span>
                        </p>
                      </div>

                      <div class="mt-auto package-divider pt-3 pt-sm-4">
                        <p class="text-caption text-sm-body-2 text-medium-emphasis mb-0">
                          {{ pkg.description || 'Paket internet digital dengan aktivasi otomatis setelah pembayaran berhasil.' }}
                        </p>
                      </div>
                    </VCardText>
                  </VCard>
                </VCol>
              </VRow>
            </VCardText>
          </VCard>
        </VCol>

        <VCol cols="12" lg="4" class="ps-lg-4">
          <VCard class="surface-card mb-6" rounded="0" variant="outlined">
            <VCardText class="pa-6 pa-sm-8">
              <div class="section-head mb-5 mb-sm-6">
                <span class="section-head-accent" />
                <h3 class="text-h6 text-sm-h5 font-weight-bold text-white mb-0">Informasi Merchant</h3>
              </div>

              <div class="merchant-meta">
                <div class="meta-item">
                  <span class="meta-label">Nama</span>
                  <span class="meta-value">{{ merchantName }}</span>
                </div>
                <div class="meta-item">
                  <span class="meta-label">Bidang</span>
                  <span class="meta-value">{{ merchantBusinessType }}</span>
                </div>
                <div class="meta-item">
                  <span class="meta-label">Alamat</span>
                  <span class="meta-value">{{ merchantAddress || '-' }}</span>
                </div>
                <div class="meta-item">
                  <span class="meta-label">Email CS</span>
                  <a v-if="supportEmail" class="meta-link" :href="`mailto:${supportEmail}`">{{ supportEmail }}</a>
                  <span v-else class="meta-value">-</span>
                </div>
                <div class="meta-item">
                  <span class="meta-label">WhatsApp CS</span>
                  <a v-if="supportWhatsAppHref" class="meta-link" :href="supportWhatsAppHref" target="_blank" rel="noopener noreferrer">
                    {{ supportWhatsAppFormatted }}
                  </a>
                  <span v-else class="meta-value">-</span>
                </div>
              </div>
            </VCardText>
          </VCard>

          <VCard class="surface-card" rounded="0" variant="outlined">
            <VCardText class="pa-6 pa-sm-8">
              <div class="section-head mb-5 mb-sm-6">
                <span class="section-head-accent" />
                <h3 class="text-h6 text-sm-h5 font-weight-bold text-white mb-0">Kebijakan Layanan</h3>
              </div>

              <ul class="policy-list mb-6 mb-sm-8">
                <li class="policy-item">Produk dikirimkan digital secara real-time setelah pembayaran sukses.</li>
                <li class="policy-item">Tidak ada ongkir karena bukan produk fisik.</li>
                <li class="policy-item">Refund hanya untuk kasus pembayaran sukses tetapi layanan gagal masuk.</li>
              </ul>

              <div class="d-flex flex-column ga-3">
                <VBtn block variant="tonal" color="secondary" to="/merchant-center/privacy">Lihat Privacy Policy</VBtn>
                <VBtn block variant="tonal" color="secondary" to="/merchant-center/terms">Lihat Terms Of Service</VBtn>
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
  border-radius: 1rem;
  background: linear-gradient(135deg, rgba(var(--v-theme-primary), 1) 0%, rgba(var(--v-theme-primary), 0.74) 100%);
  box-shadow: 0 12px 30px rgba(var(--v-theme-primary), 0.22);
}

.hero-overline {
  color: rgba(255, 255, 255, 0.74);
  font-size: 0.72rem;
  font-weight: 700;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

.hero-title {
  color: #fff;
  font-size: clamp(1.85rem, 5vw, 2.4rem);
  line-height: 1.12;
  font-weight: 800;
  letter-spacing: -0.01em;
}

.hero-subtitle {
  max-inline-size: 40rem;
  color: rgba(255, 255, 255, 0.9);
  line-height: 1.65;
  font-size: clamp(0.92rem, 2.8vw, 1.02rem);
}

.hero-actions {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.hero-btn {
  inline-size: 100%;
  min-inline-size: 0;
}

.surface-card {
  border-radius: 1rem;
  box-shadow: 0 10px 24px rgba(15, 20, 34, 0.22);
  border-color: rgba(var(--v-border-color), 0.4) !important;
}

.section-title {
  color: rgb(var(--v-theme-on-surface));
  font-size: clamp(1.25rem, 3.4vw, 1.55rem);
  font-weight: 800;
  letter-spacing: -0.01em;
}

.section-subtitle {
  color: rgba(var(--v-theme-on-surface), 0.68);
  font-size: 0.9rem;
}

.package-card {
  border-radius: 0.85rem;
  box-shadow: 0 6px 16px rgba(15, 20, 34, 0.18);
  border-color: rgba(var(--v-border-color), 0.45) !important;
  transition: transform 0.28s ease, box-shadow 0.28s ease, border-color 0.28s ease;
}

.package-card {
  &:hover {
    transform: translateY(-4px);
    box-shadow: 0 14px 30px rgba(var(--v-theme-primary), 0.18);
    border-color: rgba(var(--v-theme-primary), 0.5) !important;
  }
}

.package-divider {
  border-top: 1px solid rgba(var(--v-border-color), 0.3);
}

.section-head {
  display: flex;
  align-items: center;
  gap: 0.6rem;
}

.section-head-accent {
  inline-size: 0.38rem;
  block-size: 1.55rem;
  border-radius: 999px;
  background: rgb(var(--v-theme-primary));
}

.merchant-meta {
  display: grid;
  gap: 0.95rem;
}

.meta-item {
  display: grid;
  gap: 0.2rem;
}

.meta-label {
  color: rgba(var(--v-theme-on-surface), 0.58);
  font-size: 0.7rem;
  text-transform: uppercase;
  letter-spacing: 0.12em;
  font-weight: 700;
}

.meta-value {
  color: rgb(var(--v-theme-on-surface));
  font-size: 0.93rem;
  line-height: 1.55;
  font-weight: 500;
}

.meta-link {
  color: rgb(var(--v-theme-primary));
  text-decoration: none;
  font-size: 0.93rem;
  line-height: 1.55;
  font-weight: 600;
  word-break: break-word;

  &:hover {
    text-decoration: underline;
  }
}

.policy-list {
  list-style: none;
  padding-inline-start: 0;
  display: grid;
  gap: 0.8rem;
}

.policy-item {
  position: relative;
  padding-inline-start: 1.05rem;
  color: rgba(var(--v-theme-on-surface), 0.86);
  font-size: 0.9rem;
  line-height: 1.6;

  &::before {
    content: '';
    position: absolute;
    inset-inline-start: 0;
    inset-block-start: 0.55rem;
    inline-size: 0.32rem;
    block-size: 0.32rem;
    border-radius: 999px;
    background: rgb(var(--v-theme-primary));
  }
}

@media (min-width: 600px) {
  .hero-actions {
    flex-direction: row;
    align-items: center;
    flex-wrap: wrap;
  }

  .hero-btn {
    inline-size: auto;
    min-inline-size: 11.25rem;
  }
}

@media (max-width: 359px) {
  .hero-title {
    font-size: 1.65rem;
  }
}
</style>
