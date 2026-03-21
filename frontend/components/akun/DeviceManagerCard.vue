<script lang="ts" setup>
import { useNuxtApp } from '#app'
import { computed, onMounted, ref } from 'vue'
import { useDisplay } from 'vuetify'
import { useSnackbar } from '~/composables/useSnackbar'
import { useAuthStore } from '~/store/auth'

interface DeviceItem {
  id: string
  mac_address: string
  ip_address: string | null
  label: string | null
  user_agent?: string | null
  is_authorized: boolean
  first_seen_at?: string | null
  last_seen_at?: string | null
  authorized_at?: string | null
  deauthorized_at?: string | null
}

const { $api } = useNuxtApp()
const snackbar = useSnackbar()
const authStore = useAuthStore()
const display = useDisplay()
const isMobile = computed(() => display.smAndDown.value)

const devices = ref<DeviceItem[]>([])
const loading = ref(false)
const error = ref<string | null>(null)
const confirmDialog = ref(false)
const editDialog = ref(false)
const selectedDevice = ref<DeviceItem | null>(null)
const removingId = ref<string | null>(null)
const binding = ref(false)
const savingLabel = ref(false)
const editLabel = ref('')
const bindingInfoDialog = ref(false)
const bindingInfoMessage = ref('')

const hasDevices = computed(() => devices.value.length > 0)
const authorizedDevicesCount = computed(() => devices.value.filter(device => device.is_authorized).length)
const suspendedDevicesCount = computed(() => Math.max(0, devices.value.length - authorizedDevicesCount.value))

const deviceOverviewCards = computed(() => [
  {
    key: 'total',
    label: 'Total Device',
    value: `${devices.value.length}`,
    caption: hasDevices.value ? 'Perangkat yang pernah tercatat' : 'Belum ada perangkat',
    color: 'primary',
    icon: 'tabler-devices',
  },
  {
    key: 'authorized',
    label: 'Diizinkan',
    value: `${authorizedDevicesCount.value}`,
    caption: 'Perangkat aktif yang boleh akses',
    color: 'success',
    icon: 'tabler-shield-check',
  },
  {
    key: 'suspended',
    label: 'Ditangguhkan',
    value: `${suspendedDevicesCount.value}`,
    caption: 'Perangkat yang perlu otorisasi ulang',
    color: suspendedDevicesCount.value > 0 ? 'warning' : 'secondary',
    icon: 'tabler-shield-x',
  },
])

function formatDateOnly(dateStr?: string | null) {
  if (!dateStr)
    return '—'
  const date = new Date(dateStr)
  return new Intl.DateTimeFormat('id-ID', { dateStyle: 'medium' }).format(date)
}

function formatTimeOnly(dateStr?: string | null) {
  if (!dateStr)
    return '—'
  const date = new Date(dateStr)
  return new Intl.DateTimeFormat('id-ID', { timeStyle: 'short' }).format(date)
}

function getDeviceLabel(device: DeviceItem) {
  if (device.label)
    return device.label

  const ua = (device.user_agent || '').toLowerCase()
  if (ua.includes('iphone') || ua.includes('ipad'))
    return 'Apple Device'
  if (ua.includes('android'))
    return 'Android Device'
  if (ua.includes('windows'))
    return 'Windows PC'
  if (ua.includes('mac'))
    return 'Mac Device'
  if (ua.includes('linux'))
    return 'Linux Device'

  return 'Perangkat'
}

function getDeviceIcon(device: DeviceItem) {
  const label = getDeviceLabel(device).toLowerCase()
  if (label.includes('apple'))
    return 'tabler-brand-apple'
  if (label.includes('android'))
    return 'tabler-brand-android'
  if (label.includes('windows'))
    return 'tabler-brand-windows'
  if (label.includes('mac'))
    return 'tabler-device-laptop'
  if (label.includes('linux'))
    return 'tabler-brand-linux'
  return 'tabler-devices'
}

