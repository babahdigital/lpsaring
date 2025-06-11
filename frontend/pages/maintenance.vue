<script setup lang="ts">
import { useGenerateImageVariant } from '@core/composable/useGenerateImageVariant'
import miscMaskDark from '@images/pages/misc-mask-dark.png'
import miscMaskLight from '@images/pages/misc-mask-light.png'
import miscUnderMaintenance from '@images/pages/misc-under-maintenance.png'
// import { useMaintenanceStore } from '@/store/maintenance' // Tidak perlu lagi diimpor jika pesan statis

const authThemeMask = useGenerateImageVariant(miscMaskLight, miscMaskDark)

// Jika Anda ingin pesan maintenance tetap dinamis dari store, Anda perlu mengimpornya kembali.
// const maintenanceStore = useMaintenanceStore()
// const message = computed(() => maintenanceStore.message || "Aplikasi sedang dalam perbaikan. Kami akan segera kembali.")

definePageMeta({
  layout: 'blank',
  public: true, // Pastikan halaman ini bisa diakses publik
})

// Hapus bagian onMounted yang memuat settings di sini.
// Data maintenance seharusnya sudah diisi oleh plugin atau middleware sebelum halaman ini dirender.
</script>

<template>
  <div class="misc-wrapper">
    <div class="text-center mb-15">
      <h4 class="text-h4 font-weight-medium mb-2">
        Under Maintenance! 🚧
      </h4>
      <p class="text-body-1 mb-6">
        Sorry for the inconvenience but we're performing some maintenance at the moment
      </p>

      <VBtn to="/">
        Back to Home
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
</template>

<style lang="scss" scoped>
@use "@core/scss/template/pages/misc.scss";
</style>