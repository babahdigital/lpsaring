<script setup lang="ts">
import { useFetch, useNuxtApp } from '#app'
import { computed } from 'vue'
import { buildReliabilitySummary } from '~/utils/adminMetrics'

definePageMeta({
  requiredRole: ['SUPER_ADMIN'],
})

interface AdminMetricsResponse {
  metrics?: Record<string, number | null | undefined>
  reliability_signals?: {
    payment_idempotency_degraded?: boolean
    hotspot_sync_lock_degraded?: boolean
    policy_parity_degraded?: boolean
  }
}

type AccessParityMismatchKey =
  | 'binding_type'
  | 'missing_ip_binding'
  | 'address_list'
  | 'address_list_multi_status'
  | 'no_authorized_device'
  | 'no_resolvable_ip'
  | 'dhcp_lease_missing'

interface AccessParityActionPlan {
  action: string
  mode: 'auto' | 'informational' | string
  priority?: 'low' | 'medium' | 'high' | string
}

interface AccessParityItem {
  user_id: string
  phone_number: string
  mac: string | null
  ip: string | null
  app_status: string
  expected_status: string
  expected_binding_type: string | null
  actual_binding_type: string | null
  address_list_statuses: string[]
  mismatches: AccessParityMismatchKey[]
  parity_relevant: boolean
  auto_fixable: boolean
  action_plan: AccessParityActionPlan[]
}

interface AccessParityResponse {
  items?: AccessParityItem[]
  summary?: {
    users?: number
    mismatches?: number
    mismatches_total?: number
    non_parity_mismatches?: number
    no_authorized_device_count?: number
    auto_fixable_items?: number
    mismatch_types?: Partial<Record<AccessParityMismatchKey, number>>
  }
}

interface InactiveCleanupCandidate {
  id: string
  full_name: string
  phone_number: string
  role: 'USER' | 'KOMANDAN' | 'ADMIN' | 'SUPER_ADMIN'
  is_active: boolean
  last_activity_at: string
  days_inactive: number
}

interface InactiveCleanupPreviewResponse {
  thresholds?: {
    deactivate_days?: number
    delete_days?: number
    delete_enabled?: boolean
    delete_max_per_run?: number
  }
  summary?: {
    deactivate_candidates?: number
    delete_candidates?: number
  }
  items?: {
    deactivate_candidates?: InactiveCleanupCandidate[]
    delete_candidates?: InactiveCleanupCandidate[]
  }
}

const { $api } = useNuxtApp()

const {
  data: adminMetrics,
  pending: metricsPending,
  error: metricsError,
  refresh: refreshMetrics,
} = useFetch<AdminMetricsResponse>('/admin/metrics', {
  lazy: true,
  server: false,
  $fetch: $api,
})

const {
  data: accessParity,
  pending: parityPending,
  error: parityError,
  refresh: refreshParity,
} = useFetch<AccessParityResponse>('/admin/metrics/access-parity?include_non_parity=true', {
  lazy: true,
  server: false,
  $fetch: $api,
})

const {
  data: cleanupPreview,
  pending: cleanupPending,
  error: cleanupError,
  refresh: refreshCleanup,
} = useFetch<InactiveCleanupPreviewResponse>('/admin/users/inactive-cleanup-preview?limit=12', {
  lazy: true,
  server: false,
  $fetch: $api,
})

const reliabilitySummary = computed(() => buildReliabilitySummary(adminMetrics.value))

const accessParitySummary = computed(() => ({
  users: accessParity.value?.summary?.users ?? 0,
  mismatches: accessParity.value?.summary?.mismatches ?? 0,
  mismatchesTotal: accessParity.value?.summary?.mismatches_total ?? 0,
  nonParityMismatches: accessParity.value?.summary?.non_parity_mismatches ?? 0,
  noAuthorizedDeviceCount: accessParity.value?.summary?.no_authorized_device_count ?? 0,
  autoFixableItems: accessParity.value?.summary?.auto_fixable_items ?? 0,
  mismatchTypes: accessParity.value?.summary?.mismatch_types ?? {},
}))

