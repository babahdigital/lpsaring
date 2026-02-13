<script setup lang="ts">
import type { VForm } from 'vuetify/components'
import authV1BottomShape from '@images/svg/auth-v1-bottom-shape.svg?raw'
import authV1TopShape from '@images/svg/auth-v1-top-shape.svg?raw'
import { VNodeRenderer } from '@layouts/components/VNodeRenderer'
import { themeConfig } from '@themeConfig'
import { computed, h, nextTick, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useSnackbar } from '~/composables/useSnackbar'
import { useAuthStore } from '~/store/auth'
import { normalize_to_e164 } from '~/utils/formatters'
import { useApiFetch } from '~/composables/useApiFetch'

definePageMeta({
  layout: 'blank',
})

useHead({ title: 'Login Hotspot' })

const authStore = useAuthStore()
const route = useRoute()
const { add: addSnackbar } = useSnackbar()
const config = useRuntimeConfig()

const loginFormRef = ref<InstanceType<typeof VForm> | null>(null)
const otpInputRef = ref<any>(null)
const step = ref<'phone' | 'otp' | 'error'>('phone')
const phoneNumber = ref('')
const otpCode = ref('')
const errorMessage = ref('')
const apiStatus = ref<'ok' | 'degraded' | 'down'>('ok')
const apiStatusMessage = computed(() => {
  if (apiStatus.value === 'down')
    return 'Portal tidak bisa terhubung ke server. Periksa koneksi WiFi atau hubungi admin.'
  if (apiStatus.value === 'degraded')
    return 'Server sedang sibuk. Coba lagi beberapa saat.'
  return ''
})

const portalParams = ref({
  linkLoginOnly: '',
  linkOrig: '',
  linkRedirect: '',
  chapId: '',
  chapChallenge: '',
  clientMac: '',
  clientIp: '',
})

const isSubmitting = computed(() => authStore.loading)
const hasRequiredParams = computed(() => true)
const hasClientIdentity = computed(() => Boolean(portalParams.value.clientIp && portalParams.value.clientMac))
const canSubmit = computed(() => hasRequiredParams.value)

const phoneFormatRules = [
  (v: string) => {
    if (!v)
      return 'Nomor telepon wajib diisi.'
    try {
      normalize_to_e164(v)
      return true
    }
    catch (error: any) {
      return error instanceof Error && error.message !== ''
        ? error.message
        : 'Format nomor salah. Gunakan awalan 08, 628, atau +628.'
    }
  },
]

function getQueryValue(key: string): string {
  const value = route.query[key]
  if (Array.isArray(value))
    return value[0] ?? ''
  return typeof value === 'string' ? value : ''
}

function getQueryValueFromKeys(keys: string[]): string {
  for (const key of keys) {
    const value = getQueryValue(key)
    if (value)
      return value
  }
  return ''
}

function loadPortalParams() {
  portalParams.value = {
    linkLoginOnly: getQueryValueFromKeys(['link_login_only', 'link-login-only', 'link_login', 'link-login']),
    linkOrig: getQueryValueFromKeys(['link_orig', 'link-orig']),
    linkRedirect: getQueryValueFromKeys(['link_redirect', 'link-redirect']),
    chapId: getQueryValueFromKeys(['chap_id', 'chap-id']),
    chapChallenge: getQueryValueFromKeys(['chap_challenge', 'chap-challenge']),
    clientMac: getQueryValueFromKeys(['client_mac', 'mac']),
    clientIp: getQueryValueFromKeys(['client_ip', 'ip']),
  }

  if (!hasRequiredParams.value) {
    errorMessage.value = 'IP/MAC perangkat belum terbaca. Silakan buka ulang portal dari WiFi hotspot.'
    addSnackbar({
      title: 'Parameter Hotspot Tidak Lengkap',
      text: errorMessage.value,
      type: 'warning',
    })
  }
}

onMounted(() => {
  loadPortalParams()
  refreshApiHealth()
})

const { data: healthData, error: healthError, refresh: refreshApiHealth } = useApiFetch<{ status: string }>('/health', {
  server: false,
  immediate: false,
})

