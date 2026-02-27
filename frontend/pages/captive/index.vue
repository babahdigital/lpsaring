<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { useAuthStore } from '~/store/auth'
import { TAMPING_OPTION_ITEMS } from '~/utils/constants'
import { normalize_to_e164 } from '~/utils/formatters'

definePageMeta({
  layout: 'blank',
  auth: false,
  public: true,
})

useHead({ title: 'Login Hotspot Captive' })

const authStore = useAuthStore()
const route = useRoute()
const runtimeConfig = useRuntimeConfig()

const mode = ref<'login' | 'register'>('login')
const phoneNumber = ref('')
const otpCode = ref('')
const step = ref<'phone' | 'otp'>('phone')
const regName = ref('')
const regPhoneNumber = ref('')
const regRole = ref<'USER' | 'KOMANDAN' | 'TAMPING'>('USER')
const regBlock = ref('')
const regKamar = ref('')
const regTampingType = ref('')
const registerSuccess = ref(false)
const localError = ref<string | null>(null)
const localInfo = ref<string | null>(null)
const apiStatus = ref<'ok' | 'down'>('ok')

const portalParams = ref({
  linkLoginOnly: '',
  clientMac: '',
  clientIp: '',
})

const isSubmitting = computed(() => authStore.loading)
const hasClientIdentity = computed(() => Boolean(portalParams.value.clientIp && portalParams.value.clientMac))
const showAddressFields = computed(() => regRole.value === 'USER')
const showTampingFields = computed(() => regRole.value === 'TAMPING')
const appLandingUrl = computed(() => {
  const appBase = String(runtimeConfig.public.appBaseUrl ?? '').trim()
  if (appBase)
    return appBase
  return 'https://lpsaring.babahdigital.net'
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
    clientMac: getQueryValueFromKeys(['client_mac', 'mac']),
    clientIp: getQueryValueFromKeys(['client_ip', 'ip']),
  }
}

async function refreshApiHealth() {
  try {
    await $fetch('/health', { baseURL: '/api' })
    apiStatus.value = 'ok'
  }
  catch {
    apiStatus.value = 'down'
  }
}

function clearMessages() {
  localError.value = null
  localInfo.value = null
  authStore.clearError()
  authStore.clearMessage()
}

function switchMode(nextMode: 'login' | 'register') {
  mode.value = nextMode
  localError.value = null
  localInfo.value = null
  if (nextMode === 'register')
    registerSuccess.value = false
}

function openPortalMain() {
  if (!import.meta.client)
    return
  window.location.href = appLandingUrl.value
}

function closeWindowOrRedirect() {
  if (!import.meta.client)
    return
  window.close()
  setTimeout(() => {
    window.location.href = appLandingUrl.value
  }, 400)
}

async function requestOtp() {
  clearMessages()
  let numberToSend = ''
  try {
    numberToSend = normalize_to_e164(phoneNumber.value)
  }
  catch (error: any) {
    localError.value = error instanceof Error && error.message ? error.message : 'Format nomor telepon tidak valid.'
    return
  }

  const ok = await authStore.requestOtp(numberToSend)
  if (!ok) {
    localError.value = authStore.error || 'Gagal meminta OTP.'
    return
  }

  localInfo.value = `Kode OTP sudah dikirim ke ${numberToSend}.`
  step.value = 'otp'
}

async function registerUser() {
  clearMessages()

  const trimmedName = regName.value.trim()
  const trimmedBlock = regBlock.value.trim()
  const trimmedKamar = regKamar.value.trim()
  const trimmedTampingType = regTampingType.value.trim()
  if (!trimmedName) {
    localError.value = 'Nama wajib diisi.'
    return
  }

  if (showAddressFields.value && (!trimmedBlock || !trimmedKamar)) {
    localError.value = 'Untuk USER, blok dan kamar wajib diisi.'
    return
  }

  if (showTampingFields.value && !trimmedTampingType) {
    localError.value = 'Untuk TAMPING, jenis tamping wajib dipilih.'
    return
  }

  let numberToRegister = ''
  try {
    numberToRegister = normalize_to_e164(regPhoneNumber.value)
  }
  catch (error: any) {
    localError.value = error instanceof Error && error.message ? error.message : 'Format nomor telepon tidak valid.'
    return
  }

  const ok = await authStore.register({
    full_name: trimmedName,
    phone_number: numberToRegister,
    blok: showAddressFields.value ? trimmedBlock : null,
    kamar: showAddressFields.value ? trimmedKamar : null,
    is_tamping: regRole.value === 'TAMPING',
    tamping_type: showTampingFields.value ? trimmedTampingType : null,
    register_as_komandan: regRole.value === 'KOMANDAN',
  } as any)

  if (!ok) {
    localError.value = authStore.error || 'Registrasi gagal.'
    return
  }

  localInfo.value = authStore.message || 'Pendaftaran berhasil. Silakan lanjut login OTP atau tutup halaman.'
  phoneNumber.value = regPhoneNumber.value
  otpCode.value = ''
  step.value = 'phone'
  registerSuccess.value = true
}

