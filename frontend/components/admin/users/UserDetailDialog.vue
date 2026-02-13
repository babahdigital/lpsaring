<script lang="ts" setup>
import { differenceInDays, format, isPast, isValid } from 'date-fns'
import { id } from 'date-fns/locale'
import { computed } from 'vue'

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

function onClose() {
  emit('update:modelValue', false)
}
</script>

<template>
  <VDialog :model-value="props.modelValue" max-width="600" persistent scrollable @update:model-value="onClose">
    <VCard v-if="props.user">
      <VCardTitle class="text-h6 d-flex align-center pa-4 bg-primary text-white rounded-t-lg">
        <VIcon start icon="tabler-user-circle" />
        Detail Pengguna
        <VSpacer />
        <VBtn icon="tabler-x" variant="text" size="small" class="text-white" @click="onClose" />
      </VCardTitle>
      <VDivider />
      <VCardText class="pa-5" style="max-height: 70vh; overflow-y: auto;">
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
      </VCardText>
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
</style>
