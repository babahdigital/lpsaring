<script lang="ts" setup>
import { useNuxtApp } from '#app'
import { computed, onMounted, ref } from 'vue'
import { useSnackbar } from '~/composables/useSnackbar'

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
    await $api('/users/me/devices/bind-current', { method: 'POST' })
    snackbar.add({ type: 'success', title: 'Berhasil', text: 'Perangkat berhasil diikat.' })
    await loadDevices()
  }
  catch (err: any) {
    const msg = typeof err.data?.message === 'string' ? err.data.message : 'Gagal mengikat perangkat.'
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
  <VCard>
    <VCardItem>
      <VCardTitle class="text-h5">
        Perangkat Terdaftar
      </VCardTitle>
      <VCardSubtitle>Kelola perangkat yang diizinkan mengakses akun Anda.</VCardSubtitle>
    </VCardItem>

    <VCardActions class="pt-0">
      <VSpacer />
      <VBtn
        color="primary"
        variant="tonal"
        size="small"
        prepend-icon="tabler-device-mobile"
        :loading="binding"
        @click="bindCurrentDevice"
      >
        Ikat Perangkat Saat Ini
      </VBtn>
    </VCardActions>

    <VCardText>
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
        <VList lines="three" density="compact" class="card-list">
          <template v-for="(item, index) in devices" :key="item.id">
            <VListItem>
          <VListItemTitle class="font-weight-semibold text-subtitle-1">
            {{ getDeviceLabel(item) }}
          </VListItemTitle>
          <VListItemSubtitle class="text-caption text-wrap">
            MAC: {{ item.mac_address }}
          </VListItemSubtitle>
          <VListItemSubtitle v-if="item.ip_address" class="text-caption text-wrap">
            IP: {{ item.ip_address }}
          </VListItemSubtitle>
          <VListItemSubtitle class="text-caption text-medium-emphasis text-wrap">
            Terakhir digunakan
          </VListItemSubtitle>
          <VListItemSubtitle class="text-caption text-medium-emphasis text-wrap">
            Tanggal: {{ formatDateOnly(item.last_seen_at) }}
          </VListItemSubtitle>
          <VListItemSubtitle class="text-caption text-medium-emphasis text-wrap">
            Jam: {{ formatTimeOnly(item.last_seen_at) }}
          </VListItemSubtitle>
          <template #append>
            <div class="d-flex flex-column align-end gap-2">
              <VChip
                :color="item.is_authorized ? 'success' : 'warning'"
                size="x-small"
                label
              >
                {{ item.is_authorized ? 'Diizinkan' : 'Ditangguhkan' }}
              </VChip>
              <div class="d-flex align-center gap-1">
                <VBtn
                  icon
                  variant="text"
                  size="small"
                  color="primary"
                  @click="openEditLabel(item)"
                >
                  <VIcon icon="tabler-pencil" size="16" />
                </VBtn>
                <VBtn
                  icon
                  variant="text"
                  size="small"
                  color="error"
                  :disabled="removingId === item.id"
                  @click="confirmRemove(item)"
                >
                  <VIcon icon="tabler-trash" size="16" />
                </VBtn>
              </div>
            </div>
          </template>
          </VListItem>
          <VDivider v-if="index < devices.length - 1" class="my-2" />
          </template>
        </VList>
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
.card-list {
  --v-card-list-padding: 0.5rem;
  margin-top: 1px !important;
}
.device-list {
  max-height: 420px;
}
</style>
