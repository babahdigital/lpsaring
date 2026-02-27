<script setup lang="ts">
import { computed } from 'vue'
import { useAuthStore } from '~/store/auth'
import { isCaptiveContextActive, isRestrictedInCaptiveContext } from '~/utils/captiveContext'
import { format_for_whatsapp_link, format_to_local_phone } from '~/utils/formatters'

type PolicyStatus = 'blocked' | 'inactive' | 'expired' | 'habis' | 'fup'

type PolicyAction = {
  label: string
  path: string
  kind: 'primary' | 'secondary'
}

const props = defineProps<{
  status: PolicyStatus
}>()

const authStore = useAuthStore()
const user = computed(() => authStore.currentUser ?? authStore.lastKnownUser)
const isKomandan = computed(() => user.value?.role === 'KOMANDAN')

const {
  public: { adminWhatsapp, whatsappBaseUrl },
} = useRuntimeConfig()

const adminContact = (adminWhatsapp as string) || ''
const whatsappBase = ((whatsappBaseUrl as string) || '').replace(/\/+$/, '')
const userRecord = computed(() => (user.value ?? null) as Record<string, unknown> | null)

function toSafeNumber(value: unknown): number {
  const n = Number(value)
  return Number.isFinite(n) ? n : 0
}

function formatMbToReadable(valueMb: number): string {
  const mb = Math.max(0, toSafeNumber(valueMb))
  if (mb >= 1024)
    return `${(mb / 1024).toFixed(1)}GB`
  return `${Math.round(mb)}MB`
}

function formatDateId(value: unknown): string {
  if (typeof value !== 'string' || !value.trim())
    return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime()))
    return '-'
  return date.toLocaleDateString('id-ID', {
    year: 'numeric',
    month: 'short',
    day: '2-digit',
  })
}

const quotaStats = computed(() => {
  const totalMb = Math.max(0, toSafeNumber(userRecord.value?.total_quota_purchased_mb))
  const usedMb = Math.max(0, toSafeNumber(userRecord.value?.total_quota_used_mb))
  const remainingMb = Math.max(0, totalMb - usedMb)
  return {
    totalMb,
    usedMb,
    remainingMb,
  }
})

const blockedReasonText = computed(() => {
  const reason = String(userRecord.value?.blocked_reason ?? '').trim()
  return reason || 'Tidak ada detail alasan dari sistem.'
})

const inactiveReasonText = computed(() => {
  const approvalStatus = String(userRecord.value?.approval_status ?? '').trim().toUpperCase()
  const isActive = Boolean(userRecord.value?.is_active)
  if (approvalStatus === 'PENDING' || approvalStatus === 'PENDING_APPROVAL')
    return 'Akun menunggu persetujuan admin.'
  if (approvalStatus === 'REJECTED')
    return 'Pengajuan akun ditolak. Silakan hubungi admin untuk verifikasi ulang.'
  if (!isActive)
    return 'Akun/perangkat belum aktif di sistem.'
  return 'Perangkat membutuhkan persetujuan/otorisasi sebelum dapat digunakan.'
})

const expiredAtText = computed(() => formatDateId(userRecord.value?.quota_expiry_date))

const fupUsage = computed(() => {
  const src = user.value as Record<string, unknown> | null
  const totalMb = Math.max(0, toSafeNumber(src?.total_quota_purchased_mb))
  const usedMb = Math.max(0, toSafeNumber(src?.total_quota_used_mb))

  if (totalMb <= 0) {
    return {
      percent: 100,
      label: '100% (FUP aktif)',
    }
  }

  const clampedUsedMb = Math.min(usedMb, totalMb)
  const percent = Math.min(100, Math.max(0, (clampedUsedMb / totalMb) * 100))

  return {
    percent,
    label: `${Math.round(percent)}% (${formatMbToReadable(clampedUsedMb)} / ${formatMbToReadable(totalMb)})`,
  }
})

