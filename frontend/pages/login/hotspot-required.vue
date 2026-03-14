<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { normalizeHotspotLoginUrl, resolveHotspotBridgeTarget } from '~/utils/hotspotLoginTargets'
import { resolveHotspotSuccessPresentation, resolvePostHotspotRecheckRoute } from '~/utils/hotspotRedirect'
import { useAuthStore } from '~/store/auth'
import { rememberHotspotIdentity, resolveHotspotIdentity } from '~/utils/hotspotIdentity'

definePageMeta({
  layout: 'blank',
  auth: false,
  public: true,
})

useHead({ title: 'Aktifkan Internet' })

const runtimeConfig = useRuntimeConfig()
const route = useRoute()
const { $api } = useNuxtApp()
const authStore = useAuthStore()
const activating = ref(false)
const progressMessage = ref('')
const statusMessage = ref('')
const showFallbackLogin = ref(false)
const successTitle = ref('')
const successDescription = ref('')
const successCtaLabel = ref('')
const successNextRoute = ref('')
const successCountdown = ref(0)
const HOTSPOT_BRIDGE_WINDOW_NAME = 'lpsaring-hotspot-bridge'
const HOTSPOT_BRIDGE_MESSAGE_TYPE = 'lpsaring:hotspot-identity-bridge'
const HOTSPOT_BRIDGE_TIMEOUT_MS = 8000
const LAST_MIKROTIK_LOGIN_HINT_KEY = 'lpsaring:last-mikrotik-login-link'
const SUCCESS_REDIRECT_DELAY_MS = 2200

let successRedirectTimeout: number | null = null
let successCountdownInterval: number | null = null

const queryMikrotikLink = computed(() => {
  const direct = getQueryValueFromKeys(['link_login_only', 'link-login-only', 'link_login', 'link-login', 'linkloginonly'])
  if (direct)
    return direct

  const redirectRaw = getQueryValueFromKeys(['redirect'])
  if (!redirectRaw || !redirectRaw.includes('link_login_only='))
    return null

  try {
    const parsed = new URL(redirectRaw, 'https://example.invalid')
    const nested = String(parsed.searchParams.get('link_login_only') ?? '').trim()
    return nested || null
  }
  catch {
    const marker = 'link_login_only='
    const markerIndex = redirectRaw.indexOf(marker)
    if (markerIndex < 0)
      return null
    const after = redirectRaw.slice(markerIndex + marker.length)
    const ampIndex = after.indexOf('&')
    return (ampIndex >= 0 ? after.slice(0, ampIndex) : after).trim() || null
  }
})

const storedMikrotikLink = computed(() => {
  if (!import.meta.client)
    return ''
  try {
    return String(window.localStorage.getItem(LAST_MIKROTIK_LOGIN_HINT_KEY) ?? '').trim()
  }
  catch {
    return ''
  }
})

const mikrotikLoginUrl = computed(() => {
  if (queryMikrotikLink.value)
    return normalizeHotspotLoginUrl(queryMikrotikLink.value)

  if (storedMikrotikLink.value)
    return normalizeHotspotLoginUrl(storedMikrotikLink.value)

  const appLink = String(runtimeConfig.public.appLinkMikrotik ?? '').trim()
  if (appLink)
    return normalizeHotspotLoginUrl(appLink)
  return normalizeHotspotLoginUrl(String(runtimeConfig.public.mikrotikLoginUrl ?? '').trim())
})

const hotspotBridgeTargetUrl = computed(() => {
  return resolveHotspotBridgeTarget(
    mikrotikLoginUrl.value,
    String(runtimeConfig.public.hotspotContextProbeUrl ?? '').trim(),
  )
})

function getHotspotIdentity() {
  return resolveHotspotIdentity((route.query as Record<string, unknown>) ?? {})
}

const loginHotspotUrl = computed(() => mikrotikLoginUrl.value)
const showSuccessState = computed(() => Boolean(successNextRoute.value))

function rememberMikrotikLoginLink(raw: string | null | undefined) {
  if (!import.meta.client)
    return

  const normalized = normalizeHotspotLoginUrl(String(raw ?? '').trim())
  if (!normalized)
    return

  try {
    window.localStorage.setItem(LAST_MIKROTIK_LOGIN_HINT_KEY, normalized)
  }
  catch {
    // ignore storage failures
  }
}

