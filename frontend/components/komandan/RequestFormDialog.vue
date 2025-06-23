<script lang="ts" setup>
import type { VForm } from 'vuetify/components'
import { ref, watch } from 'vue'
import { useSnackbar } from '@/composables/useSnackbar'

// --- Props & Emits ---
const props = defineProps<{
  modelValue: boolean
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void
  (e: 'submitted'): void
}>()

// --- Inisialisasi & State ---
const { $api } = useNuxtApp()
const { add: showSnackbar } = useSnackbar()

// [PENYEMPURNAAN] Pilihan preset untuk kuota dan durasi tetap sama,
// karena sudah menggunakan praktik yang baik (menampilkan GB, mengirim MB).
const quotaOptions = [
  { title: '10 GB', value: 10 * 1024 },
  { title: '30 GB', value: 30 * 1024 },
  { title: '50 GB', value: 50 * 1024 },
]

const durationOptions = [
  { title: '30 Hari', value: 30 },
  { title: '60 Hari', value: 60 },
  { title: '90 Hari', value: 90 },
]

// State Form
const formRef = ref<VForm>()
const loading = ref(false)
const requestType = ref<'QUOTA' | 'UNLIMITED'>('QUOTA')
const requestedMb = ref<number | null>(null)
const requestedDurationDays = ref<number | null>(null)
const errorMessage = ref<string | null>(null)

// Aturan Validasi
const requiredRule = (v: any) => !!v || 'Wajib dipilih.'

// Watcher untuk mereset form saat dialog ditutup
watch(() => props.modelValue, (isVisible) => {
  if (!isVisible) {
    formRef.value?.reset()
    formRef.value?.resetValidation()
    requestType.value = 'QUOTA'
    requestedMb.value = null
    requestedDurationDays.value = null
    errorMessage.value = null
  }
})

// Handler Submit (Logika tidak berubah)
async function handleSubmit() {
  errorMessage.value = null
  const { valid } = await formRef.value!.validate()
  if (!valid)
    return

  loading.value = true
  try {
    const payload = {
      request_type: requestType.value,
      // Kirim undefined jika tidak relevan, backend akan mengabaikannya
      requested_mb: requestType.value === 'QUOTA' ? requestedMb.value : undefined,
      requested_duration_days: requestType.value === 'QUOTA' ? requestedDurationDays.value : undefined,
    }

    await $api('/komandan/requests', {
      method: 'POST',
      body: payload,
    })

    showSnackbar({ type: 'success', title: 'Berhasil', text: 'Permintaan Anda telah terkirim dan sedang menunggu persetujuan.' })
    emit('submitted') // Kirim event ke parent
    closeDialog()
  }
  catch (error: any) {
    errorMessage.value = error.data?.message || 'Terjadi kesalahan pada server.'
    showSnackbar({ type: 'error', title: 'Gagal Mengirim', text: errorMessage.value })
  }
  finally {
    loading.value = false
  }
}

function closeDialog() {
  emit('update:modelValue', false)
}
</script>

<template>
  <VDialog
    :model-value="modelValue"
    max-width="600"
    persistent
    @update:model-value="closeDialog"
  >
    <VCard class="rounded-lg">
      <VForm
        ref="formRef"
        @submit.prevent="handleSubmit"
      >
        <VCardItem class="pa-4 bg-primary">
          <template #prepend>
            <VIcon
              icon="tabler-mail-plus"
              color="white"
              size="28"
            />
          </template>
          <VCardTitle class="text-h5 text-white">
            Formulir Pengajuan
          </VCardTitle>
          <VCardSubtitle class="text-white">
            Ajukan permintaan kuota atau akses unlimited
          </VCardSubtitle>
          <template #append>
            <VBtn
              icon="tabler-x"
              variant="text"
              size="small"
              class="text-white"
              @click="closeDialog"
            />
          </template>
        </VCardItem>

        <VCardText class="pa-5">
          <p class="text-subtitle-1 font-weight-medium mb-3">
            Pilih Tipe Permintaan
          </p>
          <VRadioGroup
            v-model="requestType"
            inline
            class="mb-4"
          >
            <VRadio
              label="Kuota Reguler"
              value="QUOTA"
            />
            <VRadio
              label="Akses Unlimited"
              value="UNLIMITED"
            />
          </VRadioGroup>

          <VDivider class="my-4" />

          <VExpandTransition>
            <div v-if="requestType === 'QUOTA'">
              <p class="text-subtitle-1 font-weight-medium mb-3">
                Isi Detail Kuota
              </p>
              <VRow>
                <VCol
                  cols="12"
                  sm="6"
                >
                  <AppSelect
                    v-model="requestedMb"
                    label="Jumlah Kuota"
                    :items="quotaOptions"
                    placeholder="Pilih jumlah GB"
                    :rules="[requiredRule]"
                    prepend-inner-icon="tabler-database"
                  />
                </VCol>
                <VCol
                  cols="12"
                  sm="6"
                >
                  <AppSelect
                    v-model="requestedDurationDays"
                    label="Masa Aktif"
                    :items="durationOptions"
                    placeholder="Pilih lama hari"
                    :rules="[requiredRule]"
                    prepend-inner-icon="tabler-calendar-plus"
                  />
                </VCol>
              </VRow>
            </div>
          </VExpandTransition>

          <VExpandTransition>
            <VAlert
              v-if="requestType === 'UNLIMITED'"
              type="info"
              variant="tonal"
              class="mt-2"
              icon="tabler-shield-check"
              density="compact"
            >
              Permintaan akses unlimited akan ditinjau dan disetujui secara manual oleh Admin, termasuk penentuan masa aktifnya.
            </VAlert>
          </VExpandTransition>

          <VAlert
            v-if="errorMessage"
            type="error"
            variant="tonal"
            class="mt-4"
          >
            {{ errorMessage }}
          </VAlert>
        </VCardText>

        <VDivider />
        <VCardActions class="pa-4">
          <VSpacer />
          <VBtn
            variant="tonal"
            color="secondary"
            @click="closeDialog"
          >
            Batal
          </VBtn>
          <VBtn
            type="submit"
            color="primary"
            :loading="loading"
            prepend-icon="tabler-send"
          >
            Kirim Permintaan
          </VBtn>
        </VCardActions>
      </VForm>
    </VCard>
  </VDialog>
</template>