const cleanupSummary = computed(() => ({
  deactivateCandidates: cleanupPreview.value?.summary?.deactivate_candidates ?? 0,
  deleteCandidates: cleanupPreview.value?.summary?.delete_candidates ?? 0,
  deactivateThreshold: cleanupPreview.value?.thresholds?.deactivate_days ?? 45,
  deleteThreshold: cleanupPreview.value?.thresholds?.delete_days ?? 90,
  deleteEnabled: cleanupPreview.value?.thresholds?.delete_enabled ?? false,
  deleteMaxPerRun: cleanupPreview.value?.thresholds?.delete_max_per_run ?? 0,
}))

const accessParityItems = computed(() => accessParity.value?.items ?? [])

const priorityRank: Record<string, number> = {
  high: 0,
  medium: 1,
  low: 2,
}

const sortedParityItems = computed(() => {
  return [...accessParityItems.value].sort((left, right) => {
    if (left.parity_relevant !== right.parity_relevant)
      return Number(right.parity_relevant) - Number(left.parity_relevant)

    if (left.auto_fixable !== right.auto_fixable)
      return Number(right.auto_fixable) - Number(left.auto_fixable)

    const leftPriority = Math.min(...left.action_plan.map(action => priorityRank[action.priority ?? 'low'] ?? 99), 99)
    const rightPriority = Math.min(...right.action_plan.map(action => priorityRank[action.priority ?? 'low'] ?? 99), 99)

    if (leftPriority !== rightPriority)
      return leftPriority - rightPriority

    return right.mismatches.length - left.mismatches.length
  })
})

const mismatchTypeCards = computed(() => {
  return Object.entries(accessParitySummary.value.mismatchTypes)
    .filter(([, count]) => Number(count ?? 0) > 0)
    .sort(([, left], [, right]) => Number(right ?? 0) - Number(left ?? 0))
    .slice(0, 6)
    .map(([key, count]) => {
      const meta = getParityMismatchMeta(key as AccessParityMismatchKey)

      return {
        key,
        label: meta.label,
        color: meta.color,
        count: Number(count ?? 0),
      }
    })
})

const operationsAttentionCount = computed(() => {
  return [
    reliabilitySummary.value.paymentIdempotencyDegraded,
    reliabilitySummary.value.hotspotSyncLockDegraded,
    reliabilitySummary.value.policyParityDegraded,
    accessParitySummary.value.mismatches > 0,
    cleanupSummary.value.deleteCandidates > 0,
  ].filter(Boolean).length
})

const operationCards = computed(() => [
  {
    title: 'Mismatch Inti',
    stats: `${accessParitySummary.value.mismatches}`,
    color: accessParitySummary.value.mismatches > 0 ? 'error' : 'success',
    icon: accessParitySummary.value.mismatches > 0 ? 'tabler-shield-x' : 'tabler-shield-check',
  },
  {
    title: 'Auto-Heal Queue',
    stats: `${accessParitySummary.value.autoFixableItems}`,
    color: accessParitySummary.value.autoFixableItems > 0 ? 'primary' : 'secondary',
    icon: 'tabler-refresh-alert',
  },
  {
    title: 'Watchlist Deactivate',
    stats: `${cleanupSummary.value.deactivateCandidates}`,
    color: cleanupSummary.value.deactivateCandidates > 0 ? 'warning' : 'success',
    icon: 'tabler-user-minus',
  },
  {
    title: 'Watchlist Delete',
    stats: `${cleanupSummary.value.deleteCandidates}`,
    color: cleanupSummary.value.deleteCandidates > 0 ? 'error' : 'success',
    icon: 'tabler-trash',
  },
])

