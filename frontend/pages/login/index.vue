<script setup lang="ts">
import type { ComponentPublicInstance } from 'vue'
import type { VForm } from 'vuetify/components'
import type { VOtpInput } from 'vuetify/labs/VOtpInput'
import { computed, defineAsyncComponent, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useDisplay } from 'vuetify'
import { VThemeProvider } from 'vuetify/components/VThemeProvider'
import { useAuthStore } from '~/store/auth'

// --- PENAMBAHAN BARU ---
// Impor komponen PromoAnnouncement
const PromoAnnouncement = defineAsyncComponent(() => import('~/components/promo/PromoAnnouncement.vue'))
// --- AKHIR PENAMBAHAN ---

definePageMeta({
  layout: 'blank',
})

const { mobile } = useDisplay()

const authStore = useAuthStore()
const router = useRouter()
const route = useRoute()

const initialLoading = ref(true)
const currentView = ref<'login' | 'register' | 'registerSuccess'>('login')

// Login state
const otpSent = ref(false)
const phoneNumber = ref('')
const otpCode = ref('')
const phoneInputRef = ref<ComponentPublicInstance | null>(null)
const otpInputRef = ref<InstanceType<typeof VOtpInput> | null>(null)
const loginFormRef = ref<InstanceType<typeof VForm> | null>(null)

// Registration state
const regName = ref('')
const regBlock = ref<string | null>(null)
const regKamar = ref<string | null>(null)
const regPhoneNumber = ref('')
const registrationFormRef = ref<InstanceType<typeof VForm> | null>(null)
const regNameInputRef = ref<ComponentPublicInstance | null>(null)

const blockOptions = [
  { title: 'Blok A', value: 'A' },
  { title: 'Blok B', value: 'B' },
  { title: 'Blok C', value: 'C' },
  { title: 'Blok D', value: 'D' },
  { title: 'Blok E', value: 'E' },
  { title: 'Blok F', value: 'F' },
]
const kamarOptions = Array.from({ length: 6 }, (_, i) => ({ title: `Kamar ${i + 1}`, value: (i + 1).toString() }))

const isSubmitting = computed(() => authStore.isLoading)

// Validation Rules
const phoneRules = [
  (v: string) => !!v || 'Nomor telepon wajib diisi.',
  (v: string) => /^(?:08[1-9]\d{7,11}|\+628[1-9]\d{7,11})$/.test(v.replace(/[\s-]/g, '')) || 'Format nomor telepon tidak valid (08xx atau +628xx).',
]
const otpRules = [
  (v: string) => !!v || 'Kode OTP wajib diisi.',
  (v: string) => (v.length === 6 && /^\d{6}$/.test(v)) || 'Kode OTP harus 6 digit angka.',
]
const regNameRules = [
  (v: string) => !!v || 'Nama lengkap wajib diisi.',
  (v: string) => (v && v.length >= 3) || 'Nama minimal 3 karakter.',
]
const regBlockRules = [(v: string | null) => !!v || 'Blok wajib dipilih.']
const regKamarRules = [(v: string | null) => !!v || 'Kamar wajib dipilih.']
const regPhoneRules = [
  (v: string) => !!v || 'Nomor WhatsApp wajib diisi.',
  (v: string) => /^(?:08[1-9]\d{7,11}|\+628[1-9]\d{7,11})$/.test(v.replace(/[\s-]/g, '')) || 'Format nomor WhatsApp tidak valid.',
]

// Computed validation states
const isLoginFormPhoneValid = computed(() => phoneNumber.value ? phoneRules.every(rule => rule(phoneNumber.value) === true) : false)
const isLoginFormOtpValid = computed(() => otpCode.value ? otpRules.every(rule => rule(otpCode.value) === true) : false)

const isRegistrationFormValid = computed(() => {
  return (
    regNameRules.every(rule => rule(regName.value) === true)
    && regBlockRules.every(rule => rule(regBlock.value) === true)
    && regKamarRules.every(rule => rule(regKamar.value) === true)
    && regPhoneRules.every(rule => rule(regPhoneNumber.value) === true)
  )
})

