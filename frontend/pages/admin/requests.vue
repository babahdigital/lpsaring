<script lang="ts" setup>
import type { VDataTableServer } from 'vuetify/labs/VDataTable'
import { onMounted, reactive, ref, watch } from 'vue'
import { useDisplay } from 'vuetify'
import ProcessRequestDialog from '@/components/request/ProcessRequestDialog.vue'

// --- Tipe Data (tidak berubah) ---
interface Requester { id: string, full_name: string, phone_number: string }
interface ProcessedBy { full_name: string }
interface QuotaRequest {
  id: string
  requester: Requester
  status: 'PENDING' | 'APPROVED' | 'REJECTED' | 'PARTIALLY_APPROVED'
  request_type: 'QUOTA' | 'UNLIMITED'
  request_details: Record<string, any> | null
  granted_details: Record<string, any> | null
  rejection_reason: string | null
  created_at: string
  processed_at: string | null
  processed_by: ProcessedBy | null
}
type Options = InstanceType<typeof VDataTableServer>['options']

// --- Inisialisasi & State ---
useHead({ title: 'Manajemen Permintaan' })
const { $api } = useNuxtApp()
const { smAndDown } = useDisplay()
const requests = ref<QuotaRequest[]>([])
const loading = ref(true)
const totalRequests = ref(0)
const options = ref<Options>({ page: 1, itemsPerPage: 10, sortBy: [{ key: 'created_at', order: 'desc' }], groupBy: [], search: undefined })
const statusFilter = ref<'PENDING' | 'APPROVED' | 'REJECTED' | 'PARTIALLY_APPROVED' | null>('PENDING')
const snackbar = reactive({ show: false, text: '', color: 'info' })
const dialog = ref(false)
const selectedRequest = ref<QuotaRequest | null>(null)

// --- Watchers & Lifecycle ---
watch([options, statusFilter], () => {
  fetchRequests()
}, { deep: true })
onMounted(fetchRequests)

// --- Logika Inti ---
async function fetchRequests() {
  loading.value = true
  try {
    const params = new URLSearchParams({ page: String(options.value.page), itemsPerPage: String(options.value.itemsPerPage) })
    options.value.sortBy.forEach((sortItem) => {
      params.append('sortBy', sortItem.key)
      params.append('sortOrder', sortItem.order)
    })
    if (statusFilter.value) {
      params.append('status', statusFilter.value)
    }
    const response = await $api<{ items: QuotaRequest[], totalItems: number }>(`/admin/quota-requests?${params.toString()}`)
    requests.value = response.items
    totalRequests.value = response.totalItems
  }
  catch (error: any) {
    showSnackbar(`Gagal mengambil data: ${error.data?.message || 'Server error'}`, 'error')
  }
  finally {
    loading.value = false
  }
}

function openProcessDialog(item: QuotaRequest) {
  selectedRequest.value = item
  dialog.value = true
}

function handleDialogClose(processed = false) {
  dialog.value = false
  selectedRequest.value = null
  if (processed) {
    showSnackbar('Permintaan berhasil diproses.', 'success')
    fetchRequests()
  }
}

function showSnackbar(text: string, color = 'info') {
  snackbar.text = text
  snackbar.color = color
  snackbar.show = true
}

// --- [PENYEMPURNAAN] Tampilan & Formatting ---
const headers = [
  { title: 'PEMOHON', key: 'requester.full_name', sortable: true, minWidth: '200px' },
  { title: 'TIPE', key: 'request_type', sortable: true },
  { title: 'DETAIL', key: 'request_details', sortable: false, minWidth: '220px' },
  { title: 'STATUS', key: 'status', sortable: true },
  { title: 'TANGGAL', key: 'created_at', sortable: true },
  { title: 'AKSI', key: 'actions', sortable: false, align: 'center' },
]

const statusMap = {
  PENDING: { text: 'Menunggu', color: 'warning', icon: 'tabler-hourglass' },
  APPROVED: { text: 'Disetujui', color: 'success', icon: 'tabler-check' },
  REJECTED: { text: 'Ditolak', color: 'error', icon: 'tabler-x' },
  PARTIALLY_APPROVED: { text: 'Disetujui Sebagian', color: 'info', icon: 'tabler-discount-check' },
}

const requestTypeMap = {
  QUOTA: { text: 'Kuota', color: 'primary', icon: 'tabler-database' },
  UNLIMITED: { text: 'Unlimited', color: 'success', icon: 'tabler-infinity' },
}

const filterItems = [
  { title: 'Semua Status', value: null },
  { title: 'Menunggu', value: 'PENDING' },
  { title: 'Disetujui', value: 'APPROVED' },
  { title: 'Ditolak', value: 'REJECTED' },
  { title: 'Disetujui Sebagian', value: 'PARTIALLY_APPROVED' },
]

// [PERBAIKAN 1] Fungsi baru untuk format MB ke GB
function formatQuotaToGB(mb: number | null | undefined): string {
  if (typeof mb !== 'number')
    return 'N/A'
  if (mb === 0)
    return '0 GB'
  const gb = mb / 1024
  return `${gb.toFixed(2).replace(/\.00$/, '')} GB`
}