function stopSuccessRedirectTimers() {
  if (!import.meta.client)
    return

  if (successRedirectTimeout != null) {
    window.clearTimeout(successRedirectTimeout)
    successRedirectTimeout = null
  }

  if (successCountdownInterval != null) {
    window.clearInterval(successCountdownInterval)
    successCountdownInterval = null
  }
}

function resetSuccessState() {
  stopSuccessRedirectTimers()
  successTitle.value = ''
  successDescription.value = ''
  successCtaLabel.value = ''
  successNextRoute.value = ''
  successCountdown.value = 0
}

async function finishSuccessRedirect() {
  const nextRoute = String(successNextRoute.value || '').trim()
  if (!nextRoute)
    return

  resetSuccessState()
  await navigateTo(nextRoute, { replace: true })
}

function startSuccessRedirect(nextRoute: string) {
  const targetRoute = String(nextRoute || '').trim()
  if (!targetRoute)
    return

  const presentation = resolveHotspotSuccessPresentation(targetRoute)
  stopSuccessRedirectTimers()
  progressMessage.value = ''
  statusMessage.value = ''
  showFallbackLogin.value = false
  successTitle.value = presentation.title
  successDescription.value = presentation.description
  successCtaLabel.value = presentation.ctaLabel
  successNextRoute.value = targetRoute
  successCountdown.value = Math.max(1, Math.ceil(SUCCESS_REDIRECT_DELAY_MS / 1000))

  if (!import.meta.client) {
    void navigateTo(targetRoute, { replace: true })
    return
  }

  successCountdownInterval = window.setInterval(() => {
    if (successCountdown.value > 1)
      successCountdown.value -= 1
  }, 1000)

  successRedirectTimeout = window.setTimeout(() => {
    void finishSuccessRedirect()
  }, SUCCESS_REDIRECT_DELAY_MS)
}

function isDemoUser(user: ReturnType<typeof useAuthStore>['currentUser'] | null | undefined): boolean {
  return user?.is_demo_user === true
}

async function redirectDemoUserToBuyPage(): Promise<boolean> {
  const knownUser = authStore.currentUser ?? authStore.lastKnownUser
  if (isDemoUser(knownUser)) {
    await navigateTo('/beli', { replace: true })
    return true
  }

  try {
    await authStore.refreshSessionStatus('/login/hotspot-required')
    const refreshedUser = authStore.currentUser ?? authStore.lastKnownUser
    if (isDemoUser(refreshedUser)) {
      await navigateTo('/beli', { replace: true })
      return true
    }
  }
  catch {
    // noop; fallback ke alur hotspot-required biasa
  }

  return false
}

function getQueryValueFromKeys(keys: string[]): string | null {
  const query = route.query as Record<string, string | string[] | undefined>
  for (const key of keys) {
    const value = query[key]
    if (Array.isArray(value)) {
      const first = String(value[0] ?? '').trim()
      if (first)
        return first
      continue
    }
    const text = String(value ?? '').trim()
    if (text)
      return text
  }
  return null
}

function openHotspotLogin() {
  if (!import.meta.client)
    return
  const targetUrl = String(loginHotspotUrl.value || '').trim()
  if (!targetUrl) {
    statusMessage.value = getMissingIdentityMessage()
    return
  }

  rememberMikrotikLoginLink(targetUrl)
  window.location.href = targetUrl
}

function getHotspotIdentityQuery(): Record<string, string> {
  const identity = getHotspotIdentity()
  if (identity.clientIp || identity.clientMac)
    rememberHotspotIdentity(identity)
  return {
    ...(identity.clientIp ? { client_ip: identity.clientIp } : {}),
    ...(identity.clientMac ? { client_mac: identity.clientMac } : {}),
  }
}

function hasExplicitHotspotIdentity(identity = getHotspotIdentity()): boolean {
  return Boolean(identity.clientIp || identity.clientMac)
}

