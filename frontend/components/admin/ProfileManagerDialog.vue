<script lang="ts" setup>
import { ref, reactive, computed, watch } from 'vue'
import type { VDataTableServer } from 'vuetify/labs/VDataTable'

const props = defineProps({ modelValue: { type: Boolean, required: true } })
const emit = defineEmits(['update:modelValue', 'profiles-updated'])

interface Profile {
  id: string
  profile_name: string
  description: string | null
  duration_days: number
  data_quota_gb: number
}
type Options = InstanceType<typeof VDataTableServer>['options']

const { $api } = useNuxtApp()
const profiles = ref<Profile[]>([])
const loading = ref(true)
const totalProfiles = ref(0)
const options = ref<Options>({ page: 1, itemsPerPage: 5, sortBy: [] })
const dialog = reactive({ edit: false, delete: false })
const snackbar = reactive({ show: false, text: '', color: 'info' })
const selectedProfile = ref<Profile | null>(null)
const editedProfile = ref<Partial<Profile>>({})
const defaultProfile = { profile_name: '', description: '', duration_days: 30, data_quota_gb: 1 }
const isUnlimitedSwitch = ref(false)

const isDialogVisible = computed({
  get: () => props.modelValue,
  set: (value) => emit('update:modelValue', value),
})
watch(isDialogVisible, (newValue) => { if (newValue) fetchProfiles() })

const formTitle = computed(() => (editedProfile.value.id ? 'Edit Profil' : 'Tambah Profil Baru'))
const headers = [
  { title: 'PROFIL', key: 'profile_name' },
  { title: 'DURASI', key: 'duration_days', align: 'center' },
  { title: 'KUOTA', key: 'data_quota_gb', align: 'center' },
  { title: 'AKSI', key: 'actions', sortable: false, align: 'center', width: '120px' },
]

async function fetchProfiles() {
  loading.value = true
  try {
    const params = new URLSearchParams({ page: String(options.value.page), itemsPerPage: String(options.value.itemsPerPage) })
    const response = await $api<{ items: Profile[], totalItems: number }>(`/admin/profiles?${params.toString()}`)
    profiles.value = response.items
    totalProfiles.value = response.totalItems || 0;
  } finally { loading.value = false }
}

function openSubDialog(type: 'edit' | 'delete', profile: Profile | null = null) {
  if (type === 'edit') {
    editedProfile.value = profile ? { ...profile } : { ...defaultProfile }
    isUnlimitedSwitch.value = editedProfile.value.data_quota_gb === 0
    dialog.edit = true
  } else if (type === 'delete' && profile) {
    selectedProfile.value = { ...profile }
    dialog.delete = true
  }
}

async function handleAction(type: 'create' | 'update' | 'delete') {
  let endpoint = '/admin/profiles', method: 'POST' | 'PUT' | 'DELETE' = 'POST', successMessage = '', body: object | undefined

  if (type === 'create' || type === 'update') {
    if (isUnlimitedSwitch.value) {
      editedProfile.value.data_quota_gb = 0
    }
    body = editedProfile.value
  }

  switch (type) {
    case 'create': successMessage = 'Profil baru berhasil dibuat.'; break;
    case 'update': endpoint = `/admin/profiles/${editedProfile.value.id}`; method = 'PUT'; successMessage = 'Profil berhasil diperbarui.'; break;
    case 'delete': endpoint = `/admin/profiles/${selectedProfile.value!.id}`; method = 'DELETE'; successMessage = 'Profil berhasil dihapus.'; break;
  }
  try {
    await $api(endpoint, { method, body }); snackbar.text = successMessage; snackbar.color = 'success'; snackbar.show = true
    await fetchProfiles(); emit('profiles-updated')
  } catch (error: any) {
    snackbar.text = `Error: ${error.data?.message || 'Terjadi kesalahan'}`; snackbar.color = 'error'; snackbar.show = true
  } finally {
    dialog.edit = false; dialog.delete = false
  }
}
</script>