const viewModel = computed(() => {
  if (props.status === 'blocked') {
    return {
      icon: 'tabler-alert-triangle',
      iconColor: 'rgb(var(--v-theme-error))',
      iconBgClass: 'policy-icon-bg-error',
      iconStrokeWidth: 1.5,
      cardTopClass: '',
      title: 'Akses Diblokir',
      description:
        `Akses internet Anda saat ini ditangguhkan. Alasan sistem: ${blockedReasonText.value}`,
      actions: [
        {
          label: 'Hubungi Admin',
          path: 'wa',
          kind: 'primary',
        },
      ] as PolicyAction[],
      waText: `Halo Admin, akun saya diblokir.\n\nNama: ${user.value?.full_name || 'Pengguna'}\nNo. HP: ${user.value?.phone_number ? format_to_local_phone(user.value.phone_number) : 'Tidak terdaftar'}\nAlasan: ${user.value?.blocked_reason || 'Tidak disebutkan'}\n\nMohon bantuan untuk mengaktifkan kembali.`,
      showFupProgress: false,
      showConnectedInfo: false,
    }
  }

  if (props.status === 'inactive') {
    return {
      icon: 'tabler-ban',
      iconColor: 'rgb(var(--v-theme-secondary))',
      iconBgClass: 'policy-icon-bg-secondary',
      iconStrokeWidth: 1.5,
      cardTopClass: 'policy-card-top-secondary',
      title: 'Layanan Tidak Aktif',
      description:
        `Perangkat atau akun Anda saat ini berstatus tidak aktif. ${inactiveReasonText.value}`,
      actions: [
        {
          label: 'Otorisasi Perangkat',
          path: '/captive',
          kind: 'primary',
        },
      ] as PolicyAction[],
      waText: `Halo Admin, akun saya belum aktif atau belum disetujui.\n\nNama: ${user.value?.full_name || 'Pengguna'}\nNo. HP: ${user.value?.phone_number ? format_to_local_phone(user.value.phone_number) : 'Tidak terdaftar'}\n\nMohon bantuan aktivasi akun.`,
      showFupProgress: false,
      showConnectedInfo: false,
    }
  }

  if (props.status === 'fup') {
    return {
      icon: 'tabler-bolt',
      iconColor: 'rgb(var(--v-theme-warning))',
      iconBgClass: 'policy-icon-bg-warning',
      iconStrokeWidth: 1.5,
      cardTopClass: 'policy-card-top-warning',
      title: 'Batas FUP Tercapai',
      description: 'Kecepatan internet Anda telah disesuaikan karena pemakaian telah mencapai batas wajar.',
      actions: [
        {
          label: isKomandan.value ? 'Ajukan Permintaan' : 'Tambah Quota',
          path: isKomandan.value ? '/requests' : '/beli',
          kind: 'primary',
        },
        {
          label: 'Kembali Dashboard',
          path: '/dashboard',
          kind: 'secondary',
        },
      ] as PolicyAction[],
      waText: `Halo Admin, kuota saya sudah masuk FUP.\n\nNama: ${user.value?.full_name || 'Pengguna'}\nNo. HP: ${user.value?.phone_number ? format_to_local_phone(user.value.phone_number) : 'Tidak terdaftar'}\n\nMohon bantuan untuk upgrade paket.`,
      showFupProgress: true,
      showConnectedInfo: false,
    }
  }

  if (props.status === 'expired') {
    return {
      icon: 'tabler-clock-hour-9',
      iconColor: 'rgb(var(--v-theme-secondary))',
      iconBgClass: 'policy-icon-bg-neutral',
      iconStrokeWidth: 1.5,
      cardTopClass: '',
      title: 'Paket Kadaluarsa',
      description: `Masa aktif layanan internet Anda telah berakhir${expiredAtText.value !== '-' ? ` pada ${expiredAtText.value}` : ''}.`,
      actions: [
        {
          label: 'Kembali Dashboard',
          path: '/dashboard',
          kind: 'primary',
        },
      ] as PolicyAction[],
      waText: `Halo Admin, masa aktif saya sudah berakhir.\n\nNama: ${user.value?.full_name || 'Pengguna'}\nNo. HP: ${user.value?.phone_number ? format_to_local_phone(user.value.phone_number) : 'Tidak terdaftar'}\n\nMohon bantu perpanjangan paket.`,
      showFupProgress: false,
      showConnectedInfo: false,
    }
  }

  return {
    icon: 'tabler-user-x',
    iconColor: 'rgb(var(--v-theme-primary))',
    iconBgClass: 'policy-icon-bg-primary',
    iconStrokeWidth: 1.5,
    cardTopClass: '',
    title: 'Kuota Habis',
    description: `Sisa kuota Anda ${formatMbToReadable(quotaStats.value.remainingMb)} dari total ${formatMbToReadable(quotaStats.value.totalMb)}. Silakan lakukan isi ulang atau beli paket baru untuk kembali berselancar.`,
    actions: [
      {
        label: isKomandan.value ? 'Ajukan Permintaan' : 'Beli Paket Data',
        path: isKomandan.value ? '/requests' : '/beli',
        kind: 'primary',
      },
      {
        label: 'Kembali Dashboard',
        path: '/dashboard',
        kind: 'secondary',
      },
    ] as PolicyAction[],
    waText: `Halo Admin, kuota saya habis.\n\nNama: ${user.value?.full_name || 'Pengguna'}\nNo. HP: ${user.value?.phone_number ? format_to_local_phone(user.value.phone_number) : 'Tidak terdaftar'}\n\nMohon bantu proses pembelian paket.`,
    showFupProgress: false,
    showConnectedInfo: false,
  }
})

