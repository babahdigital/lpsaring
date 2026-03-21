<script lang="ts" setup>
import { differenceInDays, format, isPast, isValid } from 'date-fns'
import { id } from 'date-fns/locale'
import { computed, ref, watch } from 'vue'
import { useDisplay } from 'vuetify'
import type { AdminUserDetailReportWhatsappResponse } from '@/types/api/contracts'
import DetailReportRecipientDialog from '@/components/admin/users/DetailReportRecipientDialog.vue'
import { useSnackbar } from '@/composables/useSnackbar'
import { resolveAccessStatusFromUser } from '@/utils/authAccess'

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
  mikrotik_user_exists?: boolean
  mikrotik_profile_name?: string | null
  last_login_at?: string | null
  device_count?: number
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
const display = useDisplay()
const isMobile = computed(() => display.smAndDown.value)

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

interface UserDetailSummaryPurchase {
  order_id: string
  package_name: string
  amount_display: string
  paid_at_display: string
  payment_method: string
}

interface UserDetailSummary {
  profile_display_name: string
  profile_source: string
  mikrotik_account_label: string
  mikrotik_account_hint: string
  access_status_label: string
  access_status_hint: string
  access_status_tone: string
  device_count: number
  device_count_label: string
  last_login_label: string
  recent_purchases: UserDetailSummaryPurchase[]
  purchase_count_30d: number
  purchase_total_amount_30d_display: string
  admin_whatsapp_default?: string
}

interface DebtBreakdownRow {
  key: 'auto' | 'manual'
  label: string
  amountMb: number
  statusText: string
  statusColor: string
  detail: string
}

interface InternalRecipientSelection {
  recipientIds: string[]
  recipients: Array<{
    id: string
    full_name: string
    role: 'ADMIN' | 'SUPER_ADMIN'
    phone_number: string
  }>
}

const manualDebtItems = ref<ManualDebtItem[]>([])
const manualDebtSummary = ref<{ manual_debt_mb: number, open_items: number, paid_items: number, total_items: number } | null>(null)
const manualDebtLoading = ref(false)
const detailSummary = ref<UserDetailSummary | null>(null)
const detailSummaryLoading = ref(false)
const isDetailRecipientDialogOpen = ref(false)
const detailWhatsappQueueMode = ref<'user' | 'internal' | null>(null)
const sendingDebtWhatsapp = ref(false)
const isDebtLedgerOpen = ref(false)

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

function formatCompactDateTime(dateString: string | null) {
  if (!dateString)
    return 'Belum pernah login'
  const date = new Date(dateString)
  return isValid(date) ? format(date, 'dd MMM yyyy, HH:mm', { locale: id }) : 'Tanggal tidak valid'
}

function formatPhoneNumberDisplay(phoneNumber: string | null) {
  if (!phoneNumber)
    return 'N/A'
  return phoneNumber.startsWith('+62') ? `0${phoneNumber.substring(3)}` : phoneNumber
}