watch([healthData, healthError], () => {
  if (healthError.value != null) {
    apiStatus.value = 'down'
    return
  }
  if (healthData.value?.status === 'ok') {
    apiStatus.value = 'ok'
    return
  }
  if (healthData.value?.status) {
    apiStatus.value = 'degraded'
    return
  }
  apiStatus.value = 'down'
})

async function tryFocus(refInstance: { focus?: () => void } | null) {
  await nextTick()
  if (refInstance !== null)
    refInstance.focus?.()
}

async function handleRequestOtp() {
  if (!hasRequiredParams.value) {
    step.value = 'error'
    errorMessage.value = 'Parameter login hotspot tidak lengkap. Silakan buka kembali halaman login dari WiFi.'
    return
  }
  if (loginFormRef.value === null)
    return

  const { valid } = await loginFormRef.value.validate()
  if (valid !== true)
    return

  try {
    const numberToSend = normalize_to_e164(phoneNumber.value)
    const success = await authStore.requestOtp(numberToSend)
    if (success === true) {
      step.value = 'otp'
      tryFocus(otpInputRef.value)
    }
  }
  catch (error: any) {
    let errorMessageValue = 'Format nomor telepon tidak valid.'
    if (error instanceof Error && error.message !== '')
      errorMessageValue = error.message
    authStore.setError(errorMessageValue)
  }
}

async function handleVerifyOtp() {
  if (!hasRequiredParams.value) {
    step.value = 'error'
    errorMessage.value = 'Parameter login hotspot tidak lengkap. Silakan buka kembali halaman login dari WiFi.'
    return
  }
  if (loginFormRef.value === null)
    return

  const { valid } = await loginFormRef.value.validate()
  if (valid !== true)
    return

  if (otpCode.value.length !== 6)
    return

  try {
    const numberToVerify = normalize_to_e164(phoneNumber.value)
    const result = await authStore.verifyOtpForCaptive(numberToVerify, otpCode.value, {
      clientIp: portalParams.value.clientIp,
      clientMac: portalParams.value.clientMac,
      hotspotLoginContext: hasRequiredParams.value,
    })

    if (result.response == null) {
      const errorText = result.errorMessage || ''
      const statusRedirectPath = authStore.getStatusRedirectPath('captive')
      if (statusRedirectPath) {
        await navigateTo(statusRedirectPath, { replace: true })
        return
      }
      if (errorText.includes('Perangkat belum diotorisasi')) {
        await navigateTo('/captive/otorisasi-perangkat', { replace: true })
        return
      }
      if (errorText.includes('Limit perangkat tercapai')) {
        await navigateTo('/captive/blokir', { replace: true })
        return
      }
      const errorStatus = result.errorStatus ?? authStore.getAccessStatusFromError(errorText)
      if (errorStatus !== null) {
        const redirectPath = authStore.getRedirectPathForStatus(errorStatus, 'captive')
        if (redirectPath) {
          await navigateTo(redirectPath, { replace: true })
          return
        }
      }
      otpCode.value = ''
      tryFocus(otpInputRef.value)
      return
    }

    const response = result.response

    const currentUser = authStore.currentUser
    if (currentUser) {
      const status = authStore.getAccessStatusFromUser(currentUser)
      const redirectPath = authStore.getRedirectPathForStatus(status, 'captive')
      if (redirectPath) {
        await navigateTo(redirectPath, { replace: true })
        return
      }
    }

    await navigateTo('/captive/terhubung', { replace: true })
  }
  catch (error: any) {
    let errorMessageValue = 'Terjadi masalah dengan nomor telepon.'
    if (error instanceof Error && error.message !== '')
      errorMessageValue = error.message
    authStore.setError(errorMessageValue)
  }
}

watch(() => authStore.error, (newError) => {
  if (typeof newError === 'string' && newError.length > 0) {
    addSnackbar({
      title: 'Terjadi Kesalahan',
      text: newError,
      type: 'error',
    })
    authStore.clearError()
  }
})

watch(() => authStore.message, (newMessage) => {
  if (typeof newMessage === 'string' && newMessage.length > 0) {
    addSnackbar({
      title: 'Informasi',
      text: newMessage,
      type: 'success',
    })
    authStore.clearMessage()
  }
})

</script>

