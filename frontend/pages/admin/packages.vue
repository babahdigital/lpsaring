<script lang="ts" setup>
import { ref, reactive, computed, onMounted, watch } from 'vue'
import type { VDataTableServer } from 'vuetify/labs/VDataTable'
import { useDisplay } from 'vuetify'
import { useNuxtApp } from '#app'

// --- STRUKTUR DATA (Tidak berubah) ---
interface Profile {
  id: string;
  profile_name: string;
}

interface Package {
  id: string;
  name: string;
  description: string | null;
  price: number;
  is_active: boolean;
  profile_id: string;
  data_quota_gb: number;
  duration_days: number;
  profile: Profile;
}

const { $api } = useNuxtApp()
const { smAndDown } = useDisplay()

const packages = ref<Package[]>([])
const loading = ref(true)
const totalPackages = ref(0)
const options = ref({ page: 1, itemsPerPage: 10, sortBy: [] as any[] })
const dialog = reactive({ edit: false, delete: false })
const snackbar = reactive({ show: false, text: '', color: 'info' })
const selectedPackage = ref<Package | null>(null)
const editedPackage = ref<Partial<Package>>({})

const defaultPackage: Partial<Package> = {
  name: '',
  price: 0,
  description: '',
  is_active: true,
  data_quota_gb: 0,
  duration_days: 30
}

// --- PENAMBAHAN 1: State untuk Switch Unlimited ---
const isUnlimited = ref(false)
// --- AKHIR PENAMBAHAN 1 ---

// --- LOGIKA FORMAT HARGA (Tidak berubah) ---
const formattedPrice = ref('')
function formatNumber(value: number | string): string {
  if (value === null || value === undefined) return ''
  return new Intl.NumberFormat('id-ID').format(Number(value))
}
function unformatNumber(value: string): number {
  return parseInt(String(value).replace(/[^0-9]/g, ''), 10) || 0
}
watch(formattedPrice, (newValue) => {
  const cleanValue = String(newValue).replace(/[^0-9]/g, '')
  editedPackage.value.price = unformatNumber(cleanValue)
  const newFormattedValue = formatNumber(cleanValue)
  if (formattedPrice.value !== newFormattedValue) {
    formattedPrice.value = newFormattedValue
  }
})

// --- PENYESUAIAN 2: Sinkronisasi Switch saat Dialog Dibuka ---
watch(() => dialog.edit, (isOpening) => {
  if (isOpening) {
    // Sinkronkan harga
    if (editedPackage.value.price !== undefined && editedPackage.value.price !== null) {
      formattedPrice.value = formatNumber(editedPackage.value.price)
    } else {
      formattedPrice.value = ''
    }
    // Sinkronkan status switch unlimited
    isUnlimited.value = editedPackage.value.data_quota_gb === 0
  } else {
    formattedPrice.value = ''
  }
})
// --- AKHIR PENYESUAIAN 2 ---


// --- PENAMBAHAN 3: Logika Reaktif untuk Switch ---
// Jika switch diaktifkan, paksa kuota menjadi 0
watch(isUnlimited, (isNowUnlimited) => {
  if (isNowUnlimited) {
    editedPackage.value.data_quota_gb = 0
  }
})
// Jika admin mengetik 0 di kuota, aktifkan switch secara otomatis
watch(() => editedPackage.value.data_quota_gb, (newQuota) => {
  if (newQuota === 0) {
    isUnlimited.value = true
  } else if (newQuota && newQuota > 0 && isUnlimited.value) {
    // Jika admin mengisi angka > 0, matikan switch
    isUnlimited.value = false
  }
})
// --- AKHIR PENAMBAHAN 3 ---


onMounted(fetchPackages)

const formTitle = computed(() => (editedPackage.value.id ? 'Edit Paket Jualan' : 'Tambah Paket Jualan'))
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
  } catch (e) {
    snackbar.text = 'Gagal memuat daftar paket.'
    snackbar.color = 'error'
    snackbar.show = true
  } finally {
    loading.value = false
  }
}

function openDialog(type: 'edit' | 'delete', pkg: Package | null = null) {
  if (type === 'edit') {
    const { profile, ...restOfPkg } = pkg || {};
    editedPackage.value = pkg ? JSON.parse(JSON.stringify(restOfPkg)) : { ...defaultPackage }
    // Saat membuka dialog, langsung atur status switch berdasarkan data
    isUnlimited.value = editedPackage.value.data_quota_gb === 0
    dialog.edit = true
  } else if (type === 'delete' && pkg) {
    selectedPackage.value = { ...pkg }
    dialog.delete = true
  }
}

