<script lang="ts" setup>
import { useNuxtApp } from 'nuxt/app'
import { reactive, ref, watch } from 'vue'
import { useDisplay } from 'vuetify'

import { useSnackbar } from '@/composables/useSnackbar'

interface Profile {
  id: string
  profile_name: string
  description: string | null
}

const props = defineProps<{ modelValue: boolean }>()
const emit = defineEmits(['update:modelValue', 'profilesUpdated'])

const { $api } = useNuxtApp()
const snackbar = useSnackbar()
const { smAndDown } = useDisplay()

const profiles = ref<Profile[]>([])
const loading = ref(true)
const dialogs = reactive({ edit: false, delete: false })

const editedProfile = ref<Partial<Profile>>({})
const defaultProfile: Partial<Profile> = { profile_name: '', description: '' }

// Fetch data ketika dialog dibuka
watch(() => props.modelValue, (isShown) => {
  if (isShown)
    fetchProfiles()
})

const headers = [
  { title: 'NAMA PROFIL', key: 'profile_name' },
  { title: 'DESKRIPSI', key: 'description' },
  { title: 'AKSI', key: 'actions', sortable: false, align: 'end' as const },
]

async function fetchProfiles() {
  loading.value = true
  try {
    const response = await $api<Profile[]>('/admin/profiles')
    profiles.value = response
  }
  catch (error: any) {
    snackbar.add({ type: 'error', title: 'Gagal Memuat', text: error.data?.message || 'Tidak dapat mengambil data profil.' })
  }
  finally {
    loading.value = false
  }
}

function openDialog(type: 'edit' | 'delete', profile: Profile | null = null) {
  if (type === 'edit') {
    editedProfile.value = profile ? { ...profile } : { ...defaultProfile }
    dialogs.edit = true
  }
  else if (type === 'delete' && profile) {
    editedProfile.value = { ...profile }
    dialogs.delete = true
  }
}

async function saveProfile() {
  const isUpdate = !!editedProfile.value.id
  const endpoint = isUpdate ? `/admin/profiles/${editedProfile.value.id}` : '/admin/profiles'
  const method = isUpdate ? 'PUT' : 'POST'

  try {
    await $api(endpoint, { method, body: editedProfile.value })
    snackbar.add({ type: 'success', title: 'Berhasil', text: `Profil berhasil ${isUpdate ? 'diperbarui' : 'disimpan'}.` })
    dialogs.edit = false
    await fetchProfiles()
    emit('profilesUpdated') // Beri sinyal ke induk untuk refresh
  }
  catch (error: any) {
    snackbar.add({ type: 'error', title: 'Gagal', text: error.data?.message || 'Terjadi kesalahan.' })
  }
}

async function deleteProfileConfirm() {
  try {
    await $api(`/admin/profiles/${editedProfile.value.id}`, { method: 'DELETE' })
    snackbar.add({ type: 'success', title: 'Dihapus', text: 'Profil berhasil dihapus.' })
    dialogs.delete = false
    await fetchProfiles()
    emit('profilesUpdated') // Beri sinyal ke induk untuk refresh
  }
  catch (error: any) {
    snackbar.add({ type: 'error', title: 'Gagal Menghapus', text: error.data?.message || 'Terjadi kesalahan.' })
  }
}

function closeMainDialog() {
  emit('update:modelValue', false)
}
</script>

<template>
  <VDialog
    :model-value="modelValue"
    max-width="800px"
    scrollable
    persistent
  >
    <VCard>
      <VCardTitle class="d-flex align-center pa-4">
        <VIcon
          start
          icon="tabler-server"
        />
        <span class="text-h6">Kelola Profil Teknis</span>
        <VSpacer />
        <VBtn
          icon="tabler-x"
          variant="text"
          size="small"
          @click="closeMainDialog"
        />
      </VCardTitle>
      <VDivider />

      <VCardText>
        <div class="d-flex mb-4">
          <VSpacer />
          <VBtn
            size="small"
            prepend-icon="tabler-plus"
            @click="openDialog('edit')"
          >
            Tambah Profil
          </VBtn>
        </div>

        <VDataTable
          v-if="!smAndDown"
          :headers="headers"
          :items="profiles"
          :loading="loading"
          density="compact"
          class="border rounded"
        >
          <template #[`item.actions`]="{ item }">
            <div class="d-flex gap-1 justify-end">
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
        </VDataTable>

        <div
          v-else
          class="d-flex flex-column gap-4"
        >
          <p
            v-if="loading"
            class="text-center text-disabled"
          >
            Memuat data...
          </p>
          <VCard
            v-for="profile in profiles"
            :key="profile.id"
            variant="tonal"
          >
            <VCardText>
              <div class="d-flex align-center">
                <h6 class="text-h6">
                  {{ profile.profile_name }}
                </h6>
                <VSpacer />
                <div class="d-flex">
                  <VBtn
                    icon
                    variant="text"
                    size="small"
                    @click="openDialog('edit', profile)"
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
                    @click="openDialog('delete', profile)"
                  >
                    <VIcon
                      icon="tabler-trash"
                      size="18"
                    />
                  </VBtn>
                </div>
              </div>
              <p class="text-body-2 text-medium-emphasis mt-2 mb-0">
                {{ profile.description || '-' }}
              </p>
            </VCardText>
          </VCard>
        </div>
      </VCardText>
      <VDivider />
      <VCardActions class="pa-4">
        <VSpacer />
        <VBtn
          color="secondary"
          @click="closeMainDialog"
        >
          Tutup
        </VBtn>
      </VCardActions>
    </VCard>

    <VDialog
      v-model="dialogs.edit"
      max-width="500px"
      persistent
    >
      <VCard>
        <VCardTitle class="text-h6 pa-4">
          {{ editedProfile.id ? 'Edit' : 'Tambah' }} Profil
        </VCardTitle>
        <VCardText class="pa-4">
          <VTextField
            v-model="editedProfile.profile_name"
            label="Nama Profil"
            placeholder="Contoh: user"
            class="mb-4"
          />
          <VTextarea
            v-model="editedProfile.description"
            label="Deskripsi (Opsional)"
            rows="2"
          />
        </VCardText>
        <VCardActions class="pa-4">
          <VSpacer />
          <VBtn
            variant="tonal"
            color="secondary"
            @click="dialogs.edit = false"
          >
            Batal
          </VBtn>
          <VBtn
            color="primary"
            @click="saveProfile"
          >
            Simpan
          </VBtn>
        </VCardActions>
      </VCard>
    </VDialog>

    <VDialog
      v-model="dialogs.delete"
      max-width="450px"
      persistent
    >
      <VCard>
        <VCardTitle class="text-h6 pa-4">
          Konfirmasi Hapus
        </VCardTitle>
        <VCardText class="pa-4">
          Anda yakin ingin menghapus profil
          <strong>{{ editedProfile.profile_name }}</strong>? Aksi ini tidak dapat dibatalkan.
        </VCardText>
        <VCardActions class="pa-4">
          <VSpacer />
          <VBtn
            variant="tonal"
            color="secondary"
            @click="dialogs.delete = false"
          >
            Batal
          </VBtn>
          <VBtn
            color="error"
            @click="deleteProfileConfirm"
          >
            Ya, Hapus
          </VBtn>
        </VCardActions>
      </VCard>
    </VDialog>
  </VDialog>
</template>
