<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { useAuthStore } from '~/store/auth'
import { clearCaptiveContext } from '~/utils/captiveContext'
import { resolveCaptiveSuccessRedirectTarget } from '~/utils/hotspotRedirect'
definePageMeta({
  layout: 'blank',
  auth: false,
  public: true,
})

useHead({ title: 'Koneksi Berhasil' })

const authStore = useAuthStore()
const { public: { captiveSuccessRedirectUrl } } = useRuntimeConfig()
const countdown = ref(5)
const isClosing = ref(false)
const isNavigatingAway = ref(false)
let statusRecheckInterval: ReturnType<typeof setInterval> | null = null
let autoCloseInterval: ReturnType<typeof setInterval> | null = null

function isConnectedStatus(status: string): boolean {
  return status === 'ok' || status === 'fup'
}

function stopAutoClose() {
  if (autoCloseInterval != null) {
    clearInterval(autoCloseInterval)
    autoCloseInterval = null
  }
}

function startAutoClose() {
  if (!import.meta.client)
    return

  autoCloseInterval = setInterval(() => {
    if (isNavigatingAway.value) {
      stopAutoClose()
      return
    }
    if (countdown.value <= 1) {
      stopAutoClose()
      void handleDone()
      return
    }
    countdown.value -= 1
  }, 1000)
}

function stopStatusRecheck() {
  if (statusRecheckInterval != null) {
    clearInterval(statusRecheckInterval)
    statusRecheckInterval = null
  }
}

function stopAllTimers() {
  stopStatusRecheck()
  stopAutoClose()
}

async function recheckAccessStatus() {
  if (isNavigatingAway.value)
    return

  await authStore.refreshSessionStatus('/captive/terhubung')
  if (isNavigatingAway.value)
    return

  const latestUser = authStore.currentUser ?? authStore.lastKnownUser
  if (!latestUser) {
    isNavigatingAway.value = true
    stopAllTimers()
    await navigateTo('/captive', { replace: true })
    return
  }

  const latestStatus = authStore.getAccessStatusFromUser(latestUser)
  if (!isConnectedStatus(latestStatus)) {
    isNavigatingAway.value = true
    stopAllTimers()
    const redirectPath = authStore.getRedirectPathForStatus(latestStatus, 'captive') || '/captive'
    await navigateTo(redirectPath, { replace: true })
  }
}

function startStatusRecheck() {
  if (!import.meta.client)
    return
  stopStatusRecheck()
  statusRecheckInterval = setInterval(() => {
    recheckAccessStatus().catch(() => {
      // best-effort periodic check
    })
  }, 4000)
}

async function redirectAfterSuccess() {
  if (!import.meta.client)
    return

  const target = resolveCaptiveSuccessRedirectTarget(captiveSuccessRedirectUrl, window.location.origin)
  if (target.startsWith('http://') || target.startsWith('https://')) {
    window.location.href = target
    return
  }

  await navigateTo(target, { replace: true })
}

async function handleDone() {
  if (isClosing.value || isNavigatingAway.value)
    return

  isClosing.value = true
  isNavigatingAway.value = true
  stopAllTimers()
  clearCaptiveContext()

  if (import.meta.client) {
    // Only attempt window.close() in popup windows. In a regular tab
    // window.close() is silently blocked by browsers; skip the 500ms wait.
    const isPopup = window.opener != null && window.opener !== window
    if (isPopup) {
      window.close()
      setTimeout(() => void redirectAfterSuccess(), 500)
    }
    else {
      void redirectAfterSuccess()
    }
  }
}

onMounted(async () => {
  const user = authStore.currentUser ?? authStore.lastKnownUser
  if (!user) {
    isNavigatingAway.value = true
    await navigateTo('/captive', { replace: true })
    return
  }

  const status = authStore.getAccessStatusFromUser(user)
  if (!isConnectedStatus(status)) {
    isNavigatingAway.value = true
    const redirectPath = authStore.getRedirectPathForStatus(status, 'captive') || '/captive'
    await navigateTo(redirectPath, { replace: true })
    return
  }

  recheckAccessStatus().catch(() => {
    // best-effort immediate check
  })
  startStatusRecheck()
  startAutoClose()
})

onBeforeUnmount(() => {
  stopAllTimers()
})
</script>

<template>
  <div class="auth-wrapper d-flex align-center justify-center pa-4">
    <VCard class="auth-card" max-width="420">
      <VCardText class="text-center">
        <VIcon icon="tabler-circle-check" size="56" class="mb-4" color="success" />
        <h4 class="text-h5 mb-2">
          Anda Terhubung!
        </h4>
        <p class="text-medium-emphasis mb-6">
          Perangkat Anda saat ini telah berhasil terhubung ke jaringan internet. Selamat menikmati layanan kami.
        </p>

        <VCard variant="tonal" color="default" class="mb-6 text-start">
          <VCardText class="py-3 px-4">
            <div class="d-flex justify-space-between align-center mb-2">
              <span class="text-medium-emphasis text-body-2">Status Akses</span>
              <span class="text-success font-weight-semibold text-body-2">Aktif</span>
            </div>
            <div class="d-flex justify-space-between align-center">
              <span class="text-medium-emphasis text-body-2">Koneksi</span>
              <span class="font-weight-semibold text-body-2">Aman & Terenkripsi</span>
            </div>
          </VCardText>
        </VCard>

        <p class="text-caption text-medium-emphasis mb-4">
          Halaman ini akan tertutup otomatis dalam {{ countdown }} detik.
        </p>

        <div class="d-flex flex-column ga-3">
          <VBtn color="primary" block :loading="isClosing" @click="handleDone">
            Mulai Browsing
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
