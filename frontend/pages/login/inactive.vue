<script setup lang="ts">
import { computed } from 'vue'
import { useAuthStore } from '~/store/auth'
import { format_for_whatsapp_link, format_to_local_phone } from '~/utils/formatters'

definePageMeta({
  layout: 'blank',
  auth: false,
  public: true,
})

useHead({ title: 'Akun Belum Aktif' })

const authStore = useAuthStore()
const user = computed(() => authStore.currentUser ?? authStore.lastKnownUser)
const { public: { adminWhatsapp, whatsappBaseUrl } } = useRuntimeConfig()
const adminContact = (adminWhatsapp as string) || ''
const whatsappBase = ((whatsappBaseUrl as string) || '').replace(/\/+$/, '')

const whatsappHref = computed(() => {
  const adminNumberForLink = format_for_whatsapp_link(adminContact)
  const name = user.value?.full_name || 'Pengguna'
  const phone = user.value?.phone_number ? format_to_local_phone(user.value.phone_number) : 'Tidak terdaftar'
  const text = `Halo Admin, akun saya belum aktif atau belum disetujui.\n\nNama: ${name}\nNo. HP: ${phone}\n\nMohon bantuan aktivasi akun.`
  if (!whatsappBase || !adminNumberForLink)
    return ''
  return `${whatsappBase}/${adminNumberForLink}?text=${encodeURIComponent(text)}`
})

function goTo(url: string) {
  if (import.meta.client)
    window.location.href = url
}
</script>

<template>
  <div class="auth-wrapper d-flex align-center justify-center pa-4">
    <VCard class="auth-card" max-width="520">
      <VCardText class="text-center">
        <VIcon icon="tabler-user-off" size="48" class="mb-4" color="warning" />
        <h4 class="text-h5 mb-2">
          Akun Belum Aktif
        </h4>
        <p class="text-medium-emphasis mb-6">
          Akun Anda belum aktif atau belum disetujui. Silakan hubungi admin untuk proses aktivasi.
        </p>
        <div class="d-flex flex-column gap-3">
          <VBtn color="success" @click="goTo(whatsappHref)">
            Hubungi Admin
          </VBtn>
          <VBtn variant="text" @click="goTo('/login')">
            Kembali ke Login
          </VBtn>
        </div>
      </VCardText>
    </VCard>
  </div>
</template>