function formatKamarLabel(kamar: string | null | undefined) {
  const rawValue = String(kamar ?? '').trim()
  if (rawValue === '')
    return ''

  const compactValue = rawValue.replace(/\s+/g, '')
  const lowered = compactValue.toLowerCase()

  if ((lowered.startsWith('kamar_') || lowered.startsWith('kamr_')) && /^\d+$/.test(compactValue.split('_').pop() || ''))
    return compactValue.split('_').pop() || ''

  const matchedDigits = compactValue.match(/(\d+)$/)
  if (matchedDigits)
    return matchedDigits[1]

  return rawValue.replace(/_/g, ' ')
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

const debtAutoMb = computed(() => (props.user?.is_unlimited_user === true ? 0 : Number(props.user?.quota_debt_auto_mb ?? 0)))
const debtManualMb = computed(() => (props.user?.is_unlimited_user === true ? 0 : Number(props.user?.quota_debt_manual_mb ?? props.user?.manual_debt_mb ?? 0)))
const debtTotalMb = computed(() => (props.user?.is_unlimited_user === true ? 0 : Number(props.user?.quota_debt_total_mb ?? (debtAutoMb.value + debtManualMb.value))))

const hasDebt = computed(() => debtTotalMb.value > 0)

const shouldShowManualDebtSection = computed(() => {
  const totalItems = Number(manualDebtSummary.value?.total_items ?? 0)
  return manualDebtLoading.value || manualDebtItems.value.length > 0 || totalItems > 0
})

const debtStatusMeta = computed(() => {
  const hasDebt = debtTotalMb.value > 0
  return {
    text: hasDebt ? 'ADA TUNGGAKAN' : 'TIDAK ADA TUNGGAKAN',
    color: hasDebt ? 'warning' : 'success',
    icon: hasDebt ? 'tabler-alert-triangle' : 'tabler-circle-check',
  }
})

const formattedAddress = computed(() => {
  if (!props.user)
    return null
  if (props.user.is_tamping)
    return props.user.tamping_type ? `Tamping ${props.user.tamping_type}` : 'Tamping'

  const blok = String(props.user.blok ?? '').trim()
  const kamar = formatKamarLabel(props.user.kamar)

  if (blok && kamar)
    return `Blok ${blok}, Kamar ${kamar}`
  if (blok)
    return `Blok ${blok}`
  if (kamar)
    return `Kamar ${kamar}`

  return null
})

const debtBreakdownRows = computed<DebtBreakdownRow[]>(() => {
  const rows: DebtBreakdownRow[] = []
  const manualSummary = manualDebtSummary.value

  if (debtAutoMb.value > 0) {
    rows.push({
      key: 'auto',
      label: 'Debt Otomatis',
      amountMb: debtAutoMb.value,
      statusText: 'Belum lunas',
      statusColor: 'warning',
      detail: 'Selisih pemakaian terhadap kuota yang tercatat sistem.',
    })
  }

  if (Number(manualSummary?.total_items ?? 0) > 0 || debtManualMb.value > 0) {
    const openItems = Number(manualSummary?.open_items ?? 0)
    const paidItems = Number(manualSummary?.paid_items ?? 0)
    rows.push({
      key: 'manual',
      label: 'Debt Manual',
      amountMb: debtManualMb.value,
      statusText: Number(manualSummary?.total_items ?? 0) > 0
        ? `${openItems} belum lunas / ${paidItems} lunas`
        : (debtManualMb.value > 0 ? 'Belum lunas' : 'Lunas'),
      statusColor: openItems > 0 || debtManualMb.value > 0 ? 'warning' : 'success',
      detail: 'Riwayat manual admin per item, termasuk yang sudah lunas.',
    })
  }

  return rows
})

type UserServiceStatusLabel = 'Aktif' | 'FUP' | 'Habis' | 'Blokir' | 'Inactive'
function getUserServiceStatusMeta(user: User | null | undefined): { text: UserServiceStatusLabel, color: string, icon: string, tooltip?: string } {
  if (!user)
    return { text: 'Inactive', color: 'secondary', icon: 'tabler-user-off' }

  const status = resolveAccessStatusFromUser(user)

  switch (status) {
    case 'blocked':
      return { text: 'Blokir', color: 'error', icon: 'tabler-lock', tooltip: user.blocked_reason ?? 'Akses login ditolak sampai blokir dibuka.' }
    case 'inactive':
      return { text: 'Inactive', color: 'secondary', icon: 'tabler-user-off' }
    case 'fup':
      return { text: 'FUP', color: 'info', icon: 'tabler-chart-arrows-vertical' }
    case 'habis':
      return { text: 'Habis', color: 'warning', icon: 'tabler-battery-off' }
    case 'expired':
      return { text: 'Habis', color: 'warning', icon: 'tabler-calendar-x', tooltip: 'Masa aktif kuota sudah berakhir.' }
    case 'ok':
    default:
      return { text: 'Aktif', color: 'success', icon: 'tabler-circle-check' }
  }
}

const detailConnectionCards = computed(() => {
  const user = props.user
  const summary = detailSummary.value
  const deviceCount = Number(summary?.device_count ?? user?.device_count ?? 0)
  const profileName = String(summary?.profile_display_name ?? user?.mikrotik_profile_name ?? '').trim()

  return [
    {
      key: 'devices',
      icon: 'tabler-devices',
      title: 'Perangkat',
      value: deviceCount > 0 ? `${deviceCount} perangkat aktif` : 'Belum ada perangkat',
      caption: deviceCount > 0 ? 'Perangkat terotorisasi yang pernah login' : 'Belum ada perangkat yang tercatat',
      color: deviceCount > 0 ? 'info' : 'secondary',
    },
    {
      key: 'login',
      icon: 'tabler-clock-play',
      title: 'Login Terakhir',
      value: summary?.last_login_label || formatCompactDateTime(user?.last_login_at ?? null),
      caption: user?.last_login_at ? 'Waktu login terakhir yang tercatat' : 'Belum ada riwayat login tersimpan',
      color: user?.last_login_at ? 'success' : 'secondary',
    },
    {
      key: 'profile',
      icon: 'tabler-shield-check',
      title: 'Profil MikroTik',
      value: profileName !== '' ? profileName : 'Belum tersedia',
      caption: summary?.mikrotik_account_label || (user?.mikrotik_user_exists ? 'Sinkron terakhir tersimpan' : 'Perlu verifikasi live MikroTik'),
      color: user?.mikrotik_user_exists ? 'primary' : 'warning',
    },
  ]
})

const hasRecentPurchases = computed(() => (detailSummary.value?.recent_purchases?.length ?? 0) > 0)

async function fetchUserDetailSummary() {
  if (!props.user?.id)
    return
  detailSummaryLoading.value = true
  try {
    const response = await $api<UserDetailSummary>(`/admin/users/${props.user.id}/detail-summary`)
    detailSummary.value = response
  }
  catch (error: any) {
    detailSummary.value = null
    showSnackbar({ type: 'warning', title: 'Detail Pengguna', text: error?.data?.message || 'Ringkasan pengguna belum bisa dimuat.' })
  }
  finally {
    detailSummaryLoading.value = false
  }
}

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
    if (props.user) {
      fetchManualDebtLedger()
      fetchUserDetailSummary()
    }
  },
)

