<script setup lang="ts">
import { computed, ref } from 'vue'
import { TAMPING_OPTION_ITEMS } from '~/utils/constants'

definePageMeta({
  layout: 'blank',
  auth: false,
  public: true,
})

useHead({ title: 'Pemutakhiran Database Pengguna' })

const runtimeConfig = useRuntimeConfig()
const route = useRoute()
const isFeatureEnabled = computed(() => String(runtimeConfig.public.publicDbUpdateFormEnabled ?? 'false').toLowerCase() === 'true')

const fullName = ref('')
const role = ref<'USER' | 'KOMANDAN' | 'TAMPING' | ''>('')
const blok = ref<string | null>(null)
const kamar = ref<string | null>(null)
const tampingType = ref<string | null>(null)
const phoneNumber = ref('')
const isSubmitting = ref(false)
const errorMessage = ref('')
const successMessage = ref('')

const roleOptions = [
  { title: 'User', value: 'USER' },
  { title: 'Komandan', value: 'KOMANDAN' },
  { title: 'Tamping', value: 'TAMPING' },
] as const

const showAddressFields = computed(() => role.value === 'USER')
const showTampingFields = computed(() => role.value === 'TAMPING')

const tampingOptions = TAMPING_OPTION_ITEMS

const hasPhoneFromLink = computed(() => {
  const normalized = String(phoneNumber.value || '').trim()
  return normalized !== ''
})

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

function normalizePhoneInput(raw: string): string {
  const digits = raw.replace(/[^\d]/g, '')
  if (digits.startsWith('62'))
    return `+${digits}`
  if (digits.startsWith('0'))
    return `+62${digits.slice(1)}`
  if (digits.startsWith('8'))
    return `+62${digits}`
  return raw.trim()
}

const phoneFromQuery = String(route.query.phone ?? route.query.msisdn ?? '').trim()
if (phoneFromQuery !== '')
  phoneNumber.value = normalizePhoneInput(phoneFromQuery)

const nameFromQuery = String(route.query.name ?? '').trim()
if (nameFromQuery !== '' && fullName.value.trim() === '')
  fullName.value = nameFromQuery

async function submitForm() {
  if (!isFeatureEnabled.value)
    return

  if (!hasPhoneFromLink.value) {
    errorMessage.value = 'Nomor WhatsApp tidak ditemukan dari link. Silakan buka kembali link resmi dari WhatsApp.'
    return
  }

  errorMessage.value = ''
  successMessage.value = ''

  const payload = {
    full_name: fullName.value,
    role: role.value,
    blok: showAddressFields.value ? blok.value : null,
    kamar: showAddressFields.value ? kamar.value : null,
    tamping_type: showTampingFields.value ? tampingType.value : null,
    phone_number: phoneNumber.value,
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
    tampingType.value = null
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
            Silakan isi data pemutakhiran. Nomor WhatsApp diisi otomatis dari link resmi dan tidak bisa diubah.
          </p>

          <VAlert
            v-if="!hasPhoneFromLink"
            type="error"
            variant="tonal"
            class="mb-4"
          >
            Nomor WhatsApp tidak ditemukan pada link. Buka link dari pesan WhatsApp yang Anda terima.
          </VAlert>

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

            <template v-if="showAddressFields">
              <VSelect
                v-model="blok"
                label="Blok Tempat Tinggal"
                variant="outlined"
                :items="blockOptions"
                item-title="title"
                item-value="value"
                :rules="[requiredRule]"
                class="mb-3"
              />

              <VSelect
                v-model="kamar"
                label="Nomor Kamar"
                variant="outlined"
                :items="kamarOptions"
                item-title="title"
                item-value="value"
                :rules="[requiredRule]"
                class="mb-3"
              />
            </template>

            <template v-if="showTampingFields">
              <VSelect
                v-model="tampingType"
                label="Jenis Tamping"
                variant="outlined"
                :items="tampingOptions"
                item-title="title"
                item-value="value"
                :rules="[requiredRule]"
                class="mb-3"
              />
            </template>

            <VTextField
              v-model="phoneNumber"
              label="Nomor Telepon WhatsApp"
              variant="outlined"
              hint="Diisi otomatis dari link WhatsApp"
              persistent-hint
              disabled
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
              :disabled="isSubmitting || !hasPhoneFromLink"
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
