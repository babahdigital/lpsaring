<script lang="ts" setup>
import AppTextarea from '@core/components/app-form-elements/AppTextarea.vue'
import AppTextField from '@core/components/app-form-elements/AppTextField.vue'
import { computed, ref, watch } from 'vue'
import { VForm } from 'vuetify/components'

// --- Interface & Props ---
interface Requester {
  id: string
  full_name: string
}

interface QuotaRequest {
  id: string
  requester: Requester
  status: string
  request_type: 'QUOTA' | 'UNLIMITED'
  request_details: {
    requested_mb?: number
    requested_duration_days?: number
  } | null
}

const props = defineProps<{
  isDialogVisible: boolean
  requestData: QuotaRequest
}>()

const emit = defineEmits<{
  (e: 'update:isDialogVisible', value: boolean): void
  (e: 'processed'): void
}>()

// --- Inisialisasi & State ---
const { $api } = useNuxtApp()
const formRef = ref<InstanceType<typeof VForm> | null>(null)
const loading = ref(false)
const errorMessage = ref<string | null>(null)

const action = ref<'APPROVE' | 'REJECT' | 'REJECT_AND_GRANT_QUOTA'>('APPROVE')
const rejection_reason = ref<string | null>(null)

// v-model akan terikat ke string untuk kontrol validasi yang lebih baik
const granted_quota_gb = ref<string | null>(null)
const granted_duration_days = ref<string | null>(null)
// [PERBAIKAN] State baru untuk durasi unlimited
const unlimited_duration_days = ref<string>('30') // Default 30 hari

// [PENYEMPURNAAN] Computed property untuk mengecek tipe request
const isUnlimitedRequest = computed(() => props.requestData.request_type === 'UNLIMITED')

function dialogModelValueUpdate(val: boolean) {
  emit('update:isDialogVisible', val)
}

// --- Watcher ---
watch(() => props.isDialogVisible, (isVisible) => {
  if (isVisible) {
    // Reset state saat dialog muncul
    action.value = 'APPROVE'
    rejection_reason.value = null
    granted_quota_gb.value = null
    granted_duration_days.value = null
    errorMessage.value = null
    unlimited_duration_days.value = '30' // Reset ke default
  }
})

watch(action, (newAction) => {
  if (newAction === 'REJECT_AND_GRANT_QUOTA') {
    if (props.requestData.request_type === 'QUOTA' && props.requestData.request_details) {
      const requested_mb = props.requestData.request_details.requested_mb
      if (typeof requested_mb === 'number') {
        granted_quota_gb.value = Number.parseFloat((requested_mb / 1024).toFixed(2)).toString()
      }
      granted_duration_days.value = props.requestData.request_details.requested_duration_days?.toString() ?? null
    }
    else {
      granted_quota_gb.value = null
      granted_duration_days.value = null
    }
  }
  else {
    granted_quota_gb.value = null
    granted_duration_days.value = null
  }
})

// --- Logika Inti ---
async function processRequest() {
  errorMessage.value = null
  const { valid } = await formRef.value!.validate()
  if (!valid)
    return

  loading.value = true

  // Validasi tambahan di frontend
  if (action.value === 'REJECT_AND_GRANT_QUOTA') {
    const quotaGbValue = granted_quota_gb.value ? Number.parseFloat(granted_quota_gb.value) : 0
    const durationDaysValue = granted_duration_days.value ? Number.parseInt(granted_duration_days.value, 10) : 0
    if (quotaGbValue <= 0 && durationDaysValue <= 0) {
      errorMessage.value = 'Untuk proses sebagian, harap isi minimal salah satu: Kuota (GB) atau Durasi (Hari) dengan nilai positif.'
      loading.value = false
      return
    }
  }

  // [PERBAIKAN] Validasi untuk durasi unlimited
  if (action.value === 'APPROVE' && isUnlimitedRequest.value) {
    const unlimitedDays = unlimited_duration_days.value ? Number.parseInt(unlimited_duration_days.value, 10) : 0
    if (unlimitedDays <= 0) {
      errorMessage.value = 'Durasi untuk akses unlimited harus lebih dari 0 hari.'
      loading.value = false
      return
    }
  }

  // [PERBAIKAN] Payload disesuaikan untuk mengirim data baru
  const payload: {
    action: string
    rejection_reason?: string | null
    granted_quota_mb?: number
    granted_duration_days?: number
    unlimited_duration_days?: number
  } = {
    action: action.value,
  }

  if (action.value === 'REJECT' || action.value === 'REJECT_AND_GRANT_QUOTA') {
    payload.rejection_reason = rejection_reason.value
  }

  if (action.value === 'REJECT_AND_GRANT_QUOTA') {
    const quotaGb = granted_quota_gb.value ? Number.parseFloat(granted_quota_gb.value) : 0
    payload.granted_quota_mb = Math.round(quotaGb * 1024)
    payload.granted_duration_days = granted_duration_days.value ? Number.parseInt(granted_duration_days.value, 10) : 0
  }

  // [PERBAIKAN] Tambahkan durasi unlimited ke payload jika relevan
  if (action.value === 'APPROVE' && isUnlimitedRequest.value) {
    payload.unlimited_duration_days = Number.parseInt(unlimited_duration_days.value, 10)
  }

  try {
    await $api(`/admin/quota-requests/${props.requestData.id}/process`, {
      method: 'POST',
      body: payload,
    })
    emit('processed')
    emit('update:isDialogVisible', false)
  }
  catch (error: any) {
    if (error.data?.errors) {
      const errorMessages = error.data.errors.map((e: any) => e.msg).join('; ')
      errorMessage.value = `Gagal Validasi: ${errorMessages}`
    }
    else {
      errorMessage.value = error.data?.message || 'Terjadi kesalahan tidak dikenal saat memproses permintaan.'
    }
  }
  finally {
    loading.value = false
  }
}