watch(
  () => props.user?.id,
  () => {
    if (props.modelValue && props.user) {
      fetchManualDebtLedger()
      fetchUserDetailSummary()
    }
  },
)

function openUserDetailPdf() {
  if (!props.user)
    return
  window.open(`/api/admin/users/${props.user.id}/detail-report/export?format=pdf`, '_blank', 'noopener')
}

function formatQueuedRecipientSummary(response: AdminUserDetailReportWhatsappResponse) {
  if (response.recipients.length === 0)
    return response.message
  const names = response.recipients.map(recipient => recipient.full_name).join(', ')
  return `${response.message} Penerima: ${names}.`
}

async function queueUserDetailWhatsapp(body: { recipient_mode: 'user' | 'internal', recipient_user_ids?: string[] }) {
  if (!props.user)
    return

  detailWhatsappQueueMode.value = body.recipient_mode
  try {
    const resp = await $api<AdminUserDetailReportWhatsappResponse>(`/admin/users/${props.user.id}/detail-report/send-whatsapp`, {
      method: 'POST',
      body,
    })
    showSnackbar({ type: 'success', title: 'Detail Pengguna', text: formatQueuedRecipientSummary(resp) })
  }
  catch (error: any) {
    showSnackbar({ type: 'warning', title: 'Detail Pengguna', text: error?.data?.message || 'Gagal mengirim PDF detail pengguna ke WhatsApp.' })
  }
  finally {
    detailWhatsappQueueMode.value = null
  }
}

async function sendUserDetailWhatsappToUser() {
  await queueUserDetailWhatsapp({ recipient_mode: 'user' })
}

function openDetailRecipientDialog() {
  isDetailRecipientDialogOpen.value = true
}

async function sendUserDetailWhatsappToInternal(selection: InternalRecipientSelection) {
  await queueUserDetailWhatsapp({
    recipient_mode: 'internal',
    recipient_user_ids: selection.recipientIds,
  })
}

function openDebtPdf() {
  if (!props.user)
    return
  window.open(`/api/admin/users/${props.user.id}/debts/export?format=pdf`, '_blank', 'noopener')
}

async function sendDebtWhatsapp() {
  if (!props.user)
    return

  sendingDebtWhatsapp.value = true
  try {
    const resp = await $api<{ message?: string }>(`/admin/users/${props.user.id}/debts/send-whatsapp`, { method: 'POST' })
    showSnackbar({ type: 'success', title: 'Tunggakan', text: resp?.message || 'Ringkasan tunggakan berhasil diantrikan ke WhatsApp.' })
  }
  catch (error: any) {
    showSnackbar({ type: 'warning', title: 'Tunggakan', text: error?.data?.message || 'Gagal mengirim ringkasan tunggakan ke WhatsApp.' })
  }
  finally {
    sendingDebtWhatsapp.value = false
  }
}

