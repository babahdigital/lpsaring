<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useSnackbar } from '@/composables/useSnackbar'
import { useAuthStore } from '@/store/auth'

interface BackupItem {
  name: string
  size_bytes: number
  created_at: string
}

const { $api } = useNuxtApp()
const { add: showSnackbar } = useSnackbar()
const authStore = useAuthStore()

definePageMeta({
  requiredRole: ['ADMIN', 'SUPER_ADMIN'],
})

useHead({ title: 'Backup & Restore Database' })

const backups = ref<BackupItem[]>([])
const loading = ref(false)
const creating = ref(false)
const uploading = ref(false)
const restoring = ref(false)
const restoreDialog = ref(false)
const selectedBackup = ref<BackupItem | null>(null)
const uploadFile = ref<File | null>(null)
const restoreReplaceUsers = ref(false)

function formatSize(bytes: number) {
  if (!bytes)
    return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.min(Math.floor(Math.log(bytes) / Math.log(k)), sizes.length - 1)
  return `${(bytes / k ** i).toFixed(2)} ${sizes[i]}`
}

function formatDate(value: string) {
  return new Date(value).toLocaleString('id-ID', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

async function fetchBackups() {
  loading.value = true
  try {
    const response = await $api<{ items: BackupItem[] }>('/admin/backups')
    backups.value = response.items
  } catch (error: any) {
    const errorMessage = (typeof error.data?.message === 'string' && error.data.message !== '')
      ? error.data.message
      : 'Gagal memuat daftar backup.'
    showSnackbar({ type: 'error', title: 'Terjadi Kesalahan', text: errorMessage })
  } finally {
    loading.value = false
  }
}

async function createBackup() {
  creating.value = true
  try {
    await $api('/admin/backups', { method: 'POST' })
    showSnackbar({ type: 'success', title: 'Berhasil', text: 'Backup berhasil dibuat.' })
    await fetchBackups()
  } catch (error: any) {
    const errorMessage = (typeof error.data?.message === 'string' && error.data.message !== '')
      ? error.data.message
      : 'Gagal membuat backup.'
    showSnackbar({ type: 'error', title: 'Terjadi Kesalahan', text: errorMessage })
  } finally {
    creating.value = false
  }
}

async function uploadBackupFile() {
  if (!uploadFile.value)
    return

  uploading.value = true
  try {
    const formData = new FormData()
    formData.append('file', uploadFile.value)

    await $api('/admin/backups/upload', {
      method: 'POST',
      body: formData,
    })

    showSnackbar({ type: 'success', title: 'Berhasil', text: 'File backup berhasil diunggah.' })
    uploadFile.value = null
    await fetchBackups()
  } catch (error: any) {
    const errorMessage = (typeof error.data?.message === 'string' && error.data.message !== '')
      ? error.data.message
      : 'Gagal mengunggah file backup.'
    showSnackbar({ type: 'error', title: 'Terjadi Kesalahan', text: errorMessage })
  } finally {
    uploading.value = false
  }
}

function openRestoreDialog(item: BackupItem) {
  selectedBackup.value = item
  restoreReplaceUsers.value = false
  restoreDialog.value = true
}

async function restoreBackup() {
  if (!selectedBackup.value)
    return

  restoring.value = true
  try {
    await $api('/admin/backups/restore', {
      method: 'POST',
      body: {
        filename: selectedBackup.value.name,
        confirm: 'RESTORE',
        restore_mode: restoreReplaceUsers.value ? 'replace_users' : 'merge',
      },
    })
    showSnackbar({ type: 'success', title: 'Restore Berhasil', text: `Restore ${selectedBackup.value.name} selesai dijalankan.` })
    restoreDialog.value = false
    restoreReplaceUsers.value = false
  } catch (error: any) {
    const errorMessage = (typeof error.data?.message === 'string' && error.data.message !== '')
      ? error.data.message
      : 'Gagal menjalankan restore database.'
    showSnackbar({ type: 'error', title: 'Terjadi Kesalahan', text: errorMessage })
  } finally {
    restoring.value = false
  }
}

onMounted(fetchBackups)
</script>

<template>
  <div>
    <VRow class="mb-4" align="center">
      <VCol cols="12" md="6">
        <h3 class="text-h4">Backup Database</h3>
        <p class="text-body-2 text-disabled">
          Buat backup, unduh file, unggah backup `.sql/.dump`, dan restore oleh Super Admin.
        </p>
      </VCol>
      <VCol cols="12" md="6" class="d-flex justify-end">
        <VBtn
          color="primary"
          :loading="creating"
          @click="createBackup"
        >
          Buat Backup
        </VBtn>
      </VCol>
    </VRow>

    <VCard
      v-if="authStore.isSuperAdmin === true"
      class="mb-4"
    >
      <VCardItem>
        <VCardTitle>Upload File Backup</VCardTitle>
      </VCardItem>
      <VCardText>
        <VRow>
          <VCol cols="12" md="9">
            <VFileInput
              v-model="uploadFile"
              label="Pilih file backup"
              accept=".dump,.sql"
              prepend-icon="tabler-upload"
              density="comfortable"
              show-size
            />
          </VCol>
          <VCol cols="12" md="3" class="d-flex align-center">
            <VBtn
              block
              color="secondary"
              :loading="uploading"
              :disabled="!uploadFile"
              @click="uploadBackupFile"
            >
              Upload
            </VBtn>
          </VCol>
        </VRow>
      </VCardText>
    </VCard>

    <VCard>
      <VDataTable
        :items="backups"
        :loading="loading"
        class="text-no-wrap"
      >
        <template #headers>
          <tr>
            <th class="text-left">Nama File</th>
            <th class="text-left">Ukuran</th>
            <th class="text-left">Dibuat</th>
            <th class="text-left">Aksi</th>
          </tr>
        </template>
        <template #item="{ item }">
          <tr>
            <td>{{ item.name }}</td>
            <td>{{ formatSize(item.size_bytes) }}</td>
            <td>{{ formatDate(item.created_at) }}</td>
            <td>
              <VBtn
                :href="`/api/admin/backups/${item.name}`"
                target="_blank"
                rel="noopener"
                size="small"
                variant="tonal"
                color="primary"
              >
                Unduh
              </VBtn>
              <VBtn
                v-if="authStore.isSuperAdmin === true"
                class="ms-2"
                size="small"
                variant="outlined"
                color="warning"
                :disabled="restoring"
                @click="openRestoreDialog(item)"
              >
                Restore
              </VBtn>
            </td>
          </tr>
        </template>
        <template #no-data>
          <div class="text-center text-disabled py-6">
            Belum ada backup.
          </div>
        </template>
      </VDataTable>
    </VCard>

    <VDialog
      v-model="restoreDialog"
      max-width="500"
    >
      <VCard>
        <VCardItem>
          <VCardTitle>Konfirmasi Restore Database</VCardTitle>
        </VCardItem>
        <VCardText>
          Restore akan menimpa data saat ini dengan isi backup <strong>{{ selectedBackup?.name }}</strong>.
          Lanjutkan hanya jika Anda yakin.

          <VSwitch
            v-if="selectedBackup?.name?.toLowerCase().endsWith('.sql')"
            v-model="restoreReplaceUsers"
            class="mt-4"
            color="warning"
            label="Ganti data users saat restore SQL (truncate users dulu)"
            hint="Aktifkan ini untuk file SQL data-only users agar tidak gagal duplicate key."
            persistent-hint
          />
        </VCardText>
        <VCardActions>
          <VSpacer />
          <VBtn
            variant="text"
            :disabled="restoring"
            @click="restoreDialog = false"
          >
            Batal
          </VBtn>
          <VBtn
            color="warning"
            :loading="restoring"
            @click="restoreBackup"
          >
            Ya, Restore
          </VBtn>
        </VCardActions>
      </VCard>
    </VDialog>
  </div>
</template>
