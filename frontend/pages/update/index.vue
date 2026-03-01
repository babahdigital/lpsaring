<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute } from 'vue-router'
import { useAuthStore } from '~/store/auth'

definePageMeta({
  layout: 'blank',
})

useHead({ title: 'Pemutakhiran Database Pengguna' })

const runtimeConfig = useRuntimeConfig()
const route = useRoute()
const authStore = useAuthStore()
const isFeatureEnabled = computed(() => String(runtimeConfig.public.publicDbUpdateFormEnabled ?? 'false').toLowerCase() === 'true')

const fullName = ref('')
const role = ref<'KOMANDAN' | 'TAMPING' | ''>('')
const blok = ref<string | null>(null)
const kamar = ref<string | null>(null)
const isSubmitting = ref(false)
const errorMessage = ref('')
const successMessage = ref('')
const linkedPhoneNumber = computed(() => {
  const queryPhone = typeof route.query.phone === 'string' ? route.query.phone : ''
  const authPhone = String((authStore.currentUser as any)?.phone_number ?? '').trim()
  return (authPhone || queryPhone).trim()
})

const roleOptions = [
  { title: 'Komandan', value: 'KOMANDAN' },
  { title: 'Tamping', value: 'TAMPING' },
] as const

const blockOptions = Array.from({ length: 6 }, (_, index) => {
  const value = String.fromCharCode(65 + index)

  return {
    title: `Blok ${value}`,
    value,
  }
})

const kamarOptions = Array.from({ length: 6 }, (_, index) => {
  const value = String(index + 1)

  return {
    title: `Kamar ${value}`,
    value,
  }
})

const requiredRule = (value: unknown) => {
  if (value == null)
    return 'Wajib diisi.'
  if (typeof value === 'string' && value.trim() === '')
    return 'Wajib diisi.'

  return true
}

async function submitForm() {
  if (!isFeatureEnabled.value)
    return

  errorMessage.value = ''
  successMessage.value = ''

  const payload = {
    full_name: fullName.value,
    role: role.value,
    blok: blok.value,
    kamar: kamar.value,
    phone_number: linkedPhoneNumber.value,
  }

  isSubmitting.value = true
  try {
    const response = await $fetch<{ success: boolean, message?: string }>('/api/users/database-update-submissions', {
      method: 'POST',
      body: payload,
    })

    if (response.success !== true)
      throw new Error(response.message ?? 'Gagal mengirim data.')

    successMessage.value = response.message ?? 'Data berhasil dikirim.'
    fullName.value = ''
    role.value = ''
    blok.value = null
    kamar.value = null
  }
  catch (error: any) {
    const fallback = 'Gagal mengirim data pemutakhiran.'
    const messageFromBody = error?.data?.message
    const messageFromError = error instanceof Error ? error.message : ''

    errorMessage.value = String(messageFromBody || messageFromError || fallback)
  }
  finally {
    isSubmitting.value = false
  }
}
</script>

<template>
  <VContainer class="d-flex align-center justify-center py-10" style="min-height: 100vh;">
    <VCard max-width="640" width="100%">
      <VCardTitle class="text-wrap py-5 px-6">
        Pemutakhiran Database Pengguna (Sementara)
      </VCardTitle>

      <VCardText class="px-6 pb-6">
        <VAlert
          v-if="!isFeatureEnabled"
          type="warning"
          variant="tonal"
          class="mb-4"
        >
          Form pemutakhiran database sedang dinonaktifkan.
        </VAlert>

        <template v-else>
          <p class="text-body-2 mb-4">
            Silakan isi data Anda untuk pemutakhiran database. Nomor telepon mengikuti akun login Anda.
          </p>

          <VForm @submit.prevent="submitForm">
            <VTextField
              v-model="fullName"
              label="Nama Lengkap"
              variant="outlined"
              :rules="[requiredRule]"
              class="mb-3"
            />

            <VSelect
              v-model="role"
              label="Role"
              variant="outlined"
              :items="roleOptions"
              item-title="title"
              item-value="value"
              :rules="[requiredRule]"
              class="mb-3"
            />

            <VSelect
              v-model="blok"
              label="Blok"
              variant="outlined"
              :items="blockOptions"
              item-title="title"
              item-value="value"
              :rules="[requiredRule]"
              class="mb-3"
            />

            <VSelect
              v-model="kamar"
              label="Kamar"
              variant="outlined"
              :items="kamarOptions"
              item-title="title"
              item-value="value"
              :rules="[requiredRule]"
              class="mb-3"
            />

            <VTextField
                :model-value="linkedPhoneNumber"
                label="Nomor Telepon WhatsApp"
              variant="outlined"
                hint="Mengikuti nomor akun yang sedang login"
              persistent-hint
                readonly
              class="mb-4"
            />

            <VAlert
              v-if="errorMessage"
              type="error"
              variant="tonal"
              class="mb-3"
            >
              {{ errorMessage }}
            </VAlert>

            <VAlert
              v-if="successMessage"
              type="success"
              variant="tonal"
              class="mb-3"
            >
              {{ successMessage }}
            </VAlert>

            <VBtn
              type="submit"
              color="primary"
              :loading="isSubmitting"
              :disabled="isSubmitting"
              block
            >
              Kirim Data Pemutakhiran
            </VBtn>
          </VForm>
        </template>
      </VCardText>
    </VCard>
  </VContainer>
</template>