function onClose() {
  emit('update:modelValue', false)
}
</script>

<template>
  <VDialog
    :model-value="props.modelValue"
    :fullscreen="isMobile"
    :max-width="isMobile ? undefined : 900"
    persistent
    @update:model-value="onClose"
  >
    <VCard v-if="props.user" :class="isMobile ? 'rounded-0' : 'rounded-lg'">
      <VCardTitle class="admin-user-detail__hero text-white" :class="isMobile ? '' : 'rounded-t-lg'">
        <div class="admin-user-detail__hero-main">
          <div class="admin-user-detail__hero-copy">
            <div class="admin-user-detail__hero-icon">
              <VIcon icon="tabler-user-circle" size="24" />
            </div>
            <div class="admin-user-detail__hero-text">
              <div class="admin-user-detail__hero-title">
                Detail Pengguna
              </div>
              <div class="admin-user-detail__hero-subtitle">
                {{ props.user.full_name }}
              </div>
              <div class="admin-user-detail__hero-pills">
                <span class="admin-user-detail__hero-pill">
                  <VIcon icon="tabler-phone" size="14" class="me-1" />
                  {{ formatPhoneNumberDisplay(props.user.phone_number) }}
                </span>
                <span class="admin-user-detail__hero-pill">
                  <VIcon icon="tabler-shield-check" size="14" class="me-1" />
                  {{ roleMap[props.user.role]?.text }}
                </span>
              </div>
            </div>
          </div>
          <VBtn icon="tabler-x" variant="text" size="small" class="text-white admin-user-detail__hero-close" @click="onClose" />
        </div>
      </VCardTitle>
      <VDivider />
      <AppPerfectScrollbar class="pa-4 pa-md-6" :native-scroll="isMobile" :style="isMobile ? 'max-height: calc(100vh - 128px);' : 'max-height: 70vh;'">
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

        <div class="admin-user-detail__meta-grid mb-4">
          <div v-for="item in detailConnectionCards" :key="item.key" class="admin-user-detail__meta-card">
            <div class="admin-user-detail__meta-cardHead">
              <VAvatar size="34" :color="item.color" variant="tonal">
                <VIcon :icon="item.icon" size="18" />
              </VAvatar>
              <div class="admin-user-detail__meta-cardTitle">
                {{ item.title }}
              </div>
            </div>
            <div class="admin-user-detail__meta-cardValue">
              {{ item.value }}
            </div>
            <div class="admin-user-detail__meta-cardCaption">
              {{ item.caption }}
            </div>
          </div>
        </div>

        <VSheet rounded="lg" border class="pa-3 mb-4 admin-user-detail__actionCard">
          <div class="admin-user-detail__actionHead">
            <div>
              <div class="text-overline">
                Aksi Laporan
              </div>
              <div class="text-body-2 text-medium-emphasis">
                Semua aksi laporan diringkas dalam satu grup agar tidak memenuhi area detail.
              </div>
            </div>
            <div class="admin-user-detail__actionButtons">
              <VBtn icon size="small" color="error" variant="tonal" class="admin-user-detail__actionBtn" @click="openUserDetailPdf">
                <VIcon icon="tabler-file-type-pdf" size="18" />
                <VTooltip activator="parent">PDF Detail</VTooltip>
              </VBtn>
              <VBtn icon size="small" color="success" variant="tonal" class="admin-user-detail__actionBtn" :loading="detailWhatsappQueueMode === 'user'" @click="sendUserDetailWhatsappToUser">
                <VIcon icon="tabler-user-share" size="18" />
                <VTooltip activator="parent">Kirim ke User</VTooltip>
              </VBtn>
              <VBtn icon size="small" color="primary" variant="tonal" class="admin-user-detail__actionBtn" :loading="detailWhatsappQueueMode === 'internal'" @click="openDetailRecipientDialog">
                <VIcon icon="tabler-users-group" size="18" />
                <VTooltip activator="parent">Kirim ke Admin</VTooltip>
              </VBtn>
            </div>
          </div>
          <div class="text-caption text-medium-emphasis mt-3">
            Pengiriman internal memakai popup pemilih penerima agar laporan tidak terkirim ke semua admin secara otomatis.
          </div>
        </VSheet>

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
              <div class="admin-user-detail__status-chips">
                <VChip :color="statusMap[props.user.approval_status]?.color" size="small" label>
                  {{ statusMap[props.user.approval_status]?.text }}
                </VChip>
                <VTooltip v-if="getUserServiceStatusMeta(props.user).tooltip" location="top" :text="getUserServiceStatusMeta(props.user).tooltip">
                  <template #activator="{ props: tooltipProps }">
                    <VChip v-bind="tooltipProps" :color="getUserServiceStatusMeta(props.user).color" size="small" label>
                      <VIcon :icon="getUserServiceStatusMeta(props.user).icon" start size="16" />
                      {{ getUserServiceStatusMeta(props.user).text }}
                    </VChip>
                  </template>
                </VTooltip>
                <VChip v-else :color="getUserServiceStatusMeta(props.user).color" size="small" label>
                  <VIcon :icon="getUserServiceStatusMeta(props.user).icon" start size="16" />
                  {{ getUserServiceStatusMeta(props.user).text }}
                </VChip>
                <VChip v-if="hasDebt" :color="debtStatusMeta.color" size="small" label>
                  <VIcon :icon="debtStatusMeta.icon" start size="16" />
                  {{ debtStatusMeta.text }}
                </VChip>
              </div>
            </template>
          </VListItem>
          <VListItem v-if="props.user.is_tamping" prepend-icon="tabler-building-bank" title="Tamping" :subtitle="props.user.tamping_type || 'N/A'" />
          <VListItem v-else-if="formattedAddress" prepend-icon="tabler-building-community" title="Alamat" :subtitle="formattedAddress" />
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
            v-if="hasDebt"
            variant="tonal"
            color="warning"
            icon="tabler-alert-triangle"
            class="mt-4"
            density="compact"
          >
            Tunggakan kuota terdeteksi: <strong>{{ formatDataSize(debtTotalMb) }}</strong>
            (otomatis {{ formatDataSize(debtAutoMb) }}, manual {{ formatDataSize(debtManualMb) }})
          </VAlert>

          <VSheet v-if="debtBreakdownRows.length > 0" rounded="lg" border class="pa-3 mt-4">
            <div class="text-overline mb-2">
              Rincian Tunggakan Sistem
            </div>
            <VTable density="compact" class="admin-user-detail__debtBreakdownTable">
              <thead>
                <tr>
                  <th>Jenis</th>
                  <th class="text-right">Nilai</th>
                  <th>Status</th>
                  <th>Keterangan</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="row in debtBreakdownRows" :key="row.key">
                  <td>{{ row.label }}</td>
                  <td class="text-right">{{ formatDataSize(row.amountMb) }}</td>
                  <td>
                    <VChip :color="row.statusColor" size="x-small" label>
                      {{ row.statusText }}
                    </VChip>
                  </td>
                  <td>{{ row.detail }}</td>
                </tr>
              </tbody>
            </VTable>
          </VSheet>

          <VSheet v-if="shouldShowManualDebtSection" rounded="lg" border class="pa-3 mt-4">
            <div class="admin-user-detail__debtHead">
              <div>
                <div class="text-overline">
                  Riwayat Tunggakan Manual
                </div>
                <div class="text-caption text-medium-emphasis">
                  Jalankan tindak lanjut debt tanpa berpindah ke dialog edit pengguna.
                </div>
              </div>
              <div class="admin-user-detail__debtActions">
                <VChip v-if="manualDebtSummary" size="x-small" label>
                  Belum lunas {{ manualDebtSummary.open_items }} / Total {{ manualDebtSummary.total_items }}
                </VChip>
                <div class="admin-user-detail__actionButtons admin-user-detail__actionButtons--compact">
                  <VBtn icon size="x-small" variant="tonal" class="admin-user-detail__actionBtn" @click="isDebtLedgerOpen = true">
                    <VIcon icon="tabler-list-details" size="16" />
                    <VTooltip activator="parent">Detail Tunggakan</VTooltip>
                  </VBtn>
                  <VBtn v-if="hasDebt" icon size="x-small" color="error" variant="tonal" class="admin-user-detail__actionBtn" @click="openDebtPdf">
                    <VIcon icon="tabler-file-type-pdf" size="16" />
                    <VTooltip activator="parent">PDF Tunggakan</VTooltip>
                  </VBtn>
                  <VBtn v-if="hasDebt" icon size="x-small" color="success" variant="tonal" class="admin-user-detail__actionBtn" :loading="sendingDebtWhatsapp" @click="sendDebtWhatsapp">
                    <VIcon icon="tabler-brand-whatsapp" size="16" />
                    <VTooltip activator="parent">WhatsApp Tunggakan</VTooltip>
                  </VBtn>
                </div>
              </div>
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

            <VTable v-else density="compact" class="mt-2 manual-debt-table">
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
                    <div class="text-body-2 manual-debt-table__date">
                      {{ formatDebtDate(item.debt_date || item.created_at) }}
                    </div>
                    <div v-if="item.note" class="text-caption text-disabled manual-debt-table__note">
                      {{ item.note }}
                    </div>
                  </td>
                  <td class="text-right">
                    {{ formatDataSize(item.amount_mb) }}
                  </td>
                  <td class="text-right">
                    {{ formatDataSize(item.paid_mb) }}
                  </td>
                  <td class="text-right">
                    {{ formatDataSize(item.remaining_mb) }}
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

        <template v-if="hasRecentPurchases">
          <VDivider class="my-4" />
          <div class="text-overline mb-2">
            Riwayat Pembelian 1 Tahun Terakhir
          </div>
          <VAlert v-if="detailSummaryLoading" type="info" variant="tonal" density="compact" class="mb-3">
            Memuat riwayat pembelian terbaru...
          </VAlert>
          <VSheet v-else rounded="lg" border class="pa-3">
            <div class="d-flex justify-space-between align-center flex-wrap gap-2 mb-3">
              <div class="text-body-2 text-medium-emphasis">
                {{ detailSummary?.purchase_count_30d }} transaksi sukses • {{ detailSummary?.purchase_total_amount_30d_display }}
              </div>
            </div>
            <VTable density="compact">
              <thead>
                <tr>
                  <th>Waktu</th>
                  <th>Paket</th>
                  <th>Metode</th>
                  <th class="text-right">Nominal</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="item in detailSummary?.recent_purchases || []" :key="`${item.order_id}-${item.paid_at_display}`">
                  <td>{{ item.paid_at_display }}</td>
                  <td>
                    <div>{{ item.package_name }}</div>
                    <div class="text-caption text-disabled">{{ item.order_id }}</div>
                  </td>
                  <td>{{ item.payment_method }}</td>
                  <td class="text-right">{{ item.amount_display }}</td>
                </tr>
              </tbody>
            </VTable>
          </VSheet>
        </template>

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
    </VCard>
  </VDialog>

  <DetailReportRecipientDialog
    :model-value="isDetailRecipientDialogOpen"
    :user-name="props.user?.full_name"
    @update:model-value="isDetailRecipientDialogOpen = $event"
    @submit="sendUserDetailWhatsappToInternal"
  />

  <UserDebtLedgerDialog v-model="isDebtLedgerOpen" :user="props.user" />