async function handleAction(type: 'create' | 'update' | 'delete') {
  let endpoint = '/admin/packages', method: 'POST' | 'PUT' | 'DELETE' = 'POST', successMessage = '', body: object | undefined
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
  try {
    await $api(endpoint, { method, body })
    snackbar.text = successMessage
    snackbar.color = 'success'
    snackbar.show = true
    await fetchPackages()
  } catch (error: any) {
    snackbar.text = `Error: ${error.data?.message || 'Terjadi kesalahan'}`
    snackbar.color = 'error'
    snackbar.show = true
  } finally {
    dialog.edit = false
    dialog.delete = false
  }
}
useHead({ title: 'Manajemen Paket Mikrotik' })
</script>

<template>
  <div>
    <VCard>
      <VCardText class="d-flex align-center flex-wrap gap-4 py-4">
        <h5 class="text-h5">Manajemen Paket Jualan</h5>
        <VSpacer />
        <div class="d-flex flex-wrap gap-2">
          <VBtn prepend-icon="tabler-plus" size="small" @click="openDialog('edit')">
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
            <small class="text-caption text-medium-emphasis">Profil: {{ item.profile?.profile_name || 'N/A' }}</small>
            <div class="d-flex align-center gap-2">
              <VChip v-if="item.data_quota_gb === 0" color="success" size="x-small" label>Unlimited</VChip>
              <span v-else class="font-weight-medium">{{ item.data_quota_gb }} GB</span>
              <span>/</span>
              <span class="font-weight-medium">{{ item.duration_days }} Hari</span>
            </div>
          </div>
        </template>

        <template #item.price="{ item }">
          Rp {{ formatNumber(item.price) }}
        </template>
        
        <template #item.is_active="{ item }">
          <VChip :color="item.is_active ? 'success' : 'error'" size="small" density="comfortable">
            {{ item.is_active ? 'Aktif' : 'Nonaktif' }}
          </VChip>
        </template>

        <template #item.actions="{ item }">
          <div class="d-flex gap-1 justify-center">
            <VBtn icon variant="text" size="small" @click="openDialog('edit', item)">
              <VIcon icon="tabler-pencil" size="18" />
            </VBtn>
            <VBtn icon variant="text" size="small" @click="openDialog('delete', item)">
              <VIcon icon="tabler-trash" size="18" />
            </VBtn>
          </div>
        </template>
        
        <template #loading>
          <tr v-for="index in options.itemsPerPage" :key="index">
            <td v-for="col in headers" :key="col.key">
              <VSkeletonLoader type="text" />
            </td>
          </tr>
        </template>
      </VDataTableServer>
      
      <div v-else class="pa-3">
        </div>
    </VCard>

    <VDialog v-model="dialog.edit" max-width="600px" persistent>
      <VCard>
        <VCardTitle class="pa-4 text-h6">{{ formTitle }}</VCardTitle>
        <VCardText class="pt-2 pa-4">
          <VRow>
            <VCol cols="12">
              <VTextField v-model="editedPackage.name" label="Nama Paket (Nama Jualan)" placeholder="Contoh: Paket Hebat" />
            </VCol>
            
            <VCol cols="12" md="6">
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

            <VCol cols="12" md="6" class="d-flex align-center">
               <VSwitch
                v-model="isUnlimited"
                label="Paket Unlimited"
                color="success"
                class="me-auto"
              />
            </VCol>

            <VCol cols="12" md="6">
              <VTextField
                v-model.number="editedPackage.duration_days"
                label="Masa Berlaku (Hari)"
                type="number"
                :rules="[(v) => (v !== null && v > 0) || 'Durasi harus lebih dari 0']"
                min="1"
              />
            </VCol>

            <VCol cols="12" md="6">
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
              <VTextarea v-model="editedPackage.description" label="Deskripsi Paket (Opsional)" rows="2" />
            </VCol>
            </VRow>
        </VCardText>
        <VDivider />
        <VCardActions class="pa-4">
          <VSwitch v-model="editedPackage.is_active" label="Paket Aktif" class="mt-0"/>
          <VSpacer />
          <VBtn variant="tonal" color="secondary" @click="dialog.edit = false">Batal</VBtn>
          <VBtn color="primary" @click="handleAction(editedPackage.id ? 'update' : 'create')">Simpan</VBtn>
        </VCardActions>
      </VCard>
    </VDialog>
    
    <VDialog v-model="dialog.delete" max-width="450px" persistent>
      </VDialog>

    <VSnackbar v-model="snackbar.show" :color="snackbar.color" location="top center" :timeout="3000">
      {{ snackbar.text }}
    </VSnackbar>
  </div>
</template>