function getMissingIdentityMessage(): string {
  if (loginHotspotUrl.value) {
    return 'IP/MAC perangkat belum terbaca dari router. Tekan Aktifkan Internet agar sistem mencoba mengambil konteks hotspot otomatis. Jika tetap gagal, buka Login Hotspot sekali lalu coba lagi.'
  }

  return 'IP/MAC perangkat belum terbaca dari router. Tekan Aktifkan Internet agar sistem mencoba mengambil konteks hotspot otomatis. Jika tetap gagal, buka satu halaman HTTP biasa agar router mengarahkan ke Login Hotspot, lalu coba lagi.'
}

function parseHotspotBridgePayload(data: unknown): { clientIp: string, clientMac: string, linkLoginOnly: string } | null {
  if (!data || typeof data !== 'object')
    return null

  const message = data as Record<string, unknown>
  if (String(message.type ?? '').trim() !== HOTSPOT_BRIDGE_MESSAGE_TYPE)
    return null

  const payload = message.payload && typeof message.payload === 'object'
    ? message.payload as Record<string, unknown>
    : {}

  return {
    clientIp: String(payload.clientIp ?? '').trim(),
    clientMac: String(payload.clientMac ?? '').trim(),
    linkLoginOnly: String(payload.linkLoginOnly ?? '').trim(),
  }
}

async function captureHotspotIdentityViaBridge() {
  const currentIdentity = getHotspotIdentity()
  if (hasExplicitHotspotIdentity(currentIdentity) || !import.meta.client)
    return currentIdentity

  return await new Promise<ReturnType<typeof getHotspotIdentity>>((resolve) => {
    let settled = false
    let popupClosedWatcher: number | null = null
    let timeoutHandle: number | null = null

    const cleanup = () => {
      window.removeEventListener('message', handleMessage)
      if (popupClosedWatcher != null)
        window.clearInterval(popupClosedWatcher)
      if (timeoutHandle != null)
        window.clearTimeout(timeoutHandle)
    }

    const finish = () => {
      if (settled)
        return
      settled = true
      cleanup()
      resolve(getHotspotIdentity())
    }

    const handleMessage = (event: MessageEvent) => {
      if (event.origin !== window.location.origin)
        return

      const payload = parseHotspotBridgePayload(event.data)
      if (!payload)
        return

      rememberHotspotIdentity({
        clientIp: payload.clientIp,
        clientMac: payload.clientMac,
      })
      rememberMikrotikLoginLink(payload.linkLoginOnly)
      finish()
    }

    window.addEventListener('message', handleMessage)

    const popup = window.open(
      hotspotBridgeTargetUrl.value,
      HOTSPOT_BRIDGE_WINDOW_NAME,
      'popup=yes,width=460,height=720,resizable=yes,scrollbars=yes',
    )

    if (!popup) {
      cleanup()
      resolve(currentIdentity)
      return
    }

    try {
      popup.focus()
    }
    catch {
      // ignore focus failures
    }

    popupClosedWatcher = window.setInterval(() => {
      if (popup.closed)
        finish()
    }, 400)

    timeoutHandle = window.setTimeout(() => {
      try {
        popup.close()
      }
      catch {
        // ignore close failures
      }
      finish()
    }, HOTSPOT_BRIDGE_TIMEOUT_MS)
  })
}

function triggerHotspotProbe() {
  if (!import.meta.client)
    return

  const rawTarget = String(loginHotspotUrl.value || hotspotBridgeTargetUrl.value || '').trim()
  if (!rawTarget)
    return

  try {
    const target = new URL(rawTarget, window.location.origin)
    const identity = getHotspotIdentity()
    if (identity.clientIp)
      target.searchParams.set('client_ip', identity.clientIp)
    if (identity.clientMac)
      target.searchParams.set('client_mac', identity.clientMac)
    target.searchParams.set('_probe', String(Date.now()))

    // Best effort ping agar router memperbarui host/session state tanpa memaksa user login manual.
    void fetch(target.toString(), {
      method: 'GET',
      mode: 'no-cors',
      credentials: 'include',
      cache: 'no-store',
    }).catch(() => {})

    const img = new Image()
    img.referrerPolicy = 'no-referrer'
    img.src = target.toString()
  }
  catch {
    // ignore malformed URL
  }
}

async function fetchHotspotStatus() {
  const response = await $api<{ hotspot_login_required?: boolean | null, hotspot_binding_active?: boolean | null, hotspot_hint_applied?: boolean | null }>('/auth/hotspot-session-status', {
    method: 'GET',
    query: getHotspotIdentityQuery(),
  })

  return {
    hotspotRequired: response?.hotspot_login_required === true,
    hotspotActive: response?.hotspot_binding_active === true,
    hotspotHintApplied: response?.hotspot_hint_applied === true,
  }
}