</template>

<style scoped>
 .v-list-item { padding-inline: 4px !important; }

.admin-user-detail__hero {
  padding: 16px 18px;
  background: linear-gradient(135deg, rgb(var(--v-theme-primary)) 0%, rgba(var(--v-theme-primary), 0.82) 100%);
}

.admin-user-detail__hero-main {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.admin-user-detail__hero-copy {
  display: flex;
  align-items: center;
  gap: 14px;
  min-width: 0;
  flex: 1 1 auto;
}

.admin-user-detail__hero-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 44px;
  height: 44px;
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.14);
}

.admin-user-detail__hero-text {
  min-width: 0;
}

.admin-user-detail__hero-title {
  font-size: 1.18rem;
  font-weight: 700;
  line-height: 1.2;
}

.admin-user-detail__hero-subtitle {
  margin-top: 6px;
  font-size: 0.98rem;
  font-weight: 600;
  line-height: 1.4;
  color: rgb(var(--v-theme-on-primary));
}

.admin-user-detail__hero-pills {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 10px;
}

.admin-user-detail__hero-pill {
  display: inline-flex;
  align-items: center;
  max-width: 100%;
  padding: 6px 10px;
  border-radius: 999px;
  background: rgba(var(--v-theme-surface), 0.18);
  color: rgb(var(--v-theme-on-primary));
  font-size: 0.8rem;
  font-weight: 600;
  line-height: 1.2;
}

