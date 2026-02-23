<script lang="ts" setup>
import { differenceInDays, format, isPast, isValid } from 'date-fns'
import { id } from 'date-fns/locale'
import { computed, ref, watch } from 'vue'
import { useSnackbar } from '@/composables/useSnackbar'

// Definisikan interface User
interface User {
  id: string
  full_name: string
  phone_number: string
  role: 'USER' | 'KOMANDAN' | 'ADMIN' | 'SUPER_ADMIN'
  approval_status: 'PENDING_APPROVAL' | 'APPROVED' | 'REJECTED'
  is_active: boolean
  is_blocked?: boolean
  blocked_reason?: string | null
  created_at: string
  blok: string | null
  kamar: string | null
  is_tamping: boolean
  tamping_type: string | null
  approved_at: string | null
  total_quota_purchased_mb: number
  total_quota_used_mb: number
  manual_debt_mb?: number
  quota_debt_auto_mb?: number
  quota_debt_manual_mb?: number
  quota_debt_total_mb?: number
  quota_expiry_date: string | null
  is_unlimited_user: boolean
}

// Definisikan interface QuotaInfo
interface QuotaInfo {
  totalQuotaMB: number
  usedQuotaMB: number
  remainingQuotaMB: number
  percentageUsed: number
  isUnlimited: boolean
  expiryDate: string | null
  remainingDays: number | null
  status: 'ACTIVE' | 'EXPIRED' | 'NOT_SET' | 'UNLIMITED'
  statusColor: string
}

interface PreviewContext {
  action: 'deactivate' | 'delete'
  days_inactive: number
  threshold_days: number
}

const props = defineProps<{ modelValue: boolean, user: User | null, previewContext?: PreviewContext | null }>()
const emit = defineEmits(['update:modelValue'])
const { $api } = useNuxtApp()
const { add: showSnackbar } = useSnackbar()

interface ManualDebtItem {
  id: string
  debt_date: string | null
  amount_mb: number
  paid_mb: number
  remaining_mb: number
  is_paid: boolean
  paid_at: string | null
  note: string | null
  created_at: string
  last_paid_source?: string | null
}

const manualDebtItems = ref<ManualDebtItem[]>([])
const manualDebtSummary = ref<{ manual_debt_mb: number, open_items: number, paid_items: number, total_items: number } | null>(null)
const manualDebtLoading = ref(false)

const roleMap = { USER: { text: 'User', color: 'info' }, KOMANDAN: { text: 'Komandan', color: 'success' }, ADMIN: { text: 'Admin', color: 'primary' }, SUPER_ADMIN: { text: 'Support', color: 'secondary' } }
const statusMap = { APPROVED: { text: 'Disetujui', color: 'success' }, PENDING_APPROVAL: { text: 'Menunggu', color: 'warning' }, REJECTED: { text: 'Ditolak', color: 'error' } }
const previewAlertMeta = computed(() => {
  if (!props.previewContext)
    return null

  const isDelete = props.previewContext.action === 'delete'

  return {
    title: isDelete ? 'Kandidat Auto-Delete' : 'Kandidat Auto-Deactivate',
    color: isDelete ? 'error' : 'warning',
    icon: isDelete ? 'tabler-alert-triangle' : 'tabler-alert-circle',
    text: `Pengguna tidak aktif selama ${props.previewContext.days_inactive} hari (threshold ${props.previewContext.threshold_days} hari).`,
  }
})

function formatSimpleDateTime(dateString: string | null) {
  if (!dateString)
    return 'N/A'
  const date = new Date(dateString)
  return isValid(date) ? format(date, 'dd MMMM yyyy, HH:mm', { locale: id }) : 'Tanggal tidak valid'
}

function formatPhoneNumberDisplay(phoneNumber: string | null) {
  if (!phoneNumber)
    return 'N/A'
  return phoneNumber.startsWith('+62') ? `0${phoneNumber.substring(3)}` : phoneNumber
}

function formatDataSize(sizeInMB: number) {
  // PERBAIKAN: Menggunakan Number.isNaN
  if (Number.isNaN(sizeInMB))
    return '0 MB'
  const options = { minimumFractionDigits: 2, maximumFractionDigits: 2 }
  if (sizeInMB < 1)
    return `${(sizeInMB * 1024).toLocaleString('id-ID', options)} KB`
  else if (sizeInMB < 1024)
    return `${sizeInMB.toLocaleString('id-ID', options)} MB`
  else return `${(sizeInMB / 1024).toLocaleString('id-ID', options)} GB`
}

