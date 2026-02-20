<script setup lang="ts">
import { computed } from 'vue'
import { useAuthStore } from '~/store/auth'
import { format_for_whatsapp_link, format_to_local_phone } from '~/utils/formatters'

definePageMeta({
  layout: 'blank',
  auth: false,
  public: true,
})

useHead({ title: 'Kuota FUP' })

const authStore = useAuthStore()
const user = computed(() => authStore.currentUser ?? authStore.lastKnownUser)
const isKomandan = computed(() => user.value?.role === 'KOMANDAN')
const { public: { adminWhatsapp, whatsappBaseUrl } } = useRuntimeConfig()
const adminContact = (adminWhatsapp as string) || ''
const whatsappBase = ((whatsappBaseUrl as string) || '').replace(/\/+$/, '')

const whatsappHref = computed(() => {
  const adminNumberForLink = format_for_whatsapp_link(adminContact)
  const name = user.value?.full_name || 'Pengguna'
  const phone = user.value?.phone_number ? format_to_local_phone(user.value.phone_number) : 'Tidak terdaftar'
  const text = `Halo Admin, kuota saya sudah masuk FUP.\n\nNama: ${name}\nNo. HP: ${phone}\n\nMohon bantuan untuk upgrade paket.`
  if (!whatsappBase || !adminNumberForLink)
    return ''
  return `${whatsappBase}/${adminNumberForLink}?text=${encodeURIComponent(text)}`
})

const primaryActionPath = computed(() => (isKomandan.value ? '/requests' : '/captive/beli'))
const primaryActionLabel = computed(() => (isKomandan.value ? 'Ajukan Permintaan' : 'Upgrade Paket'))

function goTo(url: string) {
  if (import.meta.client)
    window.location.href = url
}
</script>

<template>
  <div class="auth-wrapper d-flex align-center justify-center pa-4">
    <VCard class="auth-card" max-width="520">
      <VCardText class="text-center">
        <VIcon icon="tabler-gauge" size="48" class="mb-4" color="info" />
        <h4 class="text-h5 mb-2">
          Kuota FUP
        </h4>
        <p class="text-medium-emphasis mb-6">
          Kuota Anda sudah masuk batas FUP. Kecepatan dapat dibatasi sampai paket diperbarui.
        </p>
        <div class="d-flex flex-column gap-3">
          <VBtn color="primary" @click="goTo(primaryActionPath)">
            {{ primaryActionLabel }}
          </VBtn>
          <VBtn variant="tonal" color="success" @click="goTo(whatsappHref)">
            Hubungi Admin
          </VBtn>
          <VBtn variant="text" @click="goTo('/captive')">
            Kembali ke Login
          </VBtn>
        </div>
      </VCardText>
    </VCard>
  </div>
</template>
