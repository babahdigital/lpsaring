<script lang="ts" setup>
import { useNuxtApp } from '#app'
import { onMounted, ref } from 'vue'
import { useDisplay } from 'vuetify'

interface LoginHistoryItem {
  login_time: string | null
  ip_address: string | null
  user_agent_string: string | null
}

interface DisplayHistoryItem {
  date: string
  ip_address: string
  device: string
  os: string
  icon: string
}

// --- Inisialisasi & State ---
const { $api } = useNuxtApp()
const display = useDisplay()
const loginHistory = ref<DisplayHistoryItem[]>([])
const loginHistoryLoading = ref(true)
const loginHistoryAlert = ref<{ type: 'success' | 'error' | 'info', message: string } | null>(null)

// --- Fungsi ---
function parseUserAgent(uaString?: string | null): { device: string, os: string, icon: string } {
  if (!uaString)
    return { device: 'Tidak diketahui', os: 'Tidak diketahui', icon: 'tabler-device-desktop-question' }
  let device = 'Desktop'
  let os = 'OS Tidak diketahui'
  let icon = 'tabler-device-desktop'
  if (/android/i.test(uaString)) { os = 'Android'; device = 'Mobile'; icon = 'tabler-device-mobile' }
  else if (/iphone|ipad|ipod/i.test(uaString)) { os = 'iOS'; device = 'Mobile'; icon = 'tabler-device-mobile' }
  else if (/windows nt/i.test(uaString)) { os = 'Windows'; icon = 'tabler-brand-windows' }
  else if (/macintosh|mac os x/i.test(uaString)) { os = 'macOS'; icon = 'tabler-brand-apple' }
  else if (/linux/i.test(uaString)) { os = 'Linux'; icon = 'tabler-brand-linux' }
  return { device, os, icon }
}

function formatDate(dateString?: string | Date | null) {
  if (!dateString)
    return 'N/A'
  const isMobile = display.smAndDown.value
  const options: Intl.DateTimeFormatOptions = isMobile
    ? { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }
    : { year: 'numeric', month: 'long', day: 'numeric', hour: '2-digit', minute: '2-digit' }
  try { return new Date(dateString).toLocaleString('id-ID', options) }
  catch (e) { return String(dateString) }
}

async function fetchLoginHistory() {
  loginHistoryLoading.value = true
  loginHistoryAlert.value = null
  try {
    const response = await $api<LoginHistoryItem[]>('/users/me/login-history', { params: { limit: 5 } }) // Mengambil 5 data terakhir

    if (Array.isArray(response)) {
      loginHistory.value = response.map((item: LoginHistoryItem) => ({
        date: formatDate(item.login_time),
        ip_address: item.ip_address || 'N/A',
        ...parseUserAgent(item.user_agent_string),
      }))
      if (loginHistory.value.length === 0) {
        loginHistoryAlert.value = { type: 'info', message: 'Belum ada riwayat akses.' }
      }
    }
    else {
      throw new TypeError('Format respons data riwayat tidak valid.')
    }
  }
  catch (error: any) {
    loginHistoryAlert.value = { type: 'error', message: `Gagal memuat riwayat: ${error.data?.message || error.message}` }
    loginHistory.value = []
  }
  finally {
    loginHistoryLoading.value = false
  }
}

onMounted(fetchLoginHistory)
</script>

<template>
  <div>
    <div v-if="loginHistoryLoading" class="text-center pa-6">
      <VProgressCircular indeterminate color="primary" />
    </div>
    <VAlert
      v-else-if="loginHistoryAlert"
      :type="loginHistoryAlert.type"
      variant="tonal"
      density="compact"
      class="ma-4"
    >
      {{ loginHistoryAlert.message }}
    </VAlert>
    <VList v-else-if="loginHistory.length > 0" lines="two" density="compact" class="card-list pb-8 ma-6">
      <VListItem v-for="(item, index) in loginHistory" :key="index">
        <template #prepend>
          <VAvatar rounded color="secondary" variant="tonal" class="me-3">
            <VIcon :icon="item.icon" size="22" />
          </VAvatar>
        </template>
        <VListItemTitle class="font-weight-semibold text-subtitle-1">
          {{ item.device }} ({{ item.os }})
        </VListItemTitle>
        <VListItemSubtitle class="text-caption">
          IP: {{ item.ip_address }}
        </VListItemSubtitle>
        <template #append>
          <span class="text-caption text-disabled">{{ item.date }}</span>
        </template>
      </VListItem>
    </VList>
  </div>
</template>

<style lang="scss" scoped>
.card-list {
  --v-card-list-padding: 0.5rem;
  margin-top: 1px !important;
}
</style>
