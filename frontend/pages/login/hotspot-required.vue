<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { resolvePostHotspotRecheckRoute } from '~/utils/hotspotRedirect'
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
const LAST_MIKROTIK_LOGIN_HINT_KEY = 'lpsaring:last-mikrotik-login-link'

const appBaseUrl = computed(() => String(runtimeConfig.public.appBaseUrl ?? '').trim())

function shouldForceHttpForHost(hostname: string): boolean {
  const host = String(hostname || '').trim().toLowerCase()
  if (!host)
    return false

  if (host === 'localhost' || host.endsWith('.local') || host.endsWith('.home.arpa'))
    return true

  if (/^\d{1,3}(\.\d{1,3}){3}$/.test(host)) {
    const octets = host.split('.').map(n => Number.parseInt(n, 10))
    if (octets.length === 4) {
      const [a, b] = octets
      if (a === 10)
        return true
      if (a === 172 && b >= 16 && b <= 31)
        return true
      if (a === 192 && b === 168)
        return true
      if (a === 169 && b === 254)
        return true
    }
  }

  return false
}

function normalizeHotspotLoginUrl(raw: string): string {
  const input = String(raw || '').trim()
  if (!input)
    return ''

  const candidate = input.startsWith('//') ? `http:${input}` : input

  try {
    const parsed = new URL(candidate)
    if (parsed.protocol === 'https:' && shouldForceHttpForHost(parsed.hostname))
      parsed.protocol = 'http:'
    return parsed.toString()
  }
  catch {
    const withScheme = /^https?:\/\//i.test(candidate) ? candidate : `http://${candidate.replace(/^\/+/, '')}`
    try {
      const parsed = new URL(withScheme)
      if (parsed.protocol === 'https:' && shouldForceHttpForHost(parsed.hostname))
        parsed.protocol = 'http:'
      return parsed.toString()
    }
    catch {
      return candidate
    }
  }
}

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

const fallbackLoginPath = computed(() => {
  const base = appBaseUrl.value
  if (!base)
    return '/captive'
  return `${base.replace(/\/+$/, '')}/captive`
})

function getHotspotIdentity() {
  return resolveHotspotIdentity((route.query as Record<string, unknown>) ?? {})
}

const loginHotspotUrl = computed(() => mikrotikLoginUrl.value || fallbackLoginPath.value)

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
  if (!targetUrl)
    return

  window.location.assign(targetUrl)

  setTimeout(() => {
    if (document.visibilityState !== 'visible')
      return
    const fallbackLink = document.createElement('a')
    fallbackLink.href = targetUrl
    fallbackLink.target = '_self'
    fallbackLink.rel = 'noopener'
    fallbackLink.click()
  }, 600)
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

function triggerHotspotProbe() {
  if (!import.meta.client)
    return

  const rawTarget = String(loginHotspotUrl.value || '').trim()
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
  const response = await $api<{ hotspot_login_required?: boolean | null, hotspot_binding_active?: boolean | null }>('/auth/hotspot-session-status', {
    method: 'GET',
    query: getHotspotIdentityQuery(),
  })

  return {
    hotspotRequired: response?.hotspot_login_required === true,
    hotspotActive: response?.hotspot_binding_active === true,
  }
}

function wait(ms: number) {
  return new Promise(resolve => setTimeout(resolve, ms))
}

async function continueToPortal() {
  if (await redirectDemoUserToBuyPage())
    return

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
    await navigateTo(nextRoute, { replace: true })
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

  const identity = getHotspotIdentity()
  rememberHotspotIdentity(identity)

  try {
    triggerHotspotProbe()
    await wait(600)

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
    showFallbackLogin.value = true
    statusMessage.value = authStore.error || 'Internet belum aktif. Coba buka Login Hotspot sekali, lalu tekan Aktifkan Internet lagi.'
  }
  catch {
    progressMessage.value = ''
    showFallbackLogin.value = true
    statusMessage.value = 'Internet belum bisa diaktifkan otomatis. Silakan buka Login Hotspot, lalu coba lagi.'
  }
  finally {
    activating.value = false
  }
}

onMounted(async () => {
  rememberHotspotIdentity(getHotspotIdentity())

  if (await redirectDemoUserToBuyPage())
    return

  try {
    triggerHotspotProbe()
    await wait(250)

    const status = await fetchHotspotStatus()
    if (!status.hotspotRequired || status.hotspotActive)
      await continueToPortal()
  }
  catch {
    // best effort
  }
})
</script>

<template>
  <div class="auth-wrapper d-flex align-center justify-center pa-4 pa-sm-6">
    <VCard class="auth-card" max-width="460" width="100%">
      <VCardText class="text-center pa-6 pa-sm-8">
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

          <VBtn v-if="showFallbackLogin" variant="tonal" color="warning" size="large" block :disabled="activating" @click="openHotspotLogin">
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
