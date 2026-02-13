<script lang="ts" setup>
import type { VDataTableServer } from 'vuetify/labs/VDataTable'
import { onMounted, ref, watch } from 'vue'
import RequestFormDialog from '@/components/komandan/RequestFormDialog.vue'

// --- [PENYEMPURNAAN] Interface data yang lebih rapi ---
interface RequestHistoryItem {
  id: string
  created_at: string
  request_type: 'QUOTA' | 'UNLIMITED'
  status: 'PENDING' | 'APPROVED' | 'REJECTED' | 'PARTIALLY_APPROVED'
  requested_mb: number | null
  requested_duration_days: number | null
  processed_at: string | null
  rejection_reason: string | null
  processed_by_admin: string | null
  granted_details?: {
    granted_mb?: number
    granted_duration_days?: number
  } | null
}

type Options = InstanceType<typeof VDataTableServer>['options']
type SortItem = NonNullable<Options['sortBy']>[number]

// --- Inisialisasi & State ---
useHead({ title: 'Riwayat Permintaan Saya' })
const { $api } = useNuxtApp()

const requests = ref<RequestHistoryItem[]>([])
const loading = ref(true)
const totalRequests = ref(0)
const options = ref<Options>({
  page: 1,
  itemsPerPage: 10,
  sortBy: [{ key: 'created_at', order: 'desc' }],
  groupBy: [],
  search: undefined,
})

const snackbar = reactive({ show: false, text: '', color: 'info' })
const isRequestFormVisible = ref(false)

// --- Watchers & Lifecycle ---
watch(options, () => fetchRequests(), { deep: true })
onMounted(fetchRequests)

// --- Logika Inti ---
async function fetchRequests() {
  loading.value = true
  try {
    const params = new URLSearchParams({
      page: String(options.value.page),
      itemsPerPage: String(options.value.itemsPerPage),
    })

    if (Array.isArray(options.value.sortBy)) {
      options.value.sortBy.forEach((sortItem: SortItem) => {
        if (sortItem?.key) {
          params.append('sortBy', sortItem.key)
          params.append('sortOrder', sortItem.order ?? 'asc')
        }
      })
    }

    const response = await $api<{ items: RequestHistoryItem[], totalItems: number }>(`/komandan/requests/history?${params.toString()}`)

    requests.value = response.items
    totalRequests.value = response.totalItems
  }
  catch (error: any) {
    // PERBAIKAN: Mengganti || dengan ?? untuk nilai fallback yang eksplisit.
    showSnackbar(`Gagal mengambil data: ${error.data?.message ?? 'Server error'}`, 'error')
  }
  finally {
    loading.value = false
  }
}

// --- [PENYEMPURNAAN] Tampilan & Formatting ---
const headers = [
  { title: 'TANGGAL PENGAJUAN', key: 'created_at', sortable: true, width: '200px' },
  { title: 'TIPE', key: 'request_type', sortable: true },
  { title: 'DETAIL PERMINTAAN', key: 'details', sortable: false, minWidth: '250px' },
  { title: 'STATUS', key: 'status', sortable: true },
  { title: 'AKSI ADMIN', key: 'processed_at', sortable: true },
]

const statusMap: Record<RequestHistoryItem['status'], { text: string, color: string, icon: string }> = {
  PENDING: { text: 'Menunggu', color: 'warning', icon: 'tabler-hourglass' },
  APPROVED: { text: 'Disetujui', color: 'success', icon: 'tabler-check' },
  REJECTED: { text: 'Ditolak', color: 'error', icon: 'tabler-x' },
  PARTIALLY_APPROVED: { text: 'Disetujui Sebagian', color: 'info', icon: 'tabler-discount' },
}

const requestTypeMap: Record<RequestHistoryItem['request_type'], { text: string, color: string, icon: string }> = {
  QUOTA: { text: 'Kuota', color: 'primary', icon: 'tabler-database' },
  UNLIMITED: { text: 'Unlimited', color: 'success', icon: 'tabler-infinity' },
}

const requestTypeMapAny: Record<string, { text: string, color: string, icon: string }> = requestTypeMap
const statusMapAny: Record<string, { text: string, color: string, icon: string }> = statusMap
const getRequestTypeMetaByKey = (key: unknown) => requestTypeMapAny[String(key)]
const getStatusMetaByKey = (key: unknown) => statusMapAny[String(key)]

