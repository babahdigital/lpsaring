<script setup lang="ts">
import type { VDataTableServer } from 'vuetify/labs/VDataTable'
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useDisplay } from 'vuetify'
import UserFilterDialog from '@/components/admin/log/UserFilterDialog.vue'
import UserActionConfirmDialog from '@/components/admin/users/UserActionConfirmDialog.vue'
import { useSnackbar } from '@/composables/useSnackbar'
import { useAuthStore } from '@/store/auth'

// --- Tipe Data ---
interface AdminUserInfo {
  id: string
  full_name: string
  phone_number: string
}

interface AdminActionLog {
  id: string
  action_type: string
  details: string | null
  created_at: string
  admin: AdminUserInfo
  target_user: AdminUserInfo | null
}
type DatatableOptions = InstanceType<typeof VDataTableServer>['options']

// --- State Management ---
const { $api } = useNuxtApp()
const { smAndDown } = useDisplay()
const isHydrated = ref(false)
const isMobile = computed(() => (isHydrated.value ? smAndDown.value : false))
const authStore = useAuthStore()
const { add: showSnackbar } = useSnackbar()

const exportLoading = ref(false)
const options = ref<DatatableOptions>({ page: 1, itemsPerPage: 15, sortBy: [{ key: 'created_at', order: 'desc' }] })

// --- State untuk Filter ---
const search = ref('')
const startDate = ref<Date | null>(null)
const endDate = ref<Date | null>(null)
const isStartDateMenuOpen = ref(false)
const isEndDateMenuOpen = ref(false)
const adminFilter = ref<AdminUserInfo | null>(null)
const targetUserFilter = ref<AdminUserInfo | null>(null)

// --- State untuk Dialog ---
const isUserFilterDialogOpen = ref(false)
const userFilterMode = ref<'admin' | 'target'>('admin')
const confirmDialog = reactive({
  visible: false,
  title: '',
  message: '',
  action: async () => {},
})

// --- Data Fetching ---
const queryParams = computed(() => ({
  page: options.value.page,
  itemsPerPage: options.value.itemsPerPage,
  sortBy: options.value.sortBy[0]?.key ?? 'created_at',
  sortOrder: options.value.sortBy[0]?.order ?? 'desc',
  search: search.value,
  admin_id: adminFilter.value?.id,
  target_user_id: targetUserFilter.value?.id,
  start_date: startDate.value ? startDate.value.toISOString() : undefined,
  end_date: endDate.value ? endDate.value.toISOString() : undefined,
}))

const { data: fetchedData, pending: loading, error, refresh } = useAsyncData(
  'fetch-logs',
  () => $api<{ items: AdminActionLog[], totalItems: number }>('/admin/action-logs', {
    params: queryParams.value,
  }),
  { watch: [queryParams] },
)

const logList = computed(() => fetchedData.value?.items ?? [])
const totalLogs = computed(() => fetchedData.value?.totalItems ?? 0)

const hasLoadedOnce = ref(false)
const showInitialSkeleton = computed(() => loading.value === true && hasLoadedOnce.value === false)
const showSilentRefreshing = computed(() => loading.value === true && hasLoadedOnce.value === true)

onMounted(() => {
  isHydrated.value = true
})

watch(loading, (val) => {
  if (val === false)
    hasLoadedOnce.value = true
}, { immediate: true })

watch(error, (newError) => {
  if (newError) {
    const errData = (newError as { data?: { message?: string } }).data
    showSnackbar({ type: 'error', title: 'Gagal Memuat Log', text: errData?.message ?? 'Terjadi kesalahan server.' })
  }
})