.admin-user-detail__hero-close {
  background: rgba(255, 255, 255, 0.1);
  border-radius: 12px;
  margin-top: -2px;
}

.admin-user-detail__meta-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

.admin-user-detail__meta-card {
  padding: 14px 16px;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.08);
  border-radius: 16px;
  background: rgba(var(--v-theme-surface), 0.88);
  box-shadow: 0 18px 38px rgba(15, 23, 42, 0.05);
}

.admin-user-detail__actionCard {
  background: rgba(var(--v-theme-surface), 0.9);
}

.admin-user-detail__actionHead {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.admin-user-detail__actionButtons {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  padding: 6px;
  border-radius: 16px;
  background: rgba(var(--v-theme-on-surface), 0.04);
  box-shadow: inset 0 0 0 1px rgba(var(--v-theme-on-surface), 0.08);
}

.admin-user-detail__actionButtons--compact {
  padding: 4px;
  border-radius: 14px;
}

.admin-user-detail__actionBtn {
  border-radius: 12px;
}

.admin-user-detail__debtHead {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.admin-user-detail__debtActions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  flex-wrap: wrap;
}

.admin-user-detail__meta-cardHead {
  display: flex;
  align-items: center;
  gap: 10px;
}

.admin-user-detail__meta-cardTitle {
  font-size: 0.82rem;
  font-weight: 600;
  color: rgba(var(--v-theme-on-surface), 0.68);
}

.admin-user-detail__meta-cardValue {
  margin-top: 12px;
  font-size: 1rem;
  font-weight: 700;
  line-height: 1.35;
}

.admin-user-detail__meta-cardCaption {
  margin-top: 4px;
  font-size: 0.78rem;
  line-height: 1.4;
  color: rgba(var(--v-theme-on-surface), 0.62);
}

.admin-user-detail__status-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 4px;
}