const quotaDetails = computed((): QuotaInfo | null => {
  if (!props.user)
    return null
  // [PERBAIKAN LOGIKA] Untuk Admin dan Super Admin, kita tidak menampilkan detail kuota.
  // computed property ini akan mengembalikan null, dan template akan menanganinya.
  if (props.user.role === 'ADMIN' || props.user.role === 'SUPER_ADMIN')
    return null

  const user = props.user
  const totalMB = user.total_quota_purchased_mb || 0
  const usedMB = user.total_quota_used_mb || 0
  const remainingMB = Math.max(0, totalMB - usedMB)
  const percentage = totalMB > 0 ? Math.min(100, (usedMB / totalMB) * 100) : 0
  // PERBAIKAN: Memisahkan setiap deklarasi ke baris baru
  let status: QuotaInfo['status'] = 'NOT_SET'
  let statusColor = 'grey'
  let remainingDays: number | null = null

  if (user.is_unlimited_user) {
    // PERBAIKAN: Memisahkan setiap pernyataan ke baris baru
    status = 'UNLIMITED'
    statusColor = 'success'
    if (user.quota_expiry_date) {
      const expiry = new Date(user.quota_expiry_date)
      if (isValid(expiry))
        remainingDays = Math.max(0, differenceInDays(expiry, new Date()))
    }
  }
  else if (user.quota_expiry_date) {
    const expiry = new Date(user.quota_expiry_date)
    if (isValid(expiry)) {
      // PERBAIKAN: Memisahkan isi blok if/else ke beberapa baris
      if (isPast(expiry)) {
        status = 'EXPIRED'
        statusColor = 'error'
        remainingDays = 0
      }
      else {
        status = 'ACTIVE'
        statusColor = 'success'
        remainingDays = differenceInDays(expiry, new Date()) + 1
      }
    }
  }

  return {
    totalQuotaMB: totalMB,
    usedQuotaMB: usedMB,
    remainingQuotaMB: remainingMB,
    percentageUsed: percentage,
    isUnlimited: user.is_unlimited_user,
    expiryDate: user.quota_expiry_date ? format(new Date(user.quota_expiry_date), 'dd MMMM yyyy, HH:mm', { locale: id }) : null,
    remainingDays,
    status,
    statusColor,
  }
})

const debtAutoMb = computed(() => Number(props.user?.quota_debt_auto_mb ?? 0))
const debtManualMb = computed(() => Number(props.user?.quota_debt_manual_mb ?? props.user?.manual_debt_mb ?? 0))
const debtTotalMb = computed(() => Number(props.user?.quota_debt_total_mb ?? (debtAutoMb.value + debtManualMb.value)))

const debtStatusMeta = computed(() => {
  const hasDebt = debtTotalMb.value > 0
  return {
    text: hasDebt ? 'ADA TUNGGAKAN' : 'TIDAK ADA TUNGGAKAN',
    color: hasDebt ? 'warning' : 'success',
    icon: hasDebt ? 'tabler-alert-triangle' : 'tabler-circle-check',
  }
})

function formatMb(value: number) {
  if (!Number.isFinite(value))
    return '0'
  return value.toLocaleString('id-ID', { maximumFractionDigits: 2 })
}

function formatDebtDate(value: string | null) {
  if (!value)
    return '-'
  const dt = new Date(value)
  return isValid(dt) ? format(dt, 'dd MMM yyyy', { locale: id }) : value
}

async function fetchManualDebtLedger() {
  if (!props.user)
    return
  manualDebtLoading.value = true
  manualDebtItems.value = []
  manualDebtSummary.value = null
  try {
    const resp = await $api<{ items: ManualDebtItem[], summary: any }>(`/admin/users/${props.user.id}/debts`)
    manualDebtItems.value = Array.isArray(resp.items) ? resp.items : []
    manualDebtSummary.value = resp.summary ?? null
  }
  catch (error: any) {
    showSnackbar({ type: 'warning', title: 'Tunggakan', text: error?.data?.message || 'Gagal memuat riwayat tunggakan.' })
  }
  finally {
    manualDebtLoading.value = false
  }
}

watch(
  () => props.modelValue,
  (isOpen) => {
    if (!isOpen)
      return
    if (props.user)
      fetchManualDebtLedger()
  },
)

watch(
  () => props.user?.id,
  () => {
    if (props.modelValue && props.user)
      fetchManualDebtLedger()
  },
)

function onClose() {
  emit('update:modelValue', false)
}
</script>

