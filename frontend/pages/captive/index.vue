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
import { TAMPING_OPTION_ITEMS } from '~/utils/constants'
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
const otpSent = ref(false)
const phoneNumber = ref('')
const otpCode = ref('')
const viewState = ref<'form' | 'success'>('form')
const currentTab = ref<'login' | 'register'>('login')

// Register (lightweight: USER only)
const registerFormRef = ref<InstanceType<typeof VForm> | null>(null)
const regName = ref('')
const regPhoneNumber = ref('')
const regRole = ref<'USER' | 'TAMPING' | 'KOMANDAN'>('USER')
const regBlock = ref<string | null>(null)
const regKamar = ref<string | null>(null)
const regTampingType = ref<string | null>(null)

const registerHint = ref<string | null>(null)
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
const hasClientIdentity = computed(() => Boolean(portalParams.value.clientIp && portalParams.value.clientMac))
const hotspotLoginOnlyUrl = computed(() => portalParams.value.linkLoginOnly || '')
const canSubmit = computed(() => true)

const formattedPhoneNumberDisplay = computed(() => {
  let num = phoneNumber.value.replace(/[\s-]/g, '')
  if (num.startsWith('08'))
    num = `+62 ${num.substring(1)}`

  return num || phoneNumber.value
})

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

const requiredRule = (v: any) => (v !== null && v !== undefined && v !== '') || 'Wajib diisi.'

const blockOptions = Array.from({ length: 6 }, (_, i) => ({ title: `Blok ${String.fromCharCode(65 + i)}`, value: String.fromCharCode(65 + i) }))
const kamarOptions = Array.from({ length: 6 }, (_, i) => ({ title: `Kamar ${i + 1}`, value: (i + 1).toString() }))

const showAddressFields = computed(() => regRole.value === 'USER')
const showTampingFields = computed(() => regRole.value === 'TAMPING')

const tampingOptions = TAMPING_OPTION_ITEMS

watch(regRole, (newRole) => {
  if (newRole === 'TAMPING') {
    regBlock.value = null
    regKamar.value = null
  }
  else if (newRole === 'USER') {
    regTampingType.value = null
  }
  else if (newRole === 'KOMANDAN') {
    regBlock.value = null
    regKamar.value = null
    regTampingType.value = null
  }
})

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

function resetLoginView() {
  otpSent.value = false
  otpCode.value = ''
}

function backToForms() {
  viewState.value = 'form'
  currentTab.value = 'login'
}