const effectiveActions = computed(() => {
  return viewModel.value.actions.map((action) => {
    if (isCaptiveContextActive() && isRestrictedInCaptiveContext(action.path)) {
      return {
        ...action,
        label: action.kind === 'primary' ? 'Kembali ke Portal Captive' : action.label,
        path: '/captive',
      }
    }
    return action
  })
})

const whatsappHref = computed(() => {
  const adminNumberForLink = format_for_whatsapp_link(adminContact)
  if (!whatsappBase || !adminNumberForLink)
    return ''
  return `${whatsappBase}/${adminNumberForLink}?text=${encodeURIComponent(viewModel.value.waText)}`
})

function goTo(path: string) {
  if (!import.meta.client)
    return

  if (path === 'wa') {
    if (whatsappHref.value)
      window.location.href = whatsappHref.value
    return
  }

  window.location.href = path
}
</script>

<template>
  <div class="policy-wrapper">
    <VCard class="policy-card" :class="viewModel.cardTopClass" max-width="560" width="100%">
      <VCardText class="policy-card-body">
        <div class="policy-icon-wrap" :class="viewModel.iconBgClass">
          <VIcon :icon="viewModel.icon" :style="{ color: viewModel.iconColor }" :size="64" :stroke-width="viewModel.iconStrokeWidth" />
        </div>

        <h1 class="policy-title">
          {{ viewModel.title }}
        </h1>

        <p class="policy-description">
          {{ viewModel.description }}
        </p>

        <div v-if="viewModel.showFupProgress" class="policy-fup-progress">
          <div class="policy-fup-head">
            <span>Pemakaian FUP</span>
            <span class="policy-fup-value">{{ fupUsage.label }}</span>
          </div>
          <VProgressLinear :model-value="fupUsage.percent" color="warning" bg-color="grey-lighten-1" rounded height="10" />
        </div>

        <div v-if="viewModel.showConnectedInfo" class="policy-connected-info">
          <div class="policy-info-row">
            <span class="policy-info-label">Status Akses</span>
            <span class="policy-info-value policy-info-value--success">Aktif</span>
          </div>
          <div class="policy-info-row">
            <span class="policy-info-label">Koneksi</span>
            <span class="policy-info-value">Aman &amp; Terenkripsi</span>
          </div>
        </div>

        <div class="policy-actions">
          <VBtn
            v-for="(action, index) in effectiveActions"
            :key="`${action.label}-${index}`"
            :variant="action.kind === 'primary' ? 'flat' : 'outlined'"
            :color="action.kind === 'primary' ? 'primary' : 'secondary'"
            block
            class="policy-btn"
            @click="goTo(action.path)"
          >
            {{ action.label }}
          </VBtn>
        </div>
      </VCardText>
    </VCard>
  </div>