// --- Helper, Kamus, dan Fungsi Format ---
const hasActiveFilters = computed(() => adminFilter.value !== null || targetUserFilter.value !== null || startDate.value !== null)
const formatPhoneNumber = (phone?: string) => phone != null ? phone.replace('+62', '0') : ''
const formatDateTime = (date: string) => new Date(date).toLocaleString('id-ID', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' })
const formatDate = (date: Date | null) => date !== null ? new Date(date).toLocaleDateString('id-ID', { day: '2-digit', month: 'long', year: 'numeric' }) : ''

const actionDisplayMap = computed(() => ({
  CREATE_USER: { color: 'success', icon: 'tabler-user-plus' },
  APPROVE_USER: { color: 'success', icon: 'tabler-user-check' },
  REJECT_USER: { color: 'error', icon: 'tabler-user-x' },
  UPDATE_USER_PROFILE: { color: 'primary', icon: 'tabler-edit' },
  DEACTIVATE_USER: { color: 'warning', icon: 'tabler-user-off' },
  RESET_HOTSPOT_PASSWORD: { color: 'warning', icon: 'tabler-key' },
  GENERATE_ADMIN_PASSWORD: { color: 'warning', icon: 'tabler-key-off' },
  INJECT_QUOTA: { color: 'primary', icon: 'tabler-database-plus' },
  MANUAL_USER_DELETE: { color: 'error', icon: 'tabler-trash' },
  CHANGE_USER_ROLE: { color: 'info', icon: 'tabler-users' },
  UPGRADE_TO_ADMIN: { color: 'info', icon: 'tabler-arrow-up-circle' },
  DOWNGRADE_FROM_ADMIN: { color: 'info', icon: 'tabler-arrow-down-circle' },
  SET_UNLIMITED_STATUS: { color: 'purple', icon: 'tabler-infinity' },
  REVOKE_UNLIMITED_STATUS: { color: 'orange', icon: 'tabler-infinity-off' },
  PROCESS_QUOTA_REQUEST_APPROVE: { color: 'success', icon: 'tabler-checks' },
  PROCESS_QUOTA_REQUEST_REJECT: { color: 'error', icon: 'tabler-x' },
  PROCESS_QUOTA_REQUEST_PARTIALLY_APPROVED: { color: 'info', icon: 'tabler-check' },
  DEFAULT: { color: 'secondary', icon: 'tabler-question-mark' },
}))
const getActionChip = (action: string) => actionDisplayMap.value[action as keyof typeof actionDisplayMap.value] ?? actionDisplayMap.value.DEFAULT

const keyDictionary: Record<string, string> = {
  is_unlimited_user: 'Status Unlimited',
  is_active: 'Status Akun',
  full_name: 'Nama Lengkap',
  role: 'Peran',
  blok: 'Blok',
  kamar: 'Kamar',
  added_mb: 'Kuota',
  added_days: 'Masa Aktif',
  injected_quota: 'Injeksi Kuota',
  status: 'Status',
  profile: 'Profil Mikrotik',
  reason: 'Alasan',
  result: 'Hasil',
}

function formatValue(key: string, value: any): string {
  if (typeof value === 'boolean')
    return value ? 'Aktif' : 'Nonaktif'

  if (key === 'added_mb' && typeof value === 'number')
    return `${(value / 1024).toFixed(2)} GB`

  if (key === 'added_days' && typeof value === 'number')
    return `${value} hari`

  if (typeof value === 'object' && value !== null) {
    if (value.gb != null && value.days != null)
      return `${value.gb} GB & ${value.days} hari`
    return JSON.stringify(value)
  }
  if (typeof value === 'string' && value.includes('MB')) {
    const mbValue = Number.parseFloat(value.match(/(\d+)\s*MB/)?.[1] ?? '0')
    if (mbValue > 0) {
      const gbValue = (mbValue / 1024).toFixed(2)
      return value.replace(/(\d+)\s*MB/, `${gbValue} GB`)
    }
  }
  return String(value)
}

function formatLogDetails(log: AdminActionLog): string {
  if (log.details == null)
    return '-'
  try {
    const details = JSON.parse(log.details)
    const parts: string[] = []
    switch (log.action_type) {
      case 'CREATE_USER': return `Membuat pengguna baru dengan peran '${details.role}'.`
      case 'DEACTIVATE_USER': return `Alasan: ${details.reason ?? 'Tidak ada'}.`
      case 'INJECT_QUOTA': {
        const addedParts: string[] = []
        if (details.added_mb != null && Number(details.added_mb) > 0)
          addedParts.push(`${(Number(details.added_mb) / 1024).toFixed(2)} GB`)

        if (details.added_days != null && Number(details.added_days) > 0)
          addedParts.push(`${details.added_days} hari`)

        return `Menambah ${addedParts.join(' & ')}.`
      }
      case 'SET_UNLIMITED_STATUS':
      case 'REVOKE_UNLIMITED_STATUS':
        return `Status diubah menjadi '${formatValue('status', details.status)}', profil Mikrotik diatur ke '${details.profile}'.`
      case 'UPDATE_USER_PROFILE':
        for (const key in details)
          parts.push(`Mengubah ${keyDictionary[key] ?? key} menjadi '${formatValue(key, details[key])}'.`)

        return parts.join(' ')
      default:
        return Object.entries(details)
          .map(([key, value]) => `${keyDictionary[key] ?? key}: ${formatValue(key, value)}`)
          .join('; ')
    }
  }
  catch {
    return log.details
  }
}

// --- Fungsi Aksi ---
function openUserFilter(mode: 'admin' | 'target') {
  userFilterMode.value = mode
  isUserFilterDialogOpen.value = true
}
function handleUserSelected(user: AdminUserInfo) {
  if (userFilterMode.value === 'admin')
    adminFilter.value = user
  else targetUserFilter.value = user
  isUserFilterDialogOpen.value = false
}
function clearAllFilters() {
  startDate.value = null
  endDate.value = null
  adminFilter.value = null
  targetUserFilter.value = null
  search.value = ''
}
async function exportLogs(format: 'csv' | 'txt') {
  exportLoading.value = true
  try {
    const exportParams = { ...queryParams.value, format, page: 1, itemsPerPage: -1 }
    const data = await $api('/admin/action-logs/export', { params: exportParams, responseType: 'blob' })
    const url = window.URL.createObjectURL(new Blob([data as BlobPart]))
    const link = document.createElement('a')
    link.href = url
    link.setAttribute('download', `log-aktivitas-${new Date().toISOString().split('T')[0]}.${format}`)
    document.body.appendChild(link)
    link.click()
    link.remove()
    showSnackbar({ type: 'success', title: 'Berhasil', text: 'Laporan log berhasil diunduh.' })
  }
  catch (err: any) {
    showSnackbar({ type: 'error', title: 'Gagal', text: err.data?.message ?? 'Gagal mengunduh laporan.' })
  }
  finally {
    exportLoading.value = false
  }
}
function openClearLogDialog() {
  confirmDialog.title = 'Hapus Semua Log Aktivitas'
  confirmDialog.message = 'Anda yakin ingin menghapus **semua** catatan log secara permanen? Aksi ini tidak dapat dibatalkan.'
  confirmDialog.action = async () => {
    try {
      const response = await $api<any>('/admin/action-logs', { method: 'DELETE' })
      showSnackbar({ type: 'success', title: 'Berhasil', text: response.message })
      refresh()
    }
    catch (err: any) {
      showSnackbar({ type: 'error', title: 'Gagal', text: err.data?.message ?? 'Gagal menghapus log.' })
    }
  }
  confirmDialog.visible = true
}

// --- Headers & Metadata ---
const headers = computed(() => {
  const base = [
    { title: 'Waktu', key: 'created_at', width: '180px' },
    { title: 'Admin Pelaku', key: 'admin', sortable: false },
    { title: 'Aksi', key: 'action_type', align: 'center', width: '220px' },
    { title: 'Detail Aksi', key: 'details', sortable: false, width: '30%' },
    { title: 'Target Pengguna', key: 'target_user', sortable: false },
  ]
  return isMobile.value ? base.filter(h => ['admin', 'action_type'].includes(h.key)) : base
})

definePageMeta({ requiredRole: ['ADMIN', 'SUPER_ADMIN'] })
useHead({ title: 'Log Aktivitas Admin' })
</script>

<template>
  <div>
    <VCard class="mb-6 rounded-lg">
      <VCardItem>
        <VCardTitle class="d-flex align-center flex-wrap gap-2">
          <VIcon icon="tabler-filter" class="me-2" />
          Filter & Pencarian Log
        </VCardTitle>
      </VCardItem>
      <VCardText class="pa-5 pt-0">
        <VRow class="d-flex flex-wrap gap-y-4 align-center">
          <VCol cols="12" sm="6" md="3">
            <VTextField id="start-date-activator" :model-value="formatDate(startDate)" label="Tanggal Mulai" readonly clearable prepend-inner-icon="tabler-calendar" @click:clear="startDate = null" />
            <VMenu v-model="isStartDateMenuOpen" activator="#start-date-activator" :close-on-content-click="false">
              <VDatePicker v-model="startDate" no-title color="primary" :max="new Date()" @update:model-value="isStartDateMenuOpen = false" />
            </VMenu>
          </VCol>
          <VCol cols="12" sm="6" md="3">
            <VTextField id="end-date-activator" :model-value="formatDate(endDate)" label="Tanggal Akhir" readonly clearable :disabled="!startDate" prepend-inner-icon="tabler-calendar" @click:clear="endDate = null" />
            <VMenu v-model="isEndDateMenuOpen" activator="#end-date-activator" :close-on-content-click="false">
              <VDatePicker v-model="endDate" no-title color="primary" :min="startDate" :max="new Date()" @update:model-value="isEndDateMenuOpen = false" />
            </VMenu>
          </VCol>
          <VCol cols="12" sm="6" md="3">
            <VBtn block prepend-icon="tabler-user-shield" variant="outlined" color="primary" height="48" @click="openUserFilter('admin')">
              Filter Admin
            </VBtn>
          </VCol>
          <VCol cols="12" sm="6" md="3">
            <VBtn block prepend-icon="tabler-user-search" variant="outlined" color="primary" height="48" @click="openUserFilter('target')">
              Filter Target
            </VBtn>
          </VCol>
        </VRow>
        <VRow v-if="hasActiveFilters" class="mt-4">
          <VCol cols="12" class="d-flex flex-wrap gap-2 align-center">
            <VChip v-if="adminFilter" color="primary" closable prepend-icon="tabler-user-shield" @click:close="adminFilter = null">
              Admin: {{ adminFilter.full_name }}
            </VChip>
            <VChip v-if="targetUserFilter" color="primary" closable prepend-icon="tabler-user" @click:close="targetUserFilter = null">
              Target: {{ targetUserFilter.full_name }}
            </VChip>
            <VChip v-if="startDate" color="primary" closable prepend-icon="tabler-calendar" @click:close="() => { startDate = null; endDate = null; }">
              Periode Aktif
            </VChip>
            <VBtn variant="text" color="secondary" size="small" class="ms-2" @click="clearAllFilters">
              Reset Semua Filter
            </VBtn>
          </VCol>
        </VRow>
      </VCardText>
    </VCard>

    <VCard class="rounded-lg">
      <VCardTitle class="d-flex align-center flex-wrap">
        <VIcon icon="tabler-history" class="me-2" />
        <span class="text-h6">Hasil Log Aktivitas</span>
        <VSpacer />
        <div class="d-flex align-center gap-2">
          <VMenu offset-y>
            <template #activator="{ props }">
              <VBtn color="secondary" v-bind="props" prepend-icon="tabler-download" :loading="exportLoading">
                Ekspor
              </VBtn>
            </template>
            <VList density="compact">
              <VListItem @click="exportLogs('csv')">
                <VListItemTitle>CSV</VListItemTitle>
              </VListItem>
              <VListItem @click="exportLogs('txt')">
                <VListItemTitle>TXT</VListItemTitle>
              </VListItem>
            </VList>
          </VMenu>
          <VBtn v-if="authStore.isSuperAdmin" color="error" prepend-icon="tabler-trash" @click="openClearLogDialog">
            Hapus Log
          </VBtn>
        </div>
      </VCardTitle>

      <VCardText class="py-3 px-6 logs-toolbar">
        <DataTableToolbar
          v-model:items-per-page="options.itemsPerPage"
          v-model:search="search"
          search-placeholder="Cari di semua data log..."
          @update:items-per-page="() => (options.page = 1)"
        >
          <template #end>
            <div class="text-body-2 text-disabled">
              {{ totalLogs }} log
            </div>
          </template>
        </DataTableToolbar>
      </VCardText>

      <VProgressLinear
        v-if="showSilentRefreshing"
        indeterminate
        color="primary"
        height="2"
      />

      <client-only>
        <VDataTableServer v-if="!isMobile" v-model:options="options" :headers="headers" :items="logList" :items-length="totalLogs" :loading="showInitialSkeleton" class="text-no-wrap" item-value="id" hide-default-footer>
          <template #item.created_at="{ item }">
            <VTooltip location="top">
              <template #activator="{ props }">
                <span v-bind="props">{{ formatDateTime(item.created_at) }}</span>
              </template><span>{{ new Date(item.created_at).toLocaleString('id-ID', { dateStyle: 'full', timeStyle: 'long' }) }}</span>
            </VTooltip>
          </template>
          <template #item.admin="{ item }">
            <div v-if="item.admin !== null" class="d-flex flex-column">
              <span class="font-weight-medium">{{ item.admin.full_name }}</span><small class="text-disabled">{{ formatPhoneNumber(item.admin.phone_number) }}</small>
            </div><span v-else class="text-disabled">Sistem</span>
          </template>
          <template #item.action_type="{ item }">
            <VChip :color="getActionChip(item.action_type).color" size="small" label>
              <VIcon :icon="getActionChip(item.action_type).icon" start size="16" />{{ item.action_type.replace(/_/g, ' ') }}
            </VChip>
          </template>
          <template #item.details="{ item }">
            <p class="text-body-2 mb-0" style="max-width: 450px; white-space: normal;">
              {{ formatLogDetails(item) }}
            </p>
          </template>
          <template #item.target_user="{ item }">
            <div v-if="item.target_user !== null" class="d-flex flex-column">
              <span class="font-weight-medium">{{ item.target_user.full_name }}</span><small class="text-disabled">{{ formatPhoneNumber(item.target_user.phone_number) }}</small>
            </div><span v-else class="text-disabled">N/A</span>
          </template>
          <template #no-data>
            <div class="text-center py-8 text-disabled">
              Tidak ada data log yang cocok dengan filter.
            </div>
          </template>
          <template #loading>
            <div v-if="showInitialSkeleton" class="pa-5">
              <div v-for="i in 5" :key="i" class="d-flex align-center w-100 pa-4">
                <div class="flex-grow-1">
                  <VSkeletonLoader type="text" width="90%" />
                </div>
                <div class="flex-grow-1">
                  <VSkeletonLoader type="text" width="70%" />
                </div>
              </div>
            </div>
          </template>
        </VDataTableServer>

        <TablePagination
          v-if="!isMobile && totalLogs > 0"
          :page="options.page"
          :items-per-page="options.itemsPerPage"
          :total-items="totalLogs"
          @update:page="val => (options.page = val)"
        />

        <div v-else class="pa-4">
          <div v-if="showInitialSkeleton" class="pa-5">
            <VCard v-for="i in 3" :key="i" class="mb-3">
              <VSkeletonLoader type="list-item-two-line" />
            </VCard>
          </div>
          <div v-else-if="logList.length === 0" class="py-8 text-center text-disabled">
            <VIcon icon="tabler-database-off" size="32" class="mb-2" /><p>Tidak ada data log.</p>
          </div>
          <VCard v-for="log in logList" v-else :key="log.id" class="mb-3">
            <VList lines="two" density="compact" class="py-0">
              <VListItem>
                <template #prepend>
                  <VIcon :icon="getActionChip(log.action_type).icon" :color="getActionChip(log.action_type).color" />
                </template>
                <VListItemTitle class="font-weight-bold">
                  {{ log.action_type.replace(/_/g, ' ') }}
                </VListItemTitle>
                <VListItemSubtitle>{{ formatDateTime(log.created_at) }}</VListItemSubtitle>
              </VListItem>
            </VList>
            <VDivider />
            <VCardText>
              <div class="mb-2">
                <strong>Admin:</strong> {{ log.admin.full_name }}
              </div>
              <div v-if="log.target_user !== null" class="mb-2">
                <strong>Target:</strong> {{ log.target_user.full_name }}
              </div>
              <div><strong>Detail:</strong> {{ formatLogDetails(log) }}</div>
            </VCardText>
          </VCard>

          <TablePagination
            v-if="totalLogs > 0"
            :page="options.page"
            :items-per-page="options.itemsPerPage"
            :total-items="totalLogs"
            @update:page="val => (options.page = val)"
          />
        </div>

        <template #fallback>
          <div class="d-flex justify-center align-center pa-10">
            <VProgressCircular indeterminate color="primary" size="64" />
          </div>
        </template>
      </client-only>
    </VCard>

    <UserFilterDialog v-model="isUserFilterDialogOpen" :mode="userFilterMode" :role-filter="userFilterMode === 'admin' ? ['ADMIN', 'SUPER_ADMIN'] : []" @select="handleUserSelected" />
    <UserActionConfirmDialog v-model="confirmDialog.visible" :title="confirmDialog.title" :message="confirmDialog.message" color="error" :loading="loading" @confirm="confirmDialog.action" />
  </div>
</template>

<style scoped>
.logs-toolbar :deep(.datatable-toolbar__search) {
  min-width: 320px;
}
</style>