async function handleRequestOtp() {
  if (loginFormRef.value === null)
    return

  const { valid } = await loginFormRef.value.validate()
  if (valid !== true)
    return

  try {
    const numberToSend = normalize_to_e164(phoneNumber.value)
    const success = await authStore.requestOtp(numberToSend)
    if (success === true) {
      otpSent.value = true
      tryFocus(otpInputRef.value)
      return
    }

    // Jika nomor belum terdaftar, arahkan ke tab daftar dengan prefill.
    if ((authStore.error || '').toLowerCase().includes('tidak terdaftar')) {
      currentTab.value = 'register'
      registerHint.value = 'Nomor belum terdaftar. Silakan daftar terlebih dulu.'
      if (!regPhoneNumber.value)
        regPhoneNumber.value = phoneNumber.value
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
      hotspotLoginContext: true,
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

async function handleRegister() {
  if (registerFormRef.value === null)
    return

  registerHint.value = null
  const { valid } = await registerFormRef.value.validate()
  if (valid !== true)
    return

  let numberToSend: string
  try {
    numberToSend = normalize_to_e164(regPhoneNumber.value)
  }
  catch (error: any) {
    const msg = error instanceof Error && error.message ? error.message : 'Format nomor WhatsApp tidak valid.'
    authStore.setError(msg)
    return
  }

  const payload = {
    full_name: regName.value,
    phone_number: numberToSend,
    blok: showAddressFields.value ? regBlock.value : null,
    kamar: showAddressFields.value ? regKamar.value : null,
    is_tamping: regRole.value === 'TAMPING',
    tamping_type: regRole.value === 'TAMPING' ? regTampingType.value : null,
    register_as_komandan: regRole.value === 'KOMANDAN',
  }

  const ok = await authStore.register(payload as any)
  if (!ok) {
    const errText = (authStore.error || '').toLowerCase()
    if (errText.includes('sudah terdaftar')) {
      currentTab.value = 'login'
      phoneNumber.value = regPhoneNumber.value
      registerHint.value = 'Nomor sudah terdaftar. Silakan masuk (OTP).'
    }
    return
  }

  viewState.value = 'success'
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
        <div v-if="viewState === 'form'">
          <ClientOnly>
            <VTabs
              v-model="currentTab"
              grow
              stacked
              class="mb-4"
            >
              <VTab value="login">
                <VIcon icon="tabler-login" class="mb-2" />
                <span>Masuk</span>
              </VTab>
              <VTab value="register">
                <VIcon icon="tabler-user-plus" class="mb-2" />
                <span>Daftar</span>
              </VTab>
            </VTabs>
            <template #fallback>
              <div class="mb-4">
                <VSkeletonLoader type="text@2" />
              </div>
            </template>
          </ClientOnly>
        </div>

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
          v-if="viewState === 'form' && currentTab === 'login' && !hasClientIdentity"
          type="info"
          variant="tonal"
          density="compact"
          class="mb-4"
        >
          <div class="d-flex flex-column ga-3">
            <div>
              IP/MAC perangkat belum terbaca dari router. Jika Anda baru tersambung ke WiFi hotspot, buka login MikroTik (popup) lalu kembali ke halaman ini.
            </div>
            <VBtn
              v-if="hotspotLoginOnlyUrl"
              :href="hotspotLoginOnlyUrl"
              target="_blank"
              rel="noopener"
              size="small"
              variant="outlined"
            >
              Buka Login MikroTik
            </VBtn>
          </div>
        </VAlert>

        <div v-if="viewState === 'form'">
          <VWindow v-model="currentTab" :touch="false">
            <VWindowItem value="login">
              <h4 class="text-h4 mb-1">
                Selamat Datang! 👋🏻
              </h4>
              <p class="mb-6 text-medium-emphasis">
                Silakan masuk dengan nomor WhatsApp Anda untuk mengaktifkan akses internet.
              </p>

              <VForm
                ref="loginFormRef"
                lazy-validation
                @submit.prevent="otpSent ? handleVerifyOtp() : handleRequestOtp()"
              >
                <div v-if="!otpSent">
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
                    <strong class="text-primary">{{ formattedPhoneNumberDisplay }}</strong>
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
                    @click="resetLoginView"
                  >
                    Ganti Nomor
                  </VBtn>
                </div>
              </VForm>

              <VAlert
                v-if="registerHint"
                type="info"
                variant="tonal"
                density="compact"
                class="mt-4"
              >
                {{ registerHint }}
              </VAlert>

              <VAlert
                type="info"
                variant="tonal"
                density="compact"
                class="mt-4"
              >
                Jika OTP gagal berulang, cek sinyal jaringan dan pastikan nomor WhatsApp benar.
              </VAlert>
            </VWindowItem>

            <VWindowItem value="register">
              <h4 class="text-h4 mb-1">
                Daftar Akun
              </h4>
              <p class="mb-6 text-medium-emphasis">
                Lengkapi data untuk membuat akun baru.
              </p>

              <VAlert
                v-if="registerHint"
                type="info"
                variant="tonal"
                density="compact"
                class="mb-4"
              >
                {{ registerHint }}
              </VAlert>

              <VForm
                ref="registerFormRef"
                lazy-validation
                @submit.prevent="handleRegister"
              >
                <VRadioGroup
                  v-model="regRole"
                  inline
                  label="Daftar sebagai:"
                  class="mb-4"
                  :disabled="isSubmitting"
                >
                  <VRadio label="User" value="USER" />
                  <VRadio label="Tamping" value="TAMPING" />
                  <VRadio label="Komandan" value="KOMANDAN" />
                </VRadioGroup>

                <AppTextField
                  v-model="regName"
                  label="Nama Lengkap"
                  placeholder="Contoh: Sobigidul"
                  prepend-inner-icon="tabler-user"
                  :rules="[requiredRule]"
                  :disabled="isSubmitting"
                  class="mb-4"
                />

                <div v-show="showTampingFields">
                  <AppSelect
                    v-model="regTampingType"
                    :items="tampingOptions"
                    label="Jenis Tamping"
                    placeholder="Pilih Jenis Tamping"
                    prepend-inner-icon="tabler-building-bank"
                    :rules="showTampingFields ? [requiredRule] : []"
                    :disabled="isSubmitting"
                    class="mb-4"
                  />
                </div>

                <div v-show="showAddressFields">
                  <AppSelect
                    v-model="regBlock"
                    :items="blockOptions"
                    label="Blok Tempat Tinggal"
                    placeholder="Pilih Blok"
                    prepend-inner-icon="tabler-map-pin"
                    :rules="showAddressFields ? [requiredRule] : []"
                    :disabled="isSubmitting"
                    class="mb-4"
                  />
                  <AppSelect
                    v-model="regKamar"
                    :items="kamarOptions"
                    label="Nomor Kamar"
                    placeholder="Pilih Nomor Kamar"
                    prepend-inner-icon="tabler-door"
                    :rules="showAddressFields ? [requiredRule] : []"
                    :disabled="isSubmitting"
                    class="mb-4"
                  />
                </div>

                <AppTextField
                  v-model="regPhoneNumber"
                  label="Nomor WhatsApp"
                  placeholder="Contoh: 081234567890"
                  prepend-inner-icon="tabler-brand-whatsapp"
                  :rules="phoneFormatRules"
                  :disabled="isSubmitting"
                  class="mb-4"
                  maxlength="20"
                />

                <VBtn block type="submit" :loading="isSubmitting">
                  Daftar
                </VBtn>
              </VForm>

              <VAlert
                type="info"
                variant="tonal"
                density="compact"
                class="mt-4"
              >
                Catatan: validasi WhatsApp aktif tidak dilakukan di captive (sering terblokir sebelum internet aktif). Admin akan memverifikasi setelah pendaftaran.
              </VAlert>
            </VWindowItem>
          </VWindow>
        </div>

        <div v-else-if="viewState === 'success'" class="text-center">
          <VIcon icon="tabler-circle-check" :size="56" color="success" class="mb-4" />
          <h4 class="text-h5 mb-2">Registrasi Diproses</h4>
          <p class="mb-6 text-medium-emphasis">
            Terima kasih! Akun Anda menunggu persetujuan Admin.
          </p>
          <VBtn block @click="backToForms">Kembali ke Masuk</VBtn>
        </div>
        </VCardText>
      </VCard>
    </div>
  </div>
</template>

<style lang="scss">
@use "@core/scss/template/pages/page-auth.scss";

.v-otp-input {
  .v-otp-input__content {
    padding-inline: 0;
  }
}
</style>
