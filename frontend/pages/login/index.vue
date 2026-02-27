<script setup lang="ts">
import type { VForm } from 'vuetify/components'
import authV1BottomShape from '@images/svg/auth-v1-bottom-shape.svg?raw'

import authV1TopShape from '@images/svg/auth-v1-top-shape.svg?raw'
import { VNodeRenderer } from '@layouts/components/VNodeRenderer'
import { themeConfig } from '@themeConfig'

import { computed, h, nextTick, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useDisplay } from 'vuetify'
import { useSnackbar } from '~/composables/useSnackbar'
import { useAuthStore } from '~/store/auth'
import { normalize_to_e164 } from '~/utils/formatters'
import { TAMPING_OPTION_ITEMS } from '~/utils/constants'

definePageMeta({
  layout: 'blank',
})

const authStore = useAuthStore()
const { add: addSnackbar } = useSnackbar()
const display = useDisplay()
const route = useRoute()
const isHydrated = ref(false)
const isWidePadding = computed(() => (isHydrated.value ? display.smAndUp.value : false))

// --- State untuk UI dan Tab ---
const currentTab = ref<'login' | 'register'>('login')
const viewState = ref<'form' | 'success'>('form')
useHead({ title: 'Portal Hotspot' })
onMounted(() => {
  isHydrated.value = true
  const tab = typeof route.query.tab === 'string' ? route.query.tab : ''
  if (tab === 'register')
    currentTab.value = 'register'
})

// --- State untuk Form Login ---
const loginFormRef = ref<InstanceType<typeof VForm> | null>(null)
const otpSent = ref(false)
const phoneNumber = ref('')
const otpCode = ref('')
const otpInputRef = ref<any>(null)

// --- State untuk Form Register ---
const registerFormRef = ref<InstanceType<typeof VForm> | null>(null)
const regName = ref('')
const regPhoneNumber = ref('')
const regRole = ref<'USER' | 'TAMPING' | 'KOMANDAN'>('USER')
const regBlock = ref<string | null>(null)
const regKamar = ref<string | null>(null)
const regIsTamping = ref(false)
const regTampingType = ref<string | null>(null)

// --- Computed Properties ---
const isSubmitting = computed(() => authStore.loading)
const showAddressFields = computed(() => regRole.value === 'USER')
const showTampingFields = computed(() => regRole.value === 'TAMPING')
const formattedPhoneNumberDisplay = computed(() => {
  let num = phoneNumber.value.replace(/[\s-]/g, '')
  if (num.startsWith('08'))
    num = `+62 ${num.substring(1)}`

  return num || phoneNumber.value
})

function getQueryValue(key: string): string {
  const value = route.query[key]
  if (Array.isArray(value))
    return value[0] ?? ''
  return typeof value === 'string' ? value : ''
}

function getRedirectTargetAfterLogin(): string | null {
  const redirectQuery = route.query.redirect
  const redirectPath = Array.isArray(redirectQuery) ? redirectQuery[0] : redirectQuery
  if (typeof redirectPath !== 'string' || redirectPath.length === 0)
    return null
  if (!redirectPath.startsWith('/') || redirectPath.startsWith('//'))
    return null
  if (redirectPath.includes('://'))
    return null

  // Hindari loop ke halaman auth/guest.
  const disallowedPrefixes = ['/login', '/register', '/daftar', '/captive', '/session/consume']
  if (disallowedPrefixes.some(prefix => redirectPath === prefix || redirectPath.startsWith(`${prefix}/`)))
    return null

  // Non-admin tidak boleh diarahkan ke area admin.
  if (!authStore.isAdmin && (redirectPath === '/admin' || redirectPath.startsWith('/admin/')))
    return null

  // Admin boleh ke /admin/*, tapi jangan ke halaman login admin.
  if (authStore.isAdmin) {
    if (redirectPath === '/admin' || redirectPath === '/admin/login' || redirectPath.startsWith('/admin/login/'))
      return null
  }

  return redirectPath
}

function getQueryValueFromKeys(keys: string[]): string {
  for (const key of keys) {
    const value = getQueryValue(key)
    if (value)
      return value
  }
  return ''
}