function formatDateTime(dateStr?: string | null) {
  if (!dateStr)
    return 'Belum ada aktivitas'
  const date = new Date(dateStr)
  return new Intl.DateTimeFormat('id-ID', { dateStyle: 'medium', timeStyle: 'short' }).format(date)
}

async function loadDevices() {
  loading.value = true
  error.value = null
  try {
    const response = await $api<{ devices: DeviceItem[] }>('/users/me/devices')
    devices.value = response.devices || []
  }
  catch (err: any) {
    const msg = typeof err.data?.message === 'string' ? err.data.message : 'Gagal memuat perangkat.'
    error.value = msg
  }
  finally {
    loading.value = false
  }
}

function confirmRemove(device: DeviceItem) {
  selectedDevice.value = device
  confirmDialog.value = true
}

function openEditLabel(device: DeviceItem) {
  selectedDevice.value = device
  editLabel.value = device.label || ''
  editDialog.value = true
}

async function removeDevice() {
  if (!selectedDevice.value)
    return

  removingId.value = selectedDevice.value.id
  try {
    await $api(`/users/me/devices/${selectedDevice.value.id}`, { method: 'DELETE' })
    devices.value = devices.value.filter(d => d.id !== selectedDevice.value?.id)
    snackbar.add({ type: 'success', title: 'Berhasil', text: 'Perangkat berhasil dihapus.' })
  }
  catch (err: any) {
    const msg = typeof err.data?.message === 'string' ? err.data.message : 'Gagal menghapus perangkat.'
    snackbar.add({ type: 'error', title: 'Gagal', text: msg })
  }
  finally {
    confirmDialog.value = false
    selectedDevice.value = null
    removingId.value = null
  }
}

async function saveLabel() {
  if (!selectedDevice.value)
    return

  savingLabel.value = true
  try {
    await $api(`/users/me/devices/${selectedDevice.value.id}/label`, {
      method: 'PUT',
      body: { label: editLabel.value },
    })
    selectedDevice.value.label = editLabel.value.trim() || null
    snackbar.add({ type: 'success', title: 'Berhasil', text: 'Label perangkat diperbarui.' })
    editDialog.value = false
  }
  catch (err: any) {
    const msg = typeof err.data?.message === 'string' ? err.data.message : 'Gagal memperbarui label.'
    snackbar.add({ type: 'error', title: 'Gagal', text: msg })
  }
  finally {
    savingLabel.value = false
  }
}

async function bindCurrentDevice() {
  binding.value = true
  try {
    const ok = await authStore.authorizeDevice()
    if (!ok)
      throw new Error(authStore.error || 'Gagal mengikat perangkat.')

    snackbar.add({ type: 'success', title: 'Berhasil', text: 'Perangkat berhasil diikat.' })
    await loadDevices()
  }
  catch (err: any) {
    const msg = typeof err.data?.message === 'string'
      ? err.data.message
      : typeof err.message === 'string'
        ? err.message
        : 'Gagal mengikat perangkat.'
    if (msg.includes('Perangkat belum diotorisasi') || msg.includes('Limit perangkat tercapai')) {
      bindingInfoMessage.value = msg
      bindingInfoDialog.value = true
    }
    snackbar.add({ type: 'error', title: 'Gagal', text: msg })
  }
  finally {
    binding.value = false
  }
}

onMounted(() => {
  loadDevices()
})
</script>