// Utility Functions
function getFormattedNumberToSend(num: string): string | null {
  let cleaned = num.replace(/[\s-]/g, '')
  if (cleaned.startsWith('08'))
    cleaned = `+62${cleaned.substring(1)}`
  else if (cleaned.startsWith('628'))
    cleaned = `+${cleaned}`

  return /^\+628[1-9]\d{7,11}$/.test(cleaned) ? cleaned : null
}

const formattedPhoneNumberDisplay = computed(() => {
  let num = phoneNumber.value.replace(/[\s-]/g, '')
  if (num.startsWith('08'))
    num = `+62 ${num.substring(1)}`
  else if (num.startsWith('+628'))
    num = `+62 ${num.substring(3)}`
  else if (num.startsWith('628'))
    num = `+62 ${num.substring(2)}`

  return num || phoneNumber.value
})

async function tryFocus(refInstance: ComponentPublicInstance | null | any, refName: string) {
  await nextTick()
  await new Promise(resolve => setTimeout(resolve, 50))

  if (refInstance) {
    if (refName === 'otpInputRef' && refInstance.focusInput) {
      refInstance.focusInput(0)
      return
    }

    if (typeof refInstance.focus === 'function') {
      refInstance.focus()
    }
    else if (refInstance.$el && typeof refInstance.$el.querySelector === 'function') {
      const inputElement = refInstance.$el.querySelector('input, textarea') as HTMLInputElement | HTMLTextAreaElement | null
      if (inputElement) {
        inputElement.focus()
        if (typeof inputElement.select === 'function') {
          inputElement.select()
        }
      }
    }
  }
}

// Form Handlers
async function handleRequestOtp() {
  const formValidation = await loginFormRef.value?.validate()
  if (!formValidation?.valid || !isLoginFormPhoneValid.value) {
    console.warn('[Login] Validasi form nomor telepon gagal.')
    tryFocus(phoneInputRef.value, 'phoneInputRef')
    return
  }

  const numberToSend = getFormattedNumberToSend(phoneNumber.value)
  if (!numberToSend) {
    authStore.setError('Format nomor telepon tidak valid untuk pengiriman OTP.')
    tryFocus(phoneInputRef.value, 'phoneInputRef')
    return
  }

  const success = await authStore.requestOtp(numberToSend)
  if (success) {
    otpSent.value = true
  }
  else {
    console.error(`[Login] Gagal meminta OTP untuk ${numberToSend}. Error dari store: ${authStore.getError}`)
    tryFocus(phoneInputRef.value, 'phoneInputRef')
  }
}

async function handleVerifyOtp() {
  const formValidation = await loginFormRef.value?.validate()
  if (!formValidation?.valid || !isLoginFormOtpValid.value || otpCode.value.length !== 6) {
    console.warn('[Login] Validasi form OTP gagal atau OTP tidak lengkap.')
    if (otpCode.value.length !== 6 && !authStore.getError) {
      authStore.setError('Kode OTP harus 6 digit.')
    }
    tryFocus(otpInputRef.value, 'otpInputRef')
    return
  }

  const numberToVerify = getFormattedNumberToSend(phoneNumber.value)
  if (!numberToVerify) {
    authStore.setError('Terjadi masalah dengan nomor telepon. Silakan coba lagi dari awal.')
    resetLoginView()
    return
  }

  const loginSuccess = await authStore.verifyOtp(numberToVerify, otpCode.value)
  if (loginSuccess) {
    const redirectPath = route.query.redirect as string | undefined
    let targetPath = '/dashboard'
    if (redirectPath && redirectPath !== '/' && !redirectPath.startsWith('/login')) {
      targetPath = redirectPath
    }
    await router.push(targetPath)
  }
  else {
    console.error(`[Login] Gagal verifikasi OTP untuk ${numberToVerify}. Error dari store: ${authStore.getError}`)
    otpCode.value = ''
    tryFocus(otpInputRef.value, 'otpInputRef')
  }
}

function resetLoginView() {
  otpSent.value = false
  otpCode.value = ''
  authStore.clearError()
  authStore.clearMessage()
  nextTick(async () => {
    await loginFormRef.value?.resetValidation()
  })
}