async function verifyOtp() {
  clearMessages()

  const otpDigitsOnly = String(otpCode.value ?? '').replace(/\D/g, '')
  const otpToSend = otpDigitsOnly.length >= 6 ? otpDigitsOnly.slice(-6) : otpDigitsOnly
  if (otpToSend.length !== 6) {
    localError.value = 'Kode OTP harus 6 digit.'
    return
  }

  let numberToVerify = ''
  try {
    numberToVerify = normalize_to_e164(phoneNumber.value)
  }
  catch (error: any) {
    localError.value = error instanceof Error && error.message ? error.message : 'Format nomor telepon tidak valid.'
    return
  }

  const result = await authStore.verifyOtpForCaptive(numberToVerify, otpToSend, {
    clientIp: portalParams.value.clientIp,
    clientMac: portalParams.value.clientMac,
    hotspotLoginContext: true,
  })

  if (result.response == null) {
    const statusRedirectPath = authStore.getStatusRedirectPath('captive')
    if (statusRedirectPath) {
      await navigateTo(statusRedirectPath, { replace: true })
      return
    }

    const errorText = result.errorMessage || authStore.error || ''
    if (errorText.includes('Perangkat belum diotorisasi')) {
      await navigateTo('/captive/otorisasi-perangkat', { replace: true })
      return
    }

    if (errorText.includes('Limit perangkat tercapai')) {
      const blockedPath = authStore.getRedirectPathForStatus('blocked', 'captive')
      if (blockedPath) {
        await navigateTo(blockedPath, { replace: true })
        return
      }
    }

    const errorStatus = result.errorStatus ?? authStore.getAccessStatusFromError(errorText)
    if (errorStatus !== null) {
      const redirectPath = authStore.getRedirectPathForStatus(errorStatus, 'captive')
      if (redirectPath) {
        await navigateTo(redirectPath, { replace: true })
        return
      }
    }

    localError.value = errorText || 'Verifikasi OTP gagal.'
    otpCode.value = ''
    return
  }

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

onMounted(async () => {
  loadPortalParams()
  await refreshApiHealth()
})
</script>

<template>
  <main class="captive-page">
    <section class="box">
      <h1>Portal Hotspot</h1>
      <p class="muted">Login untuk Mikrotik.</p>

      <div class="switcher" role="tablist" aria-label="Mode autentikasi">
        <button type="button" :class="['switch', { active: mode === 'login' }]" @click="switchMode('login')">
          Masuk
        </button>
        <button type="button" :class="['switch', { active: mode === 'register' }]" @click="switchMode('register')">
          Daftar
        </button>
      </div>

      <p v-if="apiStatus === 'down'" class="alert error">
        Server tidak terjangkau. Periksa koneksi WiFi/hotspot.
      </p>

      <p v-if="mode === 'login' && !hasClientIdentity" class="alert warn">
        IP/MAC belum terbaca dari router.
        <a v-if="portalParams.linkLoginOnly" :href="portalParams.linkLoginOnly" target="_blank" rel="noopener">Buka login MikroTik</a>
      </p>

      <form v-if="mode === 'login' && step === 'phone'" class="form" @submit.prevent="requestOtp">
        <label for="phone">Nomor WhatsApp</label>
        <input id="phone" v-model="phoneNumber" type="tel" inputmode="numeric" autocomplete="tel" placeholder="08xxxxxxxxxx" :disabled="isSubmitting">

        <button type="submit" :disabled="isSubmitting">
          {{ isSubmitting ? 'Memproses...' : 'Kirim OTP' }}
        </button>
      </form>

      <form v-else-if="mode === 'login'" class="form" @submit.prevent="verifyOtp">
        <label for="otp">Kode OTP (6 digit)</label>
        <input id="otp" v-model="otpCode" type="text" inputmode="numeric" maxlength="6" autocomplete="one-time-code" placeholder="000000" :disabled="isSubmitting">

        <button type="submit" :disabled="isSubmitting">
          {{ isSubmitting ? 'Memverifikasi...' : 'Verifikasi & Hubungkan' }}
        </button>

        <button type="button" class="ghost" :disabled="isSubmitting" @click="step = 'phone'; otpCode = ''">
          Ganti nomor
        </button>
      </form>

      <div v-else-if="registerSuccess" class="alert ok success-box">
        <p class="success-title">Pendaftaran Berhasil</p>
        <p class="success-text">{{ localInfo }}</p>
        <div class="actions">
          <button type="button" class="ghost" @click="closeWindowOrRedirect">
            Tutup Halaman
          </button>
          <button type="button" @click="openPortalMain">
            Buka Portal Utama
          </button>
        </div>
      </div>

      <form v-else class="form" @submit.prevent="registerUser">
        <label for="reg-name">Nama Lengkap</label>
        <input id="reg-name" v-model="regName" type="text" autocomplete="name" placeholder="Nama lengkap" :disabled="isSubmitting">

        <label for="reg-phone">Nomor WhatsApp</label>
        <input id="reg-phone" v-model="regPhoneNumber" type="tel" inputmode="numeric" autocomplete="tel" placeholder="08xxxxxxxxxx" :disabled="isSubmitting">

        <label for="reg-role">Daftar sebagai</label>
        <select id="reg-role" v-model="regRole" :disabled="isSubmitting">
          <option value="USER">USER</option>
          <option value="KOMANDAN">KOMANDAN</option>
          <option value="TAMPING">TAMPING</option>
        </select>

        <template v-if="showAddressFields">
          <label for="reg-block">Blok</label>
          <input id="reg-block" v-model="regBlock" type="text" autocomplete="off" placeholder="Contoh: A" :disabled="isSubmitting">

          <label for="reg-kamar">Kamar</label>
          <input id="reg-kamar" v-model="regKamar" type="text" autocomplete="off" placeholder="Contoh: 1" :disabled="isSubmitting">
        </template>

        <template v-if="showTampingFields">
          <label for="reg-tamping">Jenis Tamping</label>
          <select id="reg-tamping" v-model="regTampingType" :disabled="isSubmitting">
            <option value="">Pilih jenis tamping</option>
            <option v-for="item in TAMPING_OPTION_ITEMS" :key="item.value" :value="item.value">
              {{ item.title }}
            </option>
          </select>
        </template>

        <button type="submit" :disabled="isSubmitting">
          {{ isSubmitting ? 'Memproses...' : 'Daftar' }}
        </button>
      </form>

      <p v-if="localInfo" class="alert ok">{{ localInfo }}</p>
      <p v-if="localError" class="alert error">{{ localError }}</p>

      <p class="footer-note">
        Login dan registrasi tersedia langsung di halaman ini.
      </p>
    </section>
  </main>
</template>

<style scoped>
.captive-page {
  min-height: 100vh;
  display: grid;
  place-items: center;
  padding: 16px;
}

.box {
  width: 100%;
  max-width: 360px;
  border: 1px solid rgba(127, 127, 127, 0.3);
  border-radius: 10px;
  padding: 16px;
}

h1 {
  margin: 0 0 4px;
  font-size: 20px;
}

.muted {
  margin: 0 0 16px;
  opacity: 0.8;
  font-size: 14px;
}

.form {
  display: grid;
  gap: 10px;
  margin-bottom: 10px;
}

.switcher {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
  margin-bottom: 12px;
}

.switch {
  height: 34px;
  border: 1px solid rgba(127, 127, 127, 0.5);
  border-radius: 8px;
  background: transparent;
  color: inherit;
}

.switch.active {
  background: #2563eb;
  border-color: #2563eb;
  color: white;
}

label {
  font-size: 14px;
}

input {
  width: 100%;
  height: 38px;
  border: 1px solid rgba(127, 127, 127, 0.5);
  border-radius: 8px;
  padding: 0 10px;
  background: transparent;
}

select {
  width: 100%;
  height: 38px;
  border: 1px solid rgba(127, 127, 127, 0.5);
  border-radius: 8px;
  padding: 0 10px;
  background: transparent;
  color: inherit;
}

button {
  height: 38px;
  border: 0;
  border-radius: 8px;
  cursor: pointer;
  background: #2563eb;
  color: white;
}

button:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

button.ghost {
  background: transparent;
  border: 1px solid rgba(127, 127, 127, 0.5);
  color: inherit;
}

.alert {
  font-size: 13px;
  border-radius: 8px;
  padding: 8px 10px;
  margin: 8px 0;
}

.alert.ok {
  background: rgba(34, 197, 94, 0.15);
}

.alert.warn {
  background: rgba(245, 158, 11, 0.15);
}

.alert.error {
  background: rgba(239, 68, 68, 0.15);
}

.footer-note {
  margin-top: 8px;
  font-size: 13px;
}

.success-box {
  margin-bottom: 12px;
}

.success-title {
  margin: 0 0 6px;
  font-weight: 700;
}

.success-text {
  margin: 0 0 10px;
}

.actions {
  display: grid;
  gap: 8px;
}

a {
  color: #2563eb;
  text-decoration: none;
}
</style>
