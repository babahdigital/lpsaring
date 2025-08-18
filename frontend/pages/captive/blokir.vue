<script setup lang="ts">
import { definePageMeta, navigateTo, useHead } from '#imports'
import { computed, onMounted, ref } from 'vue'
import { useDisplay } from 'vuetify'

import { useAuthStore } from '~/store/auth'
import { useSettingsStore } from '~/store/settings'
import { format_for_whatsapp_link, format_to_local_phone } from '~/utils/formatters'

definePageMeta({
  layout: 'blank',
  auth: false,
})

useHead({
  title: 'Akses Diblokir - Portal Hotspot',
  meta: [
    { name: 'robots', content: 'noindex, nofollow' },
  ],
})

const authStore = useAuthStore()
const settingsStore = useSettingsStore()
const { smAndDown } = useDisplay()

// State management
const isLoading = ref(true)
const isCaptiveBrowser = ref(false)

// Computed properties
const user = computed(() => authStore.currentUser)
const adminContact = computed(() => settingsStore.settings?.ADMIN_WHATSAPP_NUMBER || '+62811580039')

const whatsappHref = computed(() => {
  const adminNumberForLink = format_for_whatsapp_link(adminContact.value)
  let text = 'Halo Admin, akun saya telah diblokir. Mohon bantuannya untuk mengatasi masalah ini.'

  if (user.value) {
    const nama = user.value.full_name || 'Tanpa Nama'
    const noHpPengguna = format_to_local_phone(user.value.phone_number) || 'Tidak terdaftar'
    text = `Halo Admin, akun saya dengan detail berikut telah diblokir:\n\n*Nama:* ${nama}\n*No. Telepon:* ${noHpPengguna}\n\nMohon bantuannya untuk mengatasi masalah ini dan mengaktifkan kembali akun saya.`
  }

  return `https://wa.me/${adminNumberForLink}?text=${encodeURIComponent(text)}`
})

const userPhone = computed(() => {
  if (!user.value?.phone_number)
    return ''
  return format_to_local_phone(user.value.phone_number)
})

const blockingReason = computed(() => {
  return user.value?.blocking_reason || 'Tidak ada alasan yang tertera'
})

// Captive browser detection
function detectCaptiveBrowser(): boolean {
  if (import.meta.server)
    return false

  const userAgent = navigator.userAgent
  const captivePatterns = [
    /CaptiveNetworkSupport/i,
    /Apple-captive/i,
    /iOS.*CaptiveNetworkSupport/i,
    /Android.*CaptivePortalLogin/i,
    /dalvik/i,
    /Microsoft-CryptoAPI/i,
    /Microsoft NCSI/i,
    /wispr/i,
    /CaptivePortal/i,
    /ConnectivityCheck/i,
    /NetworkProbe/i,
  ]

  return captivePatterns.some(pattern => pattern.test(userAgent))
}

function applyCaptiveBrowserOptimizations() {
  (window as any).__IS_CAPTIVE_BROWSER__ = true

  const style = document.createElement('style')
  style.innerHTML = `
    *, *::before, *::after {
      animation-duration: 0.01ms !important;
      animation-iteration-count: 1 !important;
      transition-duration: 0.01ms !important;
      scroll-behavior: auto !important;
    }
  `
  document.head.appendChild(style)
}

// Navigation functions
function goToLogin() {
  if (isCaptiveBrowser.value) {
    window.location.href = '/captive?flow=captive'
  }
  else {
    navigateTo('/login')
  }
}

function contactAdmin() {
  const whatsappUrl = whatsappHref.value

  if (import.meta.client) {
    // Use location.href for better compatibility in both regular and captive browsers
    window.location.href = whatsappUrl
  }
}

// Lifecycle
onMounted(async () => {
  if (import.meta.client) {
    isCaptiveBrowser.value = detectCaptiveBrowser()

    if (isCaptiveBrowser.value) {
      applyCaptiveBrowserOptimizations()
    }
  }

  // Settings are loaded by plugin automatically
  isLoading.value = false
})
</script>