<template>
  <VDialog :model-value="props.modelValue" max-width="600" persistent @update:model-value="onClose">
    <VCard v-if="props.user">
      <VCardTitle class="text-h6 pa-4 bg-primary text-white rounded-t-lg">
        <div class="dialog-titlebar">
          <div class="dialog-titlebar__title">
            <VIcon start icon="tabler-user-circle" />
            <span>Detail Pengguna</span>
          </div>
          <div class="dialog-titlebar__actions">
            <VBtn icon="tabler-x" variant="text" size="small" class="text-white" @click="onClose" />
          </div>
        </div>
      </VCardTitle>
      <VDivider />
      <AppPerfectScrollbar class="pa-5" style="max-height: 70vh;">
        <VAlert
          v-if="previewAlertMeta"
          :color="previewAlertMeta.color"
          :icon="previewAlertMeta.icon"
          :title="previewAlertMeta.title"
          variant="tonal"
          class="mb-4"
        >
          {{ previewAlertMeta.text }}
        </VAlert>

        <div class="text-overline mb-2">
          Informasi Dasar
        </div>
        <VList lines="two" density="compact">
          <VListItem prepend-icon="tabler-user" title="Nama Lengkap" :subtitle="props.user.full_name" />
          <VListItem prepend-icon="tabler-phone" title="Nomor Telepon" :subtitle="formatPhoneNumberDisplay(props.user.phone_number)" />
          <VListItem prepend-icon="tabler-shield-check" title="Peran">
            <template #subtitle>
              <div class="d-flex align-center">
                <VChip :color="roleMap[props.user.role]?.color" size="small" label>
                  {{ roleMap[props.user.role]?.text }}
                </VChip>
                <VTooltip v-if="props.user.is_unlimited_user" location="top" text="Akses Unlimited">
                  <template #activator="{ props: tooltipProps }">
                    <VIcon v-bind="tooltipProps" icon="tabler-infinity" color="success" size="small" class="ms-2" />
                  </template>
                </VTooltip>
              </div>
            </template>
          </VListItem>
          <VListItem prepend-icon="tabler-checkup-list" title="Status Akun">
            <template #subtitle>
              <VChip :color="statusMap[props.user.approval_status]?.color" size="small" label>
                {{ statusMap[props.user.approval_status]?.text }}
              </VChip>
              <VChip :color="props.user.is_active ? 'success' : 'error'" size="small" class="ms-2" label>
                {{ props.user.is_active ? 'Aktif' : 'Nonaktif' }}
              </VChip>
              <VChip v-if="props.user.is_blocked" color="error" size="small" class="ms-2" label>
                Diblokir
              </VChip>
              <VChip :color="debtStatusMeta.color" size="small" class="ms-2" label>
                <VIcon :icon="debtStatusMeta.icon" start size="16" />
                {{ debtStatusMeta.text }}
              </VChip>
            </template>
          </VListItem>
          <VListItem v-if="props.user.is_tamping" prepend-icon="tabler-building-bank" title="Tamping" :subtitle="props.user.tamping_type || 'N/A'" />
          <VListItem v-else-if="props.user.blok && props.user.kamar" prepend-icon="tabler-building-community" title="Alamat" :subtitle="`Blok ${props.user.blok}, Kamar ${props.user.kamar.replace('Kamar_', '')}`" />
        </VList>

        <template v-if="quotaDetails">
          <VDivider class="my-4" />
          <div class="text-overline mb-2">
            Informasi Kuota & Akses
          </div>

          <VAlert v-if="quotaDetails.isUnlimited" variant="tonal" color="success" icon="tabler-infinity" class="mb-4" title="Langganan Unlimited Aktif">
            Pengguna ini menikmati koneksi internet tanpa batas kuota.
            <div v-if="quotaDetails.expiryDate" class="text-caption mt-1">
              Berlaku hingga: {{ quotaDetails.expiryDate }} (sisa {{ quotaDetails.remainingDays }} hari)
            </div>
          </VAlert>

          <div v-else-if="quotaDetails.totalQuotaMB > 0">
            <VRow>
              <VCol cols="12" sm="4">
                <VListItem prepend-icon="tabler-database" title="Total Kuota" :subtitle="formatDataSize(quotaDetails.totalQuotaMB)" class="pa-0" />
              </VCol>
              <VCol cols="12" sm="4">
                <VListItem prepend-icon="tabler-database-import" title="Terpakai" :subtitle="formatDataSize(quotaDetails.usedQuotaMB)" class="pa-0" />
              </VCol>
              <VCol cols="12" sm="4">
                <VListItem prepend-icon="tabler-database-export" title="Sisa Kuota" :subtitle="formatDataSize(quotaDetails.remainingQuotaMB)" class="pa-0" subtitle-class="font-weight-bold" />
              </VCol>
            </VRow>
            <VProgressLinear :model-value="quotaDetails.percentageUsed" color="primary" height="8" rounded class="my-4" />
          </div>

          <VAlert v-else variant="tonal" color="warning" icon="tabler-alert-circle" density="compact">
            Pengguna belum memiliki paket kuota aktif.
          </VAlert>

          <VAlert
            v-if="debtTotalMb > 0"
            variant="tonal"
            color="warning"
            icon="tabler-alert-triangle"
            class="mt-4"
            density="compact"
          >
            Tunggakan kuota terdeteksi: <strong>{{ formatMb(debtTotalMb) }} MB</strong>
            (otomatis {{ formatMb(debtAutoMb) }} MB, manual {{ formatMb(debtManualMb) }} MB)
          </VAlert>

          <VSheet rounded="lg" border class="pa-3 mt-4">
            <div class="d-flex justify-space-between align-center">
              <div class="text-overline">
                Riwayat Tunggakan Manual
              </div>
              <VChip v-if="manualDebtSummary" size="x-small" label>
                Belum lunas {{ manualDebtSummary.open_items }} / Total {{ manualDebtSummary.total_items }}
              </VChip>
            </div>

            <VAlert v-if="manualDebtLoading" variant="tonal" density="compact" type="info" class="mt-2">
              Memuat riwayat tunggakan...
            </VAlert>
            <VAlert
              v-else-if="manualDebtItems.length === 0"
              variant="tonal"
              density="compact"
              type="info"
              class="mt-2"
            >
              Belum ada entri tunggakan manual.
            </VAlert>

            <VTable v-else density="compact" class="mt-2">
              <thead>
                <tr>
                  <th>Tanggal</th>
                  <th class="text-right">Jumlah</th>
                  <th class="text-right">Dibayar</th>
                  <th class="text-right">Sisa</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="item in manualDebtItems" :key="item.id">
                  <td>
                    <div class="text-body-2">
                      {{ formatDebtDate(item.debt_date || item.created_at) }}
                    </div>
                    <div v-if="item.note" class="text-caption text-disabled">
                      {{ item.note }}
                    </div>
                  </td>
                  <td class="text-right">
                    {{ formatMb(item.amount_mb) }}
                  </td>
                  <td class="text-right">
                    {{ formatMb(item.paid_mb) }}
                  </td>
                  <td class="text-right">
                    {{ formatMb(item.remaining_mb) }}
                  </td>
                  <td>
                    <VChip :color="item.is_paid ? 'success' : 'warning'" size="x-small" label>
                      {{ item.is_paid ? 'Lunas' : 'Belum' }}
                    </VChip>
                  </td>
                </tr>
              </tbody>
            </VTable>
          </VSheet>
        </template>
        <div v-else-if="props.user.role === 'ADMIN' || props.user.role === 'SUPER_ADMIN'">
          <VDivider class="my-4" />
          <div class="text-overline mb-2">
            Informasi Kuota & Akses
          </div>
          <VAlert variant="tonal" color="success" icon="tabler-shield-check" density="compact">
            Akses internet untuk peran ini bersifat <strong>Unlimited</strong> dan tidak dibatasi kuota.
          </VAlert>
        </div>

        <VDivider class="my-4" />
        <div class="text-overline mb-2">
          Informasi Waktu
        </div>
        <VList lines="one" density="compact">
          <template v-if="quotaDetails">
            <VListItem v-if="quotaDetails.expiryDate" prepend-icon="tabler-calendar-due" title="Masa Berlaku Hingga" :subtitle="quotaDetails.expiryDate" />
            <VListItem v-if="quotaDetails.remainingDays !== null" prepend-icon="tabler-hourglass-high" title="Sisa Masa Aktif">
              <template #subtitle>
                <VChip :color="quotaDetails.statusColor" size="x-small" label>
                  {{ quotaDetails.status === 'EXPIRED' ? 'Telah Berakhir' : `${quotaDetails.remainingDays} hari lagi` }}
                </VChip>
              </template>
            </VListItem>
          </template>
          <VListItem prepend-icon="tabler-calendar-plus" title="Tanggal Pendaftaran" :subtitle="formatSimpleDateTime(props.user.created_at)" />
          <VListItem v-if="props.user.approval_status === 'APPROVED'" prepend-icon="tabler-calendar-check" title="Tanggal Disetujui" :subtitle="formatSimpleDateTime(props.user.approved_at)" />
          <VListItem v-if="props.user.is_blocked" prepend-icon="tabler-ban" title="Alasan Blokir" :subtitle="props.user.blocked_reason || 'Tidak disebutkan'" />
          </VList>
        </AppPerfectScrollbar>
      <VDivider />
      <VCardActions class="pa-4 d-flex justify-end">
        <VBtn variant="tonal" color="secondary" @click="onClose">
          Tutup
        </VBtn>
      </VCardActions>
    </VCard>
  </VDialog>
</template>

<style scoped>
 .v-list-item { padding-inline: 4px !important; }

.dialog-titlebar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  width: 100%;
}

.dialog-titlebar__title {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}

.dialog-titlebar__actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

@media (max-width: 600px) {
  .dialog-titlebar {
    flex-direction: column;
    align-items: flex-start;
  }

  .dialog-titlebar__actions {
    width: 100%;
    justify-content: flex-end;
  }
}
</style>