<template>
  <VDialog
    v-model="isDialogVisible"
    fullscreen
    persistent
    transition="dialog-bottom-transition"
    content-class="profile-manager-dialog"
  >
    <VCard class="h-100 d-flex flex-column">
      <VToolbar color="primary" density="compact">
        <VBtn
          icon
          variant="plain"
          @click="isDialogVisible = false"
        >
          <VIcon color="white" icon="tabler-x" />
        </VBtn>
        <VToolbarTitle class="text-subtitle-1 font-weight-bold">Kelola Profil Paket</VToolbarTitle>
        <VSpacer />
        <VToolbarItems>
          <VBtn
            variant="text"
            size="small"
            @click="isDialogVisible = false"
          >Tutup</VBtn>
        </VToolbarItems>
      </VToolbar>
      
      <VCardText class="flex-grow-1 pa-4" style="overflow-y: auto;">
        <VCard class="h-100">
          <VCardText class="d-flex justify-end pa-2">
            <VBtn
              prepend-icon="tabler-plus"
              size="small"
              @click="openSubDialog('edit')"
            >Tambah Profil</VBtn>
          </VCardText>
          <VDivider />
          
            <VDataTableServer
            v-model:options="options"
            :headers="headers"
            :items="profiles"
            :items-length="totalProfiles"
            :loading="loading"
            density="comfortable"
            class="elevation-0"
            @update:options="fetchProfiles"
            >
            <template #item.duration_days="{ item }">
              {{ item.duration_days }} Hari
            </template>
            <template #item.data_quota_gb="{ item }">
              <VChip
                v-if="item.data_quota_gb === 0"
                color="success"
                size="small"
              >Unlimited</VChip>
              <span v-else>{{ item.data_quota_gb }} GB</span>
            </template>
            <template #item.actions="{ item }">
              <div class="d-flex gap-1">
                <VBtn
                  icon
                  variant="text"
                  size="small"
                  @click="openSubDialog('edit', item)"
                ><VIcon icon="tabler-pencil" size="18" /></VBtn>
                <VBtn
                  icon
                  variant="text"
                  size="small"
                  @click="openSubDialog('delete', item)"
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

            <VPagination
            v-if="totalProfiles > 0 && totalProfiles > options.itemsPerPage"
            v-model="options.page"
            :length="Math.ceil(totalProfiles / options.itemsPerPage)"
            :total-visible="5"
            density="comfortable"
            class="mt-4"
            />
        </VCard>
      </VCardText>
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
              <AppTextField
                v-model="editedProfile.profile_name"
                label="Nama Profil (di Mikrotik)"
                autofocus
              />
            </VCol>
            <VCol cols="12">
              <AppTextarea
                v-model="editedProfile.description"
                label="Deskripsi Internal"
                rows="2"
              />
            </VCol>
            <VCol
              cols="12"
              sm="6"
            >
              <AppTextField
                v-model.number="editedProfile.duration_days"
                label="Durasi (Hari)"
                type="number"
                suffix="Hari"
              />
            </VCol>
            <VCol
              v-if="!isUnlimitedSwitch"
              cols="12"
              sm="6"
            >
              <AppTextField
                v-model.number="editedProfile.data_quota_gb"
                label="Kuota Data (GB)"
                type="number"
                suffix="GB"
              />
            </VCol>
          </VRow>
        </VCardText>

        <VCardActions class="pa-4">
          <VSwitch
            v-model="isUnlimitedSwitch"
            color="success"
            label="Kuota Unlimited"
            class="mt-0"
          />
          <VSpacer />
          <VBtn
            color="secondary"
            variant="tonal"
            @click="dialog.edit = false"
          >
            Batal
          </VBtn>
          <VBtn
            color="primary"
            @click="handleAction(editedProfile.id ? 'update' : 'create')"
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
    >
      <VCard>
        <VCardTitle class="pa-4 text-h6">Konfirmasi Hapus</VCardTitle>
        <VCardText class="pt-2 pa-4">
          <p>Yakin ingin menghapus profil <strong>{{ selectedProfile?.profile_name }}</strong>?</p>
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
    
    <VSnackbar
      v-model="snackbar.show"
      :color="snackbar.color"
      :timeout="3000"
      location="top center"
    >
      {{ snackbar.text }}
    </VSnackbar>
  </VDialog>
</template>

<style scoped>
.profile-manager-dialog {
  max-width: 100%;
  max-height: 100%;
}
</style>