const reliabilityCards = computed(() => [
  {
    key: 'payment-idempotency',
    title: 'Payment Idempotency',
    status: reliabilitySummary.value.paymentIdempotencyDegraded ? 'Perlu perhatian' : 'Stabil',
    detail: reliabilitySummary.value.paymentIdempotencyDegraded
      ? `Redis unavailable ${reliabilitySummary.value.paymentIdempotencyRedisUnavailableCount} kali.`
      : 'Redis aktif, proteksi transaksi ganda tetap konsisten.',
    color: reliabilitySummary.value.paymentIdempotencyDegraded ? 'error' : 'success',
    icon: 'tabler-shield-check',
  },
  {
    key: 'hotspot-sync-lock',
    title: 'Hotspot Sync Lock',
    status: reliabilitySummary.value.hotspotSyncLockDegraded ? 'Perlu perhatian' : 'Stabil',
    detail: reliabilitySummary.value.hotspotSyncLockDegraded
      ? `Lock miss ${reliabilitySummary.value.hotspotSyncLockDegradedCount} kali.`
      : 'Lock sinkronisasi aktif untuk proses eksklusif.',
    color: reliabilitySummary.value.hotspotSyncLockDegraded ? 'error' : 'success',
    icon: 'tabler-plug-connected',
  },
  {
    key: 'policy-parity',
    title: 'Policy Parity',
    status: reliabilitySummary.value.policyParityDegraded ? 'Perlu perhatian' : 'Stabil',
    detail: reliabilitySummary.value.policyParityDegraded
      ? `${reliabilitySummary.value.policyParityMismatchCount} mismatch parity terdeteksi.`
      : 'Akses utama aplikasi dan router saat ini sinkron.',
    color: reliabilitySummary.value.policyParityDegraded ? 'error' : 'success',
    icon: 'tabler-router',
  },
])

const cleanupSections = computed(() => [
  {
    key: 'deactivate',
    title: 'Watchlist Deactivate',
    subtitle: `Akan ditinjau saat inactivity >= ${cleanupSummary.value.deactivateThreshold} hari.`,
    count: cleanupSummary.value.deactivateCandidates,
    color: 'warning',
    icon: 'tabler-user-minus',
    items: cleanupPreview.value?.items?.deactivate_candidates ?? [],
    emptyText: 'Belum ada kandidat deactivate pada siklus saat ini.',
  },
  {
    key: 'delete',
    title: 'Watchlist Delete',
    subtitle: `Auto-delete ${cleanupSummary.value.deleteEnabled ? 'aktif' : 'nonaktif'} dengan threshold ${cleanupSummary.value.deleteThreshold} hari.`,
    count: cleanupSummary.value.deleteCandidates,
    color: 'error',
    icon: 'tabler-trash',
    items: cleanupPreview.value?.items?.delete_candidates ?? [],
    emptyText: 'Belum ada kandidat delete pada siklus saat ini.',
  },
])

const ACCESS_PARITY_MISMATCH_META: Record<AccessParityMismatchKey, { label: string, color: string }> = {
  binding_type: { label: 'Binding tidak sesuai', color: 'error' },
  missing_ip_binding: { label: 'IP binding belum tersedia', color: 'error' },
  address_list: { label: 'Address-list belum sinkron', color: 'error' },
  address_list_multi_status: { label: 'Address-list multi-status', color: 'warning' },
  no_authorized_device: { label: 'Perangkat belum terdaftar', color: 'default' },
  no_resolvable_ip: { label: 'IP belum terbaca', color: 'warning' },
  dhcp_lease_missing: { label: 'Lease DHCP belum tersedia', color: 'info' },
}

function getParityMismatchMeta(mismatch: AccessParityMismatchKey): { label: string, color: string } {
  return ACCESS_PARITY_MISMATCH_META[mismatch] ?? { label: mismatch, color: 'default' }
}

function getActionLabel(action: string): string {
  switch (action) {
    case 'wait_for_user_reconnect':
      return 'Tunggu reconnect'
    case 'upsert_ip_binding_expected_type':
      return 'Sinkron binding'
    case 'upsert_dhcp_static_lease':
      return 'Sinkron DHCP'
    case 'sync_address_list_for_single_user':
      return 'Sinkron address-list'
    case 'cleanup_extra_address_lists_for_ip':
      return 'Bersihkan address-list'
    default:
      return action.replaceAll('_', ' ')
  }
}

function getActionModeMeta(mode: string): { label: string, color: string } {
  if (mode === 'auto')
    return { label: 'Auto-heal', color: 'primary' }

  return { label: 'Observasi', color: 'secondary' }
}

function formatPhoneNumberForDisplay(phoneNumber?: string | null) {
  if (!phoneNumber)
    return '-'

  const cleaned = phoneNumber.replace(/\D+/g, '')
  if (cleaned.startsWith('62') && cleaned.length >= 11)
    return `+${cleaned}`
  if (cleaned.startsWith('0') && cleaned.length >= 10)
    return `+62${cleaned.slice(1)}`

  return phoneNumber
}

