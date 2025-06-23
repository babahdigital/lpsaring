<script lang="ts" setup>
import type { VDataTableServer } from 'vuetify/labs/VDataTable'
import { useNuxtApp } from '#app'
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useDisplay } from 'vuetify'
import ProfileManagementDialog from '@/components/packages/ProfileManagementDialog.vue' // <--- IMPORT DIALOG BARU
import ProfileSetupDialog from '@/components/packages/ProfileSetupDialog.vue'
import { useSnackbar } from '@/composables/useSnackbar'
import { useAuthStore } from '@/store/auth' // <--- IMPORT AUTH STORE

// --- TIPE DATA ---
interface Profile {
  id: string
  profile_name: string
}
interface Package {
  id: string
  name: string
  description: string | null
  price: number
  is_active: boolean
  profile_id: string
  data_quota_gb: number
  duration_days: number
  profile: Profile
}

// --- INISIALISASI & STATE ---
const { $api } = useNuxtApp()
const { smAndDown } = useDisplay()
const snackbar = useSnackbar()
const authStore = useAuthStore() // <--- INISIALISASI AUTH STORE

const packages = ref<Package[]>([])
const loading = ref(true)
const totalPackages = ref(0)
const options = ref({ page: 1, itemsPerPage: 10, sortBy: [] as any[] })

const dialog = reactive({ edit: false, delete: false })
const selectedPackage = ref<Package | null>(null)
const editedPackage = ref<Partial<Package>>({})

// State untuk Dialog
const showProfileSetupDialog = ref(false)
const showProfileManagementDialog = ref(false) // <--- STATE UNTUK DIALOG BARU
const profileErrorMessage = ref('')
const lastFailedAction = ref<(() => void) | null>(null)

// State untuk form
const isUnlimited = ref(false)
const formattedPrice = ref('')

const defaultPackage: Partial<Package> = {
  name: '',
  price: 0,
  description: '',
  is_active: true,
  data_quota_gb: 0,
  duration_days: 30,
}

// --- FUNGSI & LOGIKA ---
onMounted(fetchPackages)

// Perbaikan: Pengecekan `id` yang mungkin `undefined` dibuat eksplisit.
const formTitle = computed(() => (editedPackage.value.id != null ? 'Edit Paket Jualan' : 'Tambah Paket Jualan'))

const headers = [
  { title: 'NAMA PAKET', key: 'name', sortable: false },
  { title: 'DETAIL & PROFIL', key: 'details', sortable: false, align: 'start' },
  { title: 'HARGA', key: 'price', align: 'end' },
  { title: 'STATUS', key: 'is_active', align: 'center' },
  { title: 'AKSI', key: 'actions', sortable: false, align: 'center' },
]

async function fetchPackages() {
  loading.value = true
  try {
    const params = new URLSearchParams({
      page: String(options.value.page),
      itemsPerPage: String(options.value.itemsPerPage),
    })
    const response = await $api<{ items: Package[], totalItems: number }>(`/admin/packages?${params.toString()}`)
    packages.value = response.items
    totalPackages.value = response.totalItems || 0
  }
  catch (e: any) {
    // Perbaikan: Menggunakan operator `??` (nullish coalescing) untuk `any`.
    snackbar.add({ type: 'error', title: 'Gagal Memuat', text: e.data?.message ?? 'Tidak dapat memuat daftar paket.' })
  }
  finally {
    loading.value = false
  }
}

function openDialog(type: 'edit' | 'delete', pkg: Package | null = null) {
  if (type === 'edit') {
    const { profile, ...restOfPkg } = pkg || {}
    editedPackage.value = pkg ? JSON.parse(JSON.stringify(restOfPkg)) : { ...defaultPackage }
    isUnlimited.value = editedPackage.value.data_quota_gb === 0
    dialog.edit = true
  }
  else if (type === 'delete' && pkg) {
    selectedPackage.value = { ...pkg }
    dialog.delete = true
  }
}

