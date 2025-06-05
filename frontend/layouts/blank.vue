<script lang="ts" setup>
import { useSkins } from '@core/composable/useSkins' // Pastikan path import ini benar

const { injectSkinClasses } = useSkins()

// ℹ️ This will inject classes in body tag for accurate styling
injectSkinClasses()
</script>

<template>
  <div
    class="layout-wrapper layout-blank"
    data-allow-mismatch
  >
    <v-app>
      <v-main>
        <slot />
      </v-main>
    </v-app>
  </div>
</template>

<style>
/* Style dasar untuk wrapper jika diperlukan oleh tema */
/* Hindari menambahkan style yang memaksakan tinggi atau centering di sini */
.layout-wrapper.layout-blank {
  /* Style minimal yang mungkin dibutuhkan oleh tema Anda */
  /* Misalnya, memastikan wrapper bisa expand jika v-app butuh tinggi */
  min-height: 100vh;
  display: flex; /* Memastikan v-app bisa mengisi wrapper */
  flex-direction: column;
}

/* Pastikan v-app mengisi wrapper */
.layout-wrapper.layout-blank > .v-application.v-theme--light, /* Sesuaikan nama tema jika perlu */
.layout-wrapper.layout-blank > .v-application.v-theme--dark {
    min-height: 100%;
    display: flex;
    flex-direction: column;
    flex-grow: 1; /* Memastikan v-app mengambil ruang yang tersedia */
}

/* Biarkan v-main default, halaman di dalam slot yang akan mengatur isinya */
.layout-wrapper.layout-blank .v-main {
   /* Tidak perlu style flex khusus di sini untuk layout blank general */
   /* flex-grow: 1; */ /* Biasanya v-main sudah otomatis grow */
}
</style>