<template>
  <div class="account-blocked">
    <!-- Background -->
    <div class="background-pattern" />

    <!-- Loading overlay -->
    <VOverlay
      v-model="isLoading"
      persistent
      class="d-flex align-center justify-center"
    >
      <VProgressCircular
        indeterminate
        size="48"
        color="error"
      />
      <div class="ml-4 text-body-1">
        Memuat informasi...
      </div>
    </VOverlay>

    <!-- Main content -->
    <div class="full-height-container">
      <VContainer
        fluid
        class="fill-height pa-0 d-flex align-center justify-center"
      >
        <VRow
          justify="center"
          align="center"
          class="fill-height ma-0"
          no-gutters
        >
          <VCol
            cols="12"
            sm="10"
            md="8"
            lg="6"
            xl="4"
            class="pa-4"
          >
            <!-- Main Card -->
            <VCard
              class="blocked-card mx-auto"
              :elevation="smAndDown ? 0 : 24"
              rounded="xl"
            >
              <!-- Header -->
              <div class="blocked-header">
                <div class="icon-container mb-6">
                  <svg
                    width="80"
                    height="80"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="1.5"
                    class="error-icon"
                  >
                    <circle cx="12" cy="12" r="10" />
                    <path d="M15 9l-6 6" />
                    <path d="M9 9l6 6" />
                  </svg>
                </div>

                <h1 class="blocked-title">
                  Akses Diblokir
                </h1>

                <p class="blocked-subtitle">
                  Akun Anda telah diblokir oleh administrator
                </p>
              </div>

              <!-- Content -->
              <VCardText class="pa-6">
                <!-- User info -->
                <div v-if="user" class="user-info-card mb-6">
                  <div class="d-flex align-center mb-3">
                    <svg
                      width="20"
                      height="20"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      stroke-width="2"
                      class="text-primary mr-3"
                    >
                      <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
                      <circle cx="12" cy="7" r="4" />
                    </svg>
                    <div>
                      <div class="text-body-1 font-weight-medium">
                        {{ user.full_name || 'Pengguna' }}
                      </div>
                      <div class="text-body-2 text-medium-emphasis">
                        {{ userPhone }}
                      </div>
                    </div>
                  </div>

                  <!-- Blocking reason -->
                  <div class="blocking-reason">
                    <div class="d-flex align-center mb-2">
                      <svg
                        width="16"
                        height="16"
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        stroke-width="2"
                        class="text-error mr-3"
                      >
                        <circle cx="12" cy="12" r="10" />
                        <line x1="12" y1="8" x2="12" y2="12" />
                        <line x1="12" y1="16" x2="12.01" y2="16" />
                      </svg>
                      <span class="text-body-2 font-weight-medium text-error">
                        Alasan Pemblokiran
                      </span>
                    </div>
                    <div class="text-body-2 text-medium-emphasis ml-7">
                      {{ blockingReason }}
                    </div>
                  </div>
                </div>

                <!-- Status alert -->
                <VAlert
                  color="error"
                  variant="tonal"
                  class="mb-6"
                  rounded="lg"
                >
                  <template #prepend>
                    <div class="alert-icon">
                      <svg
                        xmlns="http://www.w3.org/2000/svg"
                        width="24" height="24"
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        stroke-width="2"
                        stroke-linecap="round"
                        stroke-linejoin="round"
                      >
                        <path stroke="none" d="M0 0h24v24H0z" fill="none" />
                        <path d="M12.277 20.925c-.092 .026 -.184 .051 -.277 .075a12 12 0 0 1 -8.5 -15a12 12 0 0 0 8.5 -3a12 12 0 0 0 8.5 3a12 12 0 0 1 .145 6.232" />
                        <path d="M19 19m-3 0a3 3 0 1 0 6 0a3 3 0 1 0 -6 0" />
                        <path d="M17 21l4 -4" />
                      </svg>
                    </div>
                  </template>

                  <VAlertTitle class="text-body-1 font-weight-bold">
                    Akses Internet Diblokir
                  </VAlertTitle>

                  <div class="text-body-2 mt-2">
                    Akun Anda telah diblokir oleh administrator sistem. Untuk mengaktifkan kembali akses internet, silakan hubungi administrator.
                  </div>
                </VAlert>

                <!-- Information card -->
                <VCard
                  color="surface-variant"
                  variant="tonal"
                  class="mb-6"
                  rounded="lg"
                >
                  <VCardText class="pa-4">
                    <div class="d-flex align-center mb-3">
                      <svg
                        width="20"
                        height="20"
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        stroke-width="2"
                        class="text-info mr-3"
                      >
                        <circle cx="12" cy="12" r="10" />
                        <path d="M12 16v-4" />
                        <path d="M12 8h.01" />
                      </svg>
                      <span class="text-body-1 font-weight-medium">
                        Apa yang harus dilakukan?
                      </span>
                    </div>

                    <div class="text-body-2 text-medium-emphasis ml-8">
                      <div class="mb-2">1. Hubungi administrator melalui WhatsApp</div>
                      <div class="mb-2">2. Jelaskan situasi dan minta bantuan</div>
                      <div>3. Tunggu konfirmasi dari administrator</div>
                    </div>
                  </VCardText>
                </VCard>

                <!-- Action buttons -->
                <div class="action-buttons">
                  <!-- Contact admin button -->
                  <VBtn
                    color="error"
                    size="large"
                    block
                    rounded="lg"
                    class="mb-3 font-weight-bold"
                    @click="contactAdmin"
                  >
                    <template #prepend>
                      <svg
                        width="20"
                        height="20"
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        stroke-width="2"
                        class="mr-2"
                      >
                        <path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z" />
                      </svg>
                    </template>
                    Hubungi Administrator
                  </VBtn>

                  <!-- Back to login button -->
                  <VBtn
                    color="primary"
                    variant="outlined"
                    size="large"
                    block
                    rounded="lg"
                    class="font-weight-bold"
                    @click="goToLogin"
                  >
                    <template #prepend>
                      <svg
                        width="20"
                        height="20"
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        stroke-width="2"
                        class="mr-2"
                      >
                        <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
                        <polyline points="16,17 21,12 16,7" />
                        <line x1="21" y1="12" x2="9" y2="12" />
                      </svg>
                    </template>
                    Kembali ke Login
                  </VBtn>
                </div>
              </VCardText>

              <!-- Footer -->
              <div class="blocked-footer">
                <VDivider class="mb-4" />
                <div class="d-flex align-center justify-center">
                  <svg
                    width="16"
                    height="16"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="2"
                    class="mr-2 text-medium-emphasis"
                  >
                    <path d="M9 12l2 2 4-4" />
                    <path d="M21 12c0 4.97-4.03 9-9 9s-9-4.03-9-9 4.03-9 9-9c1.48 0 2.87.36 4.09 1" />
                  </svg>
                  <span class="text-caption text-medium-emphasis">
                    Akses akan dipulihkan setelah persetujuan administrator
                  </span>
                </div>
              </div>
            </VCard>
          </VCol>
        </VRow>
      </VContainer>
    </div>
  </div>
