<script lang="ts" setup>
import { useSnackbar } from '@/composables/useSnackbar'

// Ambil fungsi 'add' dari composable snackbar kita
const { add: addSnackbar } = useSnackbar()

const triggerSuccess = () => {
  addSnackbar({
    type: 'success',
    title: 'Berhasil',
    text: 'Ini adalah notifikasi sukses dari halaman tes.',
  })
}

const triggerError = () => {
  addSnackbar({
    type: 'error',
    title: 'Error Terjadi',
    text: 'Ini adalah notifikasi error dari halaman tes.',
  })
}

const triggerWarning = () => {
  addSnackbar({
    type: 'warning',
    title: 'Peringatan',
    text: 'Ini adalah notifikasi peringatan dari halaman tes.',
  })
}

const triggerInfo = () => {
  addSnackbar({
    type: 'info',
    title: 'Informasi',
    text: 'Ini adalah notifikasi informasi dari halaman tes.',
  })
}
</script>

<template>
  <VCard title="Alat Tes Snackbar">
    <VCardText>
      Gunakan tombol-tombol di bawah ini untuk memicu berbagai jenis notifikasi
      snackbar dan memeriksa apakah ikonnya muncul dengan benar.
    </VCardText>

    <VCardActions class="flex-wrap">
      <VBtn
        variant="tonal"
        color="success"
        @click="triggerSuccess"
      >
        <VIcon
          start
          icon="tabler:circle-check"
        />
        Tampilkan Sukses
      </VBtn>
      <VBtn
        variant="tonal"
        color="error"
        @click="triggerError"
      >
        <VIcon
          start
          icon="tabler:alert-circle"
        />
        Tampilkan Error
      </VBtn>
      <VBtn
        variant="tonal"
        color="warning"
        @click="triggerWarning"
      >
        <VIcon
          start
          icon="tabler:alert-triangle"
        />
        Tampilkan Peringatan
      </VBtn>
      <VBtn
        variant="tonal"
        color="info"
        @click="triggerInfo"
      >
        <VIcon
          start
          icon="tabler:info-circle"
        />
        Tampilkan Info
      </VBtn>
    </VCardActions>
  </VCard>
</template>