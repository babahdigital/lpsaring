<script setup lang="ts">
import type { VForm } from 'vuetify/components'
import type { VOtpInput } from 'vuetify/labs/VOtpInput'
import authV1BottomShape from '@images/svg/auth-v1-bottom-shape.svg?raw'

import authV1TopShape from '@images/svg/auth-v1-top-shape.svg?raw'
import { VNodeRenderer } from '@layouts/components/VNodeRenderer'
import { themeConfig } from '@themeConfig'

import { computed, h, nextTick, ref, watch } from 'vue'
import { useSnackbar } from '~/composables/useSnackbar'
import { useAuthStore } from '~/store/auth'
import { normalize_to_e164 } from '~/utils/formatters'

definePageMeta({
  layout: 'blank',
})

const authStore = useAuthStore()
const { add: addSnackbar } = useSnackbar()
useHead({ title: 'Portal Hotspot' })

// --- State untuk UI dan Tab ---
const currentTab = ref<'login' | 'register'>('login')
const viewState = ref<'form' | 'success'>('form')

// --- State untuk Form Login ---
const loginFormRef = ref<InstanceType<typeof VForm> | null>(null)
const otpSent = ref(false)
const phoneNumber = ref('')
const otpCode = ref('')
const otpInputRef = ref<InstanceType<typeof VOtpInput> | null>(null)

// --- State untuk Form Register ---
const registerFormRef = ref<InstanceType<typeof VForm> | null>(null)
const regName = ref('')
const regPhoneNumber = ref('')
const regRole = ref<'USER' | 'KOMANDAN'>('USER')
const regBlock = ref<string | null>(null)
const regKamar = ref<string | null>(null)

// --- Computed Properties ---
const isSubmitting = computed(() => authStore.loading)
const showAddressFields = computed(() => regRole.value === 'USER')
const formattedPhoneNumberDisplay = computed(() => {
  let num = phoneNumber.value.replace(/[\s-]/g, '')
  if (num.startsWith('08'))
    num = `+62 ${num.substring(1)}`

  return num || phoneNumber.value
})

// --- Opsi untuk Select Input ---
const blockOptions = Array.from({ length: 6 }, (_, i) => ({ title: `Blok ${String.fromCharCode(65 + i)}`, value: String.fromCharCode(65 + i) }))
const kamarOptions = Array.from({ length: 6 }, (_, i) => ({ title: `Kamar ${i + 1}`, value: (i + 1).toString() }))

// --- Aturan Validasi ---
const phoneFormatRules = [
  (v: string) => {
    if (!v)
      return 'Nomor telepon wajib diisi.'

    // ATURAN BARU YANG KETAT:
    // 1. Harus diawali '08'
    // 2. Diikuti oleh 8-10 digit angka (total 10-12 digit)
    // 3. Tidak boleh ada karakter selain angka.
    const phoneRegex = /^08[1-9]\d{7,9}$/

    if (!phoneRegex.test(v)) {
      return 'Format nomor salah. Contoh: 08123456789 (10-12 digit).'
    }

    return true
  },
]
const requiredRule = (v: any) => (v !== null && v !== undefined && v !== '') || 'Wajib diisi.'

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
        const response = await $fetch('/api/users/validate-whatsapp', {
          method: 'POST',
          body: { phone_number: v },
          timeout: 3000 // 3 detik timeout
        })

        if (response.isValid === true) {
          resolve(true)
        } else {
          let errorMsg = 'Nomor WhatsApp tidak valid'

          // Berikan pesan lebih spesifik
          if (response.message.includes('terdaftar')) {
            errorMsg = 'Nomor sudah terdaftar di sistem'
          } else if (response.message.includes('aktif')) {
            errorMsg = 'Nomor tidak aktif di WhatsApp'
          } else if (response.message.includes('timeout')) {
            errorMsg = 'Validasi timeout, coba lagi'
          }

          resolve(errorMsg)
        }
      } catch (error: any) {
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
    const numberToVerify = normalize_to_e164(phoneNumber.value)
    const loginSuccess = await authStore.verifyOtp(numberToVerify, otpCode.value)
    if (loginSuccess !== true) {
      otpCode.value = ''
      tryFocus(otpInputRef.value)
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
        :class="$vuetify.display.smAndUp ? 'pa-6' : 'pa-0'"
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
                <p class="mb-6">
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
                      :disabled="isSubmitting || otpCode.length !== 6"
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
              </VWindowItem>

              <VWindowItem value="register">
                <h4 class="text-h4 mb-1">
                  Ayo, Daftar Akun. 🚀
                </h4>
                <p class="mb-6">
                  Lengkapi data untuk membuat akun baru.
                </p>
                <VForm
                  ref="registerFormRef"
                  lazy-validation
                  @submit.prevent="handleRegister"
                >
                  <VRadioGroup
                    v-model="regRole"
                    inline
                    label="Saya mendaftar sebagai:"
                    class="mb-4"
                    :disabled="isSubmitting"
                  >
                    <VRadio
                      label="User"
                      value="USER"
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
            <p class="mb-6">
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
</style>