async function handleAction(type: 'create' | 'update' | 'delete') {
  let endpoint = '/admin/packages'
  let method: 'POST' | 'PUT' | 'DELETE' = 'POST'
  let successMessage = ''
  let body: object | undefined

  switch (type) {
    case 'create':
      successMessage = 'Paket baru berhasil dibuat.'
      body = editedPackage.value
      break
    case 'update':
      endpoint = `/admin/packages/${editedPackage.value.id}`
      method = 'PUT'
      successMessage = 'Paket berhasil diperbarui.'
      body = editedPackage.value
      break
    case 'delete':
      endpoint = `/admin/packages/${selectedPackage.value!.id}`
      method = 'DELETE'
      successMessage = 'Paket berhasil dihapus.'
      break
  }

  const apiCall = async () => {
    try {
      await $api(endpoint, { method, body })
      snackbar.add({ type: 'success', title: 'Berhasil', text: successMessage })
      await fetchPackages()
      dialog.edit = false
      dialog.delete = false
    }
    catch (error: unknown) { // Mengubah 'any' menjadi 'unknown'
      let errorMessage = 'Terjadi kesalahan tidak terduga.';
      let statusCode = 500;

      if (typeof error === 'object' && error !== null && 'statusCode' in error) {
        statusCode = (error as { statusCode: number }).statusCode;
      }

      if (typeof error === 'object' && error !== null && 'data' in error) {
        const errorData = (error as { data: unknown }).data;
        if (typeof errorData === 'object' && errorData !== null && 'message' in errorData && typeof errorData.message === 'string') {
          errorMessage = errorData.message;
        } else if (typeof errorData === 'object' && errorData !== null && 'errors' in errorData && Array.isArray(errorData.errors)) {
          // Perbaikan: Pengecekan tipe yang eksplisit untuk setiap item error di dalam array
          errorMessage = (errorData.errors as unknown[]).map((err: unknown) => {
            if (typeof err === 'object' && err !== null && 'msg' in err && typeof (err as { msg: string }).msg === 'string') {
              return (err as { msg: string }).msg;
            }
            return String(err);
          }).join(', ');
        }
      }

      // Perbaikan: Pengecekan `error.statusCode` yang lebih eksplisit
      if (statusCode === 409 && errorMessage.includes('Profil')) { // Menggunakan errorMessage yang sudah di-parse
        profileErrorMessage.value = errorMessage;
        showProfileSetupDialog.value = true;
        lastFailedAction.value = apiCall;
      } else {
        snackbar.add({ type: 'error', title: 'Gagal', text: errorMessage });
      }
    }
  }
  await apiCall()
}

function onProfilesCreated() {
  // Perbaikan: Pengecekan eksplisit terhadap `null`.
  if (lastFailedAction.value !== null) {
    snackbar.add({ type: 'info', title: 'Mencoba Lagi', text: 'Konfigurasi selesai, mencoba menyimpan paket kembali...' })
    lastFailedAction.value()
    lastFailedAction.value = null
  }
}

function formatNumber(value: number | string | null | undefined): string { // Perbaikan: Tambahkan null | undefined
  // Perbaikan: Tangani nullish atau NaN secara eksplisit di awal
  const numValue = Number(value);
  if (Number.isNaN(numValue)) { // Perbaikan: Gunakan Number.isNaN
    return '0';
  }
  return new Intl.NumberFormat('id-ID').format(numValue);
}

function unformatNumber(value: string | null | undefined): number { // Perbaikan: Tambahkan null | undefined
  if (value === null || value === undefined) {
    return 0;
  }
  const parsed = Number.parseInt(String(value).replace(/\D/g, ''), 10)
  return Number.isNaN(parsed) ? 0 : parsed // Perbaikan: Gunakan Number.isNaN
}

watch(formattedPrice, (newValue) => {
  const cleanValue = String(newValue).replace(/\D/g, '')
  editedPackage.value.price = unformatNumber(cleanValue)
  const newFormattedValue = formatNumber(cleanValue)
  if (formattedPrice.value !== newFormattedValue)
    formattedPrice.value = newFormattedValue
})
watch(() => dialog.edit, (isOpening) => {
  if (isOpening) {
    // Perbaikan: Tangani editedPackage.value.price yang mungkin null atau undefined
    formattedPrice.value = formatNumber(editedPackage.value.price ?? 0)
    isUnlimited.value = editedPackage.value.data_quota_gb === 0
  }
})
watch(isUnlimited, (isNowUnlimited) => {
  if (isNowUnlimited) {
    editedPackage.value.data_quota_gb = 0
  }
})
watch(() => editedPackage.value.data_quota_gb, (newQuota) => {
  if (newQuota === 0) {
    isUnlimited.value = true
  }
  // Perbaikan: Pengecekan `null` secara eksplisit pada `newQuota`.
  else if (newQuota != null && newQuota > 0 && isUnlimited.value) {
    isUnlimited.value = false
  }
})

useHead({ title: 'Manajemen Paket Jualan' })
</script>