function wait(ms: number) {
  return new Promise(resolve => setTimeout(resolve, ms))
}

async function continueToPortal() {
  if (await redirectDemoUserToBuyPage())
    return

  resetSuccessState()
  statusMessage.value = ''
  try {
    await authStore.refreshSessionStatus('/login/hotspot-required')
    const latestUser = authStore.currentUser ?? authStore.lastKnownUser
    if (!latestUser) {
      await navigateTo('/login', { replace: true })
      return
    }

    const latestStatus = authStore.getAccessStatusFromUser(latestUser)
    const nextRoute = resolvePostHotspotRecheckRoute(latestStatus)
    startSuccessRedirect(nextRoute)
  }
  catch {
    statusMessage.value = 'Gagal memuat sesi terbaru. Silakan coba lagi.'
  }
}

async function activateInternetOneClick() {
  if (activating.value)
    return

  if (await redirectDemoUserToBuyPage())
    return

  activating.value = true
  showFallbackLogin.value = false
  statusMessage.value = ''
  progressMessage.value = 'Menyiapkan koneksi internet...'

  let identity = getHotspotIdentity()
  rememberHotspotIdentity(identity)

  try {
    if (!hasExplicitHotspotIdentity(identity)) {
      progressMessage.value = 'Mengambil konteks perangkat dari hotspot...'
      identity = await captureHotspotIdentityViaBridge()
      rememberHotspotIdentity(identity)
    }

    triggerHotspotProbe()
    await wait(600)

    progressMessage.value = 'Memeriksa perangkat...'
    const initialStatus = await fetchHotspotStatus()
    if (!initialStatus.hotspotRequired || initialStatus.hotspotActive) {
      progressMessage.value = ''
      await continueToPortal()
      return
    }

    if (!hasExplicitHotspotIdentity(identity) && !initialStatus.hotspotHintApplied) {
      progressMessage.value = ''
      showFallbackLogin.value = Boolean(loginHotspotUrl.value)
      statusMessage.value = getMissingIdentityMessage()
      return
    }

    progressMessage.value = 'Mengaktifkan internet...'
    const bindSuccess = await authStore.authorizeDevice({
      clientIp: identity.clientIp || null,
      clientMac: identity.clientMac || null,
      bestEffort: true,
    })

    triggerHotspotProbe()

    if (bindSuccess) {
      // Binding berhasil dibuat di MikroTik — poll singkat untuk konfirmasi, lalu langsung portal
      const quickAttempts = 3
      for (let attempt = 1; attempt <= quickAttempts; attempt++) {
        progressMessage.value = `Memverifikasi koneksi... (${attempt}/${quickAttempts})`
        const status = await fetchHotspotStatus()
        if (!status.hotspotRequired || status.hotspotActive) {
          progressMessage.value = ''
          await continueToPortal()
          return
        }
        if (attempt < quickAttempts)
          await wait(900)
      }
      // ip-binding sudah aktif di MikroTik — langsung portal meski status belum terkonfirmasi
      progressMessage.value = ''
      await continueToPortal()
      return
    }

    // bind-current gagal — coba polling konfirmasi
    const maxAttempts = 6
    for (let attempt = 1; attempt <= maxAttempts; attempt++) {
      progressMessage.value = `Sinkronisasi akses hotspot... (${attempt}/${maxAttempts})`
      const status = await fetchHotspotStatus()
      if (!status.hotspotRequired || status.hotspotActive) {
        progressMessage.value = ''
        await continueToPortal()
        return
      }

      if (attempt < maxAttempts)
        await wait(1200)
    }

    progressMessage.value = ''
    showFallbackLogin.value = Boolean(loginHotspotUrl.value)
    statusMessage.value = authStore.error || 'Internet belum aktif. Coba buka Login Hotspot sekali, lalu tekan Aktifkan Internet lagi.'
  }
  catch {
    progressMessage.value = ''
    showFallbackLogin.value = Boolean(loginHotspotUrl.value)
    statusMessage.value = 'Internet belum bisa diaktifkan otomatis. Silakan buka Login Hotspot, lalu coba lagi.'
  }
  finally {
    activating.value = false
  }
}

