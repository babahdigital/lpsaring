<script setup lang="ts">
import type { VForm, VOtpInput } from 'vuetify/components'

import authV1BottomShape from '@images/svg/auth-v1-bottom-shape.svg?raw'
import authV1TopShape from '@images/svg/auth-v1-top-shape.svg?raw'
import { VNodeRenderer } from '@layouts/components/VNodeRenderer'
import { themeConfig } from '@themeConfig'
import { navigateTo, useNuxtApp } from 'nuxt/app'
import { computed, h, nextTick, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useDisplay } from 'vuetify'

import type { VerifyOtpPayload } from '~/types/auth'

import { useClientDetection } from '~/composables/useClientDetection'
import { useSnackbar } from '~/composables/useSnackbar'
import { useAuthStore } from '~/store/auth'
import { normalize_to_e164 } from '~/utils/formatters'

definePageMeta({
  layout: 'blank',
  middleware: 'captive-portal',
})

const authStore = useAuthStore()
const _route = useRoute()
const { $api } = useNuxtApp()
const { smAndUp } = useDisplay()
const { add: addSnackbar } = useSnackbar()

const { forceDetection, clientInfo, isLoading: _isDetecting, needsManualDetection, isClientInCaptivePortal } = useClientDetection()

useHead({ title: 'Portal Hotspot Sobigidul' })

const isDetectionComplete = ref(false)

onMounted(async () => {
  if (import.meta.client) {
    try {
      const result = await forceDetection()

      if (result?.summary) {
        isDetectionComplete.value = true

        if (result.summary.user_guidance && !result.summary.mac_detected) {
          addSnackbar({
            title: 'Info Deteksi',
            text: result.summary.user_guidance,
            color: 'info',
            timeout: 5000,
          })
        }
      }
    }
    catch (_error) {
      // Silent error handling for production
    }
    finally {
      isDetectionComplete.value = true
    }
  }
})

const currentTab = ref<'login' | 'register'>('login')
const viewState = ref<'form' | 'success'>('form')
const loginFormRef = ref<InstanceType<typeof VForm> | null>(null)
const otpSent = ref(false)
const phoneNumber = ref('')
const otpCode = ref('')
const otpInputRef = ref<InstanceType<typeof VOtpInput> | null>(null)
const registerFormRef = ref<InstanceType<typeof VForm> | null>(null)
const regName = ref('')
const regPhoneNumber = ref('')
const regRole = ref<'USER' | 'KOMANDAN'>('USER')
const regBlock = ref<string | null>(null)
const regKamar = ref<string | null>(null)

const isSubmitting = computed(() => authStore.loading)
const showAddressFields = computed(() => regRole.value === 'USER')
const formattedPhoneNumberDisplay = computed(() => {
  let num = phoneNumber.value.replace(/[\s-]/g, '')
  if (num.startsWith('08'))
    num = `+62 ${num.substring(1)}`
  return num || phoneNumber.value
})

const blockOptions = Array.from({ length: 6 }, (_, i) => ({
  title: `Blok ${String.fromCharCode(65 + i)}`,
  value: String.fromCharCode(65 + i),
}))
const kamarOptions = Array.from({ length: 6 }, (_, i) => ({
  title: `Kamar ${i + 1}`,
  value: (i + 1).toString(),
}))

const phoneFormatRules = [
  (v: string) => {
    if (!v)
      return 'Nomor telepon wajib diisi.'
    const phoneRegex = /^08[1-9]\d{7,10}$/
    if (!phoneRegex.test(v))
      return 'Format nomor salah. Contoh: 08123456789 (10-13 digit).'
    return true
  },
]

const requiredRule = (v: any) => !!v || 'Wajib diisi.'

let validationTimeout: NodeJS.Timeout | null = null

function loginPhoneValidationRule(v: string) {
  const isFormatBasicallyCorrect = phoneFormatRules.every(rule => rule(v) === true)
  if (!isFormatBasicallyCorrect)
    return true

  return new Promise<boolean | string>((resolve) => {
    if (validationTimeout)
      clearTimeout(validationTimeout)

    validationTimeout = setTimeout(async () => {
      try {
        const response = await $api<any>('/users/check-or-register', {
          method: 'POST',
          body: { phone_number: normalize_to_e164(v) },
        })
        if (response.user_exists) {
          resolve(true)
        }
        else {
          resolve('Nomor Anda belum terdaftar. Silakan daftar terlebih dahulu.')
        }
      }
      catch (error: any) {
        const errorMsg = error.data?.message || 'Gagal memvalidasi nomor.'
        resolve(errorMsg)
      }
    }, 800)
  })
}