<template>
  <VCard class="device-manager-card">
    <VCardItem>
      <VCardTitle class="text-h5">
        Perangkat Terdaftar
      </VCardTitle>
      <VCardSubtitle>Kelola perangkat yang diizinkan mengakses akun Anda.</VCardSubtitle>
    </VCardItem>

    <VCardText>
      <div class="device-manager__overview">
        <div class="device-manager__overview-grid">
          <div v-for="item in deviceOverviewCards" :key="item.key" class="device-manager__overview-card">
            <div class="device-manager__overview-head">
              <VAvatar size="34" :color="item.color" variant="tonal">
                <VIcon :icon="item.icon" size="18" />
              </VAvatar>
              <div class="device-manager__overview-label">{{ item.label }}</div>
            </div>
            <div class="device-manager__overview-value">{{ item.value }}</div>
            <div class="device-manager__overview-caption">{{ item.caption }}</div>
          </div>
        </div>

        <VBtn
          color="primary"
          variant="tonal"
          size="small"
          prepend-icon="tabler-device-mobile"
          :loading="binding"
          :block="isMobile"
          @click="bindCurrentDevice"
        >
          Ikat Perangkat Saat Ini
        </VBtn>
      </div>

      <VAlert v-if="error" type="error" variant="tonal" density="compact" class="mb-4">
        {{ error }}
      </VAlert>

      <div v-if="loading" class="text-center py-6">
        <VProgressCircular indeterminate color="primary" />
      </div>

      <VAlert v-else-if="!hasDevices" type="info" variant="tonal" density="compact">
        Belum ada perangkat terdaftar.
      </VAlert>

      <AppPerfectScrollbar v-else class="device-list">
        <div class="device-manager__list">
          <div v-for="item in devices" :key="item.id" class="device-manager__deviceCard">
            <div class="device-manager__deviceHeader">
              <div class="device-manager__deviceIdentity">
                <VAvatar size="42" color="primary" variant="tonal">
                  <VIcon :icon="getDeviceIcon(item)" size="20" />
                </VAvatar>
                <div class="device-manager__deviceCopy">
                  <div class="font-weight-semibold text-subtitle-1">
                    {{ getDeviceLabel(item) }}
                  </div>
                  <div class="text-caption text-medium-emphasis">
                    {{ formatDateTime(item.last_seen_at) }}
                  </div>
                </div>
              </div>

              <div class="device-manager__deviceActions">
                <VChip :color="item.is_authorized ? 'success' : 'warning'" size="x-small" label>
                  {{ item.is_authorized ? 'Diizinkan' : 'Ditangguhkan' }}
                </VChip>
                <div class="d-flex align-center gap-1">
                  <VBtn icon variant="tonal" size="small" color="primary" @click="openEditLabel(item)">
                    <VIcon icon="tabler-pencil" size="16" />
                  </VBtn>
                  <VBtn icon variant="tonal" size="small" color="error" :disabled="removingId === item.id" @click="confirmRemove(item)">
                    <VIcon icon="tabler-trash" size="16" />
                  </VBtn>
                </div>
              </div>
            </div>

            <div class="device-manager__metaGrid mt-4">
              <div class="device-manager__metaItem">
                <div class="device-manager__metaLabel">MAC</div>
                <div class="device-manager__metaValue">{{ item.mac_address }}</div>
              </div>
              <div class="device-manager__metaItem">
                <div class="device-manager__metaLabel">IP</div>
                <div class="device-manager__metaValue">{{ item.ip_address || 'Belum ada IP' }}</div>
              </div>
              <div class="device-manager__metaItem">
                <div class="device-manager__metaLabel">Pertama Terlihat</div>
                <div class="device-manager__metaValue">{{ formatDateOnly(item.first_seen_at) }}</div>
              </div>
              <div class="device-manager__metaItem">
                <div class="device-manager__metaLabel">Terakhir Aktif</div>
                <div class="device-manager__metaValue">{{ formatDateOnly(item.last_seen_at) }} • {{ formatTimeOnly(item.last_seen_at) }}</div>
              </div>
            </div>
          </div>
        </div>
      </AppPerfectScrollbar>
    </VCardText>

    <VDialog v-model="confirmDialog" max-width="420">
      <VCard>
        <VCardTitle>Hapus Perangkat?</VCardTitle>
        <VCardText>
          <p class="mb-2">
            Perangkat yang akan dihapus:
          </p>
          <p class="text-body-1 font-weight-medium">
            {{ selectedDevice ? getDeviceLabel(selectedDevice) : '' }}
          </p>
          <p class="text-caption text-medium-emphasis">
            Aksi ini akan mencabut akses perangkat tersebut.
          </p>
        </VCardText>
        <VCardActions>
          <VSpacer />
          <VBtn variant="text" @click="confirmDialog = false">
            Batal
          </VBtn>
          <VBtn
            color="error"
            :loading="!!removingId"
            @click="removeDevice"
          >
            Hapus
          </VBtn>
        </VCardActions>
      </VCard>
    </VDialog>

    <VDialog v-model="editDialog" max-width="480">
      <VCard>
        <VCardTitle>Ubah Label Perangkat</VCardTitle>
        <VCardText>
          <AppTextField
            v-model="editLabel"
            label="Label Perangkat"
            placeholder="Contoh: HP pribadi"
            maxlength="100"
          />
        </VCardText>
        <VCardActions>
          <VSpacer />
          <VBtn variant="text" @click="editDialog = false">
            Batal
          </VBtn>
          <VBtn
            color="primary"
            :loading="savingLabel"
            @click="saveLabel"
          >
            Simpan
          </VBtn>
        </VCardActions>
      </VCard>
    </VDialog>

    <VDialog v-model="bindingInfoDialog" max-width="420">
      <VCard>
        <VCardTitle class="text-h6">
          Otorisasi Perangkat
        </VCardTitle>
        <VCardText>
          {{ bindingInfoMessage }}
          <div class="mt-3 text-medium-emphasis">
            Jika perangkat belum diotorisasi, coba login melalui portal captive dan ikuti langkah otorisasi perangkat.
          </div>
        </VCardText>
        <VCardActions class="justify-end">
          <VBtn color="primary" @click="bindingInfoDialog = false">
            Mengerti
          </VBtn>
        </VCardActions>
      </VCard>
    </VDialog>
  </VCard>