onMounted(async () => {
  rememberMikrotikLoginLink(queryMikrotikLink.value)
  rememberHotspotIdentity(getHotspotIdentity())

  if (await redirectDemoUserToBuyPage())
    return

  try {
    triggerHotspotProbe()
    await wait(250)

    const status = await fetchHotspotStatus()
    if (!status.hotspotRequired || status.hotspotActive) {
      await continueToPortal()
      return
    }

    if (!hasExplicitHotspotIdentity() && !status.hotspotHintApplied) {
      showFallbackLogin.value = Boolean(loginHotspotUrl.value)
      statusMessage.value = getMissingIdentityMessage()
    }
  }
  catch {
    // best effort
  }
})

onBeforeUnmount(() => {
  stopSuccessRedirectTimers()
})
</script>

<template>
  <div class="auth-wrapper d-flex align-center justify-center pa-4 pa-sm-6">
    <VCard class="auth-card" max-width="460" width="100%">
      <VCardText v-if="showSuccessState" class="text-center pa-6 pa-sm-8">
        <VIcon icon="tabler-circle-check" size="56" color="success" class="mb-4" />

        <h4 class="text-h5 text-sm-h4 mb-2">
          {{ successTitle }}
        </h4>

        <p class="text-medium-emphasis mb-6 text-body-2 text-sm-body-1">
          {{ successDescription }}
        </p>

        <VCard variant="tonal" color="success" class="mb-6 text-start">
          <VCardText class="py-3 px-4">
            <div class="d-flex justify-space-between align-center mb-2">
              <span class="text-body-2">Status</span>
              <span class="font-weight-semibold text-body-2">Berhasil</span>
            </div>
            <div class="d-flex justify-space-between align-center">
              <span class="text-body-2">Redirect</span>
              <span class="font-weight-semibold text-body-2">{{ successCountdown }} detik</span>
            </div>
          </VCardText>
        </VCard>

        <p class="text-caption text-medium-emphasis mb-4">
          Anda akan diarahkan otomatis. Jika belum berpindah, gunakan tombol di bawah.
        </p>

        <div class="d-flex flex-column ga-3">
          <VBtn color="success" size="large" block @click="finishSuccessRedirect">
            {{ successCtaLabel }}
          </VBtn>
        </div>
      </VCardText>

      <VCardText v-else class="text-center pa-6 pa-sm-8">
        <VIcon icon="tabler-router" size="56" color="warning" class="mb-4" />

        <h4 class="text-h5 text-sm-h4 mb-2">
          Aktifkan Internet
        </h4>

        <p class="text-medium-emphasis mb-6 text-body-2 text-sm-body-1">
          Anda sudah berhasil login. Tekan tombol di bawah agar internet langsung aktif.
        </p>

        <VAlert type="info" variant="tonal" density="comfortable" class="mb-6 text-start">
          Proses ini berjalan otomatis. Jika belum aktif, gunakan tombol Login Hotspot lalu coba lagi.
        </VAlert>

        <VAlert
          v-if="progressMessage"
          type="info"
          variant="tonal"
          density="comfortable"
          class="mb-6 text-start"
        >
          {{ progressMessage }}
        </VAlert>

        <VAlert
          v-if="statusMessage"
          type="warning"
          variant="tonal"
          density="comfortable"
          class="mb-6 text-start"
        >
          {{ statusMessage }}
        </VAlert>

        <div class="d-flex flex-column ga-3">
          <VBtn color="primary" size="large" block :loading="activating" :disabled="activating" @click="activateInternetOneClick">
            Aktifkan Internet
          </VBtn>

          <VBtn v-if="showFallbackLogin && loginHotspotUrl" variant="tonal" color="warning" size="large" block :disabled="activating" @click="openHotspotLogin">
            Buka Login Hotspot
          </VBtn>

          <VBtn variant="text" color="default" size="small" :disabled="activating" @click="continueToPortal">
            Lanjut ke Portal (cek status terbaru)
          </VBtn>
        </div>
      </VCardText>
    </VCard>
  </div>
</template>

<style scoped>
.auth-wrapper {
  min-block-size: 100dvh;
}
</style>
