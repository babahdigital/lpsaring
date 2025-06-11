<script setup lang="ts">
import { useGenerateImageVariant } from '@core/composable/useGenerateImageVariant'
import miscMaskDark from '@images/pages/misc-mask-dark.png'
import miscMaskLight from '@images/pages/misc-mask-light.png'
import miscUnderMaintenance from '@images/pages/misc-under-maintenance.png'
import { useMaintenanceStore } from '@/store/maintenance'

// --- PENAMBAHAN BARU ---
// Impor komponen PromoAnnouncement secara dinamis
import { defineAsyncComponent } from 'vue'
const PromoAnnouncement = defineAsyncComponent(() => import('~/components/promo/PromoAnnouncement.vue'))
// --- AKHIR PENAMBAHAN ---

const authThemeMask = useGenerateImageVariant(miscMaskLight, miscMaskDark)
const maintenanceStore = useMaintenanceStore()

// Pesan diambil secara dinamis dari store
const message = computed(() => maintenanceStore.message || "Aplikasi sedang dalam perbaikan. Kami akan segera kembali.")

definePageMeta({
  layout: 'blank',
  public: true,
})
useHead({ title: 'Maintenance On' })
</script>

<template>
  <NuxtLayout>
    <div class="misc-wrapper">
      <div class="text-center mb-15">
        <h4 class="text-h4 font-weight-medium mb-2">
          Sedang Dalam Pemeliharaan! 🚧
        </h4>
        <p class="text-body-1 mb-6">
          {{ message }}
        </p>

        <!-- --- PENAMBAHAN BARU --- -->
        <!-- Menampilkan promo di sini jika ada -->
        <div class="mx-auto" style="max-width: 600px;">
          <PromoAnnouncement />
        </div>
        <!-- --- AKHIR PENAMBAHAN --- -->

        <VBtn to="/">
          Kembali ke Halaman Utama
        </VBtn>
      </div>

      <div class="misc-avatar w-100 text-center">
        <VImg
          :src="miscUnderMaintenance"
          alt="Under Maintenance"
          :max-width="550"
          :min-height="300"
          class="mx-auto"
        />
      </div>

      <img
        class="misc-footer-img d-none d-md-block"
        :src="authThemeMask"
        alt="misc-footer-img"
        height="320"
      >
    </div>
  </NuxtLayout>
</template>

<style lang="scss" scoped>
@use "@core/scss/template/pages/misc.scss";
</style>