// --- Opsi untuk Select Input ---
const blockOptions = Array.from({ length: 6 }, (_, i) => ({ title: `Blok ${String.fromCharCode(65 + i)}`, value: String.fromCharCode(65 + i) }))
const kamarOptions = Array.from({ length: 6 }, (_, i) => ({ title: `Kamar ${i + 1}`, value: (i + 1).toString() }))
const tampingOptions = TAMPING_OPTION_ITEMS

// --- Aturan Validasi ---
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
const tampingRequiredRule = (v: any) => (v !== null && v !== undefined && v !== '') || 'Jenis tamping wajib dipilih.'

watch(regRole, (newRole) => {
  if (newRole === 'TAMPING') {
    regIsTamping.value = true
    regBlock.value = null
    regKamar.value = null
  }
  else if (newRole === 'USER') {
    regIsTamping.value = false
    regTampingType.value = null
  }
  else if (newRole === 'KOMANDAN') {
    regIsTamping.value = false
    regBlock.value = null
    regKamar.value = null
    regTampingType.value = null
  }
})

watch(regIsTamping, (isTamping) => {
  if (isTamping) {
    regBlock.value = null
    regKamar.value = null
  }
  else {
    regTampingType.value = null
  }
})

// --- Aturan Validasi Asinkron untuk Nomor WhatsApp ---
let validationTimeout: NodeJS.Timeout | null = null
function whatsappValidationRule(v: string) {
  const isFormatBasicallyCorrect = phoneFormatRules.every(rule => rule(v) === true)
  if (isFormatBasicallyCorrect !== true)
    return true

  return new Promise<boolean | string>((resolve) => {
    if (validationTimeout !== null)
      clearTimeout(validationTimeout)

    validationTimeout = setTimeout(async () => {
      try {
        const response = await $fetch<{ isValid: boolean, message?: string }>('/api/users/validate-whatsapp', {
          method: 'POST',
          body: { phone_number: v },
          timeout: 3000, // 3 detik timeout
        })

        if (response.isValid === true) {
          resolve(true)
        }
        else {
          let errorMsg = 'Nomor WhatsApp tidak valid'

          // Berikan pesan lebih spesifik
          if (response.message?.includes('terdaftar')) {
            errorMsg = 'Nomor sudah terdaftar di sistem'
          }
          else if (response.message?.includes('aktif')) {
            errorMsg = 'Nomor tidak aktif di WhatsApp'
          }
          else if (response.message?.includes('timeout')) {
            errorMsg = 'Validasi timeout, coba lagi'
          }

          resolve(errorMsg)
        }
      }
      catch (error: any) {
        let errorMsg = 'Gagal memvalidasi nomor'

        // Handle timeout khusus
        if (error.name === 'FetchError' && error.message.includes('timed out')) {
          errorMsg = 'Timeout: Layanan validasi tidak merespon'
        }

        resolve(errorMsg)
      }
    }, 500)
  })
} // <-- Kurung kurawal penutup ini yang hilang

// --- Fungsi Helper ---
async function tryFocus(refInstance: { focus?: () => void } | null) {
  await nextTick()
  if (refInstance !== null)
    refInstance.focus?.()
}

// --- Handler Aksi Form ---
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
    }
  }
  catch (error: any) {
    let errorMessage = 'Format nomor telepon tidak valid.'
    // [PERBAIKAN] Pengecekan bertingkat untuk memuaskan linter.
    if (error instanceof Error) {
      if (error.message !== '')
        errorMessage = error.message
    }
    authStore.setError(errorMessage)
  }
}