<template>
  <div>
    <VCard>
      <VCardText class="d-flex align-center flex-wrap gap-4 py-4">
        <h5 class="text-h5">
          Manajemen Paket Jualan
        </h5>
        <VSpacer />
        <div class="d-flex flex-wrap gap-2">
          <VBtn
            v-if="authStore.user?.role === 'SUPER_ADMIN'"
            prepend-icon="tabler-server"
            size="small"
            variant="tonal"
            color="secondary"
            @click="showProfileManagementDialog = true"
          >
            Kelola Profil
          </VBtn>
          <VBtn
            prepend-icon="tabler-plus"
            size="small"
            @click="openDialog('edit')"
          >
            Tambah Paket
          </VBtn>
        </div>
      </VCardText>

      <VDataTableServer
        v-if="!smAndDown"
        v-model:options="options"
        :headers="headers"
        :items="packages"
        :items-length="totalPackages"
        :loading="loading"
        density="comfortable"
        @update:options="fetchPackages"
      >
        <template #item.details="{ item }">
          <div class="d-flex flex-column py-2">
            <small class="text-caption text-medium-emphasis">Profil: {{ item.profile?.profile_name ?? 'N/A' }}</small>
            <div class="d-flex align-center gap-2">
              <VChip
                v-if="item.data_quota_gb === 0"
                color="success"
                size="x-small"
                label
              >
                Unlimited
              </VChip>
              <span
                v-else
                class="font-weight-medium"
              >{{ item.data_quota_gb }} GB</span>
              <span>/</span>
              <span class="font-weight-medium">{{ item.duration_days }} Hari</span>
            </div>
          </div>
        </template>
        <template #item.price="{ item }">
          Rp {{ formatNumber(item.price) }}
        </template>
        <template #item.is_active="{ item }">
          <VChip
            :color="item.is_active ? 'success' : 'error'"
            size="small"
            density="comfortable"
          >
            {{ item.is_active ? 'Aktif' : 'Nonaktif' }}
          </VChip>
        </template>
        <template #item.actions="{ item }">
          <div class="d-flex gap-1 justify-center">
            <VBtn
              icon
              variant="text"
              size="small"
              @click="openDialog('edit', item)"
            >
              <VIcon
                icon="tabler-pencil"
                size="18"
              />
            </VBtn>
            <VBtn
              icon
              variant="text"
              size="small"
              @click="openDialog('delete', item)"
            >
              <VIcon
                icon="tabler-trash"
                size="18"
              />
            </VBtn>
          </div>
        </template>
        <template #loading>
          <tr
            v-for="index in options.itemsPerPage"
            :key="index"
          >
            <td
              v-for="col in headers"
              :key="col.key"
            >
              <VSkeletonLoader type="text" />
            </td>
          </tr>
        </template>
      </VDataTableServer>

      <div
        v-else
        class="pa-4"
      >
        <p class="text-center text-disabled">
          Tampilan tabel tidak tersedia di layar kecil. Gunakan mode daftar untuk mobile.
        </p>
      </div>
    </VCard>

    <VDialog
      v-model="dialog.edit"
      max-width="600px"
      persistent
    >
      <VCard>
        <VCardTitle class="pa-4 text-h6">
          {{ formTitle }}
        </VCardTitle>
        <VCardText class="pt-2 pa-4">
          <VRow>
            <VCol cols="12">
              <VTextField
                v-model="editedPackage.name"
                label="Nama Paket (Nama Jualan)"
                placeholder="Contoh: Paket Hebat"
              />
            </VCol>
            <VCol
              cols="12"
              md="6"
            >
              <VTextField
                v-model.number="editedPackage.data_quota_gb"
                label="Kuota Data (GB)"
                type="number"
                :rules="[(v) => (v !== null && v >= 0) || 'Kuota harus angka positif']"
                min="0"
                step="0.01"
                :disabled="isUnlimited"
              />
            </VCol>
            <VCol
              cols="12"
              md="6"
              class="d-flex align-center"
            >
              <VSwitch
                v-model="isUnlimited"
                label="Paket Unlimited"
                color="success"
                class="me-auto"
              />
            </VCol>
            <VCol
              cols="12"
              md="6"
            >
              <VTextField
                v-model.number="editedPackage.duration_days"
                label="Masa Berlaku (Hari)"
                type="number"
                :rules="[(v) => (v !== null && v > 0) || 'Durasi harus lebih dari 0']"
                min="1"
              />
            </VCol>
            <VCol
              cols="12"
              md="6"
            >
              <VTextField
                v-model="formattedPrice"
                label="Harga Jual"
                type="text"
                prefix="Rp"
                placeholder="50.000"
                :rules="[(v) => (unformatNumber(v) >= 0) || 'Harga harus angka positif']"
              />
            </VCol>
            <VCol cols="12">
              <VTextarea
                v-model="editedPackage.description"
                label="Deskripsi Paket (Opsional)"
                rows="2"
              />
            </VCol>
          </VRow>
        </VCardText>
        <VDivider />
        <VCardActions class="pa-4">
          <VSwitch
            v-model="editedPackage.is_active"
            label="Paket Aktif"
            class="mt-0"
          />
          <VSpacer />
          <VBtn
            variant="tonal"
            color="secondary"
            @click="dialog.edit = false"
          >
            Batal
          </VBtn>
          <VBtn
            color="primary"
            @click="handleAction(editedPackage.id ? 'update' : 'create')"
          >
            Simpan
          </VBtn>
        </VCardActions>
      </VCard>
    </VDialog>

    <VDialog
      v-model="dialog.delete"
      max-width="450px"
      persistent
    />

    <ProfileSetupDialog
      v-model="showProfileSetupDialog"
      :error-message="profileErrorMessage"
      @profiles-created="onProfilesCreated"
    />

    <ProfileManagementDialog
      v-model="showProfileManagementDialog"
      @profiles-updated="fetchPackages"
    />
  </div>
</template>