</template>

<style scoped>
.account-blocked {
  min-height: 100vh;
  min-height: 100dvh; /* Support for dynamic viewport height */
  position: relative;
  background: linear-gradient(135deg,
    rgba(var(--v-theme-error), 0.08) 0%,
    rgba(var(--v-theme-error), 0.12) 100%);
  overflow-y: auto; /* Allow scrolling */
}

.full-height-container {
  position: relative; /* Changed from absolute */
  width: 100%;
  min-height: 100vh;
  min-height: 100dvh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px 0; /* Add padding for mobile scroll */
}

.background-pattern {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-image:
    radial-gradient(circle at 25% 75%, rgba(var(--v-theme-error), 0.1) 0%, transparent 50%),
    radial-gradient(circle at 75% 25%, rgba(var(--v-theme-error), 0.15) 0%, transparent 50%);
  background-size: 400px 400px, 300px 300px;
  animation: float 25s ease-in-out infinite;
}

@keyframes float {
  0%, 100% { transform: translateY(0px) rotate(0deg); }
  50% { transform: translateY(-25px) rotate(-2deg); }
}

.blocked-card {
  backdrop-filter: blur(20px);
  background: rgba(255, 255, 255, 0.95);
  border: 1px solid rgba(var(--v-theme-error), 0.2);
  max-width: 500px;
  overflow: hidden;
}