.manual-debt-table :deep(th),
.manual-debt-table :deep(td) {
  padding-block: 10px;
}

.admin-user-detail__debtBreakdownTable :deep(th),
.admin-user-detail__debtBreakdownTable :deep(td) {
  padding-block: 10px;
}

.manual-debt-table__date {
  line-height: 1.25rem;
}

.manual-debt-table__note {
  margin-top: 4px;
  line-height: 1.15rem;
}

@media (max-width: 600px) {
  .admin-user-detail__hero {
    padding: 14px;
  }

  .admin-user-detail__actionHead {
    flex-direction: column;
  }

  .admin-user-detail__actionButtons {
    width: 100%;
  }

  .admin-user-detail__actionButtons :deep(.v-btn) {
    flex: 1 1 0;
  }

  .admin-user-detail__debtHead {
    flex-direction: column;
  }

  .admin-user-detail__debtActions {
    width: 100%;
    justify-content: stretch;
  }

  .admin-user-detail__debtActions :deep(.v-btn),
  .admin-user-detail__debtActions :deep(.v-chip) {
    width: 100%;
    justify-content: center;
  }

  .admin-user-detail__hero-main {
    gap: 10px;
  }

  .admin-user-detail__hero-copy {
    gap: 10px;
  }

  .admin-user-detail__hero-icon {
    width: 38px;
    height: 38px;
    border-radius: 12px;
  }

  .admin-user-detail__hero-title {
    font-size: 1rem;
  }

  .admin-user-detail__hero-subtitle {
    font-size: 0.86rem;
  }

  .admin-user-detail__hero-pill {
    font-size: 0.74rem;
  }

  .admin-user-detail__meta-grid {
    grid-template-columns: 1fr;
  }

  .admin-user-detail__status-chips {
    gap: 6px;
  }

  .admin-user-detail__actionButtons {
    width: 100%;
    justify-content: flex-start;
  }

  .admin-user-detail__actionButtons :deep(.v-btn) {
    flex: 0 0 auto;
  }
}
</style>
