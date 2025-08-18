// pages/captive/index.vue
<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from 'vue'

import { useClientDetection } from '~/composables/useClientDetection'
import { useSnackbar } from '~/composables/useSnackbar'
import { useAuthStore } from '~/store/auth'
import { normalize_to_e164 } from '~/utils/formatters'

definePageMeta({ layout: 'captive' })
useHead({ title: 'Login Portal' })

const authStore = useAuthStore()
const { add: addSnackbar } = useSnackbar()
const { forceDetection } = useClientDetection()
// const { $api } = useNuxtApp()

const step = ref<'phone' | 'otp'>('phone')
const phone = ref('')
const otp = ref('')
const isLoading = ref(false)
const otpTimer = ref(0)
const otpInputRef = ref<any>(null)

onMounted(async () => {
  // Captive middleware sudah melakukan clear-cache + sync auto bila sudah login.
  // Di sini cukup pastikan deteksi lokal siap untuk alur OTP.
  await forceDetection()
})

const phoneValid = computed(() => /^(?:\+62|62|0)\d{9,13}$/.test(phone.value))
const canResendOtp = computed(() => otpTimer.value === 0)

function startOtpTimer() {
  otpTimer.value = 60
  const interval = setInterval(() => {
    otpTimer.value--
    if (otpTimer.value <= 0)
      clearInterval(interval)
  }, 1000)
}

async function handleRequestOtp() {
  if (!phoneValid.value || isLoading.value)
    return
  isLoading.value = true
  try {
    const success = await authStore.requestOtp(normalize_to_e164(phone.value))
    if (success) {
      step.value = 'otp'
      startOtpTimer()
      nextTick(() => otpInputRef.value?.focus())
    }
    else {
      addSnackbar({ type: 'error', title: 'Gagal', text: authStore.error || 'Gagal mengirim OTP.' })
    }
  }
  finally {
    isLoading.value = false
  }
}

async function handleVerifyOtp() {
  if (otp.value.length !== 6 || isLoading.value)
    return
  isLoading.value = true
  try {
    const payload = {
      phone_number: normalize_to_e164(phone.value),
      otp: otp.value,
      client_ip: authStore.clientIp,
      client_mac: authStore.clientMac,
    }
    const success = await authStore.verifyOtp(payload)
    if (success) {
      // Clear any throttling data after successful login
      localStorage.removeItem('last_device_sync')

      // Setelah login, arahkan ke halaman otorisasi bila perlu atau terhubung.
      // Biarkan middleware/user-status atau halaman tujuan men-trigger sync seperlunya.
      const res: any = await authStore.syncDevice()
      if (res?.status === 'DEVICE_UNREGISTERED' || authStore.isNewDeviceDetected) {
        await navigateTo('/captive/otorisasi-perangkat', { replace: true })
      }
      else {
        await navigateTo('/captive/terhubung', { replace: true })
      }
    }
    else {
      addSnackbar({ type: 'error', title: 'Verifikasi Gagal', text: authStore.error || 'Kode OTP tidak valid.' })
    }
  }
  finally {
    isLoading.value = false
  }
}
</script>

<template>
  <VCard class="w-100 pa-2 pa-sm-8" rounded="xl" elevation="12">
    <VCardText>
      <div v-if="step === 'phone'">
        <div class="text-center mb-6">
          <h2 class="text-h5 font-weight-bold">Selamat Datang</h2>
          <p class="text-medium-emphasis">Masukkan nomor WhatsApp untuk login.</p>
        </div>
        <VForm @submit.prevent="handleRequestOtp">
          <VTextField
            v-model="phone"
            label="Nomor WhatsApp"
            placeholder="08123456789"
            variant="outlined"
            type="tel"
            prepend-inner-icon="tabler-phone"
            autofocus
          />
          <VBtn
            :loading="isLoading"
            :disabled="!phoneValid"
            type="submit"
            block
            color="primary"
            size="large"
            class="mt-4"
          >
            Kirim Kode OTP
          </VBtn>
        </VForm>
      </div>

      <div v-if="step === 'otp'">
        <div class="text-center mb-6">
          <h2 class="text-h5 font-weight-bold">Verifikasi Kode</h2>
          <p class="text-medium-emphasis">
            Kami telah mengirim kode 6 digit ke <strong>{{ phone }}</strong>.
          </p>
        </div>
        <VForm @submit.prevent="handleVerifyOtp">
          <VTextField
            ref="otpInputRef"
            v-model="otp"
            label="Kode OTP"
            variant="outlined"
            maxlength="6"
            placeholder="------"
            class="otp-input"
          />
          <VBtn
            :loading="isLoading"
            :disabled="otp.length !== 6"
            type="submit"
            block
            color="primary"
            size="large"
            class="mt-4"
          >
            Verifikasi & Masuk
          </VBtn>
        </VForm>
        <div class="d-flex justify-space-between align-center mt-4">
          <VBtn variant="text" size="small" @click="step = 'phone'">
            Ganti Nomor
          </VBtn>
          <VBtn variant="text" size="small" :disabled="!canResendOtp" @click="handleRequestOtp">
            Kirim Ulang {{ canResendOtp ? '' : `(${otpTimer}s)` }}
          </VBtn>
        </div>
      </div>
    </VCardText>
  </VCard>
</template>

<style scoped>
.otp-input :deep(input) {
  text-align: center;
  font-size: 1.5rem;
  letter-spacing: 0.5em;
}
</style>
