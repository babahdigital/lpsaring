<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { normalizeHotspotLoginUrl, resolveHotspotBridgeTarget } from '~/utils/hotspotLoginTargets'
import { resolveHotspotSuccessPresentation, resolvePostHotspotRecheckRoute } from '~/utils/hotspotRedirect'
import { type HotspotActivationStepState, type HotspotActivationStage, resolveHotspotActivationProgress } from '~/utils/hotspotActivationProgress'
import { clearPendingHotspotBridge, rememberPendingHotspotBridge } from '~/utils/hotspotBridgeState'
import { useAuthStore } from '~/store/auth'
import { getHotspotIdentityFromQuery, rememberHotspotIdentity, resolveHotspotIdentity } from '~/utils/hotspotIdentity'
import { extractHotspotLoginHintFromQuery, resolveHotspotTrustConfig, sanitizeHotspotLoginHint, sanitizeResolvedHotspotIdentity } from '~/utils/hotspotTrust'

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
const hotspotTrustConfig = resolveHotspotTrustConfig({
  hotspotAllowedClientCidrs: runtimeConfig.public.hotspotAllowedClientCidrs,
  hotspotTrustedLoginHosts: runtimeConfig.public.hotspotTrustedLoginHosts,
  trustedLoginUrls: [runtimeConfig.public.appLinkMikrotik, runtimeConfig.public.mikrotikLoginUrl],
})
const activating = ref(false)
const progressMessage = ref('')
const statusMessage = ref('')
const showFallbackLogin = ref(false)
const activationStage = ref<HotspotActivationStage>('idle')
const successTitle = ref('')
const successDescription = ref('')
const successCtaLabel = ref('')
const successNextRoute = ref('')
const successCountdown = ref(0)
const BRIDGE_RESUME_QUERY_KEY = 'bridge_resume'
const AUTO_START_QUERY_KEY = 'auto_start'
const LAST_MIKROTIK_LOGIN_HINT_KEY = 'lpsaring:last-mikrotik-login-link'
const SUCCESS_REDIRECT_DELAY_MS = 900
const HOTSPOT_AUTO_START_DELAY_MS = 50
const HOTSPOT_BRIDGE_RESUME_DELAY_MS = 50
const HOTSPOT_INITIAL_PROBE_DELAY_MS = 100
const HOTSPOT_PROBE_SETTLE_MS = 200
const HOTSPOT_CONFIRM_ATTEMPTS = 6
const HOTSPOT_CONFIRM_DELAY_FAST_MS = 500
const HOTSPOT_CONFIRM_DELAY_RECOVERY_MS = 700

let successRedirectTimeout: number | null = null
let successCountdownInterval: number | null = null

const queryMikrotikLink = computed(() => {
  return sanitizeHotspotLoginHint(extractHotspotLoginHintFromQuery((route.query as Record<string, unknown>) ?? {}), hotspotTrustConfig) || null
})

const foreignHotspotContextMessage = computed(() => {
  const rawIdentity = getHotspotIdentityFromQuery((route.query as Record<string, unknown>) ?? {})
  const sanitizedIdentity = sanitizeResolvedHotspotIdentity(rawIdentity, hotspotTrustConfig)
  if (rawIdentity.clientIp && !sanitizedIdentity.clientIp)
    return 'Konteks hotspot dari jaringan lain terdeteksi dan diblokir. Gunakan portal hotspot jaringan asal, bukan LPSaring.'

  return ''
})

function getStoredMikrotikLink(): string {
  if (!import.meta.client)
    return ''
  try {
    const raw = String(window.localStorage.getItem(LAST_MIKROTIK_LOGIN_HINT_KEY) ?? '').trim()
    if (!raw)
      return ''

    const sanitized = sanitizeHotspotLoginHint(raw, hotspotTrustConfig)
    if (!sanitized) {
      window.localStorage.removeItem(LAST_MIKROTIK_LOGIN_HINT_KEY)
      return ''
    }

    return sanitized
  }
  catch {
    return ''
  }
}

