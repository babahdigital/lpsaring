<script setup lang="ts">
import { definePageMeta, useHead } from '#imports'
import { computed } from 'vue'
import { useRoute } from 'vue-router'

import { useAuthStore } from '~/store/auth'
import { useSettingsStore } from '~/store/settings'
import { format_for_whatsapp_link, format_to_local_phone } from '~/utils/formatters'

// [PERUBAHAN KUNCI] Layout diatur secara statis dan permanen ke 'blank'.
// Semua logika dinamis untuk mengubah layout telah dihapus untuk simplisitas.
definePageMeta({
  layout: 'blank',
})

// Logika ini tetap diperlukan untuk membedakan tombol aksi.
const route = useRoute()
const isCaptiveFlow = computed(() => route.query.flow === 'captive')

useHead({ title: 'Kuota Habis' })

const authStore = useAuthStore()
const settingsStore = useSettingsStore()

const user = computed(() => authStore.currentUser)
const adminContact = computed(() => settingsStore.settings?.ADMIN_WHATSAPP_NUMBER || '+62811580039')

// Logika untuk link WhatsApp tetap sama dan relevan.
const whatsappHref = computed(() => {
  const adminNumberForLink = format_for_whatsapp_link(adminContact.value)
  let text = 'Halo Admin, kuota internet saya telah habis dan butuh bantuan untuk pembelian paket.'

  if (user.value) {
    const nama = user.value.full_name || 'Tanpa Nama'
    const noHpPengguna = format_to_local_phone(user.value.phone_number) || 'Tidak terdaftar'
    text = `Halo Admin, kuota internet saya dengan detail berikut telah habis:\n\n*Nama:* ${nama}\n*No. Telepon:* ${noHpPengguna}\n\nMohon bantuannya untuk proses pembelian paket baru.`
  }

  return `https://wa.me/${adminNumberForLink}?text=${encodeURIComponent(text)}`
})

// Fungsi untuk menutup jendela popup captive portal.
function closeWindow() {
  window.open('about:blank', '_self')?.close()
}
</script>

<template>
  <VContainer fluid class="pa-4 fill-height bg-grey-lighten-4">
    <VRow align="center" justify="center" class="fill-height text-center">
      <VCol cols="12" sm="10" md="8" lg="5" xl="4">
        <VCard class="pa-6 pa-md-10" elevation="8" rounded="lg">
          <div class="d-flex justify-center mb-6">
            <div class="bg-amber-lighten-4 pa-4 rounded-circle">
              <svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="#D97706" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon icon-tabler icons-tabler-outline icon-tabler-battery-off">
                <path stroke="none" d="M0 0h24v24H0z" fill="none" />
                <path d="M3 3l18 18" />
                <path d="M11 7h6a2 2 0 0 1 2 2v.5a.5 .5 0 0 0 .5 .5a.5 .5 0 0 1 .5 .5v3a.5 .5 0 0 1 -.5 .5a.5 .5 0 0 0 -.5 .5v.5m-2 2h-11a2 2 0 0 1 -2 -2v-6a2 2 0 0 1 2 -2h1" />
              </svg>
            </div>
          </div>

          <h1 class="text-h4 font-weight-bold text-grey-darken-3 mb-3">
            Kuota Internet Habis
          </h1>

          <p class="text-body-1 text-medium-emphasis mb-8">
            Masa aktif atau kuota data pada paket Anda telah berakhir. Silakan lakukan tindakan di bawah ini untuk dapat melanjutkan akses internet.
          </p>

          <VBtn
            v-if="!isCaptiveFlow"
            to="/beli"
            color="amber-darken-3"
            variant="flat"
            size="large"
            class="text-white mb-6"
            :block="true"
          >
            <template #prepend>
              <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24" style="fill: currentColor;">
                <title>package-variant-closed-plus</title>
                <path d="M13 19.3V12.6L19 9.2V13C19.7 13 20.4 13.1 21 13.4V7.5C21 7.1 20.8 6.8 20.5 6.6L12.6 2.2C12.4 2.1 12.2 2 12 2S11.6 2.1 11.4 2.2L3.5 6.6C3.2 6.8 3 7.1 3 7.5V16.5C3 16.9 3.2 17.2 3.5 17.4L11.4 21.8C11.6 21.9 11.8 22 12 22S12.4 21.9 12.6 21.8L13.5 21.3C13.2 20.7 13.1 20 13 19.3M12 4.2L18 7.5L16 8.6L10.1 5.2L12 4.2M11 19.3L5 15.9V9.2L11 12.6V19.3M12 10.8L6 7.5L8 6.3L14 9.8L12 10.8M20 15V18H23V20H20V23H18V20H15V18H18V15H20Z" />
              </svg>
            </template>
            Beli Paket Sekarang
          </VBtn>

          <VBtn
            v-else
            color="grey-darken-3"
            variant="flat"
            size="large"
            class="text-white mb-6"
            :block="true"
            @click="closeWindow"
          >
            <template #prepend>
              <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 6 6 18" /><path d="m6 6 12 12" /></svg>
            </template>
            Tutup Halaman Ini
          </VBtn>

          <VAlert density="compact" variant="tonal" color="grey-darken-1">
            <p class="text-caption">
              Butuh Bantuan? Hubungi Admin di
              <a :href="whatsappHref" class="font-weight-medium text-amber-darken-4" target="_blank" rel="noopener noreferrer">
                {{ adminContact }}
              </a>
            </p>
          </VAlert>
        </VCard>
      </VCol>
    </VRow>
  </VContainer>
</template>

<style scoped>
.fill-height {
  min-height: 100vh;
}
.v-btn {
  text-transform: none;
  font-weight: bold;
}
.v-alert a {
  text-decoration: none;
}
.v-alert a:hover {
  text-decoration: underline;
}
</style>