<template>
  <div class="auth-wrapper d-flex align-center justify-center pa-4">
    <div class="position-relative my-sm-16">
      <VNodeRenderer
        :nodes="h('div', { innerHTML: authV1TopShape })"
        class="text-primary auth-v1-top-shape d-none d-sm-block"
      />

      <VNodeRenderer
        :nodes="h('div', { innerHTML: authV1BottomShape })"
        class="text-primary auth-v1-bottom-shape d-none d-sm-block"
      />

      <VCard class="auth-card pa-4 pa-sm-6" max-width="480">
        <VCardItem class="justify-center">
          <VCardTitle>
            <NuxtLink to="/">
              <div class="app-logo">
                <VNodeRenderer :nodes="themeConfig.app.logo" />
                <h1 class="app-logo-title">
                  {{ themeConfig.app.title }}
                </h1>
              </div>
            </NuxtLink>
          </VCardTitle>
        </VCardItem>

        <VCardText>
        <div v-if="step === 'error'" class="text-center">
          <VIcon icon="tabler-alert-triangle" size="44" class="mb-4" color="error" />
          <h4 class="text-h5 mb-2">
            Gagal Memuat Login
          </h4>
          <p class="text-medium-emphasis">
            {{ errorMessage }}
          </p>
        </div>

        <div v-else>
          <h4 class="text-h5 mb-1">
            Login Hotspot
          </h4>
          <p class="text-medium-emphasis mb-6">
            Masuk dengan nomor WhatsApp untuk mengaktifkan akses internet.
          </p>

          <VAlert
            v-if="apiStatus !== 'ok'"
            :type="apiStatus === 'down' ? 'error' : 'warning'"
            variant="tonal"
            density="compact"
            class="mb-4"
          >
            {{ apiStatusMessage }}
          </VAlert>

          <VAlert
            v-if="!hasClientIdentity"
            type="warning"
            variant="tonal"
            density="compact"
            class="mb-4"
          >
            <div class="d-flex flex-column ga-3">
              <div>
                Perangkat belum mengirim IP/MAC. Silakan buka halaman login hotspot Mikrotik agar data perangkat terbaca.
              </div>
              <VBtn
                to="/portal"
                size="small"
                variant="outlined"
              >
                Buka Portal Info
              </VBtn>
            </div>
          </VAlert>

          <VForm
            ref="loginFormRef"
            lazy-validation
            @submit.prevent="step === 'otp' ? handleVerifyOtp() : handleRequestOtp()"
          >
            <div v-if="step === 'phone'">
              <AppTextField
                v-model="phoneNumber"
                autofocus
                label="Nomor WhatsApp"
                placeholder="Contoh: 081234567890"
                prepend-inner-icon="tabler-device-mobile"
                :rules="phoneFormatRules"
                :disabled="isSubmitting"
              />
              <VBtn
                class="mt-4"
                block
                type="submit"
                :loading="isSubmitting"
                :disabled="isSubmitting || !canSubmit"
              >
                Kirim Kode OTP
              </VBtn>
            </div>

            <div v-else>
              <p class="mb-2 text-center">
                Masukkan 6 digit kode OTP yang dikirim ke
                <br>
                <strong class="text-primary">{{ phoneNumber }}</strong>
              </p>
              <VOtpInput
                ref="otpInputRef"
                v-model="otpCode"
                :length="6"
                type="number"
                class="my-4"
                :loading="isSubmitting"
                :disabled="isSubmitting"
                @finish="handleVerifyOtp"
              />
              <VBtn
                block
                type="submit"
                :loading="isSubmitting"
                :disabled="isSubmitting || otpCode.length !== 6 || !canSubmit"
              >
                Verifikasi & Hubungkan
              </VBtn>
              <VBtn
                variant="text"
                block
                size="small"
                class="mt-2"
                :disabled="isSubmitting"
                @click="step = 'phone'; otpCode = ''"
              >
                Ganti Nomor
              </VBtn>
              <VAlert
                type="info"
                variant="tonal"
                density="compact"
                class="mt-4"
              >
                Jika sering diminta OTP ulang, matikan Private MAC untuk SSID hotspot agar perangkat dikenali.
              </VAlert>
            </div>
          </VForm>
        </div>
        </VCardText>
      </VCard>
    </div>
  </div>
</template>