function registerPhoneValidationRule(v: string) {
  const isFormatBasicallyCorrect = phoneFormatRules.every(rule => rule(v) === true)
  if (!isFormatBasicallyCorrect)
    return true

  return new Promise<boolean | string>((resolve) => {
    if (validationTimeout)
      clearTimeout(validationTimeout)

    validationTimeout = setTimeout(async () => {
      try {
        const response = await $api('/users/validate-whatsapp', {
          method: 'POST',
          body: { phone_number: normalize_to_e164(v) },
        })

        if (response.isValid) {
          resolve(true)
        }
        else {
          const errorMsg = response.message || 'Nomor WhatsApp tidak valid atau sudah terdaftar.'
          resolve(errorMsg)
        }
      }
      catch (error: any) {
        const errorMsg = error.data?.message || 'Gagal memvalidasi nomor.'
        resolve(errorMsg)
      }
    }, 800)
  })
}

async function tryFocus(refInstance: { focus?: () => void } | null) {
  await nextTick()
  refInstance?.focus?.()
}

async function handleRequestOtp() {
  if (!loginFormRef.value)
    return

  const { valid } = await loginFormRef.value.validate()
  if (!valid)
    return

  try {
    const numberToSend = normalize_to_e164(phoneNumber.value)
    const success = await authStore.requestOtp(numberToSend)

    if (success) {
      otpSent.value = true
      await tryFocus(otpInputRef.value)
      addSnackbar({
        title: 'OTP Terkirim',
        text: `Kode OTP telah dikirim ke ${formattedPhoneNumberDisplay.value}`,
        type: 'success',
      })
    }
  }
  catch (error: any) {
    const errorMessage = error.message || 'Gagal mengirim kode OTP. Periksa nomor telepon Anda.'
    addSnackbar({
      title: 'Gagal Mengirim OTP',
      text: errorMessage,
      type: 'error',
    })
  }
}

async function handleVerifyOtp() {
  if (otpCode.value.length !== 6 || isSubmitting.value)
    return

  try {
    const numberToVerify = normalize_to_e164(phoneNumber.value)
    const payload: VerifyOtpPayload = {
      phone_number: numberToVerify,
      otp: otpCode.value,
      client_ip: authStore.clientIp,
      client_mac: authStore.clientMac,
    }

    const otpSuccess = await authStore.verifyOtp(payload)

    if (!otpSuccess) {
      otpCode.value = ''
      await tryFocus(otpInputRef.value)
      return
    }

    await authStore.initializeAuth(true)

    if (authStore.isAdmin) {
      navigateTo('/admin/dashboard', { replace: true })
    }
    else {
      navigateTo('/dashboard', { replace: true })
    }

    addSnackbar({
      title: 'Login Berhasil',
      text: 'Selamat datang di Portal Hotspot!',
      type: 'success',
    })
  }
  catch (error: any) {
    const errorMessage = error.message || 'Gagal memverifikasi OTP.'
    addSnackbar({
      title: 'Verifikasi Gagal',
      text: errorMessage,
      type: 'error',
    })
    otpCode.value = ''
    await tryFocus(otpInputRef.value)
  }
}

async function handleRegister() {
  if (!registerFormRef.value)
    return

  const { valid } = await registerFormRef.value.validate()
  if (!valid) {
    addSnackbar({
      title: 'Validasi Gagal',
      text: 'Silakan periksa kembali semua data yang wajib diisi, termasuk memastikan nomor WhatsApp valid.',
      type: 'warning',
    })
    return
  }

  try {
    const registrationPayload = {
      full_name: regName.value,
      phone_number: normalize_to_e164(regPhoneNumber.value),
      blok: showAddressFields.value ? regBlock.value : null,
      kamar: showAddressFields.value ? regKamar.value : null,
      register_as_komandan: regRole.value === 'KOMANDAN',
    }

    const registerSuccess = await authStore.registerUser(registrationPayload)

    if (registerSuccess) {
      viewState.value = 'success'
      addSnackbar({
        title: 'Registrasi Berhasil',
        text: 'Akun Anda sedang menunggu persetujuan admin.',
        type: 'success',
      })
    }
  }
  catch (error: any) {
    const errorMessage = error.message || 'Gagal melakukan registrasi.'
    addSnackbar({
      title: 'Registrasi Gagal',
      text: errorMessage,
      type: 'error',
    })
  }
}