.blocked-header {
  text-align: center;
  padding: 3rem 2rem 1.5rem;
  background: linear-gradient(135deg,
    rgba(var(--v-theme-error), 0.1) 0%,
    rgba(var(--v-theme-error), 0.05) 100%);
  border-bottom: 1px solid rgba(var(--v-theme-error), 0.2);
}

.icon-container {
  display: flex;
  justify-content: center;
  align-items: center;
  width: 120px;
  height: 120px;
  background: linear-gradient(135deg,
    rgb(var(--v-theme-error)),
    #d32f2f);
  border-radius: 30px;
  margin: 0 auto;
  box-shadow:
    0 8px 32px rgba(var(--v-theme-error), 0.3),
    0 0 0 1px rgba(255, 255, 255, 0.1);
}

.error-icon {
  color: white;
  filter: drop-shadow(0 2px 4px rgba(0, 0, 0, 0.2));
}

.blocked-title {
  font-size: 2.25rem;
  font-weight: 800;
  color: rgb(var(--v-theme-error));
  margin-bottom: 0.5rem;
  letter-spacing: -0.02em;
}

.blocked-subtitle {
  font-size: 1.1rem;
  font-weight: 500;
  margin: 0;
  opacity: 0.9; /* Better visibility */
}

.alert-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  color: rgb(var(--v-theme-error));
}

.alert-icon svg {
  filter: drop-shadow(0 1px 2px rgba(0, 0, 0, 0.1));
}

.user-info-card {
  background: rgba(var(--v-theme-primary), 0.05);
  border: 1px solid rgba(var(--v-theme-primary), 0.15);
  border-radius: 16px;
  padding: 1.5rem;
}

.blocking-reason {
  margin-top: 1rem;
  padding-top: 1rem;
  border-top: 1px solid rgba(var(--v-theme-outline), 0.2);
}

.action-buttons {
  margin-top: 1.5rem;
}

.blocked-footer {
  padding: 1.5rem 2rem 2rem;
  background: rgba(var(--v-theme-surface-variant), 0.3);
  border-top: 1px solid rgba(var(--v-theme-outline), 0.1);
}

/* Dark theme adjustments */
.v-theme--dark .blocked-card {
  background: rgba(30, 30, 30, 0.95);
  border: 1px solid rgba(var(--v-theme-error), 0.3);
}

.v-theme--dark .user-info-card {
  background: rgba(var(--v-theme-primary), 0.1);
  border: 1px solid rgba(var(--v-theme-primary), 0.2);
}

.v-theme--dark .blocked-footer {
  background: rgba(var(--v-theme-surface-variant), 0.1);
}

/* Mobile optimizations */
@media (max-width: 600px) {
  .account-blocked {
    background: rgb(var(--v-theme-surface));
  }

  .background-pattern {
    opacity: 0.3;
  }

  .blocked-card {
    background: rgb(var(--v-theme-surface));
    box-shadow: none !important;
    border: none;
  }

  .blocked-header {
    padding: 2rem 1.5rem 1rem;
  }

  .icon-container {
    width: 100px;
    height: 100px;
    border-radius: 25px;
  }

  .blocked-title {
    font-size: 2rem;
  }

  .blocked-subtitle {
    font-size: 1rem;
  }
}

/* Captive browser optimizations */
.__IS_CAPTIVE_BROWSER__ .blocked-card {
  animation: none !important;
  transition: none !important;
}

.__IS_CAPTIVE_BROWSER__ .background-pattern {
  animation: none !important;
}
</style>