// [PERBAIKAN] Fungsi untuk format MB ke GB
function formatQuotaToGB(mb: number | null | undefined): string {
  if (typeof mb !== 'number')
    return 'N/A'
  if (mb === 0)
    return '0 GB'
  const gb = mb / 1024
  // Menghilangkan .00 jika tidak ada desimal
  return `${gb.toFixed(2).replace(/\.00$/, '')} GB`
}

function formatDateTime(dateString: string | null) {
  // PERBAIKAN: Mengganti !dateString dengan pengecekan null dan string kosong yang eksplisit.
  if (dateString == null || dateString === '')
    return '-'
  return new Date(dateString).toLocaleString('id-ID', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function showSnackbar(text: string, color = 'info') {
  snackbar.text = text
  snackbar.color = color
  snackbar.show = true
}
useHead({ title: 'Request Quota' })
</script>

<template>
  <div>
    <VCard class="mb-6 rounded-lg">
      <VCardItem>
        <template #prepend>
          <VIcon icon="tabler-history" color="primary" size="32" class="me-2" />
        </template>
        <VCardTitle class="text-h4">
          Riwayat Permintaan
        </VCardTitle>
        <VCardSubtitle>Lacak status semua permintaan yang telah Anda ajukan.</VCardSubtitle>
        <template #append>
          <VBtn prepend-icon="tabler-plus" @click="isRequestFormVisible = true">
            Buat Permintaan Baru
          </VBtn>
        </template>
      </VCardItem>
    </VCard>

    <VCard class="rounded-lg">
      <VDataTableServer
        v-model:options="options"
        :headers="headers"
        :items="requests"
        :items-length="totalRequests"
        :loading="loading"
        item-value="id"
        class="text-no-wrap"
      >
        <template #item.created_at="{ item }">
          <span class="text-high-emphasis">{{ formatDateTime(item.created_at) }}</span>
        </template>

        <template #item.request_type="{ item }">
          <VChip :color="getRequestTypeMetaByKey(item.request_type)?.color" size="small" label>
            <VIcon start :icon="getRequestTypeMetaByKey(item.request_type)?.icon" size="16" />
            {{ getRequestTypeMetaByKey(item.request_type)?.text }}
          </VChip>
        </template>

        <template #item.details="{ item }">
          <div v-if="item.request_type === 'QUOTA'">
            <div class="d-flex align-center">
              <VChip color="secondary" size="x-small" label class="me-2">
                Diminta
              </VChip>
              <span class="font-weight-medium">
                {{ formatQuotaToGB(item.requested_mb) }} / {{ item.requested_duration_days }} hari
              </span>
            </div>
            <div v-if="item.status === 'PARTIALLY_APPROVED' && item.granted_details" class="d-flex align-center mt-1">
              <VChip color="info" size="x-small" label class="me-2">
                Diberikan
              </VChip>
              <span class="text-info">
                {{ formatQuotaToGB(item.granted_details.granted_mb) }} / {{ item.granted_details.granted_duration_days }} hari
              </span>
            </div>
          </div>
          <span v-else class="text-disabled">—</span>
        </template>

        <template #item.status="{ item }">
          <VChip :color="getStatusMetaByKey(item.status)?.color" size="small" label>
            <VIcon start :icon="getStatusMetaByKey(item.status)?.icon" size="16" />
            {{ getStatusMetaByKey(item.status)?.text }}
          </VChip>
        </template>

        <template #item.processed_at="{ item }">
          <div v-if="item.status !== 'PENDING'" class="d-flex flex-column">
            <span class="text-high-emphasis">{{ formatDateTime(item.processed_at) }}</span>
            <small class="text-medium-emphasis">oleh {{ item.processed_by_admin || 'Admin' }}</small>
            <small v-if="item.rejection_reason" class="text-error mt-1" style="max-width: 200px; white-space: normal;">
              Alasan: {{ item.rejection_reason }}
            </small>
          </div>
          <span v-else class="text-disabled">—</span>
        </template>

        <template #no-data>
          <div class="text-center py-8">
            <VIcon icon="tabler-file-off" size="48" class="mb-2 text-disabled" />
            <p class="text-disabled">
              Anda belum pernah membuat permintaan.
            </p>
          </div>
        </template>

        <template #loading>
          <VSkeletonLoader type="table-row@5" />
        </template>
      </VDataTableServer>
    </VCard>

    <RequestFormDialog
      v-model="isRequestFormVisible"
      @submitted="fetchRequests"
    />

    <VSnackbar
      v-model="snackbar.show"
      :color="snackbar.color"
      :timeout="4000"
      location="top end"
    >
      {{ snackbar.text }}
    </VSnackbar>
  </div>
</template>