</template>

<style scoped>
.device-manager-card {
  border: 1px solid rgba(var(--v-theme-on-surface), 0.08);
}

.device-manager__overview {
  display: flex;
  flex-direction: column;
  gap: 16px;
  margin-bottom: 20px;
}

.device-manager__overview-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

.device-manager__overview-card {
  padding: 14px 16px;
  border-radius: 16px;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.08);
  background: rgba(var(--v-theme-surface), 0.72);
}

.device-manager__overview-head {
  display: flex;
  align-items: center;
  gap: 10px;
}

.device-manager__overview-label {
  font-size: 0.78rem;
  font-weight: 700;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: rgba(var(--v-theme-on-surface), 0.56);
}

.device-manager__overview-value {
  margin-top: 12px;
  font-size: 1.02rem;
  font-weight: 700;
}

.device-manager__overview-caption {
  margin-top: 4px;
  font-size: 0.8rem;
  line-height: 1.4;
  color: rgba(var(--v-theme-on-surface), 0.62);
}

.device-list {
  max-height: 420px;
}

.device-manager__list {
  display: grid;
  gap: 12px;
}

.device-manager__deviceCard {
  padding: 16px;
  border-radius: 18px;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.08);
  background: rgba(var(--v-theme-surface), 0.9);
}

.device-manager__deviceHeader {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.device-manager__deviceIdentity {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
  flex: 1 1 auto;
}

.device-manager__deviceCopy {
  min-width: 0;
}

.device-manager__deviceActions {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 10px;
}

.device-manager__metaGrid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.device-manager__metaItem {
  padding: 10px 12px;
  border-radius: 14px;
  background: rgba(var(--v-theme-on-surface), 0.025);
}

.device-manager__metaLabel {
  font-size: 0.72rem;
  font-weight: 700;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: rgba(var(--v-theme-on-surface), 0.56);
}

.device-manager__metaValue {
  margin-top: 6px;
  font-size: 0.86rem;
  line-height: 1.45;
  word-break: break-word;
}

@media (max-width: 600px) {
  .device-manager__overview-grid {
    grid-template-columns: 1fr;
  }

  .device-manager__deviceHeader {
    flex-direction: column;
  }

  .device-manager__deviceActions {
    width: 100%;
    align-items: stretch;
  }

  .device-manager__metaGrid {
    grid-template-columns: 1fr;
  }
}
</style>
