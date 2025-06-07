<script lang="ts" setup>
import { ref, reactive, computed, onMounted, watch } from 'vue'
import type { VDataTableServer } from 'vuetify/labs/VDataTable'
import { useDisplay } from 'vuetify'
import ProfileManagerDialog from '~/components/admin/ProfileManagerDialog.vue'

interface Profile {
  id: string
  profile_name: string
  data_quota_gb: number
  duration_days: number
}
interface Package {
  id: string
  name: string
  description: string | null
  price: number
  is_active: boolean
  profile_id: string
  profile: Profile
}

const { $api } = useNuxtApp()
const { smAndDown } = useDisplay()
const packages = ref<Package[]>([])
const profiles = ref<Profile[]>([])
const loading = ref(true)
const loadingProfiles = ref(false)
const profileError = ref(false)
const totalPackages = ref(0)
const options = ref({ page: 1, itemsPerPage: 10, sortBy: [] })
const dialog = reactive({ edit: false, delete: false })
const snackbar = reactive({ show: false, text: '', color: 'info' })
const selectedPackage = ref<Package | null>(null)
const editedPackage = ref<Partial<Package>>({})
const defaultPackage = { name: '', price: 0, description: '', is_active: true, profile_id: '' }
const isProfileManagerDialogVisible = ref(false)

const formattedPrice = ref('')

watch(formattedPrice, (newValue) => {
  const rawNumber = parseInt(newValue.replace(/\./g, ''), 10)
  if (!isNaN(rawNumber)) {
    editedPackage.value.price = rawNumber
  } else if (newValue === '') {
    editedPackage.value.price = 0
  }
})

watch(() => dialog.edit, (isOpening) => {
  if (isOpening && editedPackage.value.price) {
    formattedPrice.value = new Intl.NumberFormat('id-ID').format(editedPackage.value.price)
  } else if (isOpening) {
    formattedPrice.value = ''
  } else {
    formattedPrice.value = ''
  }
})

onMounted(async () => {
  await fetchPackages()
  await fetchAllProfilesForSelect()
})

const formTitle = computed(() => (editedPackage.value.id ? 'Edit Paket Jualan' : 'Tambah Paket Jualan'))
const headers = [
  { title: 'NAMA PAKET', key: 'name' },
  { title: 'PROFIL', key: 'profile.profile_name' },
  { title: 'HARGA', key: 'price', align: 'end' },
  { title: 'STATUS', key: 'is_active', align: 'center' },
  { title: 'AKSI', key: 'actions', sortable: false, align: 'center' },
]

async function fetchPackages() {
  loading.value = true
  try {
    const params = new URLSearchParams({ page: String(options.value.page), itemsPerPage: String(options.value.itemsPerPage) })
    const response = await $api<{ items: Package[], totalItems: number }>(`/admin/packages?${params.toString()}`)
    packages.value = response.items;
    totalPackages.value = response.totalItems || 0;
  } finally { loading.value = false }
}

async function fetchAllProfilesForSelect() {
  loadingProfiles.value = true
  profileError.value = false
  try {
    const response = await $api<Profile[]>('/admin/profiles?all=true')
    profiles.value = response
  } catch (error) {
    profileError.value = true
    snackbar.text = 'Gagal memuat daftar profil';
    snackbar.color = 'error';
    snackbar.show = true
  } finally {
    loadingProfiles.value = false
  }
}

function openDialog(type: 'edit' | 'delete', pkg: Package | null = null) {
  if (type === 'edit') {
    editedPackage.value = pkg ? JSON.parse(JSON.stringify(pkg)) : { ...defaultPackage }
    dialog.edit = true
  } else if (type === 'delete' && pkg) {
    selectedPackage.value = { ...pkg }; dialog.delete = true
  }
}

async function handleAction(type: 'create' | 'update' | 'delete') {
  let endpoint = '/admin/packages', method: 'POST' | 'PUT' | 'DELETE' = 'POST', successMessage = '', body: object | undefined
  switch (type) {
    case 'create': successMessage = 'Paket baru berhasil dibuat.'; body = editedPackage.value; break
    case 'update': endpoint = `/admin/packages/${editedPackage.value.id}`; method = 'PUT'; successMessage = 'Paket berhasil diperbarui.'; body = editedPackage.value; break
    case 'delete': endpoint = `/admin/packages/${selectedPackage.value!.id}`; method = 'DELETE'; successMessage = 'Paket berhasil dihapus.'; break
  }
  try {
    await $api(endpoint, { method, body });
    snackbar.text = successMessage;
    snackbar.color = 'success';
    snackbar.show = true
    await fetchPackages()
  } catch (error: any) {
    snackbar.text = `Error: ${error.data?.message || 'Terjadi kesalahan'}`;
    snackbar.color = 'error';
    snackbar.show = true
  } finally {
    dialog.edit = false;
    dialog.delete = false
  }
}
</script>