function showRegistrationForm() {
  currentView.value = 'register'
  authStore.clearError()
  authStore.clearMessage()
  phoneNumber.value = ''
  otpCode.value = ''
  otpSent.value = false
  nextTick(async () => {
    await registrationFormRef.value?.reset()
    await registrationFormRef.value?.resetValidation()
  })
}

function showLoginForm() {
  currentView.value = 'login'
  authStore.clearError()
  authStore.clearMessage()
  regName.value = ''
  regBlock.value = null
  regKamar.value = null
  regPhoneNumber.value = ''
  nextTick(async () => {
    await loginFormRef.value?.resetValidation()
  })
}

async function handleRegister() {
  const formValidation = await registrationFormRef.value?.validate()
  if (!formValidation?.valid || !isRegistrationFormValid.value) {
    console.warn('[Register] Validasi form registrasi gagal.')
    return
  }

  const numberToSend = getFormattedNumberToSend(regPhoneNumber.value)
  if (!numberToSend || !regBlock.value || !regKamar.value) {
    authStore.setError('Data registrasi tidak lengkap atau format nomor telepon salah.')
    return
  }

  const registrationPayload = {
    full_name: regName.value,
    phone_number: numberToSend,
    blok: regBlock.value,
    kamar: regKamar.value,
  }

  const registerSuccess = await authStore.register(registrationPayload)
  if (registerSuccess) {
    currentView.value = 'registerSuccess'
    regName.value = ''
    regBlock.value = null
    regKamar.value = null
    regPhoneNumber.value = ''
    await registrationFormRef.value?.reset()
    await registrationFormRef.value?.resetValidation()
  }
  else {
    console.error(`[Register] Gagal registrasi. Error: ${authStore.getError}`)
  }
}

// Snackbar state
const snackbarVisible = ref(false)
const snackbarText = ref('')
const snackbarColor = ref<'error' | 'success' | 'info'>('info')

// Watchers for auto-focusing inputs
watch([phoneInputRef, () => currentView.value, () => otpSent.value, () => initialLoading.value], ([newRef, view, oSent, iLoading]) => {
  if (newRef && view === 'login' && !oSent && !iLoading) {
    setTimeout(() => tryFocus(newRef, 'phoneInputRef'), 300)
  }
}, { flush: 'post', immediate: false })

watch([otpInputRef, () => currentView.value, () => otpSent.value, () => initialLoading.value], ([newRef, view, oSent, iLoading]) => {
  if (newRef && view === 'login' && oSent && !iLoading) {
    tryFocus(newRef, 'otpInputRef')
  }
}, { flush: 'post', immediate: false })

watch([regNameInputRef, () => currentView.value, () => initialLoading.value], ([newRef, view, iLoading]) => {
  if (newRef && view === 'register' && !iLoading) {
    tryFocus(newRef, 'regNameInputRef')
  }
}, { flush: 'post', immediate: false })

// Lifecycle Hooks
onMounted(() => {
  if (route.query.message === 'account_pending_approval') {
    snackbarText.value = 'Akun Anda sedang menunggu persetujuan Admin. Silakan coba login kembali nanti.'
    snackbarColor.value = 'info'
    snackbarVisible.value = true
    router.replace({ query: {} })
  }
  else if (route.query.error === 'session_expired') {
    snackbarText.value = 'Sesi Anda telah berakhir. Silakan login kembali.'
    snackbarColor.value = 'error'
    snackbarVisible.value = true
    router.replace({ query: {} })
  }

  setTimeout(() => {
    initialLoading.value = false
  }, 100)
})

onUnmounted(() => {
  authStore.clearError()
  authStore.clearMessage()
  snackbarVisible.value = false
})

// Computed properties for UI text
const cardTitle = computed(() => {
  if (currentView.value === 'register')
    return 'Buat Akun Baru'
  if (currentView.value === 'registerSuccess')
    return 'Registrasi Diproses'
  return 'Portal Hotspot'
})

const cardSubtitle = computed(() => {
  if (currentView.value === 'register')
    return 'Lengkapi data diri Anda di bawah ini.'
  if (currentView.value === 'registerSuccess')
    return authStore.getMessage || 'Permintaan registrasi Anda telah berhasil dikirim.'
  return 'Selamat datang! Masuk atau daftar dengan nomor WhatsApp Anda.'
})