async function handleVerifyOtp() {
  if (loginFormRef.value === null)
    return

  const { valid } = await loginFormRef.value.validate()
  if (valid !== true)
    return

  try {
    const otpDigitsOnly = String(otpCode.value ?? '').replace(/\D/g, '')
    const otpToSend = otpDigitsOnly.length >= 6 ? otpDigitsOnly.slice(-6) : otpDigitsOnly
    if (otpToSend.length !== 6) {
      authStore.setError('Kode OTP harus 6 digit.')
      return
    }

    const numberToVerify = normalize_to_e164(phoneNumber.value)
    const clientIp = getQueryValueFromKeys(['client_ip', 'ip', 'client-ip'])
    const clientMac = getQueryValueFromKeys(['client_mac', 'mac', 'mac-address', 'client-mac'])
    const loginResponse = await authStore.verifyOtp(numberToVerify, otpToSend, {
      clientIp: clientIp || null,
      clientMac: clientMac || null,
    })
    if (loginResponse == null) {
      const errorText = authStore.error || ''
      const statusRedirectPath = authStore.getStatusRedirectPath('login')
      if (statusRedirectPath && import.meta.client) {
        await navigateTo(statusRedirectPath, { replace: true })
        return
      }

      if (import.meta.client && errorText.includes('Perangkat belum diotorisasi')) {
        await navigateTo('/captive/otorisasi-perangkat', { replace: true })
        return
      }
      if (import.meta.client && errorText.includes('Limit perangkat tercapai')) {
        await navigateTo('/akun', { replace: true })
        return
      }
      const errorStatus = authStore.getAccessStatusFromError(authStore.error)
      if (errorStatus !== null) {
        const redirectPath = authStore.getRedirectPathForStatus(errorStatus, 'login')
        if (redirectPath && import.meta.client) {
          await navigateTo(redirectPath, { replace: true })
          return
        }
      }
      otpCode.value = ''
      tryFocus(otpInputRef.value)
      return
    }

    const status = authStore.getAccessStatusFromUser(authStore.currentUser)
    const redirectPath = authStore.getRedirectPathForStatus(status, 'login')
    if (redirectPath && import.meta.client) {
      await navigateTo(redirectPath, { replace: true })
      return
    }
    if (import.meta.client) {
      if (loginResponse.hotspot_login_required === true && loginResponse.hotspot_session_active === false && !clientIp && !clientMac) {
        await navigateTo('/login/hotspot-required', { replace: true })
        return
      }

      const sessionUrl = loginResponse.session_url
      if (sessionUrl)
        window.location.replace(sessionUrl)
      else {
        const redirectTarget = getRedirectTargetAfterLogin()
        await navigateTo(redirectTarget ?? '/dashboard', { replace: true })
      }
    }
  }
  catch (error: any) {
    let errorMessage = 'Terjadi masalah dengan nomor telepon.'
    // [PERBAIKAN] Pengecekan bertingkat untuk memuaskan linter.
    if (error instanceof Error) {
      if (error.message !== '')
        errorMessage = error.message
    }
    authStore.setError(errorMessage)
    resetLoginView()
  }
}

async function handleRegister() {
  if (registerFormRef.value === null)
    return
  const { valid } = await registerFormRef.value.validate()
  if (valid !== true) {
    addSnackbar({
      title: 'Validasi Gagal',
      text: 'Silakan periksa kembali semua data yang wajib diisi, termasuk memastikan nomor WhatsApp valid.',
      type: 'warning',
    })
    return
  }

  let numberToSend: string
  try {
    numberToSend = normalize_to_e164(regPhoneNumber.value)
  }
  catch (error: any) {
    let errorMessage = 'Format nomor WhatsApp tidak valid.'
    // [PERBAIKAN] Pengecekan bertingkat untuk memuaskan linter.
    if (error instanceof Error) {
      if (error.message !== '')
        errorMessage = error.message
    }
    authStore.setError(errorMessage)

    return
  }

  const registrationPayload = {
    full_name: regName.value,
    phone_number: numberToSend,
    blok: showAddressFields.value ? regBlock.value : null,
    kamar: showAddressFields.value ? regKamar.value : null,
    is_tamping: regRole.value === 'TAMPING',
    tamping_type: showTampingFields.value ? regTampingType.value : null,
    register_as_komandan: regRole.value === 'KOMANDAN',
  }

  const registerSuccess = await authStore.register(registrationPayload)
  if (registerSuccess === true)
    viewState.value = 'success'
}

// --- Fungsi Reset View ---
function resetLoginView() {
  otpSent.value = false
  phoneNumber.value = ''
  otpCode.value = ''
  authStore.clearError()
  authStore.clearMessage()
  if (loginFormRef.value !== null)
    loginFormRef.value.resetValidation()
}