</template>

<style scoped>
.policy-wrapper {
  background: rgb(var(--v-theme-background));
  min-block-size: 100dvh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 16px;
}

.policy-card {
  border-radius: 12px;
  box-shadow: 0 8px 24px rgba(47, 51, 73, 0.12);
}

.policy-card-top-warning {
  border-top: 4px solid rgb(var(--v-theme-warning));
}

.policy-card-top-secondary {
  border-top: 4px solid rgb(var(--v-theme-secondary));
}

.policy-card-top-success {
  border-top: 4px solid rgb(var(--v-theme-success));
}

.policy-card-body {
  padding: 32px;
  text-align: center;
}

.policy-icon-wrap {
  margin: 0 auto 24px;
  inline-size: 96px;
  block-size: 96px;
  border-radius: 999px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.policy-icon-bg-primary {
  background: color-mix(in srgb, rgb(var(--v-theme-primary)) 18%, transparent);
}

.policy-icon-bg-warning {
  background: color-mix(in srgb, rgb(var(--v-theme-warning)) 18%, transparent);
}

.policy-icon-bg-secondary {
  background: color-mix(in srgb, rgb(var(--v-theme-secondary)) 16%, transparent);
}

.policy-icon-bg-success {
  background: color-mix(in srgb, rgb(var(--v-theme-success)) 18%, transparent);
}

.policy-icon-bg-error {
  background: color-mix(in srgb, rgb(var(--v-theme-error)) 16%, transparent);
}

.policy-icon-bg-neutral {
  background: color-mix(in srgb, rgb(var(--v-theme-secondary)) 12%, transparent);
  border: 2px solid color-mix(in srgb, rgb(var(--v-theme-secondary)) 26%, transparent);
}

.policy-title {
  font-size: 1.5rem;
  line-height: 1.35;
  font-weight: 700;
  margin-block-end: 8px;
}

.policy-description {
  margin-block-end: 24px;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
  font-size: 0.875rem;
  line-height: 1.6;
}

.policy-fup-progress {
  margin-block-end: 24px;
  text-align: start;
}

.policy-fup-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-block-end: 8px;
  font-size: 0.875rem;
  font-weight: 600;
}

.policy-fup-value {
  color: rgb(var(--v-theme-warning));
}

.policy-connected-info {
  margin-block-end: 24px;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.08);
  border-radius: 10px;
  padding: 14px 16px;
  text-align: start;
  background: rgba(var(--v-theme-on-surface), 0.02);
}

.policy-info-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 0.875rem;
}

.policy-info-row + .policy-info-row {
  margin-top: 8px;
}

.policy-info-label {
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
}

.policy-info-value {
  font-weight: 600;
}

.policy-info-value--success {
  color: rgb(var(--v-theme-success));
}

.policy-actions {
  display: grid;
  gap: 12px;
}

.policy-btn {
  min-block-size: 44px;
  text-transform: none;
  font-weight: 500;
}

@media (max-width: 599px) {
  .policy-card-body {
    padding: 24px;
  }

  .policy-icon-wrap {
    inline-size: 88px;
    block-size: 88px;
  }

  .policy-title {
    font-size: 1.25rem;
  }
}
</style>