// Watchers for Pinia store changes (error/message)
watch([() => authStore.getError, () => authStore.getMessage], ([newError, newMessage], [oldError, oldMessage]) => {
  if (newError && newError !== oldError) {
    snackbarText.value = newError
    snackbarColor.value = 'error'
    snackbarVisible.value = true
  }
  else if (newMessage && newMessage !== oldMessage) {
    snackbarText.value = newMessage
    snackbarColor.value = 'success'
    snackbarVisible.value = true
  }
}, { immediate: false })

function closeSnackbar() {
  snackbarVisible.value = false
}
useHead({ title: 'Login Dan Registrasi' })
</script>

<template>
  <VThemeProvider theme="dark">
    <v-responsive class="fill-height d-flex align-center justify-center pa-0 bg-background">
      <!-- --- PENAMBAHAN BARU --- -->
      <!-- Menempatkan promo di dalam container utama agar responsif -->
      <div class="d-flex flex-column" style="width: 100%; max-width: 480px;">
        <!-- Menampilkan komponen promo di sini -->
        <PromoAnnouncement />

        <v-card
          class="pa-md-8 pa-sm-6 pa-4 mx-auto"
          :rounded="mobile ? 'md' : 'lg'"
          elevation="12"
          width="100%"
          :loading="isSubmitting"
          style="overflow: visible;"
          variant="outlined"
        >
          <v-progress-linear v-if="isSubmitting" indeterminate color="primary" absolute top />

          <ClientOnly>
            <template v-if="initialLoading">
              <div>
                <v-skeleton-loader type="heading" class="mb-2" />
                <v-skeleton-loader type="text" class="mb-8" />
                <v-skeleton-loader type="text" class="skeleton-as-textfield mb-4" />
                <v-skeleton-loader type="button" />
              </div>
            </template>
            <template #fallback>
              <div style="min-height: 380px; display: flex; align-items: center; justify-content: center;">
                <v-progress-circular indeterminate color="primary" size="40" />
              </div>
            </template>
          </ClientOnly>

          <template v-if="!initialLoading">
            <div class="text-center mb-8">
              <h1 :class="mobile ? 'text-h5' : 'text-h4'" class="font-weight-bold text-primary">
                {{ cardTitle }}
              </h1>
              <p class="text-medium-emphasis">
                {{ cardSubtitle }}
              </p>
            </div>

            <v-form v-if="currentView === 'login'" ref="loginFormRef" lazy-validation @submit.prevent="otpSent ? handleVerifyOtp() : handleRequestOtp()">
              <div v-if="!otpSent">
                <AppTextField
                  ref="phoneInputRef"
                  v-model="phoneNumber"
                  label="Nomor WhatsApp"
                  placeholder="Contoh: 081234567890"
                  prepend-inner-icon="mdi-whatsapp"
                  variant="outlined"
                  density="comfortable"
                  color="primary"
                  :rules="phoneRules"
                  :disabled="isSubmitting"
                  autocomplete="tel"
                  class="mb-4"
                  required
                />
                <v-btn
                  type="submit"
                  color="primary"
                  block
                  :size="mobile ? 'default' : 'large'"
                  class="mb-2"
                  :loading="isSubmitting"
                  :disabled="!isLoginFormPhoneValid || isSubmitting"
                >
                  Kirim Kode OTP
                </v-btn>
              </div>
              <div v-else>
                <p class="text-body-1 mb-2 font-weight-medium">
                  Verifikasi OTP
                </p>
                <p class="text-body-2 mb-4">
                  Kode OTP telah dikirim ke nomor WhatsApp
                  <strong class="text-primary">{{ formattedPhoneNumberDisplay }}</strong>.
                  Masukkan 6 digit kode.
                </p>
                <v-otp-input
                  ref="otpInputRef"
                  v-model="otpCode"
                  :length="6"
                  variant="underlined"
                  placeholder="-"
                  label="Masukkan Kode OTP"
                  :loading="isSubmitting"
                  :disabled="isSubmitting"
                  class="mb-4"
                  autocomplete="one-time-code"
                  required
                  :rules="otpRules"
                  @finish="handleVerifyOtp"
                />
                <v-btn
                  type="submit"
                  color="primary"
                  block
                  :size="mobile ? 'default' : 'large'"
                  class="mb-2"
                  :loading="isSubmitting"
                  :disabled="!isLoginFormOtpValid || isSubmitting || otpCode.length !== 6"
                >
                  Verifikasi & Masuk
                </v-btn>
                <v-btn
                  variant="text"
                  block
                  size="small"
                  :disabled="isSubmitting"
                  class="text-caption text-medium-emphasis"
                  prepend-icon="mdi-arrow-left"
                  @click="resetLoginView"
                >
                  Ganti Nomor Telepon
                </v-btn>
              </div>
              <div class="text-center mt-6">
                <span class="text-body-2 text-medium-emphasis">Belum punya akun?</span>
                <v-btn
                  variant="text"
                  color="primary"
                  size="small"
                  class="ms-1 text-body-2"
                  :disabled="isSubmitting"
                  @click="showRegistrationForm"
                >
                  Registrasi di sini
                </v-btn>
              </div>
            </v-form>

            <v-form v-else-if="currentView === 'register'" ref="registrationFormRef" lazy-validation @submit.prevent="handleRegister">
              <AppTextField
                ref="regNameInputRef"
                v-model="regName"
                label="Nama Lengkap"
                placeholder="Masukkan nama lengkap Anda"
                prepend-inner-icon="mdi-account-outline"
                variant="outlined"
                density="comfortable"
                color="primary"
                :rules="regNameRules"
                :disabled="isSubmitting"
                class="mb-4"
                required
              />
              <AppSelect
                v-model="regBlock"
                :items="blockOptions"
                item-title="title"
                item-value="value"
                label="Blok Tempat Tinggal"
                placeholder="Pilih blok tempat tinggal Anda"
                prepend-inner-icon="mdi-map-marker-outline"
                variant="outlined"
                density="comfortable"
                color="primary"
                :rules="regBlockRules"
                :disabled="isSubmitting"
                class="mb-4"
                required
                clearable
              />
              <AppSelect
                v-model="regKamar"
                :items="kamarOptions"
                item-title="title"
                item-value="value"
                label="Nomor Kamar"
                placeholder="Pilih nomor kamar Anda"
                prepend-inner-icon="mdi-door-closed"
                variant="outlined"
                density="comfortable"
                color="primary"
                :rules="regKamarRules"
                :disabled="isSubmitting"
                class="mb-4"
                required
                clearable
              />
              <AppTextField
                v-model="regPhoneNumber"
                label="Nomor WhatsApp Aktif"
                placeholder="Contoh: 081234567890"
                prepend-inner-icon="mdi-whatsapp"
                variant="outlined"
                density="comfortable"
                color="primary"
                :rules="regPhoneRules"
                :disabled="isSubmitting"
                autocomplete="tel"
                class="mb-4"
                required
              />
              <v-btn
                type="submit"
                color="primary"
                block
                :size="mobile ? 'default' : 'large'"
                class="mb-2"
                :loading="isSubmitting"
                :disabled="!isRegistrationFormValid || isSubmitting"
              >
                Daftar Akun
              </v-btn>
              <div class="text-center mt-6">
                <span class="text-body-2 text-medium-emphasis">Sudah punya akun?</span>
                <v-btn
                  variant="text"
                  color="primary"
                  size="small"
                  class="ms-1 text-body-2"
                  :disabled="isSubmitting"
                  @click="showLoginForm"
                >
                  Masuk di sini
                </v-btn>
              </div>
            </v-form>

            <div v-else-if="currentView === 'registerSuccess'" class="text-center">
              <v-icon :size="mobile ? 56 : 64" color="success" class="d-block mx-auto mb-4">
                mdi-check-decagram-outline
              </v-icon>
              <h2 class="text-h5 font-weight-medium mb-2">
                Registrasi Diproses
              </h2>
              <p class="text-body-1 text-medium-emphasis mb-4">
                {{ authStore.getMessage || 'Permintaan registrasi Anda telah berhasil dikirim.' }}
              </p>
              <p class="text-body-2 text-medium-emphasis mb-6">
                Akun Anda sedang menunggu persetujuan Admin. Anda akan menerima notifikasi melalui WhatsApp jika akun Anda telah disetujui dan diaktifkan.
              </p>
              <v-btn color="primary" variant="tonal" block :size="mobile ? 'default' : 'large'" @click="showLoginForm">
                Kembali ke Halaman Login
              </v-btn>
            </div>
          </template>
        </v-card>
      </div>

      <div class="text-center text-caption mt-8 page-footer">
        &copy; {{ new Date().getFullYear() }} Babah Digital. Semua Hak Cipta Dilindungi.
      </div>

      <v-snackbar
        v-model="snackbarVisible"
        :color="snackbarColor"
        location="bottom center"
        variant="elevated"
        :timeout="snackbarColor === 'error' ? 7000 : 5000"
        multi-line
        @update:model-value="(value) => { if (!value) { if (snackbarColor === 'error' && authStore.getError) authStore.clearError(); else if (snackbarColor !== 'error' && authStore.getMessage) authStore.clearMessage(); } }"
      >
        {{ snackbarText }}
        <template #actions>
          <v-btn icon="mdi-close" variant="text" @click="closeSnackbar" />
        </template>
      </v-snackbar>
    </v-responsive>
  </VThemeProvider>