function backToForms() {
  viewState.value = 'form'
  currentTab.value = 'login'
  resetLoginView()

  regName.value = ''
  regPhoneNumber.value = ''
  regRole.value = 'USER'
  regBlock.value = null
  regKamar.value = null
  regIsTamping.value = false
  regTampingType.value = null
  if (registerFormRef.value !== null)
    registerFormRef.value.reset()
}

// --- Watchers untuk menampilkan Notifikasi dan Perbaikan Bug ---
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

watch(regRole, () => {
  if (registerFormRef.value !== null)
    registerFormRef.value.resetValidation()
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

      <VCard
        class="auth-card"
        max-width="460"
        :class="isWidePadding ? 'pa-6' : 'pa-4'"
      >
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

        <VCardText v-if="viewState === 'form'">
          <ClientOnly>
            <VTabs
              v-model="currentTab"
              grow
              stacked
              class="mb-4"
            >
              <VTab value="login">
                <VIcon
                  icon="tabler-login"
                  class="mb-2"
                />
                <span>Masuk</span>
              </VTab>
              <VTab value="register">
                <VIcon
                  icon="tabler-user-plus"
                  class="mb-2"
                />
                <span>Daftar</span>
              </VTab>
            </VTabs>
            <template #fallback>
              <div class="mb-4">
                <VSkeletonLoader type="text@2" />
              </div>
            </template>
          </ClientOnly>
        </VCardText>

        <VCardText>
          <div v-if="viewState === 'form'">
            <VWindow
              v-model="currentTab"
              :touch="false"
            >
              <VWindowItem value="login">
                <h4 class="text-h4 mb-1">
                  Selamat Datang! 👋🏻
                </h4>
                <p class="mb-6 text-medium-emphasis">
                  Silakan masuk dengan nomor WhatsApp Anda.
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
                      :rules="phoneFormatRules" :disabled="isSubmitting"
                    />
                    <VBtn
                      class="mt-4"
                      block
                      type="submit"
                      :loading="isSubmitting"
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
                      :disabled="isSubmitting || String(otpCode ?? '').replace(/\D/g, '').length < 6"
                    >
                      Verifikasi & Masuk
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
                  Ayo, Daftar Akun. 🚀
                </h4>
                <p class="mb-6 text-medium-emphasis">
                  Lengkapi data untuk membuat akun baru.
                </p>
                <VForm
                  ref="registerFormRef"
                  lazy-validation
                  @submit.prevent="handleRegister"
                >
                  <VRadioGroup
                    v-model="regRole"
                    :inline="isWidePadding"
                    label="Saya mendaftar sebagai:"
                    class="mb-4"
                    :disabled="isSubmitting"
                  >
                    <VRadio
                      label="User"
                      value="USER"
                    />
                    <VRadio
                      label="Tamping"
                      value="TAMPING"
                    />
                    <VRadio
                      label="Komandan"
                      value="KOMANDAN"
                    />
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
                      :rules="showTampingFields ? [tampingRequiredRule] : []"
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
                    label="Nomor WhatsApp Aktif"
                    placeholder="Contoh: 081234567890"
                    prepend-inner-icon="tabler-brand-whatsapp"
                    :rules="[...phoneFormatRules, whatsappValidationRule]"
                    :disabled="isSubmitting"
                    class="mb-4"
                    maxlength="12"
                    validate-on="input"
                  />
                  <VBtn
                    block
                    type="submit"
                    :loading="isSubmitting"
                  >
                    Daftar Akun
                  </VBtn>
                </VForm>
              </VWindowItem>
            </VWindow>
          </div>

          <div
            v-else-if="viewState === 'success'"
            class="text-center"
          >
            <VIcon
              icon="tabler-circle-check"
              :size="64"
              color="success"
              class="mb-4"
            />
            <h4 class="text-h4 mb-2">
              Registrasi Diproses
            </h4>
            <p class="mb-6 text-medium-emphasis">
              Terima kasih! Akun Anda sedang menunggu persetujuan Admin. Notifikasi akan dikirim melalui WhatsApp jika akun Anda telah aktif.
            </p>
            <VBtn
              block
              @click="backToForms"
            >
              Kembali ke Halaman Masuk
            </VBtn>
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

.auth-wrapper {
  min-block-size: 100dvh;
}
</style>