function formatDateTime(dateString?: string | null) {
  if (!dateString)
    return '-'

  const date = new Date(dateString)
  if (Number.isNaN(date.getTime()))
    return '-'

  return date.toLocaleString('id-ID', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

async function handleRefreshOperations() {
  await Promise.all([
    refreshMetrics(),
    refreshParity(),
    refreshCleanup(),
  ])
}
</script>

<template>
  <div class="d-flex flex-column gap-6">
    <VRow class="match-height">
      <VCol cols="12">
        <VCard class="operations-page__hero">
          <VCardItem>
            <template #prepend>
              <VAvatar color="info" variant="tonal" rounded="lg" size="44">
                <VIcon icon="tabler-activity-heartbeat" size="22" />
              </VAvatar>
            </template>
            <VCardTitle>Pusat Operasional</VCardTitle>
            <VCardSubtitle>Detail parity access, cleanup watchlist, dan sinyal reliabilitas dipisah dari dashboard utama agar monitoring tetap ringkas tetapi observabilitas tetap lengkap.</VCardSubtitle>
            <template #append>
              <div class="d-flex align-center gap-2 flex-wrap justify-end">
                <VBtn size="small" variant="tonal" color="secondary" to="/admin/dashboard">
                  Dashboard
                </VBtn>
                <VBtn size="small" variant="tonal" color="primary" to="/admin/users">
                  Pengguna
                </VBtn>
                <VBtn
                  size="small"
                  color="info"
                  :loading="metricsPending || parityPending || cleanupPending"
                  @click="handleRefreshOperations"
                >
                  Refresh
                </VBtn>
              </div>
            </template>
          </VCardItem>
          <VCardText>
            <div class="operations-page__heroBody">
              <div class="operations-page__heroCopy">
                <div class="operations-page__eyebrow">
                  Operational pulse
                </div>
                <div class="operations-page__heroTitle">
                  {{ operationsAttentionCount === 0 ? 'Semua sinyal operasional berada dalam batas aman.' : `${operationsAttentionCount} sinyal operasional perlu dipantau lebih dekat.` }}
                </div>
                <div class="text-body-2 text-medium-emphasis mt-2">
                  Halaman ini dipakai untuk membaca drift teknis dan watchlist otomatis. Dashboard utama tetap diposisikan sebagai ringkasan manajerial, bukan panel tindakan manual harian.
                </div>
              </div>

              <div class="operations-page__heroStats">
                <div class="operations-page__heroStat">
                  <div class="operations-page__heroStatLabel">Sinkron inti</div>
                  <div class="operations-page__heroStatValue">{{ Math.max(0, accessParitySummary.users - accessParitySummary.mismatches) }}</div>
                  <div class="operations-page__heroStatHint">dari {{ accessParitySummary.users }} user</div>
                </div>
                <div class="operations-page__heroStat">
                  <div class="operations-page__heroStatLabel">Non-parity drift</div>
                  <div class="operations-page__heroStatValue">{{ accessParitySummary.nonParityMismatches }}</div>
                  <div class="operations-page__heroStatHint">perlu observasi periodik</div>
                </div>
              </div>
            </div>
          </VCardText>
        </VCard>
      </VCol>

      <VCol v-for="card in operationCards" :key="card.title" cols="12" sm="6" lg="3">
        <CardStatisticsHorizontal :title="card.title" :stats="card.stats" :color="card.color" :icon="card.icon" />
      </VCol>
    </VRow>

    <VRow class="match-height">
      <VCol cols="12" lg="8">
        <VCard class="h-100">
          <VCardItem>
            <template #prepend>
              <VAvatar color="primary" variant="tonal" rounded="lg" size="40">
                <VIcon icon="tabler-shield-half-filled" size="20" />
              </VAvatar>
            </template>
            <VCardTitle>Detail Konsistensi Akses</VCardTitle>
            <VCardSubtitle>Daftar mismatch disusun dari yang paling relevan untuk kebijakan akses inti hingga drift operasional non-kritis.</VCardSubtitle>
          </VCardItem>
          <VCardText>
            <VAlert v-if="parityError" type="warning" variant="tonal" class="mb-4" icon="tabler-alert-triangle">
              Detail parity belum dapat dimuat. Pastikan koneksi MikroTik tersedia lalu lakukan refresh.
            </VAlert>

            <div v-if="sortedParityItems.length > 0" class="operations-page__tableWrap">
              <VTable class="operations-page__table text-no-wrap">
                <thead>
                  <tr>
                    <th>User / Device</th>
                    <th>Mismatch</th>
                    <th>Scope</th>
                    <th>Rencana Sistem</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="item in sortedParityItems.slice(0, 10)" :key="`${item.user_id}-${item.mac ?? 'no-mac'}-${item.ip ?? 'no-ip'}`">
                    <td>
                      <div class="operations-page__identity">
                        <div class="font-weight-medium text-high-emphasis">{{ formatPhoneNumberForDisplay(item.phone_number) }}</div>
                        <div class="text-caption text-medium-emphasis">
                          MAC {{ item.mac ?? '-' }}
                          <span v-if="item.ip"> • IP {{ item.ip }}</span>
                        </div>
                      </div>
                    </td>
                    <td>
                      <div class="operations-page__chipGroup">
                        <VChip
                          v-for="mismatch in item.mismatches"
                          :key="`${item.user_id}-${mismatch}`"
                          size="x-small"
                          :color="getParityMismatchMeta(mismatch).color"
                          variant="tonal"
                          label
                        >
                          {{ getParityMismatchMeta(mismatch).label }}
                        </VChip>
                      </div>
                    </td>
                    <td>
                      <VChip
                        size="x-small"
                        :color="item.parity_relevant ? 'error' : 'secondary'"
                        variant="tonal"
                        label
                      >
                        {{ item.parity_relevant ? 'Akses inti' : 'Operasional' }}
                      </VChip>
                    </td>
                    <td>
                      <div class="operations-page__chipGroup">
                        <VChip
                          v-for="action in item.action_plan.slice(0, 2)"
                          :key="`${item.user_id}-${action.action}`"
                          size="x-small"
                          :color="getActionModeMeta(action.mode).color"
                          variant="tonal"
                          label
                        >
                          {{ getActionLabel(action.action) }}
                        </VChip>
                        <VChip
                          size="x-small"
                          :color="getActionModeMeta(item.auto_fixable ? 'auto' : 'informational').color"
                          variant="tonal"
                          label
                        >
                          {{ getActionModeMeta(item.auto_fixable ? 'auto' : 'informational').label }}
                        </VChip>
                      </div>
                    </td>
                  </tr>
                </tbody>
              </VTable>
            </div>

            <div v-else-if="!parityPending" class="operations-page__emptyState">
              <VIcon icon="tabler-shield-check" size="42" class="text-success mb-2" />
              <div class="text-body-1 font-weight-medium">Tidak ada mismatch yang perlu ditampilkan.</div>
              <div class="text-body-2 text-medium-emphasis">Parity guard saat ini melaporkan kondisi sinkron atau drift teknis sudah nihil.</div>
            </div>

            <div v-else class="operations-page__emptyState">
              <VProgressCircular indeterminate color="primary" />
            </div>
          </VCardText>
        </VCard>
      </VCol>

      <VCol cols="12" lg="4">
        <VCard class="mb-6">
          <VCardItem>
            <template #prepend>
              <VAvatar color="secondary" variant="tonal" rounded="lg" size="40">
                <VIcon icon="tabler-layers-subtract" size="20" />
              </VAvatar>
            </template>
            <VCardTitle>Sinyal Parity Dominan</VCardTitle>
            <VCardSubtitle>Tipe mismatch yang paling banyak muncul pada audit terakhir.</VCardSubtitle>
          </VCardItem>
          <VCardText>
            <div v-if="mismatchTypeCards.length > 0" class="operations-page__stackList">
              <div v-for="item in mismatchTypeCards" :key="item.key" class="operations-page__stackItem">
                <div class="d-flex align-center gap-2 min-w-0">
                  <VChip size="x-small" :color="item.color" variant="tonal" label>
                    {{ item.label }}
                  </VChip>
                </div>
                <div class="operations-page__stackValue">{{ item.count }}</div>
              </div>
            </div>
            <div v-else class="text-body-2 text-medium-emphasis">
              Belum ada mismatch yang menonjol pada audit terakhir.
            </div>
          </VCardText>
        </VCard>

        <VCard>
          <VCardItem>
            <template #prepend>
              <VAvatar color="success" variant="tonal" rounded="lg" size="40">
                <VIcon icon="tabler-activity-heartbeat" size="20" />
              </VAvatar>
            </template>
            <VCardTitle>Reliability Signals</VCardTitle>
            <VCardSubtitle>Ringkasan sinyal backend yang berpengaruh ke operasi harian.</VCardSubtitle>
          </VCardItem>
          <VCardText>
            <VAlert v-if="metricsError" type="warning" variant="tonal" class="mb-4" icon="tabler-alert-triangle">
              Reliability metrics belum dapat dimuat penuh. Nilai ringkasan mungkin tidak lengkap.
            </VAlert>

            <div class="operations-page__stackList">
              <div v-for="item in reliabilityCards" :key="item.key" class="operations-page__signalItem">
                <div class="d-flex align-start gap-3">
                  <VAvatar :color="item.color" variant="tonal" size="36" rounded>
                    <VIcon :icon="item.icon" size="18" />
                  </VAvatar>
                  <div>
                    <div class="font-weight-medium text-high-emphasis">{{ item.title }}</div>
                    <div class="text-body-2 text-medium-emphasis mt-1">{{ item.detail }}</div>
                  </div>
                </div>
                <VChip size="x-small" :color="item.color" variant="tonal" label>
                  {{ item.status }}
                </VChip>
              </div>
            </div>
          </VCardText>
        </VCard>
      </VCol>
    </VRow>

    <VRow>
      <VCol cols="12">
        <VCard>
          <VCardItem>
            <template #prepend>
              <VAvatar color="warning" variant="tonal" rounded="lg" size="40">
                <VIcon icon="tabler-user-x" size="20" />
              </VAvatar>
            </template>
            <VCardTitle>Cleanup Watchlist</VCardTitle>
            <VCardSubtitle>Preview kandidat nonaktif tetap tersedia untuk review operasional, tetapi tidak lagi mengganggu halaman manajemen pengguna.</VCardSubtitle>
            <template #append>
              <div class="d-flex align-center gap-2 flex-wrap justify-end">
                <VChip size="small" color="warning" variant="tonal" label>
                  Deactivate ≥ {{ cleanupSummary.deactivateThreshold }} hari
                </VChip>
                <VChip size="small" color="error" variant="tonal" label>
                  Delete ≥ {{ cleanupSummary.deleteThreshold }} hari
                </VChip>
              </div>
            </template>
          </VCardItem>
          <VCardText>
            <VAlert v-if="cleanupError" type="warning" variant="tonal" class="mb-4" icon="tabler-alert-triangle">
              Watchlist cleanup belum dapat dimuat. Data kandidat mungkin tertunda.
            </VAlert>

            <div class="text-body-2 text-medium-emphasis mb-4">
              Auto-delete saat ini <strong>{{ cleanupSummary.deleteEnabled ? 'aktif' : 'nonaktif' }}</strong>
              dengan batas maksimum {{ cleanupSummary.deleteMaxPerRun }} user per siklus.
            </div>

            <VRow>
              <VCol v-for="section in cleanupSections" :key="section.key" cols="12" md="6">
                <div class="operations-page__watchlistCard">
                  <div class="operations-page__watchlistHead">
                    <div class="d-flex align-center gap-3">
                      <VAvatar :color="section.color" variant="tonal" rounded size="40">
                        <VIcon :icon="section.icon" size="20" />
                      </VAvatar>
                      <div>
                        <div class="font-weight-medium text-high-emphasis">{{ section.title }}</div>
                        <div class="text-body-2 text-medium-emphasis">{{ section.subtitle }}</div>
                      </div>
                    </div>
                    <div class="operations-page__watchlistCount">{{ section.count }}</div>
                  </div>

                  <VList density="compact" lines="two" class="mt-3">
                    <VListItem v-for="item in section.items" :key="item.id">
                      <template #prepend>
                        <VAvatar :color="section.color" variant="tonal" size="34" rounded>
                          <span class="text-sm font-weight-medium">{{ item.full_name.slice(0, 1).toUpperCase() }}</span>
                        </VAvatar>
                      </template>

                      <VListItemTitle>{{ item.full_name }}</VListItemTitle>
                      <VListItemSubtitle>
                        {{ formatPhoneNumberForDisplay(item.phone_number) }}
                        • {{ formatDateTime(item.last_activity_at) }}
                      </VListItemSubtitle>

                      <template #append>
                        <div class="text-end">
                          <div class="operations-page__watchlistDays">{{ item.days_inactive }} hari</div>
                          <VChip size="x-small" :color="item.is_active ? 'success' : 'secondary'" variant="tonal" label>
                            {{ item.is_active ? 'Masih aktif' : 'Sudah nonaktif' }}
                          </VChip>
                        </div>
                      </template>
                    </VListItem>

                    <VListItem v-if="section.items.length === 0 && !cleanupPending" :title="section.emptyText" />
                  </VList>
                </div>
              </VCol>
            </VRow>
          </VCardText>
        </VCard>
      </VCol>
    </VRow>
  </div>
</template>

<style lang="scss">
.operations-page__hero {
  border: 1px solid rgba(var(--v-theme-on-surface), 0.08);
  background: linear-gradient(180deg, rgba(var(--v-theme-info), 0.08) 0%, rgba(var(--v-theme-surface), 0.98) 100%);
}

.operations-page__heroBody {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 18px;
}

.operations-page__heroCopy {
  min-width: 0;
}

.operations-page__eyebrow {
  font-size: 0.72rem;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: rgba(var(--v-theme-info), 0.94);
}

.operations-page__heroTitle {
  margin-top: 8px;
  font-size: 1.28rem;
  font-weight: 700;
  line-height: 1.3;
}

.operations-page__heroStats {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  min-width: min(100%, 360px);
}

.operations-page__heroStat {
  padding: 14px 16px;
  border-radius: 18px;
  background: rgba(var(--v-theme-surface), 0.94);
  box-shadow: inset 0 0 0 1px rgba(var(--v-theme-on-surface), 0.05);
}

.operations-page__heroStatLabel {
  font-size: 0.74rem;
  font-weight: 700;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: rgba(var(--v-theme-on-surface), 0.56);
}

.operations-page__heroStatValue {
  margin-top: 8px;
  font-size: 1.5rem;
  font-weight: 700;
}

.operations-page__heroStatHint {
  margin-top: 4px;
  font-size: 0.8rem;
  color: rgba(var(--v-theme-on-surface), 0.6);
}

.operations-page__tableWrap {
  overflow-x: auto;
}

.operations-page__table th {
  font-size: 0.74rem;
  font-weight: 700;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: rgba(var(--v-theme-on-surface), 0.56);
}

.operations-page__identity {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.operations-page__chipGroup {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.operations-page__stackList {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.operations-page__stackItem,
.operations-page__signalItem {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 14px 16px;
  border-radius: 18px;
  background: rgba(var(--v-theme-on-surface), 0.03);
  box-shadow: inset 0 0 0 1px rgba(var(--v-theme-on-surface), 0.05);
}

.operations-page__stackValue {
  font-size: 1rem;
  font-weight: 700;
}

.operations-page__emptyState {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  min-height: 240px;
  text-align: center;
}

.operations-page__watchlistCard {
  height: 100%;
  padding: 16px;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.08);
  border-radius: 20px;
  background: rgba(var(--v-theme-surface), 0.96);
}

.operations-page__watchlistHead {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.operations-page__watchlistCount {
  font-size: 1.5rem;
  font-weight: 700;
}

.operations-page__watchlistDays {
  margin-bottom: 6px;
  font-size: 0.88rem;
  font-weight: 700;
}

@media (max-width: 959px) {
  .operations-page__heroBody {
    flex-direction: column;
  }

  .operations-page__heroStats {
    width: 100%;
  }
}

@media (max-width: 600px) {
  .operations-page__heroStats {
    grid-template-columns: 1fr;
  }

  .operations-page__stackItem,
  .operations-page__signalItem,
  .operations-page__watchlistHead {
    align-items: flex-start;
    flex-direction: column;
  }
}
</style>