</template>

<style scoped>
.v-otp-input :deep(input) {
  font-size: 1.5rem !important; text-align: center !important;
  min-width: 38px !important; max-width: 48px !important;
  margin: 0 3px !important; height: 50px !important;
  border-radius: 6px;
}
.v-otp-input--underlined :deep(.v-field__field) { padding-bottom: 0 !important; }
.v-otp-input :deep(input:focus) {
  border-color: rgb(var(--v-theme-primary)) !important;
  box-shadow: 0 0 0 2px rgba(var(--v-theme-primary), 0.2) !important;
}

.v-card { transition: box-shadow 0.3s ease-in-out, border-color 0.3s ease-in-out; }
.v-card--variant-outlined {
    border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}

.v-btn.text-body-2 {
  text-transform: none;
  letter-spacing: normal;
  padding: 0 4px;
  height: auto !important;
  font-weight: 500;
}

.page-footer {
  position: absolute;
  bottom: 20px;
  left: 0;
  right: 0;
  width: 100%;
  text-align: center;
  color: rgba(var(--v-theme-on-surface), var(--v-disabled-opacity));
}

.v-snackbar :deep(.v-snackbar__content) {
  text-align: center;
}

/* Penyesuaian skeleton loader */
.v-skeleton-loader--type-heading .v-skeleton-loader__heading {
  height: 32px;
  width: 60%;
  margin: 0 auto 16px auto;
}
.v-skeleton-loader--type-text .v-skeleton-loader__text {
  height: 20px;
  width: 80%;
  margin: 0 auto 32px auto; /* Margin bawah disesuaikan dengan mb-8 pada elemen subtitle */
}