const mikrotikLoginUrl = computed(() => {
  if (queryMikrotikLink.value)
    return normalizeHotspotLoginUrl(queryMikrotikLink.value)

  const storedMikrotikLink = getStoredMikrotikLink()
  if (storedMikrotikLink)
    return normalizeHotspotLoginUrl(storedMikrotikLink)

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
  return resolveHotspotIdentity((route.query as Record<string, unknown>) ?? {}, hotspotTrustConfig)
}

const loginHotspotUrl = computed(() => mikrotikLoginUrl.value)
const showSuccessState = computed(() => Boolean(successNextRoute.value))
const activationProgress = computed(() => resolveHotspotActivationProgress(activationStage.value))

function rememberMikrotikLoginLink(raw: string | null | undefined) {
  if (!import.meta.client)
    return

  const trustedHint = sanitizeHotspotLoginHint(String(raw ?? '').trim(), hotspotTrustConfig)
  if (!trustedHint) {
    try {
      window.localStorage.removeItem(LAST_MIKROTIK_LOGIN_HINT_KEY)
    }
    catch {
      // ignore storage failures
    }
    return
  }

  const normalized = normalizeHotspotLoginUrl(trustedHint)
  if (!normalized)
    return

  try {
    window.localStorage.setItem(LAST_MIKROTIK_LOGIN_HINT_KEY, normalized)
  }
  catch {
    // ignore storage failures
  }
}

function syncHotspotRouteContext(identity = getHotspotIdentity()) {
  if (!import.meta.client)
    return

  const clientIp = String(identity.clientIp ?? '').trim()
  const clientMac = String(identity.clientMac ?? '').trim()
  const linkLoginOnly = String(queryMikrotikLink.value || getStoredMikrotikLink() || '').trim()
  if (!clientIp && !clientMac && !linkLoginOnly)
    return

  try {
    const currentUrl = new URL(window.location.href)
    let changed = false

    if (clientIp && currentUrl.searchParams.get('client_ip') !== clientIp) {
      currentUrl.searchParams.set('client_ip', clientIp)
      changed = true
    }

    if (clientMac && currentUrl.searchParams.get('client_mac') !== clientMac) {
      currentUrl.searchParams.set('client_mac', clientMac)
      changed = true
    }

    if (linkLoginOnly && currentUrl.searchParams.get('link_login_only') !== linkLoginOnly) {
      currentUrl.searchParams.set('link_login_only', linkLoginOnly)
      changed = true
    }

    if (changed)
      window.history.replaceState(window.history.state, '', currentUrl.toString())
  }
  catch {
    // ignore malformed URL/state issues
  }
}

function resetActivationState() {
  activationStage.value = 'idle'
  progressMessage.value = ''
}

function setActivationStage(stage: Exclude<HotspotActivationStage, 'idle'>, message: string) {
  activationStage.value = stage
  progressMessage.value = message
}

function getActivationStepIcon(state: HotspotActivationStepState): string {
  if (state === 'completed')
    return 'tabler-circle-check'
  if (state === 'active')
    return 'tabler-loader-2'
  return 'tabler-circle'
}

function getActivationStepColor(state: HotspotActivationStepState): string {
  if (state === 'completed')
    return 'success'
  if (state === 'active')
    return 'primary'
  return 'medium-emphasis'
}

function stripBridgeResumeQueryFlag() {
  if (!import.meta.client)
    return

  try {
    const currentUrl = new URL(window.location.href)
    if (!currentUrl.searchParams.has(BRIDGE_RESUME_QUERY_KEY))
      return
    currentUrl.searchParams.delete(BRIDGE_RESUME_QUERY_KEY)
    window.history.replaceState(window.history.state, '', currentUrl.toString())
  }
  catch {
    // ignore malformed URL/state issues
  }
}

function beginSilentHotspotBridge(): boolean {
  if (!import.meta.client)
    return false

  const targetUrl = String(hotspotBridgeTargetUrl.value || '').trim()
  const manualLoginUrl = String(loginHotspotUrl.value || '').trim()
  if (!targetUrl)
    return false

  rememberPendingHotspotBridge({
    returnPath: '/login/hotspot-required',
    autoResume: true,
  })
  rememberMikrotikLoginLink(manualLoginUrl || targetUrl)
  window.location.assign(targetUrl)
  return true
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
  resetActivationState()
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
  if (foreignHotspotContextMessage.value) {
    statusMessage.value = foreignHotspotContextMessage.value
    showFallbackLogin.value = false
    return
  }
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
    rememberHotspotIdentity(identity, hotspotTrustConfig)
  syncHotspotRouteContext(identity)
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

function getHotspotNotReadyMessage(): string {
  if (loginHotspotUrl.value) {
    return 'Internet perangkat belum aktif sepenuhnya. Buka Login Hotspot sekali, lalu tekan Aktifkan Internet lagi.'
  }

  return 'Internet perangkat belum aktif sepenuhnya. Buka satu halaman HTTP biasa agar router menampilkan Login Hotspot, lalu tekan Aktifkan Internet lagi.'
}

function triggerHotspotProbe() {
  if (!import.meta.client)
    return

  const rawTarget = String(hotspotBridgeTargetUrl.value || loginHotspotUrl.value || '').trim()
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

async function waitForHotspotConfirmation(options: { attempts: number, delayMs: number, progressPrefix: string }): Promise<boolean> {
  for (let attempt = 1; attempt <= options.attempts; attempt++) {
    progressMessage.value = `${options.progressPrefix} (${attempt}/${options.attempts})`
    const status = await fetchHotspotStatus()
    if (!status.hotspotRequired || status.hotspotActive)
      return true

    if (attempt < options.attempts)
      await wait(options.delayMs)
  }

  return false
}

async function ensureHotspotReadyForPortal(): Promise<boolean> {
  try {
    const status = await fetchHotspotStatus()
    if (!status.hotspotRequired || status.hotspotActive)
      return true
  }
  catch {
    // treat as not-ready so the user stays in the recovery flow
  }

  resetSuccessState()
  resetActivationState()
  showFallbackLogin.value = Boolean(loginHotspotUrl.value)
  statusMessage.value = getHotspotNotReadyMessage()
  return false
}

async function continueToPortal(options: { requireHotspotReady?: boolean } = {}) {
  if (await redirectDemoUserToBuyPage())
    return

  const requireHotspotReady = options.requireHotspotReady !== false

  resetSuccessState()
  resetActivationState()
  statusMessage.value = ''
  try {
    await authStore.refreshSessionStatus('/login/hotspot-required')
    const latestUser = authStore.currentUser ?? authStore.lastKnownUser
    if (!latestUser) {
      await navigateTo('/login', { replace: true })
      return
    }

    if (requireHotspotReady) {
      const hotspotReady = await ensureHotspotReadyForPortal()
      if (!hotspotReady)
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

async function activateInternetOneClick(options: { allowBridgeRoundtrip?: boolean } = {}) {
  if (activating.value)
    return

  if (foreignHotspotContextMessage.value) {
    showFallbackLogin.value = false
    statusMessage.value = foreignHotspotContextMessage.value
    return
  }

  if (await redirectDemoUserToBuyPage())
    return

  const allowBridgeRoundtrip = options.allowBridgeRoundtrip !== false

  activating.value = true
  showFallbackLogin.value = false
  statusMessage.value = ''
  resetSuccessState()
  setActivationStage('context', 'Menyiapkan proses aktivasi internet...')

  let identity = getHotspotIdentity()
  rememberHotspotIdentity(identity, hotspotTrustConfig)
  syncHotspotRouteContext(identity)

  try {
    if (!hasExplicitHotspotIdentity(identity)) {
      if (allowBridgeRoundtrip) {
        setActivationStage('context', 'Mengambil konteks hotspot di tab ini tanpa popup tambahan...')
        if (beginSilentHotspotBridge())
          return
      }

      progressMessage.value = 'IP/MAC perangkat belum terbaca. Melanjutkan pengecekan lokal terlebih dahulu...'
    }

    setActivationStage('sync', 'Menyinkronkan sesi hotspot dengan router...')
    triggerHotspotProbe()
    await wait(HOTSPOT_PROBE_SETTLE_MS)

    progressMessage.value = 'Memeriksa status perangkat di hotspot...'
    const initialStatus = await fetchHotspotStatus()
    if (!initialStatus.hotspotRequired || initialStatus.hotspotActive) {
      await continueToPortal({ requireHotspotReady: false })
      return
    }

    if (!hasExplicitHotspotIdentity(identity) && !initialStatus.hotspotHintApplied) {
      resetActivationState()
      showFallbackLogin.value = Boolean(loginHotspotUrl.value)
      statusMessage.value = getMissingIdentityMessage()
      return
    }

    setActivationStage('verify', 'Mengaktifkan binding perangkat dan memverifikasi internet...')
    const bindSuccess = await authStore.authorizeDevice({
      clientIp: identity.clientIp || null,
      clientMac: identity.clientMac || null,
      bestEffort: true,
    })

    triggerHotspotProbe()

    if (bindSuccess) {
      const confirmed = await waitForHotspotConfirmation({
        attempts: HOTSPOT_CONFIRM_ATTEMPTS,
        delayMs: HOTSPOT_CONFIRM_DELAY_FAST_MS,
        progressPrefix: 'Memverifikasi koneksi internet...',
      })
      if (confirmed) {
        await continueToPortal({ requireHotspotReady: false })
        return
      }

      resetActivationState()
      showFallbackLogin.value = Boolean(loginHotspotUrl.value)
      statusMessage.value = getHotspotNotReadyMessage()
      return
    }

    const confirmed = await waitForHotspotConfirmation({
      attempts: HOTSPOT_CONFIRM_ATTEMPTS,
      delayMs: HOTSPOT_CONFIRM_DELAY_RECOVERY_MS,
      progressPrefix: 'Sinkronisasi akses hotspot...',
    })
    if (confirmed) {
      await continueToPortal({ requireHotspotReady: false })
      return
    }

    resetActivationState()
    showFallbackLogin.value = Boolean(loginHotspotUrl.value)
    statusMessage.value = authStore.error || getHotspotNotReadyMessage()
  }
  catch {
    resetActivationState()
    showFallbackLogin.value = Boolean(loginHotspotUrl.value)
    statusMessage.value = 'Internet belum bisa diaktifkan otomatis. Silakan buka Login Hotspot, lalu coba lagi.'
  }
  finally {
    activating.value = false
  }
}

onMounted(async () => {
  rememberMikrotikLoginLink(queryMikrotikLink.value)
  const initialIdentity = getHotspotIdentity()
  rememberHotspotIdentity(initialIdentity, hotspotTrustConfig)
  syncHotspotRouteContext(initialIdentity)
  const shouldAutoStart = getQueryValueFromKeys([AUTO_START_QUERY_KEY]) === '1'

  if (foreignHotspotContextMessage.value) {
    showFallbackLogin.value = false
    statusMessage.value = foreignHotspotContextMessage.value
    return
  }

  if (getQueryValueFromKeys([BRIDGE_RESUME_QUERY_KEY]) === '1') {
    clearPendingHotspotBridge()
    stripBridgeResumeQueryFlag()
    if (hasExplicitHotspotIdentity(initialIdentity)) {
      statusMessage.value = ''
      await wait(HOTSPOT_BRIDGE_RESUME_DELAY_MS)
      void activateInternetOneClick({ allowBridgeRoundtrip: false })
      return
    }
  }

  if (await redirectDemoUserToBuyPage())
    return

  if (shouldAutoStart) {
    statusMessage.value = ''
    await wait(HOTSPOT_AUTO_START_DELAY_MS)
    void activateInternetOneClick()
    return
  }

  try {
    triggerHotspotProbe()
    await wait(HOTSPOT_INITIAL_PROBE_DELAY_MS)

    const status = await fetchHotspotStatus()
    if (!status.hotspotRequired || status.hotspotActive) {
      await continueToPortal({ requireHotspotReady: false })
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

        <VCard v-if="activating && activationProgress.currentStep > 0" variant="tonal" color="info" class="mb-6 text-start">
          <VCardText class="py-4 px-4">
            <div class="d-flex justify-space-between align-center mb-3">
              <span class="text-body-2 font-weight-medium">Proses Aktivasi</span>
              <span class="text-caption text-medium-emphasis">Langkah {{ activationProgress.currentStep }}/{{ activationProgress.totalSteps }}</span>
            </div>

            <VProgressLinear :model-value="activationProgress.progressValue" color="primary" height="8" rounded class="mb-4" />

            <div class="d-flex flex-column ga-3">
              <div v-for="step in activationProgress.steps" :key="step.key" class="d-flex align-start ga-3">
                <VIcon
                  :icon="getActivationStepIcon(step.state)"
                  :color="getActivationStepColor(step.state)"
                  size="20"
                  :class="{ 'activation-step-icon--active': step.state === 'active' }"
                />

                <div class="flex-grow-1">
                  <div class="text-body-2 font-weight-medium">
                    {{ step.title }}
                  </div>
                  <div class="text-caption text-medium-emphasis">
                    {{ step.description }}
                  </div>
                </div>
              </div>
            </div>

            <p v-if="progressMessage" class="text-caption text-medium-emphasis mt-4 mb-0">
              {{ progressMessage }}
            </p>
          </VCardText>
        </VCard>

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

.activation-step-icon--active {
  animation: activation-spin 1s linear infinite;
}

@keyframes activation-spin {
  from {
    transform: rotate(0deg);
  }

  to {
    transform: rotate(360deg);
  }
}
</style>
