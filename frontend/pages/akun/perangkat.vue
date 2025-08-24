<script setup lang="ts">
import { useNuxtApp } from '#app'
import { onMounted, reactive, ref, computed } from 'vue'
import { useSnackbar } from '~/composables/useSnackbar'

interface UserDevice {
  id: string
  mac_address: string
  ip_address?: string | null
  device_name: string
  last_seen_at: string | null
  status?: string | null
}

const { $api } = useNuxtApp()
const { add: addSnackbar } = useSnackbar()
useHead({ title: 'Manajemen Perangkat' })

const devices = ref<UserDevice[]>([])
const loading = ref(true)
const actionLoading = ref(false)
const dialogs = reactive({ delete: false, edit: false })
const selectedDevice = ref<UserDevice | null>(null)
const newDeviceName = ref('')

const maxDevices = ref<number>(3)
const isLimitReached = computed(() => devices.value.length >= maxDevices.value)

async function fetchDevices() {
  loading.value = true
  try {
    devices.value = await $api<UserDevice[]>('/users/me/devices')
    // Optional: also fetch MAX_DEVICES_PER_USER if exposed via /api/public
    // const settings = await $api<Record<string, string>>('/public')
    // maxDevices.value = Number(settings.MAX_DEVICES_PER_USER ?? 3)
  }
  catch (err: any) {
    const msg = err?.data?.message || err?.message || 'Gagal memuat daftar perangkat.'
    addSnackbar({ title: 'Error', text: msg, type: 'error' })
  }
  finally {
    loading.value = false
  }
}

function openEditDialog(device: UserDevice) {
  selectedDevice.value = { ...device }
  newDeviceName.value = device.device_name
  dialogs.edit = true
}

function openDeleteDialog(device: UserDevice) {
  selectedDevice.value = device
  dialogs.delete = true
}

async function handleUpdateDeviceName() {
  if (!selectedDevice.value || !newDeviceName.value) return
  actionLoading.value = true
  try {
    await $api(`/users/me/devices/${selectedDevice.value.id}`, { method: 'PUT', body: { device_name: newDeviceName.value } })
    addSnackbar({ title: 'Berhasil', text: 'Nama perangkat berhasil diperbarui.', type: 'success' })
    dialogs.edit = false
    await fetchDevices()
  }
  catch (err: any) {
    const msg = err?.data?.message || err?.message || 'Gagal memperbarui nama perangkat.'
    addSnackbar({ title: 'Error', text: msg, type: 'error' })
  }
  finally {
    actionLoading.value = false
  }
}

async function handleDeleteDevice() {
  if (!selectedDevice.value) return
  actionLoading.value = true
  try {
    await $api(`/users/me/devices/${selectedDevice.value.id}`, { method: 'DELETE' })
    addSnackbar({ title: 'Berhasil', text: 'Perangkat berhasil dihapus.', type: 'success' })
    dialogs.delete = false
    await fetchDevices()
  }
  catch (err: any) {
    const msg = err?.data?.message || err?.message || 'Gagal menghapus perangkat.'
    addSnackbar({ title: 'Error', text: msg, type: 'error' })
  }
  finally {
    actionLoading.value = false
  }
}

function formatDateTime(dateString?: string | null) {
  if (!dateString) return 'N/A'
  return new Date(dateString).toLocaleString('id-ID', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' })
}

onMounted(fetchDevices)
</script>

<template>
  <div>
    <VCard>
      <VCardItem>
        <VCardTitle class="text-h5">
          Perangkat Saya
        </VCardTitle>
        <VCardSubtitle>Kelola perangkat yang memiliki akses ke akun Anda.</VCardSubtitle>
      </VCardItem>
      <VCardText>
        <VAlert
          v-if="!loading && devices.length < 3"
          type="info"
          variant="tonal"
          class="mb-6"
        >
          Anda dapat mendaftarkan hingga <strong>{{ 3 - devices.length }}</strong> perangkat lagi.
        </VAlert>
        <VAlert
          v-if="!loading && devices.length >= 3"
          type="warning"
          variant="tonal"
          class="mb-6"
        >
          Anda telah mencapai batas maksimum <strong>3 perangkat</strong> terdaftar.
        </VAlert>

        <VDataTable
          :headers="[
            { title: 'Perangkat', key: 'device_name' },
            { title: 'MAC', key: 'mac_address' },
            { title: 'IP', key: 'ip_address' },
            { title: 'Terakhir Aktif', key: 'last_seen_at' },
            { title: 'Aksi', key: 'actions', align: 'end' },
          ]"
          :items="devices"
          :loading="loading"
          :items-per-page="-1"
          class="text-no-wrap"
        >
          <template #item.device_name="{ item }">
            <div class="d-flex align-center">
              <VIcon icon="tabler-device-laptop" class="me-3" />
              <span class="font-weight-medium">{{ item.device_name }}</span>
            </div>
          </template>

          <template #item.last_seen_at="{ item }">
            {{ formatDateTime(item.last_seen_at) }}
          </template>

          <template #item.actions="{ item }">
            <div class="d-flex justify-end">
              <VBtn icon size="small" variant="text" @click="openEditDialog(item)">
                <VIcon icon="tabler-pencil" />
              </VBtn>
              <VBtn icon size="small" variant="text" color="error" @click="openDeleteDialog(item)">
                <VIcon icon="tabler-trash" />
              </VBtn>
            </div>
          </template>

          <template #loading>
            <VSkeletonLoader type="table-row@3" />
          </template>

          <template #no-data>
            <div class="text-center py-8">
              <VIcon icon="tabler-devices-off" size="48" class="mb-2 text-disabled" />
              <p class="text-disabled">
                Belum ada perangkat terdaftar.
              </p>
            </div>
          </template>

          <template #bottom />
        </VDataTable>
      </VCardText>
    </VCard>

    <VDialog v-model="dialogs.edit" max-width="500px" persistent>
      <VCard>
        <VCardTitle>Ubah Nama Perangkat</VCardTitle>
        <VCardText>
          <VTextField
            v-model="newDeviceName"
            label="Nama Perangkat Baru"
            placeholder="Contoh: Laptop Kerja"
            autofocus
            @keyup.enter="handleUpdateDeviceName"
          />
        </VCardText>
        <VCardActions>
          <VSpacer />
          <VBtn variant="text" @click="dialogs.edit = false">
            Batal
          </VBtn>
          <VBtn color="primary" :loading="actionLoading" @click="handleUpdateDeviceName">
            Simpan
          </VBtn>
        </VCardActions>
      </VCard>
    </VDialog>

    <VDialog v-model="dialogs.delete" max-width="500px" persistent>
      <VCard>
        <VCardTitle class="text-h5">
          Konfirmasi Hapus
        </VCardTitle>
        <VCardText>
          Apakah Anda yakin ingin menghapus perangkat <strong>{{ selectedDevice?.device_name }}</strong> ({{ selectedDevice?.mac_address }})?
          <br /><br />
          Perangkat ini tidak akan bisa terhubung ke jaringan lagi menggunakan akun Anda sampai diotorisasi ulang.
        </VCardText>
        <VCardActions>
          <VSpacer />
          <VBtn variant="text" @click="dialogs.delete = false">
            Batal
          </VBtn>
          <VBtn color="error" :loading="actionLoading" @click="handleDeleteDevice">
            Hapus
          </VBtn>
        </VCardActions>
      </VCard>
    </VDialog>
  </div>
</template>
