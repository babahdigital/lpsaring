<script lang="ts" setup>
import { formatDistanceToNow } from 'date-fns'
import { id } from 'date-fns/locale'
import { useNuxtApp } from 'nuxt/app'
import { onMounted, ref } from 'vue'
import { useDisplay } from 'vuetify'

interface LoginHistoryItem {
  login_time: string | null
  ip_address: string | null
  mac_address: string | null
  user_agent_string: string | null
}
interface DisplayHistoryItem {
  date: string
  ip_address: string
  mac_address: string
  device: string
  os: string
  icon: string
}

/* state */
const { $api } = useNuxtApp()
const _display = useDisplay() // var tak terpakai → beri prefix _
const history = ref<DisplayHistoryItem[]>([])
const loading = ref(true)
const alertMsg = ref<{ type: 'success' | 'error' | 'info', message: string } | null>(null)

/* helper user-agent */
function parseUA(ua?: string | null) {
  if (!ua)
    return { device: 'Tidak diketahui', os: 'Tidak diketahui', icon: 'tabler-device-desktop-question' }

  let device = 'Desktop'
  let os = 'OS Tidak diketahui'
  let icon = 'tabler-device-desktop'

  if (/android/i.test(ua)) { os = 'Android'; device = 'Mobile'; icon = 'tabler-device-mobile' }
  else if (/iphone|ipad|ipod/i.test(ua)) { os = 'iOS'; device = 'Mobile'; icon = 'tabler-device-mobile' }
  else if (/windows nt/i.test(ua)) { os = 'Windows'; icon = 'tabler-brand-windows' }
  else if (/macintosh|mac os x/i.test(ua)) { os = 'macOS'; icon = 'tabler-brand-apple' }
  else if (/linux/i.test(ua)) { os = 'Linux'; icon = 'tabler-brand-linux' }

  return { device, os, icon }
}

/* helper time ago */
function timeAgo(str?: string | null) {
  if (!str)
    return 'N/A'
  try { return formatDistanceToNow(new Date(str), { addSuffix: false, locale: id }) }
  catch { return String(str) } // non-binding catch → tak memicu unused-var
}

/* fetch */
async function fetchHistory() {
  loading.value = true
  alertMsg.value = null
  try {
    const resp = await $api<LoginHistoryItem[]>('/users/me/login-history', { params: { limit: 5 } })
    if (!Array.isArray(resp))
      throw new TypeError('Format respons tidak valid')

    history.value = resp.map(i => ({
      date: timeAgo(i.login_time),
      ip_address: i.ip_address || 'N/A',
      mac_address: i.mac_address || 'N/A',
      ...parseUA(i.user_agent_string),
    }))
    if (!history.value.length)
      alertMsg.value = { type: 'info', message: 'Belum ada riwayat akses.' }
  }
  catch (err: any) {
    alertMsg.value = { type: 'error', message: `Gagal memuat riwayat: ${err.data?.message || err.message}` }
    history.value = []
  }
  finally {
    loading.value = false
  }
}

onMounted(fetchHistory)
</script>

<template>
  <div>
    <div v-if="loading" class="text-center pa-6">
      <VProgressCircular indeterminate color="primary" />
    </div>

    <VAlert
      v-else-if="alertMsg"
      :type="alertMsg.type"
      variant="tonal"
      density="compact"
      class="ma-4"
    >
      {{ alertMsg.message }}
    </VAlert>

    <VList v-else-if="history.length > 0" lines="two" density="compact" class="card-list pb-8 ma-6">
      <VListItem v-for="(item, index) in history" :key="index">
        <template #prepend>
          <VAvatar rounded color="secondary" variant="tonal" class="me-3">
            <VIcon :icon="item.icon" size="22" />
          </VAvatar>
        </template>
        <VListItemTitle class="font-weight-semibold text-subtitle-1">
          {{ item.device }} ({{ item.os }})
        </VListItemTitle>
        <VListItemSubtitle class="text-caption d-flex flex-column">
          <span>IP: {{ item.ip_address }}</span>
          <span>MAC: {{ item.mac_address }}</span>
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