/* Style untuk v-skeleton-loader yang merepresentasikan text field */
.v-skeleton-loader.skeleton-as-textfield :deep(.v-skeleton-loader__text) {
  height: 56px !important; /* Sesuaikan dengan tinggi AppTextField density="comfortable" */
  width: 100%; /* Agar mengisi lebar seperti text field */
  margin: 0 auto; /* Hapus margin default jika ada, mb-4 sudah di elemen */
}

.v-skeleton-loader--type-button .v-skeleton-loader__button {
  height: 44px;
  margin-bottom: 24px;
}

/* Penyesuaian untuk layar kecil (mobile) */
@media (max-width: 600px) { /* Vuetify xs breakpoint */
  .v-otp-input :deep(input) {
    font-size: 1.25rem !important;
    height: 44px !important;
    min-width: 32px !important;
    max-width: 40px !important;
  }

  .page-footer {
    bottom: 10px;
    font-size: 0.75rem;
  }

  .v-skeleton-loader--type-heading .v-skeleton-loader__heading {
    height: 28px; /* Sedikit lebih kecil untuk text-h5 */
  }
 .v-skeleton-loader.skeleton-as-textfield :deep(.v-skeleton-loader__text) {
    height: 52px !important; /* Sedikit disesuaikan jika density input berubah di mobile */
  }
  .v-skeleton-loader--type-button .v-skeleton-loader__button {
    height: 40px; /* Sesuai v-btn size default */
  }
}
</style>