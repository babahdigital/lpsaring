<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { resolvePostHotspotRecheckRoute } from '~/utils/hotspotRedirect'
import { useAuthStore } from '~/store/auth'

definePageMeta({
  layout: 'blank',
  auth: false,
  public: true,
})

useHead({ title: 'Login Hotspot Diperlukan' })

const runtimeConfig = useRuntimeConfig()
const route = useRoute()
const { $api } = useNuxtApp()
const authStore = useAuthStore()
const rechecking = ref(false)
const statusMessage = ref('')
const LAST_MIKROTIK_LOGIN_HINT_KEY = 'lpsaring:last-mikrotik-login-link'

const appBaseUrl = computed(() => String(runtimeConfig.public.appBaseUrl ?? '').trim())
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
    return String(window.sessionStorage.getItem(LAST_MIKROTIK_LOGIN_HINT_KEY) ?? '').trim()
  }
  catch {
    return ''
  }
})

const mikrotikLoginUrl = computed(() => {
  if (queryMikrotikLink.value)
    return queryMikrotikLink.value

  if (storedMikrotikLink.value)
    return storedMikrotikLink.value

  const appLink = String(runtimeConfig.public.appLinkMikrotik ?? '').trim()
  if (appLink)
    return appLink
  return String(runtimeConfig.public.mikrotikLoginUrl ?? '').trim()
})

const fallbackLoginPath = computed(() => {
  const base = appBaseUrl.value
  if (!base)
    return '/captive'
  return `${base.replace(/\/+$/, '')}/captive`
})

const loginHotspotUrl = computed(() => mikrotikLoginUrl.value || fallbackLoginPath.value)

function isDemoUser(user: ReturnType<typeof useAuthStore>['currentUser']['value'] | null | undefined): boolean {
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
  window.location.href = loginHotspotUrl.value
}

async function continueToPortal() {
  if (await redirectDemoUserToBuyPage())
    return

  rechecking.value = true
  statusMessage.value = ''
  try {
    const clientIp = getQueryValueFromKeys(['client_ip', 'ip', 'client-ip'])
    const clientMac = getQueryValueFromKeys(['client_mac', 'mac', 'mac-address', 'client-mac'])

    const response = await $api<{ hotspot_login_required?: boolean | null, hotspot_binding_active?: boolean | null }>('/auth/hotspot-session-status', {
      method: 'GET',
      query: {
        ...(clientIp ? { client_ip: clientIp } : {}),
        ...(clientMac ? { client_mac: clientMac } : {}),
      },
    })

    const hotspotRequired = response?.hotspot_login_required === true
    const hotspotActive = response?.hotspot_binding_active === true

    if (!hotspotRequired || hotspotActive) {
      await authStore.refreshSessionStatus('/login/hotspot-required')
      const latestUser = authStore.currentUser ?? authStore.lastKnownUser
      if (!latestUser) {
        await navigateTo('/login', { replace: true })
        return
      }

      const latestStatus = authStore.getAccessStatusFromUser(latestUser)
      const nextRoute = resolvePostHotspotRecheckRoute(latestStatus)
      await navigateTo(nextRoute, { replace: true })
      return
    }

    statusMessage.value = 'Sesi hotspot belum aktif. Silakan login MikroTik terlebih dahulu, lalu cek lagi.'
  }
  catch {
    statusMessage.value = 'Gagal memeriksa status hotspot. Pastikan koneksi portal tersedia lalu coba lagi.'
  }
  finally {
    rechecking.value = false
  }
}

onMounted(async () => {
  await redirectDemoUserToBuyPage()
})
</script>

<template>
  <div class="auth-wrapper d-flex align-center justify-center pa-4 pa-sm-6">
    <VCard class="auth-card" max-width="460" width="100%">
      <VCardText class="text-center pa-6 pa-sm-8">
        <VIcon icon="tabler-router" size="56" color="warning" class="mb-4" />

        <h4 class="text-h5 text-sm-h4 mb-2">
          Login Hotspot MikroTik Diperlukan
        </h4>

        <p class="text-medium-emphasis mb-6 text-body-2 text-sm-body-1">
          Anda sudah berhasil login ke portal. Agar internet aktif, silakan login hotspot MikroTik terlebih dahulu.
        </p>

        <VAlert type="info" variant="tonal" density="comfortable" class="mb-6 text-start">
          Jika sudah login hotspot, klik <strong>Saya Sudah Login Hotspot</strong> untuk lanjut ke portal.
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
          <VBtn color="primary" size="large" block @click="openHotspotLogin">
            Buka Login MikroTik
          </VBtn>

          <VBtn variant="tonal" color="success" size="large" block :loading="rechecking" :disabled="rechecking" @click="continueToPortal">
            Saya Sudah Login Hotspot
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
