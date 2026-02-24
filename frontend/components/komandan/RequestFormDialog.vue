<script lang="ts" setup>
import { computed, onUnmounted, ref, watch } from 'vue'
import { VForm } from 'vuetify/components'
import { useDisplay } from 'vuetify'
import { useSnackbar } from '@/composables/useSnackbar'
import { useSettingsStore } from '@/store/settings'

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
const settingsStore = useSettingsStore()
const { add: showSnackbar } = useSnackbar()
const display = useDisplay()
const isMobile = computed(() => display.smAndDown.value)

// [PENYEMPURNAAN] Pilihan preset untuk kuota dan durasi tetap sama,
// karena sudah menggunakan praktik yang baik (menampilkan GB, mengirim MB).
const baseQuotaOptions = [
  { title: '10 GB', value: 10 * 1024 },
  { title: '30 GB', value: 30 * 1024 },
  { title: '50 GB', value: 50 * 1024 },
]

const baseDurationOptions = [
  { title: '30 Hari', value: 30 },
  { title: '60 Hari', value: 60 },
  { title: '90 Hari', value: 90 },
]

// State Form
const formRef = ref<InstanceType<typeof VForm> | null>(null)
const loading = ref(false)
const requestType = ref<'QUOTA' | 'UNLIMITED'>('QUOTA')
const requestedMb = ref<number | null>(null)
const requestedDurationDays = ref<number | null>(null)
const errorMessage = ref<string | null>(null)
const retryAfterSeconds = ref<number | null>(null)
const retryAtIso = ref<string | null>(null)
const countdownSeconds = ref<number | null>(null)
let countdownTimer: ReturnType<typeof setInterval> | null = null

const allowUnlimited = computed(() => settingsStore.getSettingAsBool('KOMANDAN_ALLOW_UNLIMITED_REQUEST', true))
const maxQuotaMb = computed(() => settingsStore.getSettingAsInt('KOMANDAN_MAX_QUOTA_MB', 51200))
const maxQuotaDays = computed(() => settingsStore.getSettingAsInt('KOMANDAN_MAX_QUOTA_DAYS', 30))

const quotaOptions = computed(() => {
  const maxMb = maxQuotaMb.value
  if (!Number.isFinite(maxMb) || maxMb <= 0)
    return baseQuotaOptions

  const filtered = baseQuotaOptions.filter(option => option.value <= maxMb)
  if (!filtered.some(option => option.value === maxMb)) {
    const maxGb = (maxMb / 1024).toFixed(2).replace(/\.00$/, '')
    filtered.push({ title: `${maxGb} GB (Maks)`, value: maxMb })
  }
  return filtered.sort((a, b) => a.value - b.value)
})

const durationOptions = computed(() => {
  const maxDays = maxQuotaDays.value
  if (!Number.isFinite(maxDays) || maxDays <= 0)
    return baseDurationOptions

  const filtered = baseDurationOptions.filter(option => option.value <= maxDays)
  if (!filtered.some(option => option.value === maxDays))
    filtered.push({ title: `${maxDays} Hari (Maks)`, value: maxDays })
  return filtered.sort((a, b) => a.value - b.value)
})

const retryCountdownText = computed(() => {
  if (countdownSeconds.value == null)
    return null
  const total = Math.max(0, countdownSeconds.value)
  const hours = Math.floor(total / 3600)
  const minutes = Math.floor((total % 3600) / 60)
  const seconds = total % 60
  const padded = [hours, minutes, seconds].map(part => String(part).padStart(2, '0'))
  return `Coba lagi dalam ${padded.join(':')}`
})

const maxQuotaHint = computed(() => {
  const maxMb = Number(maxQuotaMb.value ?? 0)
  const maxDays = Number(maxQuotaDays.value ?? 0)
  const gb = maxMb > 0 ? (maxMb / 1024).toFixed(2).replace(/\.00$/, '') : null
  const days = maxDays > 0 ? String(maxDays) : null
  if (!gb && !days)
    return null
  if (gb && days)
    return `Maksimal ${gb} GB dan ${days} hari per permintaan.`
  if (gb)
    return `Maksimal ${gb} GB per permintaan.`
  return `Maksimal ${days} hari per permintaan.`
})

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
    retryAfterSeconds.value = null
    retryAtIso.value = null
    countdownSeconds.value = null
    if (countdownTimer) {
      clearInterval(countdownTimer)
      countdownTimer = null
    }
  }
})

watch(allowUnlimited, (isAllowed) => {
  if (!isAllowed && requestType.value === 'UNLIMITED')
    requestType.value = 'QUOTA'
})

watch(maxQuotaMb, (maxMb) => {
  if (requestedMb.value != null && Number.isFinite(maxMb) && maxMb > 0 && requestedMb.value > maxMb)
    requestedMb.value = maxMb
})

watch(maxQuotaDays, (maxDays) => {
  if (requestedDurationDays.value != null && Number.isFinite(maxDays) && maxDays > 0 && requestedDurationDays.value > maxDays)
    requestedDurationDays.value = maxDays
})

onUnmounted(() => {
  if (countdownTimer) {
    clearInterval(countdownTimer)
    countdownTimer = null
  }
})

