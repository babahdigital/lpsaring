<script setup lang="ts">
import { computed } from 'vue'
import { useAuthStore } from '~/store/auth'
import { format_for_whatsapp_link, format_to_local_phone } from '~/utils/formatters'

type PolicyStatus = 'blocked' | 'inactive' | 'expired' | 'habis' | 'fup'

const props = defineProps<{
  status: PolicyStatus
}>()

const authStore = useAuthStore()
const user = computed(() => authStore.currentUser ?? authStore.lastKnownUser)
const isKomandan = computed(() => user.value?.role === 'KOMANDAN')

const {
  public: { adminWhatsapp, whatsappBaseUrl },
} = useRuntimeConfig()

const adminContact = (adminWhatsapp as string) || ''
const whatsappBase = ((whatsappBaseUrl as string) || '').replace(/\/+$/, '')

const viewModel = computed(() => {
  if (props.status === 'blocked') {
    return {
      icon: 'tabler-lock',
      iconColor: 'error',
      title: 'Akses Diblokir',
      description:
        'Akses internet Anda saat ini ditangguhkan karena kebijakan layanan atau masalah administratif pada akun Anda.',
      primaryLabel: 'Hubungi Admin',
      primaryPath: 'wa',
      secondaryLabel: 'Kembali ke Login',
      secondaryPath: '/login',
      waText: `Halo Admin, akun saya diblokir.\n\nNama: ${user.value?.full_name || 'Pengguna'}\nNo. HP: ${user.value?.phone_number ? format_to_local_phone(user.value.phone_number) : 'Tidak terdaftar'}\nAlasan: ${user.value?.blocked_reason || 'Tidak disebutkan'}\n\nMohon bantuan untuk mengaktifkan kembali.`,
    }
  }

  if (props.status === 'inactive') {
    return {
      icon: 'tabler-user-off',
      iconColor: 'warning',
      title: 'Akun Belum Aktif',
      description: 'Akun Anda belum aktif atau belum disetujui. Silakan hubungi admin untuk proses aktivasi.',
      primaryLabel: 'Hubungi Admin',
      primaryPath: 'wa',
      secondaryLabel: 'Kembali ke Login',
      secondaryPath: '/login',
      waText: `Halo Admin, akun saya belum aktif atau belum disetujui.\n\nNama: ${user.value?.full_name || 'Pengguna'}\nNo. HP: ${user.value?.phone_number ? format_to_local_phone(user.value.phone_number) : 'Tidak terdaftar'}\n\nMohon bantuan aktivasi akun.`,
    }
  }

  if (props.status === 'fup') {
    return {
      icon: 'tabler-gauge',
      iconColor: 'info',
      title: 'Kuota FUP',
      description: 'Kuota Anda masuk batas FUP. Kecepatan dapat dibatasi sampai paket diperbarui.',
      primaryLabel: isKomandan.value ? 'Ajukan Permintaan' : 'Upgrade Paket',
      primaryPath: isKomandan.value ? '/requests' : '/beli',
      secondaryLabel: 'Hubungi Admin',
      secondaryPath: 'wa',
      waText: `Halo Admin, kuota saya sudah masuk FUP.\n\nNama: ${user.value?.full_name || 'Pengguna'}\nNo. HP: ${user.value?.phone_number ? format_to_local_phone(user.value.phone_number) : 'Tidak terdaftar'}\n\nMohon bantuan untuk upgrade paket.`,
    }
  }

  if (props.status === 'expired') {
    return {
      icon: 'tabler-calendar-x',
      iconColor: 'error',
      title: 'Masa Aktif Berakhir',
      description: 'Masa aktif paket internet Anda telah berakhir. Silakan perpanjang paket atau hubungi admin.',
      primaryLabel: isKomandan.value ? 'Ajukan Permintaan' : 'Perpanjang Paket',
      primaryPath: isKomandan.value ? '/requests' : '/beli',
      secondaryLabel: 'Hubungi Admin',
      secondaryPath: 'wa',
      waText: `Halo Admin, masa aktif saya sudah berakhir.\n\nNama: ${user.value?.full_name || 'Pengguna'}\nNo. HP: ${user.value?.phone_number ? format_to_local_phone(user.value.phone_number) : 'Tidak terdaftar'}\n\nMohon bantu perpanjangan paket.`,
    }
  }

  return {
    icon: 'tabler-alert-triangle',
    iconColor: 'warning',
    title: 'Kuota Habis',
    description: 'Paket internet Anda habis. Silakan beli paket baru atau hubungi admin.',
    primaryLabel: isKomandan.value ? 'Ajukan Permintaan' : 'Beli Paket',
    primaryPath: isKomandan.value ? '/requests' : '/beli',
    secondaryLabel: 'Hubungi Admin',
    secondaryPath: 'wa',
    waText: `Halo Admin, kuota saya habis.\n\nNama: ${user.value?.full_name || 'Pengguna'}\nNo. HP: ${user.value?.phone_number ? format_to_local_phone(user.value.phone_number) : 'Tidak terdaftar'}\n\nMohon bantu proses pembelian paket.`,
  }
})

const whatsappHref = computed(() => {
  const adminNumberForLink = format_for_whatsapp_link(adminContact)
  if (!whatsappBase || !adminNumberForLink)
    return ''
  return `${whatsappBase}/${adminNumberForLink}?text=${encodeURIComponent(viewModel.value.waText)}`
})

function goTo(path: string) {
  if (!import.meta.client)
    return

  if (path === 'wa') {
    if (whatsappHref.value)
      window.location.href = whatsappHref.value
    return
  }

  window.location.href = path
}
</script>

<template>
  <div class="auth-wrapper d-flex align-center justify-center pa-4 pa-sm-6">
    <VCard class="auth-card policy-card" max-width="560" width="100%">
      <VCardText class="text-center pa-6 pa-sm-8">
        <VIcon :icon="viewModel.icon" :color="viewModel.iconColor" size="56" class="mb-4" />

        <h4 class="text-h5 text-sm-h4 mb-2">
          {{ viewModel.title }}
        </h4>

        <p class="text-medium-emphasis mb-6 mb-sm-8 text-body-2 text-sm-body-1">
          {{ viewModel.description }}
        </p>

        <div class="d-flex flex-column ga-3">
          <VBtn color="primary" size="large" block @click="goTo(viewModel.primaryPath)">
            {{ viewModel.primaryLabel }}
          </VBtn>

          <VBtn variant="tonal" color="success" size="large" block @click="goTo(viewModel.secondaryPath)">
            {{ viewModel.secondaryLabel }}
          </VBtn>

          <VBtn variant="text" block @click="goTo('/login')">
            Kembali ke Login
          </VBtn>
        </div>
      </VCardText>
    </VCard>
  </div>
</template>

<style scoped>
.policy-card {
  border-radius: 16px;
}
</style>