<template>
  <div>
    <VCard>
      <VCardText class="d-flex align-center flex-wrap gap-4 py-4">
        <h5 class="text-h5">Manajemen Paket Jualan</h5>
        <VSpacer />
        <div class="d-flex flex-wrap gap-2">
          <VBtn
            color="secondary"
            size="small"
            @click="isProfileManagerDialogVisible = true"
          >
            <VIcon icon="tabler-settings" class="mr-1" /> Kelola Profil
          </VBtn>
          <VBtn
            prepend-icon="tabler-plus"
            size="small"
            @click="openDialog('edit')"
          >Tambah Paket</VBtn>
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
        <template #item.profile.profile_name="{ item }">
          <div class="d-flex flex-column py-2">
            <span class="font-weight-medium text-body-2">{{ item.profile.profile_name }}</span>
            <small class="text-caption text-medium-emphasis">
              <VChip
                v-if="item.profile.data_quota_gb === 0"
                color="success"
                size="x-small"
                class="mr-1"
              >Unlimited</VChip>
              <span v-else>{{ item.profile.data_quota_gb }} GB</span>
              / {{ item.profile.duration_days }} Hari
            </small>
          </div>
        </template>
        <template #item.price="{ item }">Rp {{ new Intl.NumberFormat('id-ID').format(item.price) }}</template>
        <template #item.is_active="{ item }">
          <VChip
            :color="item.is_active ? 'success' : 'error'"
            size="small"
            density="comfortable"
          >{{ item.is_active ? 'Aktif' : 'Nonaktif' }}</VChip>
        </template>
        <template #item.actions="{ item }">
          <div class="d-flex gap-1 justify-center">
            <VBtn
              icon
              variant="text"
              size="small"
              @click="openDialog('edit', item)"
            ><VIcon icon="tabler-pencil" size="18" /></VBtn>
            <VBtn
              icon
              variant="text"
              size="small"
              @click="openDialog('delete', item)"
            ><VIcon icon="tabler-trash" size="18" /></VBtn>
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
        <div v-if="loading">
          <div v-for="i in 3" :key="i" class="mb-4">
            <VSkeletonLoader type="list-item-avatar-three-line" />
          </div>
        </div>
        
        <div v-else-if="packages.length === 0" class="text-center py-8 text-medium-emphasis">
          <VIcon icon="tabler-package-off" size="48" class="mb-2" />
          <p class="text-body-1">Tidak Ada Paket</p>
          <span class="text-caption">Silakan tambah paket baru.</span>
        </div>
        
        <div v-else>
          <VCard
            v-for="pkg in packages"
            :key="pkg.id"
            class="mb-4"
          >
            <VCardText>
              <div class="d-flex justify-space-between align-start">
                <div>
                  <div class="text-subtitle-1 font-weight-bold">{{ pkg.name }}</div>
                  <div class="text-body-2 text-medium-emphasis mb-2">
                    {{ pkg.description || 'Tidak ada deskripsi' }}
                  </div>
                  
                  <div class="d-flex align-center gap-2 mt-2">
                    <VChip
                      :color="pkg.is_active ? 'success' : 'error'"
                      size="small"
                      label
                    >{{ pkg.is_active ? 'Aktif' : 'Nonaktif' }}</VChip>
                    <div class="text-primary text-subtitle-1 font-weight-bold">
                      Rp {{ new Intl.NumberFormat('id-ID').format(pkg.price) }}
                    </div>
                  </div>
                </div>
                
                <div class="d-flex">
                  <VBtn
                    icon="tabler-pencil"
                    variant="text"
                    size="small"
                    color="primary"
                    @click="openDialog('edit', pkg)"
                  />
                  <VBtn
                    icon="tabler-trash"
                    variant="text"
                    size="small"
                    color="error"
                    @click="openDialog('delete', pkg)"
                  />
                </div>
              </div>
              
              <VDivider class="my-3" />

              <div class="d-flex align-center justify-space-between text-caption text-medium-emphasis">
                <span>Profil Teknis: <strong>{{ pkg.profile.profile_name }}</strong></span>
                <div class="d-flex align-center gap-1">
                  <VChip
                    v-if="pkg.profile.data_quota_gb === 0"
                    color="success"
                    variant="tonal"
                    size="x-small"
                    label
                  >Unlimited</VChip>
                  <span v-else>{{ pkg.profile.data_quota_gb }} GB</span>
                  <span>/</span>
                  <span>{{ pkg.profile.duration_days }} Hari</span>
                </div>
              </div>
            </VCardText>
          </VCard>
        </div>
        
        <VPagination
          v-if="totalPackages > 0 && totalPackages > options.itemsPerPage"
          v-model="options.page"
          :length="Math.ceil(totalPackages / options.itemsPerPage)"
          :total-visible="smAndDown ? 5 : 7"
          density="comfortable"
          class="mt-2"
        />
      </div>
    </VCard>

    <VDialog
      v-model="dialog.edit"
      max-width="600px"
      persistent
    >
      <VCard>
        <VCardTitle class="pa-4 text-h6">{{ formTitle }}</VCardTitle>
        <VCardText class="pt-2 pa-4">
          <VRow>
            <VCol cols="12">
              <VSelect
                v-model="editedPackage.profile_id"
                :items="profiles"
                item-title="profile_name"
                item-value="id"
                label="Pilih Profil Paket"
                placeholder="Pilih profil teknis..."
                :loading="loadingProfiles"
                :error="profileError"
                :error-messages="profileError ? 'Gagal memuat profil' : ''"
                clearable
                @click:clear="fetchAllProfilesForSelect"
              >
                <template #prepend-item v-if="loadingProfiles">
                  <VListItem>
                    <VListItemTitle>
                      <div class="d-flex align-center">
                        <VProgressCircular indeterminate size="20" width="2" class="mr-3" />
                        Memuat daftar profil...
                      </div>
                    </VListItemTitle>
                  </VListItem>
                </template>
                
                <template #no-data>
                  <VListItem>
                    <VListItemTitle>
                      <span v-if="profileError" class="text-error">Gagal memuat profil</span>
                      <span v-else>Data profil tidak tersedia atau perlu dibuat</span>
                    </VListItemTitle>
                  </VListItem>
                </template>
                
                <template #item="{ props, item }">
                  <VListItem
                    v-bind="props"
                    :title="item.raw.profile_name"
                  >
                    <template #subtitle>
                      <VChip
                        v-if="item.raw.data_quota_gb === 0"
                        color="success"
                        size="x-small"
                        class="mr-2"
                      >Unlimited</VChip>
                      <span v-else>{{ item.raw.data_quota_gb }} GB</span>
                      <span class="mx-1">/</span>
                      <span>{{ item.raw.duration_days }} Hari</span>
                    </template>
                  </VListItem>
                </template>
              </VSelect>
            </VCol>
            <VCol cols="12">
              <AppTextField
                v-model="editedPackage.name"
                label="Nama Paket (tampil ke user)"
                placeholder="Contoh: Paket Sultan 30 Hari"
              />
            </VCol>
            <VCol cols="12">
              <AppTextField
                v-model="formattedPrice"
                label="Harga Jual"
                type="text"
                prefix="Rp"
                placeholder="50.000"
              />
            </VCol>
            <VCol cols="12">
              <AppTextarea
                v-model="editedPackage.description"
                label="Deskripsi Paket"
                rows="3"
                placeholder="Jelaskan keunggulan paket ini..."
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
          >Batal</VBtn>
          <VBtn
            color="primary"
            @click="handleAction(editedPackage.id ? 'update' : 'create')"
          >Simpan</VBtn>
        </VCardActions>
      </VCard>
    </VDialog>
    
    <VDialog
      v-model="dialog.delete"
      max-width="450px"
      persistent
    >
      <VCard>
        <VCardTitle class="pa-4 text-h6">Konfirmasi Hapus</VCardTitle>
        <VCardText class="pt-2 pa-4">
          Yakin ingin menghapus paket <strong>{{ selectedPackage?.name }}</strong>?
        </VCardText>
        <VCardActions class="pa-4">
          <VSpacer />
          <VBtn 
            variant="tonal"
            color="secondary"
            @click="dialog.delete = false"
          >Batal</VBtn>
          <VBtn
            color="error"
            @click="handleAction('delete')"
          >Hapus</VBtn>
        </VCardActions>
      </VCard>
    </VDialog>

    <ProfileManagerDialog
      v-model="isProfileManagerDialogVisible"
      @profiles-updated="fetchAllProfilesForSelect"
    />
    
    <VSnackbar
      v-model="snackbar.show"
      :color="snackbar.color"
      location="top center"
      :timeout="3000"
    >{{ snackbar.text }}</VSnackbar>
  </div>
</template>