function closeDialog() {
  emit('update:isDialogVisible', false)
}

// --- Aturan Validasi ---
const reasonRule = (v: any) => (v && v.trim().length >= 5) || 'Alasan wajib diisi (minimal 5 karakter).'
const numberRule = (v: any) => (v === null || String(v).trim() === '') || (!Number.isNaN(Number(v)) && Number.isFinite(Number(v)) && Number(v) >= 0) || 'Harus berupa angka positif atau 0.'
const integerRule = (v: any) => (v === null || String(v).trim() === '') || /^\d+$/.test(String(v)) || 'Harus berupa bilangan bulat.'
const requiredIntegerRule = (v: any) => (v && /^\d+$/.test(String(v)) && Number.parseInt(v, 10) > 0) || 'Wajib diisi dengan angka bulat positif.'

function formatRequestDetails(details: Record<string, any> | null): string {
  if (!details || typeof details.requested_mb !== 'number' || typeof details.requested_duration_days !== 'number') {
    return 'Akses Penuh (Unlimited)'
  }
  const gb = (details.requested_mb / 1024).toFixed(2)
  return `Kuota: ${gb} GB, Durasi: ${details.requested_duration_days} hari`
}
</script>

<template>
  <VDialog :model-value="isDialogVisible" max-width="600" persistent @update:model-value="dialogModelValueUpdate">
    <VCard class="rounded-lg">
      <VForm ref="formRef" @submit.prevent="processRequest">
        <VCardItem class="pa-4 bg-primary">
          <template #prepend>
            <VIcon icon="tabler-mail-forward" color="white" size="28" />
          </template>
          <VCardTitle class="text-h5 text-white">
            Proses Permintaan
          </VCardTitle>
          <template #append>
            <VBtn icon="tabler-x" variant="text" size="small" class="text-white" @click="closeDialog" />
          </template>
        </VCardItem>
        <VDivider />

        <VCardText class="pt-4">
          <VList class="card-list mb-4" density="compact">
            <VListItem>
              <template #prepend>
                <VIcon icon="tabler-user" size="20" class="me-3" />
              </template>
              <VListItemTitle class="font-weight-semibold">
                Pemohon
              </VListItemTitle>
              <template #append>
                <span class="text-body-1">{{ requestData.requester.full_name }}</span>
              </template>
            </VListItem>
            <VListItem>
              <template #prepend>
                <VIcon icon="tabler-mail-check" size="20" class="me-3" />
              </template>
              <VListItemTitle class="font-weight-semibold">
                Tipe & Detail
              </VListItemTitle>
              <template #append>
                <div class="d-flex flex-column align-end">
                  <VChip size="small" :color="isUnlimitedRequest ? 'success' : 'primary'">
                    {{ requestData.request_type }}
                  </VChip>
                  <small v-if="!isUnlimitedRequest">{{ formatRequestDetails(requestData.request_details) }}</small>
                </div>
              </template>
            </VListItem>
          </VList>

          <VDivider class="my-4" />

          <VRadioGroup v-model="action" inline label="Pilih Aksi" class="mb-3">
            <VRadio label="Setujui Penuh" value="APPROVE" />
            <VRadio label="Proses Sebagian" value="REJECT_AND_GRANT_QUOTA" :disabled="isUnlimitedRequest" />
            <VRadio label="Tolak" value="REJECT" />
          </VRadioGroup>

          <VExpandTransition>
            <div v-if="action === 'APPROVE' && isUnlimitedRequest">
              <AppTextField
                v-model="unlimited_duration_days"
                label="Durasi Unlimited (Hari)"
                type="number"
                :rules="[requiredIntegerRule]"
                prepend-inner-icon="tabler-calendar-time"
              />
            </div>
          </VExpandTransition>

          <VExpandTransition>
            <div v-if="action === 'REJECT' || action === 'REJECT_AND_GRANT_QUOTA'">
              <AppTextarea v-model="rejection_reason" label="Alasan (Wajib, min 5 karakter)" :rules="[reasonRule]" rows="2" auto-grow class="mb-4" />
            </div>
          </VExpandTransition>

          <VExpandTransition>
            <div v-if="action === 'REJECT_AND_GRANT_QUOTA'">
              <p class="text-caption mb-2">
                Isi kuota dan/atau durasi yang disetujui. Otomatis terisi sesuai permintaan awal (jika ada).
              </p>
              <VRow>
                <VCol cols="12" sm="6">
                  <AppTextField v-model="granted_quota_gb" label="Beri Kuota (GB)" type="number" step="0.1" :rules="[numberRule]" prepend-inner-icon="tabler-database" />
                </VCol>
                <VCol cols="12" sm="6">
                  <AppTextField v-model="granted_duration_days" label="Beri Durasi (Hari)" type="number" :rules="[numberRule, integerRule]" prepend-inner-icon="tabler-calendar-plus" />
                </VCol>
              </VRow>
            </div>
          </VExpandTransition>

          <VAlert v-if="errorMessage" type="error" variant="tonal" class="mt-4 text-body-2">
            {{ errorMessage }}
          </VAlert>
        </VCardText>

        <VDivider />
        <VCardActions class="pa-4">
          <VSpacer />
          <VBtn variant="tonal" color="secondary" @click="closeDialog">
            Batal
          </VBtn>
          <VBtn type="submit" :loading="loading" color="primary" prepend-icon="tabler-send">
            Kirim Proses
          </VBtn>
        </VCardActions>
      </VForm>
    </VCard>
  </VDialog>
</template>

<style scoped>
.card-list {
  --v-card-list-padding: 0;
  background: transparent;
}
</style>
