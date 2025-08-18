<script setup lang="ts">
import { definePageMeta, useHead } from '#imports'
import { computed } from 'vue'
import { useDisplay } from 'vuetify'

import BlokirSkeleton from '~/components/akun/BlokirSkeleton.vue'
import { useAuthStore } from '~/store/auth'
import { useSettingsStore } from '~/store/settings'
import { format_for_whatsapp_link, format_to_local_phone } from '~/utils/formatters'

definePageMeta({
  layout: 'blank',
  // Middleware tidak diperlukan secara eksplisit di sini karena middleware global `01.auth.global.ts`
  // sudah menangani logika pengalihan ke halaman ini.
})

useHead({ title: 'Akun Diblokir' })

const authStore = useAuthStore()
const settingsStore = useSettingsStore()
const { smAndDown } = useDisplay()

// State untuk loading, aktif hingga pengecekan autentikasi awal selesai.
// Ini memastikan data pengguna (jika ada) sudah siap sebelum ditampilkan.
const isLoading = computed(() => !authStore.isAuthCheckDone)

// Mengambil data pengguna saat ini dari store.
const user = computed(() => authStore.currentUser)

// Memformat nomor telepon pengguna untuk tampilan.
const displayPhoneNumber = computed(() => {
  if (user.value?.phone_number) {
    return format_to_local_phone(user.value.phone_number) || 'Tidak terdaftar'
  }
  return 'Tidak terdaftar'
})

// Membuat link WhatsApp yang dinamis dengan pesan yang sudah diisi sebelumnya.
const whatsappHref = computed(() => {
  const adminNumberRaw = settingsStore.settings?.ADMIN_WHATSAPP_NUMBER || '62811580039'
  const adminNumberForLink = format_for_whatsapp_link(adminNumberRaw)

  let text = 'Halo Admin, akun saya telah diblokir. Mohon bantuannya untuk pengecekan lebih lanjut.'

  // Jika data pengguna tersedia, buat pesan yang lebih detail.
  if (user.value) {
    const nama = user.value.full_name || 'Tanpa Nama'
    const noHpPengguna = displayPhoneNumber.value
    const alamat = user.value.blok && user.value.kamar
      ? `Alamat: Blok ${user.value.blok}, Kamar ${user.value.kamar.replace('Kamar_', '')}`
      : 'Alamat: Tidak terdaftar'

    text = `Halo Admin, akun saya dengan detail berikut telah diblokir:\n\n*Nama:* ${nama}\n*No. Telepon:* ${noHpPengguna}\n*${alamat}*\n\nMohon bantuannya untuk pengecekan lebih lanjut.`
  }

  return `https://wa.me/${adminNumberForLink}?text=${encodeURIComponent(text)}`
})
</script>

<template>
  <VContainer
    class="pa-4"
    fluid
    fill-height
  >
    <VRow
      align="center"
      justify="center"
      class="fill-height"
    >
      <VCol
        cols="12"
        sm="10"
        md="8"
        lg="6"
        xl="4"
      >
        <BlokirSkeleton v-if="isLoading" />

        <VCard
          v-else
          class="text-center pa-6 pa-md-10"
          elevation="8"
          rounded="lg"
        >
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="80" height="80" class="mb-6" style="fill: rgb(var(--v-theme-error));">
            <title>account-lock-outline</title>
            <path d="M10 12C12.21 12 14 10.21 14 8S12.21 4 10 4 6 5.79 6 8 7.79 12 10 12M10 6C11.11 6 12 6.9 12 8S11.11 10 10 10 8 9.11 8 8 8.9 6 10 6M12 20H2V17C2 14.33 7.33 13 10 13C11 13 12.38 13.19 13.71 13.56C13.41 14.12 13.23 14.74 13.21 15.39C12.23 15.1 11.11 14.9 10 14.9C7.03 14.9 3.9 16.36 3.9 17V18.1H12C12 18.13 12 18.17 12 18.2V20M20.8 17V15.5C20.8 14.1 19.4 13 18 13C16.6 13 15.2 14.1 15.2 15.5V17C14.6 17 14 17.6 14 18.2V21.7C14 22.4 14.6 23 15.2 23H20.7C21.4 23 22 22.4 22 21.8V18.3C22 17.6 21.4 17 20.8 17M19.5 17H16.5V15.5C16.5 14.7 17.2 14.2 18 14.2C18.8 14.2 19.5 14.7 19.5 15.5V17Z" />
          </svg>

          <h1 class="text-h4 text-md-h3 font-weight-bold text-error mb-4">
            Akses Diblokir
          </h1>

          <p class="text-body-1 text-medium-emphasis mb-8">
            Mohon maaf, akses untuk akun yang terdaftar dengan nomor
            <strong v-if="user">{{ displayPhoneNumber }}</strong>
            <span v-else>Anda</span>
            saat ini dibatasi. Untuk memulihkan akses atau mendapatkan informasi lebih lanjut, silakan hubungi Administrator.
          </p>

          <VBtn
            :href="whatsappHref"
            color="primary"
            variant="flat"
            size="large"
            target="_blank"
            rel="noopener noreferrer"
            :block="smAndDown"
          >
            <template #prepend>
              <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24" style="fill: currentColor; margin-right: 8px;">
                <title>whatsapp</title>
                <path d="M12.04 2C6.58 2 2.13 6.45 2.13 11.91C2.13 13.66 2.59 15.36 3.45 16.86L2.05 22L7.3 20.62C8.75 21.41 10.38 21.83 12.04 21.83C17.5 21.83 21.95 17.38 21.95 11.92C21.95 9.27 20.92 6.78 19.05 4.91C17.18 3.03 14.69 2 12.04 2M12.05 3.67C14.25 3.67 16.31 4.53 17.87 6.09C19.42 7.65 20.28 9.72 20.28 11.92C20.28 16.46 16.58 20.15 12.04 20.15C10.56 20.15 9.11 19.76 7.85 19L7.55 18.83L4.43 19.65L5.26 16.61L5.06 16.29C4.24 15 3.8 13.47 3.8 11.91C3.81 7.37 7.5 3.67 12.05 3.67M8.53 7.33C8.37 7.33 8.1 7.39 7.87 7.64C7.65 7.89 7 8.5 7 9.71C7 10.93 7.89 12.1 8 12.27C8.14 12.44 9.76 14.94 12.25 16C12.84 16.27 13.3 16.42 13.66 16.53C14.25 16.72 14.79 16.69 15.22 16.63C15.7 16.56 16.68 16.03 16.89 15.45C17.1 14.87 17.1 14.38 17.04 14.27C16.97 14.17 16.81 14.11 16.56 14C16.31 13.86 15.09 13.26 14.87 13.18C14.64 13.1 14.5 13.06 14.31 13.3C14.15 13.55 13.67 14.11 13.53 14.27C13.38 14.44 13.24 14.46 13 14.34C12.74 14.21 11.94 13.95 11 13.11C10.26 12.45 9.77 11.64 9.62 11.39C9.5 11.15 9.61 11 9.73 10.89C9.84 10.78 10 10.6 10.1 10.45C10.23 10.31 10.27 10.2 10.35 10.04C10.43 9.87 10.39 9.73 10.33 9.61C10.27 9.5 9.77 8.26 9.56 7.77C9.36 7.29 9.16 7.35 9 7.34C8.86 7.34 8.7 7.33 8.53 7.33Z" />
              </svg>
            </template>
            Hubungi Admin
          </VBtn>
        </VCard>
      </VCol>
    </VRow>
  </VContainer>
</template>

<style scoped>
.fill-height {
  min-height: 100vh;
}
</style>