function startCountdown(seconds: number) {
  const safeSeconds = Math.max(0, Math.floor(seconds))
  countdownSeconds.value = safeSeconds
  if (countdownTimer)
    clearInterval(countdownTimer)
  countdownTimer = setInterval(() => {
    if (countdownSeconds.value == null)
      return
    if (countdownSeconds.value <= 0) {
      clearInterval(countdownTimer as ReturnType<typeof setInterval>)
      countdownTimer = null
      return
    }
    countdownSeconds.value -= 1
  }, 1000)
}

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
    retryAfterSeconds.value = typeof error.data?.retry_after_seconds === 'number' ? error.data.retry_after_seconds : null
    retryAtIso.value = typeof error.data?.retry_at === 'string' ? error.data.retry_at : null
    if (retryAfterSeconds.value != null)
      startCountdown(retryAfterSeconds.value)
    const snackbarText = errorMessage.value ?? 'Terjadi kesalahan pada server.'
    showSnackbar({ type: 'error', title: 'Gagal Mengirim', text: snackbarText })
  }
  finally {
    loading.value = false
  }
}

function closeDialog() {
  emit('update:modelValue', false)
}

function formatRetryAt(isoString: string | null) {
  if (!isoString)
    return null
  const parsed = new Date(isoString)
  if (Number.isNaN(parsed.getTime()))
    return null
  return parsed.toLocaleString('id-ID', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}
</script>

<template>
  <VDialog
    :model-value="modelValue"
    :fullscreen="isMobile"
    :max-width="isMobile ? undefined : 600"
    persistent
    @update:model-value="closeDialog"
  >
    <VCard :class="isMobile ? 'rounded-0' : 'rounded-lg'">
      <VForm
        ref="formRef"
        @submit.prevent="handleSubmit"
      >
        <VCardTitle class="pa-4 bg-primary">
          <div class="dialog-titlebar">
            <div class="dialog-titlebar__title">
              <VIcon
                icon="tabler-mail-plus"
                color="white"
                size="24"
              />
              <div class="d-flex flex-column">
                <span class="text-h6 text-white">Formulir Pengajuan</span>
                <span class="text-body-2 text-white">Ajukan permintaan kuota atau akses unlimited</span>
              </div>
            </div>
            <div class="dialog-titlebar__actions">
              <VBtn
                icon="tabler-x"
                variant="text"
                size="small"
                class="text-white"
                @click="closeDialog"
              />
            </div>
          </div>
        </VCardTitle>

        <VCardText class="pa-5">
          <div class="d-flex flex-column ga-3">
            <div>
              <p class="text-subtitle-1 font-weight-medium mb-1">
                Pilih Tipe Permintaan
              </p>
              <p v-if="maxQuotaHint" class="text-body-2 text-medium-emphasis mb-0">
                {{ maxQuotaHint }}
              </p>
            </div>

            <VRadioGroup
              v-model="requestType"
              :inline="!isMobile"
              class="mb-0"
            >
            <VRadio
              label="Kuota Reguler"
              value="QUOTA"
            />
            <VRadio
              label="Akses Unlimited"
              value="UNLIMITED"
              :disabled="!allowUnlimited"
            />
            </VRadioGroup>

            <VAlert
              v-if="!allowUnlimited"
              type="warning"
              variant="tonal"
              density="compact"
              icon="tabler-alert-triangle"
            >
              Akses unlimited sedang dinonaktifkan oleh kebijakan.
            </VAlert>

            <VDivider class="my-2" />

            <VExpandTransition>
              <div v-if="requestType === 'QUOTA'">
                <p class="text-subtitle-1 font-weight-medium mb-3">
                  Detail Kuota
                </p>
                <VRow>
                  <VCol cols="12" sm="6">
                    <AppSelect
                      v-model="requestedMb"
                      label="Jumlah Kuota"
                      :items="quotaOptions"
                      placeholder="Pilih jumlah GB"
                      :rules="[requiredRule]"
                      prepend-inner-icon="tabler-database"
                    />
                  </VCol>
                  <VCol cols="12" sm="6">
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
                icon="tabler-shield-check"
                density="compact"
              >
                Permintaan akses unlimited akan ditinjau manual oleh Admin, termasuk penentuan masa aktifnya.
              </VAlert>
            </VExpandTransition>

            <VAlert
              v-if="errorMessage"
              type="error"
              variant="tonal"
            >
              <div>{{ errorMessage }}</div>
              <div v-if="retryCountdownText" class="mt-2">
                {{ retryCountdownText }}
              </div>
              <div v-if="formatRetryAt(retryAtIso)" class="text-medium-emphasis mt-1">
                Jadwal ulang: {{ formatRetryAt(retryAtIso) }}
              </div>
            </VAlert>
          </div>
        </VCardText>

        <VDivider />
        <VCardActions class="pa-4">
          <VRow class="w-100" align="center" no-gutters>
            <VCol cols="12" sm="auto" class="pe-sm-2 mb-2 mb-sm-0">
              <VBtn
                variant="tonal"
                color="secondary"
                :block="isMobile"
                @click="closeDialog"
              >
                Batal
              </VBtn>
            </VCol>

            <VCol cols="12" sm="auto" class="flex-grow-1 d-flex justify-sm-end">
              <VBtn
                type="submit"
                color="primary"
                :loading="loading"
                prepend-icon="tabler-send"
                :block="isMobile"
              >
                Kirim Permintaan
              </VBtn>
            </VCol>
          </VRow>
        </VCardActions>
      </VForm>
    </VCard>
  </VDialog>
</template>