function resetLoginView() {
  otpSent.value = false
  phoneNumber.value = ''
  otpCode.value = ''
  authStore.clearError()
  authStore.clearMessage()
  loginFormRef.value?.resetValidation()
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
  registerFormRef.value?.reset()
}

watch(() => authStore.error, (newError) => {
  if (newError) {
    addSnackbar({
      title: 'Terjadi Kesalahan',
      text: newError,
      type: 'error',
    })
    authStore.clearError()
  }
})

watch(() => authStore.message, (newMessage) => {
  if (newMessage) {
    addSnackbar({
      title: 'Informasi',
      text: newMessage,
      type: 'success',
    })
    authStore.clearMessage()
  }
})

watch(regRole, () => {
  registerFormRef.value?.resetValidation()
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
        :class="smAndUp ? 'pa-6' : 'pa-0'"
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

        <!-- PERBAIKAN: Pindahkan VTabs ke sini, di luar VCardText -->
        <VTabs
          v-if="viewState === 'form'"
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

        <VCardText>
          <div v-if="viewState === 'form'">
            <VWindow
              v-model="currentTab"
              :touch="false"
            >
              <!-- Form Login -->
              <VWindowItem value="login">
                <h4 class="text-h4 mb-1">
                  Selamat Datang! 👋🏻
                </h4>
                <p class="mb-6">
                  Silakan masuk dengan nomor WhatsApp Anda untuk mengakses portal hotspot.
                </p>

                <VAlert
                  v-if="clientInfo && needsManualDetection"
                  color="info"
                  variant="tonal"
                  class="mb-4"
                >
                  <VAlertTitle>
                    <VIcon
                      icon="tabler-info-circle"
                      class="me-2"
                    />
                    Deteksi Perangkat
                  </VAlertTitle>
                  <span class="text-caption">
                    {{ isClientInCaptivePortal ? 'Mode captive portal aktif' : 'Login manual - perangkat akan dideteksi otomatis' }}
                  </span>
                </VAlert>

                <VForm
                  ref="loginFormRef"
                  lazy-validation
                  @submit.prevent="otpSent ? handleVerifyOtp() : handleRequestOtp()"
                >
                  <VRow>
                    <VCol
                      v-if="!otpSent"
                      cols="12"
                    >
                      <AppTextField
                        v-model="phoneNumber"
                        autofocus
                        label="Nomor WhatsApp"
                        placeholder="Contoh: 081234567890"
                        prepend-inner-icon="tabler-device-mobile"
                        :rules="[...phoneFormatRules, loginPhoneValidationRule]"
                        :disabled="isSubmitting"
                        counter="13"
                        maxlength="13"
                        validate-on="input"
                        hint="Masukkan nomor WhatsApp yang sudah terdaftar"
                        persistent-hint
                      />
                      <VBtn
                        class="mt-4"
                        block
                        type="submit"
                        color="primary"
                        size="large"
                        :loading="isSubmitting"
                        :disabled="!phoneNumber || phoneNumber.length < 10"
                      >
                        <VIcon
                          icon="tabler-send"
                          class="me-2"
                        />
                        Kirim Kode OTP
                      </VBtn>
                    </VCol>

                    <VCol
                      v-else
                      cols="12"
                    >
                      <p class="mb-2 text-center">
                        Masukkan 6 digit kode OTP yang dikirim ke <br />
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
                        color="primary"
                        size="large"
                        :loading="isSubmitting"
                        :disabled="isSubmitting || otpCode.length !== 6"
                      >
                        <VIcon
                          icon="tabler-check"
                          class="me-2"
                        />
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
                        <VIcon
                          icon="tabler-arrow-left"
                          class="me-2"
                        />
                        Ganti Nomor
                      </VBtn>
                    </VCol>
                  </VRow>
                </VForm>
              </VWindowItem>

              <!-- Form Registrasi -->
              <VWindowItem value="register">
                <h4 class="text-h4 mb-1">
                  Ayo, Daftar Akun. 🚀
                </h4>
                <p class="mb-6">
                  Lengkapi data untuk membuat akun baru di portal hotspot Sobigidul.
                </p>

                <VForm
                  ref="registerFormRef"
                  lazy-validation
                  @submit.prevent="handleRegister"
                >
                  <VRow>
                    <VCol cols="12">
                      <p class="text-base font-weight-medium mb-2">
                        Saya mendaftar sebagai:
                      </p>
                      <VRadioGroup
                        v-model="regRole"
                        inline
                        class="mb-2"
                        :disabled="isSubmitting"
                      >
                        <VRadio
                          label="Pengguna Biasa"
                          value="USER"
                        />
                        <VRadio
                          label="Komandan"
                          value="KOMANDAN"
                        />
                      </VRadioGroup>
                    </VCol>

                    <VCol cols="12">
                      <AppTextField
                        v-model="regName"
                        label="Nama Lengkap"
                        placeholder="Contoh: Budi Santoso"
                        prepend-inner-icon="tabler-user"
                        :rules="[requiredRule]"
                        :disabled="isSubmitting"
                        hint="Nama sesuai dengan identitas resmi"
                        persistent-hint
                      />
                    </VCol>

                    <VCol
                      v-if="showAddressFields"
                      cols="12"
                      sm="6"
                    >
                      <AppSelect
                        v-model="regBlock"
                        :items="blockOptions"
                        label="Blok Tempat Tinggal"
                        placeholder="Pilih Blok"
                        prepend-inner-icon="tabler-map-pin"
                        :rules="[requiredRule]"
                        :disabled="isSubmitting"
                      />
                    </VCol>

                    <VCol
                      v-if="showAddressFields"
                      cols="12"
                      sm="6"
                    >
                      <AppSelect
                        v-model="regKamar"
                        :items="kamarOptions"
                        label="Nomor Kamar"
                        placeholder="Pilih Nomor"
                        prepend-inner-icon="tabler-door"
                        :rules="[requiredRule]"
                        :disabled="isSubmitting"
                      />
                    </VCol>

                    <VCol cols="12">
                      <AppTextField
                        v-model="regPhoneNumber"
                        label="Nomor WhatsApp Aktif"
                        placeholder="Contoh: 081234567890"
                        prepend-inner-icon="tabler-brand-whatsapp"
                        :rules="[...phoneFormatRules, registerPhoneValidationRule]"
                        :disabled="isSubmitting"
                        validate-on="input"
                        counter="13"
                        maxlength="13"
                        hint="Pastikan nomor WhatsApp aktif dan dapat menerima pesan"
                        persistent-hint
                      />
                    </VCol>

                    <VCol cols="12">
                      <VBtn
                        class="mt-2"
                        block
                        type="submit"
                        color="primary"
                        size="large"
                        :loading="isSubmitting"
                      >
                        <VIcon
                          icon="tabler-user-plus"
                          class="me-2"
                        />
                        Daftar Akun
                      </VBtn>
                    </VCol>
                  </VRow>
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
              Pendaftaran Berhasil! 🎉
            </h4>
            <p class="mb-6">
              Terima kasih telah mendaftar! Akun Anda sedang menunggu persetujuan Admin.
              Konfirmasi pendaftaran telah dikirim melalui WhatsApp.
            </p>
            <VAlert
              color="info"
              variant="tonal"
              class="mb-6"
            >
              <VAlertTitle>
                <VIcon
                  icon="tabler-info-circle"
                  class="me-2"
                />
                Langkah Selanjutnya
              </VAlertTitle>
              <ul class="mt-2">
                <li>Admin akan memverifikasi data Anda</li>
                <li>Proses verifikasi biasanya 1-2 hari kerja</li>
                <li>Anda akan menerima notifikasi WhatsApp</li>
                <li>Setelah disetujui, Anda dapat login dengan nomor WhatsApp</li>
              </ul>
            </VAlert>
            <VBtn
              block
              variant="outlined"
              color="primary"
              @click="backToForms"
            >
              <VIcon
                icon="tabler-arrow-left"
                class="me-2"
              />
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

.auth-card {
  position: relative;
  z-index: 1;
}

.app-logo {
  display: flex;
  align-items: center;
  gap: 0.75rem;

  .app-logo-title {
    font-size: 1.375rem;
    font-weight: 700;
    line-height: 1.375rem;
    color: rgb(var(--v-theme-primary));
  }
}

.v-text-field .v-messages {
  font-size: 0.75rem;
  opacity: 0.7;
}

@media (max-width: 600px) {
  .auth-wrapper {
    padding: 1rem;
  }

  .auth-card {
    margin: 0;
  }
}
</style>
