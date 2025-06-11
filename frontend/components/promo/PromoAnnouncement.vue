<template>
  <!--
    Komponen ini akan menampilkan VAlert jika ada promo yang aktif.
    - Menggunakan v-if untuk memastikan alert hanya dirender jika ada data dan belum ditutup.
    - 'd-print-none' memastikan alert ini tidak ikut tercetak.
  -->
  <div v-if="isAlertVisible && data && data.id" class="d-print-none mb-6">
    <!--
      VAlert digunakan untuk menampilkan pesan pengumuman.
      - 'border="start"': Menampilkan garis batas di sisi kiri.
      - 'border-color': Mengatur warna garis batas. 'primary' digunakan agar konsisten dengan tema.
      - 'closable': Menampilkan tombol close (x).
      - '@update:modelValue': Event ini terpanggil saat tombol close diklik untuk menyembunyikan alert.
    -->
    <VAlert
      v-model="isAlertVisible"
      border="start"
      border-color="primary"
      closable
      class="promo-alert"
    >
      <div class="d-flex align-center">
        <!-- Ikon untuk menarik perhatian, ditempatkan di dalam konten -->
        <VIcon
          icon="tabler-discount-2"
          color="primary"
          class="me-3"
        />
        <div>
          <VAlertTitle class="mb-1 text-high-emphasis">
            <!-- Menampilkan nama promo sebagai judul -->
            {{ data.name }}
          </VAlertTitle>

          <!-- Menampilkan deskripsi promo -->
          <p class="mb-0">
            {{ data.description }}
          </p>
        </div>
      </div>
    </VAlert>
  </div>
</template>

<script setup lang="ts">
// === Imports ===
import { ref } from 'vue'

// === Composables ===
// Menggunakan useApiFetch untuk mengambil data promo aktif secara reaktif.
// Sesuai dengan standar di dokumentasi, ini cara yang tepat untuk GET data di komponen.
const { data, pending, error } = await useApiFetch('/public/promos/active', {
  // 'key' memastikan hasil fetch di-cache dan digunakan kembali jika komponen dipanggil di tempat lain.
  key: 'active-promo-announcement',

  // 'lazy: true' membuat navigasi tidak terblokir sambil menunggu data.
  lazy: true,

  // 'server: false' bisa ditambahkan jika Anda ingin data ini hanya diambil di sisi client
  // untuk mengurangi beban SSR. Untuk pengumuman, ini adalah opsi yang bagus.
  server: false,
});

// === State ===
// State lokal untuk mengontrol visibilitas alert.
// Defaultnya true, akan menjadi false jika pengguna menutupnya.
const isAlertVisible = ref(true)

</script>

<style lang="scss">
// Tidak ada style tambahan yang diperlukan untuk layout ini,
// karena VAlert dengan border sudah memiliki tampilan yang bersih.
</style>