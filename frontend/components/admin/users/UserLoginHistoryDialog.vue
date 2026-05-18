<script lang="ts" setup>
import { computed, ref, watch } from 'vue'
import { format } from 'date-fns'
import { id as idLocale } from 'date-fns/locale'
import { useDisplay } from 'vuetify'
import type { AdminUserLoginHistoryItem, AdminUserLoginHistoryResponse } from '@/types/api/contracts'
import { useSnackbar } from '@/composables/useSnackbar'

interface SimpleUser {
  id: string
  full_name: string
  phone_number: string
}

const props = defineProps<{ modelValue: boolean, user: SimpleUser | null }>()
const emit = defineEmits<{ (e: 'update:modelValue', value: boolean): void }>()

const { mobile: isMobile } = useDisplay()
const { add: addSnackbar } = useSnackbar()
const { $api } = useNuxtApp()

const items = ref<AdminUserLoginHistoryItem[]>([])
const loading = ref(false)
const totalItems = ref(0)
const page = ref(1)
const itemsPerPage = ref(25)

const dialogVisible = computed({
  get: () => props.modelValue,
  set: (value: boolean) => emit('update:modelValue', value),
})

const totalPages = computed(() => Math.max(1, Math.ceil(totalItems.value / itemsPerPage.value)))

async function fetchLoginHistory() {
  if (!props.user)
    return
  loading.value = true
  try {
    const data = await $api<AdminUserLoginHistoryResponse>(
      `/admin/users/${props.user.id}/login-history`,
      { query: { page: page.value, itemsPerPage: itemsPerPage.value } },
    )
    items.value = data.items ?? []
    totalItems.value = data.totalItems ?? 0
  }
  catch (e: any) {
    addSnackbar({ title: 'Gagal memuat riwayat login', text: e?.message || 'Coba lagi.', type: 'error' })
    items.value = []
    totalItems.value = 0
  }
  finally {
    loading.value = false
  }
}

watch(() => props.modelValue, (open) => {
  if (open && props.user) {
    page.value = 1
    fetchLoginHistory()
  }
})

watch(page, (newPage, oldPage) => {
  if (props.modelValue && newPage !== oldPage)
    fetchLoginHistory()
})

function formatTime(iso: string | null | undefined): string {
  if (!iso)
    return '—'
  try {
    return format(new Date(iso), 'dd MMM yyyy HH:mm', { locale: idLocale })
  }
  catch {
    return iso
  }
}

// Privacy: mask IPv4 octet terakhir (192.168.1.23 → 192.168.1.*).
// IPv6 lebih kompleks; hanya mask 64 bit terakhir.
function maskIp(ip: string | null | undefined): string {
  if (!ip)
    return '—'
  const v4 = ip.match(/^(\d{1,3}\.\d{1,3}\.\d{1,3})\.\d{1,3}$/)
  if (v4)
    return `${v4[1]}.*`
  if (ip.includes(':'))
    return `${ip.split(':').slice(0, 4).join(':')}::*`
  return ip
}

function uaShort(ua: string | null | undefined): string {
  if (!ua)
    return '—'
  const match = ua.match(/(iPhone|iPad|Android|Windows NT|Mac OS X|Linux)/)
  const browser = ua.match(/(Safari|Chrome|Firefox|Edge|SamsungBrowser|OPR)/)
  const os = match?.[0] ?? 'Unknown OS'
  const bw = browser?.[0] ?? ''
  return bw ? `${os} · ${bw}` : os
}

function onClose() {
  dialogVisible.value = false
}
</script>

<template>
  <VDialog v-model="dialogVisible" :fullscreen="isMobile" :max-width="isMobile ? undefined : 720" scrollable>
    <VCard v-if="props.user" :class="isMobile ? 'rounded-0' : 'rounded-lg'">
      <VCardTitle class="d-flex align-center justify-space-between pa-4">
        <div>
          <div class="text-h6">Riwayat Login</div>
          <div class="text-caption text-medium-emphasis">
            {{ props.user.full_name }} · {{ props.user.phone_number }}
          </div>
        </div>
        <VBtn icon="tabler-x" variant="text" size="small" @click="onClose" />
      </VCardTitle>
      <VDivider />
      <VCardText class="pa-0">
        <div v-if="loading" class="d-flex justify-center align-center" style="min-height: 200px;">
          <VProgressCircular indeterminate color="primary" />
        </div>
        <div v-else-if="items.length === 0" class="text-center text-medium-emphasis py-10">
          <VIcon icon="tabler-history-off" size="48" class="mb-3" />
          <p>Belum ada riwayat login untuk user ini.</p>
        </div>
        <VTable v-else density="comfortable">
          <thead>
            <tr>
              <th>Waktu</th>
              <th>IP Address</th>
              <th>Device / Browser</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in items" :key="row.id">
              <td class="text-no-wrap">
                {{ formatTime(row.login_time) }}
              </td>
              <td class="font-weight-medium">
                {{ maskIp(row.ip_address) }}
              </td>
              <td class="text-medium-emphasis">
                {{ uaShort(row.user_agent) }}
              </td>
            </tr>
          </tbody>
        </VTable>
      </VCardText>
      <VDivider v-if="items.length > 0" />
      <VCardActions v-if="items.length > 0" class="pa-3 d-flex align-center justify-space-between">
        <div class="text-caption text-medium-emphasis">
          Total: {{ totalItems }} · Halaman {{ page }}/{{ totalPages }}
        </div>
        <VPagination v-model="page" :length="totalPages" :total-visible="5" density="comfortable" />
      </VCardActions>
    </VCard>
  </VDialog>
</template>