function formatRequestDetails(details: Record<string, any> | null, type: 'requested' | 'granted'): string {
  if (!details || typeof details !== 'object')
    return 'Akses Penuh'
  const mb = type === 'requested' ? details.requested_mb : details.granted_mb
  const days = type === 'requested' ? details.requested_duration_days : details.granted_duration_days
  if (typeof mb === 'number' && typeof days === 'number')
    return `${formatQuotaToGB(mb)} / ${days} hari`

  return 'Akses Penuh'
}

function formatSimpleDateTime(dateString: string | null) {
  if (!dateString)
    return 'N/A'
  return new Date(dateString).toLocaleString('id-ID', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' })
}
function formatPhoneNumber(phone: string | null): string {
  if (!phone)
    return ''
  return phone.startsWith('+62') ? `0${phone.substring(3)}` : phone
}
</script>

<template>
  <div>
    <VCard class="mb-6 rounded-lg">
      <VCardItem>
        <template #prepend>
          <VIcon icon="tabler-mail-fast" color="primary" size="32" class="me-2" />
        </template>
        <VCardTitle class="text-h4">
          Manajemen Permintaan
        </VCardTitle>
        <VCardSubtitle>Proses permintaan kuota dan akses dari para Komandan.</VCardSubtitle>
        <template #append>
          <div :style="{ width: smAndDown ? '100%' : '250px' }">
            <VSelect v-model="statusFilter" :items="filterItems" label="Filter Status" density="compact" hide-details />
          </div>
        </template>
      </VCardItem>
    </VCard>

    <VCard class="rounded-lg">
      <VDataTableServer v-model:options="options" :headers="headers" :items="requests" :items-length="totalRequests" :loading="loading" item-value="id" class="text-no-wrap">
        <template #item.requester.full_name="{ item }">
          <div class="d-flex align-center py-2">
            <VAvatar color="secondary" size="38" variant="tonal" class="me-3">
              <span class="text-h6">{{ item.requester.full_name.charAt(0).toUpperCase() }}</span>
            </VAvatar>
            <div class="d-flex flex-column">
              <span class="font-weight-semibold text-high-emphasis">{{ item.requester.full_name }}</span>
              <small class="text-medium-emphasis">{{ formatPhoneNumber(item.requester.phone_number) }}</small>
            </div>
          </div>
        </template>

        <template #item.request_type="{ item }">
          <VChip :color="requestTypeMap[item.request_type]?.color" size="small" label>
            <VIcon start :icon="requestTypeMap[item.request_type]?.icon" size="16" />
            {{ requestTypeMap[item.request_type]?.text }}
          </VChip>
        </template>

        <template #item.request_details="{ item }">
          <div v-if="item.request_type === 'QUOTA'" class="d-flex flex-column text-no-wrap">
            <span>{{ formatRequestDetails(item.request_details, 'requested') }}</span>
            <small v-if="item.status === 'PARTIALLY_APPROVED' && item.granted_details" class="text-info mt-1">
              <VIcon icon="tabler-arrow-down-right" size="12" />
              Diberikan: {{ formatRequestDetails(item.granted_details, 'granted') }}
            </small>
          </div>
          <span v-else>N/A</span>
        </template>

        <template #item.status="{ item }">
          <VChip :color="statusMap[item.status]?.color" size="small" label>
            {{ statusMap[item.status]?.text }}
          </VChip>
        </template>
        <template #item.created_at="{ item }">
          <span>{{ formatSimpleDateTime(item.created_at) }}</span>
        </template>
        <template #item.actions="{ item }">
          <VBtn v-if="item.status === 'PENDING'" color="primary" variant="tonal" size="small" @click="openProcessDialog(item)">
            Proses
          </VBtn>
          <VTooltip v-else location="top" max-width="250px">
            <template #activator="{ props }">
              <VIcon v-bind="props" :color="statusMap[item.status]?.color" :icon="statusMap[item.status]?.icon" />
            </template>
            <div class="pa-1">
              <p class="mb-1">
                <strong>Diproses oleh:</strong> {{ item.processed_by?.full_name || 'N/A' }}
              </p>
              <p class="mb-0">
                <strong>Tanggal:</strong> {{ formatSimpleDateTime(item.processed_at) }}
              </p>
              <div v-if="(item.status === 'REJECTED' || item.status === 'PARTIALLY_APPROVED') && item.rejection_reason">
                <VDivider class="my-2" />
                <p class="mb-0">
                  <strong>Alasan:</strong> {{ item.rejection_reason }}
                </p>
              </div>
            </div>
          </VTooltip>
        </template>
        <template #no-data>
          <div class="text-center py-8">
            <VIcon icon="tabler-mail-off" size="48" class="mb-2" /><p>Tidak ada data permintaan yang cocok.</p>
          </div>
        </template>
        <template #loading>
          <VSkeletonLoader type="table-row@10" />
        </template>
      </VDataTableServer>
    </VCard>

    <ProcessRequestDialog v-if="selectedRequest" :is-dialog-visible="dialog" :request-data="selectedRequest" @update:is-dialog-visible="handleDialogClose" @processed="handleDialogClose(true)" />
    <VSnackbar v-model="snackbar.show" :color="snackbar.color" :timeout="4000" location="top end">
      {{ snackbar.text }}
    </VSnackbar>
  </div>
</template>
