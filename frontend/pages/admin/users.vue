<script lang="ts" setup>
import { ref, watch, computed, onMounted, nextTick, reactive } from 'vue'
import type { VDataTableServer } from 'vuetify/labs/VDataTable'
import { useDisplay } from 'vuetify'
import { useAuthStore } from '@/store/auth'
import type { VForm } from 'vuetify/components'

import AppTextField from '@core/components/app-form-elements/AppTextField.vue'
import AppSelect from '@core/components/app-form-elements/AppSelect.vue'

interface User {
  id: string
  full_name: string
  phone_number: string
  role: 'USER' | 'ADMIN' | 'SUPER_ADMIN'
  approval_status: 'PENDING_APPROVAL' | 'APPROVED' | 'REJECTED'
  is_active: boolean
  created_at: string
  blok: string | null
  kamar: string | null
  approved_at: string | null
}

type Options = InstanceType<typeof VDataTableServer>['options']

const { $api } = useNuxtApp()
const { smAndDown } = useDisplay()
const authStore = useAuthStore()

const users = ref<User[]>([])
const loading = ref(true)
const totalUsers = ref(0)
const search = ref('')
const options = ref<Options>({
  page: 1,
  itemsPerPage: 10,
  sortBy: [{ key: 'created_at', order: 'desc' }],
  groupBy: [],
  search: undefined,
})

const snackbar = reactive({ show: false, text: '', color: 'info', timeout: 4000 })
const dialog = reactive({ view: false, edit: false, delete: false, approve: false, reject: false })
const formRef = ref<InstanceType<typeof VForm> | null>(null)

const selectedUser = ref<User | null>(null)
const defaultUser = {
  full_name: '',
  phone_number: '',
  role: 'USER' as const,
  blok: null,
  kamar: null,
  is_active: true,
}

const editedUser = ref<Partial<User>>({ ...defaultUser })
const isMounted = ref(false)
const isUserDataInputActive = ref(false) // Untuk VSwitch Blok & Kamar di Admin

// Opsi Blok dan Kamar yang akan dimuat dari backend
const availableBloks = ref<string[]>([]);
const availableKamars = ref<string[]>([]);

onMounted(() => {
  isMounted.value = true
  fetchUsers()
  fetchAlamatOptions() // Memuat opsi blok/kamar saat komponen di-mount
})

const formTitle = computed(() => (editedUser.value.id ? 'Edit Pengguna' : 'Tambah Pengguna'))

const availableRoles = computed(() => {
  if (authStore.isSuperAdmin) {
    return [
      { title: 'User Biasa', value: 'USER' },
      { title: 'Admin', value: 'ADMIN' },
    ]
  }
  return [{ title: 'User Biasa', value: 'USER' }]
})

// Watcher untuk editedUser.role agar mengaktifkan switch alamat jika role adalah ADMIN
watch(() => editedUser.value.role, (newRole) => {
  if (newRole === 'ADMIN') {
    isUserDataInputActive.value = true;
  } else {
    isUserDataInputActive.value = false;
  }
});


const headers = computed(() => {
  const base = [
    { title: 'PENGGUNA', key: 'full_name', sortable: true },
    { title: 'STATUS', key: 'approval_status', sortable: true },
    { title: 'PERAN', key: 'role', sortable: true },
    { title: 'AKTIF', key: 'is_active', sortable: true },
    { title: 'TGL DAFTAR', key: 'created_at', sortable: true },
    { title: 'AKSI', key: 'actions', sortable: false, align: 'center', width: '150px' },
  ]
  if (smAndDown.value) {
    return base.filter(h => ['full_name', 'approval_status', 'actions'].includes(h.key))
  }
  return base
})

async function fetchUsers() {
  if (!isMounted.value) return
  loading.value = true
  try {
    const params = new URLSearchParams()
    params.append('page', String(options.value.page))
    params.append('itemsPerPage', String(options.value.itemsPerPage))
    if (options.value.sortBy?.length) {
      params.append('sortBy', options.value.sortBy[0].key)
      params.append('sortOrder', options.value.sortBy[0].order)
    }
    if (search.value)
      params.append('search', search.value)

    const response = await $api<{ items: User[]; totalItems: number }>(`/admin/users?${params.toString()}`)
    users.value = response.items
    totalUsers.value = response.totalItems
  }
  catch (error: any) {
    showSnackbar(`Gagal mengambil data: ${error.data?.message || 'Server error'}`, 'error')
  }
  finally {
    loading.value = false
  }
}

// Fungsi untuk memuat opsi blok dan kamar dari backend
async function fetchAlamatOptions() {
  try {
    const response = await $api<any>('/admin/form-options/alamat', { method: 'GET' });
    if (response.success) {
      availableBloks.value = response.bloks || [];
      availableKamars.value = response.kamars || [];
    } else {
      showSnackbar(response.message || 'Gagal memuat opsi alamat.', 'error');
    }
  } catch (error: any) {
    console.error("Gagal mengambil opsi alamat:", error);
    showSnackbar('Gagal memuat opsi alamat. Terjadi kesalahan jaringan.', 'error');
  }
}

watch(() => options.value, fetchUsers, { deep: true })
let searchTimeout: ReturnType<typeof setTimeout>
watch(search, () => {
  clearTimeout(searchTimeout)
  searchTimeout = setTimeout(() => {
    options.value.page = 1
    fetchUsers()
  }, 500)
})

function showSnackbar(text: string, color = 'info') {
  snackbar.text = text
  snackbar.color = color
  snackbar.show = true
}

const statusMap = {
  APPROVED: { text: 'Disetujui', color: 'success', variant: 'outlined' },
  PENDING_APPROVAL: { text: 'Menunggu', color: 'warning', variant: 'outlined' },
  REJECTED: { text: 'Ditolak', color: 'error', variant: 'outlined' },
}
const roleMap = {
  USER: { text: 'User', color: 'info', variant: 'tonal' },
  ADMIN: { text: 'Admin', color: 'primary', variant: 'tonal' },
  SUPER_ADMIN: { text: 'Super Admin', color: 'purple', variant: 'tonal' },
}

// Perbaikan: Pastikan normalisasi nomor telepon selalu ke format +62 saat blur
function normalizePhoneNumberOnBlur() {
  if (editedUser.value.phone_number) {
    let cleaned = editedUser.value.phone_number.replace(/\D/g, ''); // Hapus semua non-digit
    if (cleaned.startsWith('08')) {
      editedUser.value.phone_number = `+62${cleaned.substring(1)}`;
    } else if (cleaned.startsWith('62')) {
      editedUser.value.phone_number = `+${cleaned}`;
    } else if (cleaned.startsWith('+62')) {
      // Sudah dalam format yang benar, tidak perlu diubah
    } else {
      // Jika format tidak dikenali, biarkan seperti adanya atau berikan pesan kesalahan
      // Untuk tujuan ini, kita biarkan saja, validasi Pydantic di backend akan menangani.
      // current_app.logger.warning("Nomor telepon tidak dalam format Indonesia yang diharapkan.");
    }
  }
}

const requiredRule = (value: any) => !!value || 'Field ini wajib diisi.'

function closeDialog() {
  dialog.view = false
  dialog.edit = false
  dialog.delete = false
  dialog.approve = false
  dialog.reject = false
  nextTick(() => {
    selectedUser.value = null
    editedUser.value = { ...defaultUser }
    isUserDataInputActive.value = false
    formRef.value?.resetValidation()
  })
}

function openDialog(type: 'view' | 'approve' | 'delete' | 'edit' | 'reject', user?: User) {
  if (type === 'edit') {
    if (!user) { // Untuk ADD NEW USER (type 'edit' tanpa user)
      editedUser.value = { ...defaultUser };
      editedUser.value.phone_number_display = ''; // Untuk user baru, kosongkan display
      isUserDataInputActive.value = false; // Default: switch off for new user
      // Saat menambahkan user baru, jika default role adalah ADMIN, aktifkan switch alamat.
      if (editedUser.value.role === 'ADMIN') {
        isUserDataInputActive.value = true;
      }
      dialog.edit = true;
      return;
    }

    // Untuk EDIT EXISTING USER
    selectedUser.value = { ...user };
    const userToEdit = JSON.parse(JSON.stringify(user));
    
    // Memastikan kamar diformat menjadi hanya angka saat dialog dibuka
    if (userToEdit.kamar) {
      userToEdit.kamar = formatKamarDisplay(userToEdit.kamar);
    }
    
    // Memastikan nomor telepon diformat menjadi '0' saat dialog dibuka untuk input form
    if (userToEdit.phone_number) {
      userToEdit.phone_number_display = formatPhoneNumberDisplay(userToEdit.phone_number);
    } else {
      userToEdit.phone_number_display = ''; // Atur ke string kosong jika tidak ada nomor telepon
    }

    editedUser.value = userToEdit;
    
    // Inisialisasi isUserDataInputActive berdasarkan data yang ada HANYA untuk role ADMIN
    // Jika user yang diedit adalah ADMIN, set isUserDataInputActive default aktif
    if (editedUser.value.role === 'ADMIN') {
        isUserDataInputActive.value = true; // Selalu aktifkan untuk admin yang sudah ada
    } else {
        // Untuk USER, isUserDataInputActive selalu false karena blok/kamar selalu terlihat
        isUserDataInputActive.value = false;
    }
    dialog.edit = true;
  } else { // For other dialogs (view, approve, delete, reject)
    if (user) {
      selectedUser.value = { ...user };
      dialog[type] = true;
    } else {
      showSnackbar('Pengguna tidak ditemukan untuk aksi ini.', 'error');
    }
  }
}

async function handleAction(type: 'approve' | 'delete' | 'update' | 'create' | 'reject') {
  if (type === 'create' || type === 'update') {
    const { valid } = await formRef.value!.validate()
    if (!valid) return
  }

  let endpoint = '',
      method: 'PATCH' | 'DELETE' | 'PUT' | 'POST' = 'POST',
      successMessage = '',
      body: object | undefined

  const getPayload = () => {
    const payload: Partial<User> = { ...editedUser.value }
    
    // Handle blok and kamar based on role and switch status
    if (payload.role === 'USER') {
      // Untuk USER, blok dan kamar selalu wajib. Validasi di template sudah menangani ini.
    } else if (payload.role === 'ADMIN') { // Jika role Admin
      if (isUserDataInputActive.value) { // Jika switch diaktifkan, kirim nilai dari form
        // Validasi wajib sudah di template jika switch aktif
      } else { // Jika switch dimatikan, kirim blok dan kamar sebagai null
        payload.blok = null
        payload.kamar = null
      }
    }
    return payload
  }

  try {
    loading.value = true;

    switch (type) {
      case 'approve':
        if (!selectedUser.value) return
        endpoint = `/admin/users/${selectedUser.value.id}/approve`
        method = 'PATCH'
        successMessage = 'Pengguna berhasil disetujui.'
        break
      case 'reject':
        if (!selectedUser.value) return
        endpoint = `/admin/users/${selectedUser.value.id}/reject`
        method = 'POST'
        successMessage = 'Pendaftaran pengguna ditolak dan data telah dihapus.'
        break
      case 'delete':
        if (!selectedUser.value) return
        endpoint = `/admin/users/${selectedUser.value.id}`
        method = 'DELETE'
        successMessage = 'Pengguna berhasil dihapus.'
        break
      case 'update':
        endpoint = `/admin/users/${editedUser.value.id}`
        method = 'PUT'
        successMessage = 'Data pengguna diperbarui.'
        body = getPayload()
        break
      case 'create':
        endpoint = '/admin/users'
        method = 'POST'
        successMessage = 'Pengguna baru berhasil ditambahkan.'
        body = getPayload()
        break
    }

    await $api(endpoint, { method, body })
    showSnackbar(successMessage, 'success')
    fetchUsers()
  }
  catch (error: any) {
    console.error('API Error:', error);
    const errorMsg = error.response?._data?.message || error.data?.message || error.message || 'Terjadi kesalahan tidak dikenal'
    showSnackbar(`Error: ${errorMsg}`, 'error')
  }
  finally {
    loading.value = false;
    closeDialog()
  }
}

// Fungsi untuk Reset Password Hotspot (untuk user biasa, di dialog view)
const resetHotspotPasswordForUser = async () => {
  if (!selectedUser.value || selectedUser.value.role !== 'USER') {
    showSnackbar('Hanya pengguna biasa yang dapat mereset password hotspot.', 'warning');
    return;
  }
  
  if (confirm(`Anda yakin ingin mereset password hotspot untuk ${selectedUser.value.full_name}? Password baru akan dikirim via WhatsApp.`)) {
    try {
      loading.value = true;
      const response = await $api<{ success: boolean; message: string; }>('/admin/users/' + selectedUser.value.id + '/reset-hotspot-password', {
        method: 'POST',
      });

      if (response.success) {
        showSnackbar(response.message, 'success');
        fetchUsers();
      } else {
        showSnackbar(response.message, 'error');
      }
    } catch (error: any) {
      const errorMsg = error.response?._data?.message || error.data?.message || error.message || 'Gagal mereset password hotspot.'
      showSnackbar(`Error: ${errorMsg}`, 'error');
    } finally {
      loading.value = false;
      closeDialog();
    }
  }
};

// Fungsi untuk Generate Password Admin (untuk admin yang sedang diedit)
const generateAdminPasswordForAdmin = async () => {
  if (!selectedUser.value || selectedUser.value.role !== 'ADMIN') { // Perbaikan: Gunakan selectedUser untuk tombol di dialog view
    showSnackbar('Hanya admin yang dapat meng-generate password portal.', 'warning');
    return;
  }
  
  if (confirm(`Anda yakin ingin meng-generate ulang password portal untuk ${selectedUser.value.full_name}? Password baru akan dikirim via WhatsApp.`)) {
    try {
      loading.value = true;
      const response = await $api<{ message: string }>('/admin/users/' + selectedUser.value.id + '/generate-admin-password', { // Perbaikan: Gunakan selectedUser.id
        method: 'POST',
      });

      showSnackbar(response.message, 'success');
      fetchUsers();
    } catch (error: any) {
      const errorMsg = error.response?._data?.message || error.data?.message || error.message || 'Gagal meng-generate password admin.'
      showSnackbar(`Error: ${errorMsg}`, 'error');
    } finally {
      loading.value = false;
      closeDialog();
    }
  }
};

// Fungsi untuk memformat tanggal dan waktu sederhana
const formatSimpleDateTime = (dateString: string | null) => {
    if (!dateString) return 'N/A';
    const date = new Date(dateString);
    if (isNaN(date.getTime())) return 'Tanggal tidak valid';
    return date.toLocaleDateString('id-ID', { day: '2-digit', month: 'long', year: 'numeric', hour: '2-digit', minute: '2-digit' });
};

// Fungsi untuk memformat nilai 'kamar' agar hanya menampilkan angka
const formatKamarDisplay = (kamarValue: string | null) => {
  if (!kamarValue) return '';
  // Menghilangkan 'Kamar_' dari string jika ada
  return kamarValue.replace('Kamar_', '');
};

// Fungsi untuk memformat nomor telepon untuk tampilan (mengubah +62 menjadi 0)
const formatPhoneNumberDisplay = (phoneNumber: string | null) => {
  if (!phoneNumber) return 'N/A';
  if (phoneNumber.startsWith('+62')) {
    return '0' + phoneNumber.substring(3);
  }
  return phoneNumber;
};

useHead({ title: 'Manajemen Pengguna' })
</script>

<template>
  <div>
    <VCard class="mb-6">
      <VCardText class="d-flex align-center flex-wrap gap-4">
        <div class="d-flex align-center gap-2">
          <VIcon icon="tabler-users-group" color="primary" size="28" />
          <h5 class="text-h5">
            Manajemen Pengguna
          </h5>
        </div>
        <VSpacer />
        <div class="d-flex align-center gap-4" :style="{ width: smAndDown ? '100%' : 'auto' }">
          <div :style="{ width: smAndDown ? 'calc(100% - 110px)' : '300px' }">
            <AppTextField
              v-model="search"
              placeholder="Cari Pengguna..."
              prepend-inner-icon="tabler-search"
              clearable
              density="comfortable"
              class="search-field"
            />
          </div>
          <VBtn prepend-icon="tabler-plus" @click="openDialog('edit')">
            Tambah
          </VBtn>
        </div>
      </VCardText>
    </VCard>

    <VCard v-if="!smAndDown">
      <VDataTableServer
        v-model:options="options"
        :headers="headers"
        :items="users"
        :items-length="totalUsers"
        :loading="loading"
        :items-per-page="options.itemsPerPage"
        item-value="id"
        class="text-no-wrap"
      >
        <template #item.full_name="{ item }">
          <div class="d-flex flex-column py-2">
            <span class="font-weight-medium text-high-emphasis">{{ item.full_name }}</span>
            <small class="text-medium-emphasis">{{ formatPhoneNumberDisplay(item.phone_number) }}</small>
          </div>
        </template>
        
        <template #item.approval_status="{ item }">
          <VChip
            :color="statusMap[item.approval_status]?.color"
            :variant="statusMap[item.approval_status]?.variant"
            size="small"
            label
            class="status-chip"
            style="left: -10px;"
          >
            {{ statusMap[item.approval_status]?.text || item.approval_status }}
          </VChip>
        </template>
        
        <template #item.role="{ item }">
          <VChip
            :color="roleMap[item.role]?.color"
            :variant="roleMap[item.role]?.variant"
            size="small"
            label
            class="role-chip"
          >
            {{ roleMap[item.role]?.text || item.role }}
          </VChip>
        </template>
        
        <template #item.is_active="{ item }">
          <VTooltip :text="item.is_active ? 'Aktif' : 'Tidak Aktif'">
            <template #activator="{ props }">
              <VIcon
                v-bind="props"
                :color="item.is_active ? 'success' : 'error'"
                :icon="item.is_active ? 'tabler-plug-connected' : 'tabler-plug-connected-x'"
                size="22"
                style="left: 8px;"
              />
            </template>
          </VTooltip>
        </template>
        
        <template #item.created_at="{ item }">
          {{ new Date(item.created_at).toLocaleDateString('id-ID', { day: '2-digit', month: 'short', year: 'numeric' }) }}
        </template>
        
        <template #item.actions="{ item }">
          <div class="d-flex gap-1 justify-center action-buttons">
            <VBtn icon variant="text" color="secondary" size="small" @click="openDialog('view', item)" class="action-btn">
                <VIcon icon="tabler-eye" />
                <VTooltip activator="parent">Lihat Detail</VTooltip>
            </VBtn>

            <template v-if="item.approval_status === 'PENDING_APPROVAL'">
              <VBtn icon variant="text" color="success" size="small" @click="openDialog('approve', item)" class="action-btn">
                <VIcon icon="tabler-check" />
                <VTooltip activator="parent">Setujui</VTooltip>
              </VBtn>
              <VBtn icon variant="text" color="error" size="small" @click="openDialog('reject', item)" class="action-btn">
                <VIcon icon="tabler-trash-x-filled" />
                <VTooltip activator="parent">Tolak & Hapus</VTooltip>
              </VBtn>
            </template>

            <VBtn 
              v-if="item.id !== authStore.user?.id && (authStore.isSuperAdmin || (authStore.isAdmin && item.role === 'USER'))"
              icon variant="text" color="primary" size="small" @click="openDialog('edit', item)" class="action-btn"
            >
              <VIcon icon="tabler-pencil" />
              <VTooltip activator="parent">Edit</VTooltip>
            </VBtn>
            
            <VBtn 
              v-if="item.id !== authStore.user?.id && item.approval_status !== 'PENDING_APPROVAL' && (authStore.isSuperAdmin || (authStore.isAdmin && item.role === 'USER'))" 
              icon variant="text" color="error" size="small" @click="openDialog('delete', item)" class="action-btn"
            >
              <VIcon icon="tabler-trash" />
              <VTooltip activator="parent">Hapus</VTooltip>
            </VBtn>
          </div>
        </template>
        
        <template #loading>
          <tr v-for="i in options.itemsPerPage" :key="i">
            <td v-for="j in headers.length" :key="j">
              <VSkeletonLoader type="text" />
            </td>
          </tr>
        </template>
        
        <template #no-data>
          <div class="py-8 text-center">
            <VIcon icon="tabler-database-off" size="48" class="mb-2" />
            <p>Tidak ada data pengguna</p>
          </div>
        </template>
      </VDataTableServer>
    </VCard>

    <div v-else>
      <VCard v-if="loading" class="mb-4">
        <VCardText>
          <VSkeletonLoader type="card" />
        </VCardText>
      </VCard>

      <template v-else>
        <div v-if="users.length === 0" class="text-center py-8">
          <VIcon icon="tabler-database-off" size="48" class="mb-2" />
          <p>Tidak ada data pengguna</p>
        </div>

        <VCard v-for="user in users" :key="user.id" class="mb-4 user-card">
          <VCardText>
            <div class="d-flex justify-space-between align-center mb-2">
              <div>
                <div class="font-weight-bold user-name">{{ user.full_name }}</div>
                <div class="text-caption text-medium-emphasis">{{ formatPhoneNumberDisplay(user.phone_number) }}</div>
              </div>
              <VChip :color="statusMap[user.approval_status]?.color" :variant="statusMap[user.approval_status]?.variant" size="small" class="status-chip">
                {{ statusMap[user.approval_status]?.text }}
              </VChip>
            </div>
            
            <VDivider class="my-3" />
            
            <div class="d-flex justify-end gap-2 action-buttons">
                <VBtn icon variant="text" color="secondary" size="small" @click="openDialog('view', user)" class="action-btn">
                    <VIcon icon="tabler-eye" />
                    <VTooltip activator="parent">Lihat Detail</VTooltip>
                </VBtn>

              <template v-if="user.approval_status === 'PENDING_APPROVAL'">
                <VBtn icon variant="text" color="success" size="small" @click="openDialog('approve', user)" class="action-btn">
                  <VIcon icon="tabler-check" />
                  <VTooltip activator="parent">Setujui</VTooltip>
                </VBtn>
                <VBtn icon variant="text" color="error" size="small" @click="openDialog('reject', user)" class="action-btn">
                  <VIcon icon="tabler-trash-x-filled" />
                  <VTooltip activator="parent">Tolak & Hapus</VTooltip>
                </VBtn>
              </template>
              
              <VBtn 
                v-if="user.id !== authStore.user?.id && (authStore.isSuperAdmin || (authStore.isAdmin && user.role === 'USER'))"
                icon variant="text" color="primary" size="small" @click="openDialog('edit', user)" class="action-btn"
              >
                <VIcon icon="tabler-pencil" />
                <VTooltip activator="parent">Edit</VTooltip>
              </VBtn>
              
              <VBtn 
                v-if="user.id !== authStore.user?.id && user.approval_status !== 'PENDING_APPROVAL' && (authStore.isSuperAdmin || (authStore.isAdmin && user.role === 'USER'))" 
                icon variant="text" color="error" size="small" @click="openDialog('delete', user)" class="action-btn"
              >
                <VIcon icon="tabler-trash" />
                <VTooltip activator="parent">Hapus</VTooltip>
              </VBtn>
            </div>
          </VCardText>
        </VCard>
      </template>
      
      <div class="d-flex justify-center mt-4" v-if="!loading && users.length > 0">
        <VPagination v-model="options.page" :length="Math.ceil(totalUsers / options.itemsPerPage)" :total-visible="smAndDown ? 5 : 7" density="comfortable" />
      </div>
    </div>
    
    <VDialog v-model="dialog.view" max-width="600" scrollable>
        <VCard v-if="selectedUser">
            <DialogCloseBtn @click="closeDialog" />
            <VCardTitle class="text-h6 d-flex align-center pa-4 bg-primary text-white">
                <VIcon start icon="tabler-user-circle" />
                Detail Pengguna
            </VCardTitle>
            <VDivider />
            <VCardText class="pt-4">
                <VList lines="two" density="compact">
                    <VListItem>
                        <template #prepend><VIcon icon="tabler-user" /></template>
                        <VListItemTitle class="font-weight-semibold">{{ selectedUser.full_name }}</VListItemTitle>
                    </VListItem>
                    <VListItem>
                        <template #prepend><VIcon icon="tabler-phone" /></template>
                        <VListItemTitle>{{ formatPhoneNumberDisplay(selectedUser.phone_number) }}</VListItemTitle>
                    </VListItem>
                    <VListItem>
                        <template #prepend><VIcon icon="tabler-shield-check" /></template>
                        <VListItemTitle>
                               <VChip :color="roleMap[selectedUser.role]?.color" size="small" label>{{ roleMap[selectedUser.role]?.text }}</VChip>
                        </VListItemTitle>
                    </VListItem>
                    <VListItem>
                        <template #prepend><VIcon icon="tabler-checkup-list" /></template>
                        <VListItemTitle>
                            <VChip :color="statusMap[selectedUser.approval_status]?.color" size="small" label>{{ statusMap[selectedUser.approval_status]?.text }}</VChip>
                        </VListItemTitle>
                    </VListItem>
                    <VListItem>
                        <template #prepend><VIcon :color="selectedUser.is_active ? 'success' : 'error'" :icon="selectedUser.is_active ? 'tabler-plug-connected' : 'tabler-plug-connected-x'" /></template>
                        <VListItemTitle>{{ selectedUser.is_active ? 'Aktif' : 'Tidak Aktif' }}</VListItemTitle>
                    </VListItem>

                    <VDivider class="my-2" v-if="selectedUser.blok && selectedUser.kamar"/>

                    <VListItem v-if="selectedUser.blok && selectedUser.kamar">
                        <template #prepend><VIcon icon="tabler-building-community" /></template>
                        <VListItemTitle>Blok {{ selectedUser.blok }}, Kamar {{ formatKamarDisplay(selectedUser.kamar) }}</VListItemTitle>
                    </VListItem>

                    <VDivider class="my-2"/>

                    <VListItem>
                        <template #prepend><VIcon icon="tabler-calendar-plus" /></template>
                        <VListItemSubtitle>Tanggal Pendaftaran</VListItemSubtitle>
                        <VListItemTitle>{{ formatSimpleDateTime(selectedUser.created_at) }}</VListItemTitle>
                    </VListItem>
                    <VListItem v-if="selectedUser.approval_status === 'APPROVED'">
                        <template #prepend><VIcon icon="tabler-calendar-check" /></template>
                        <VListItemSubtitle>Tanggal Disetujui</VListItemSubtitle>
                        <VListItemTitle>{{ formatSimpleDateTime(selectedUser.approved_at) }}</VListItemTitle>
                    </VListItem>
                </VList>
            </VCardText>
            <VCardActions class="pa-4 d-flex flex-wrap justify-space-between align-center">
                <VBtn
                    v-if="selectedUser.role === 'USER' && selectedUser.is_active"
                    color="warning"
                    prepend-icon="tabler-key"
                    @click="resetHotspotPasswordForUser"
                    :loading="loading"
                    :disabled="loading"
                    class="my-1"
                >
                    Reset Hotspot Password
                </VBtn>
                
                <VBtn
                    v-if="selectedUser.role === 'ADMIN'"
                    color="info"
                    prepend-icon="tabler-refresh"
                    @click="generateAdminPasswordForAdmin"
                    :loading="loading"
                    :disabled="loading"
                    class="my-1"
                >
                    Reset Password Admin
                </VBtn>
                
                <VSpacer/>
                <VBtn variant="tonal" color="secondary" @click="closeDialog" class="my-1">Tutup</VBtn>
            </VCardActions>
        </VCard>
    </VDialog>

    <VDialog v-model="dialog.approve" max-width="400" persistent>
      <VCard>
        <VCardTitle class="d-flex align-center">
          <span class="headline">Konfirmasi Persetujuan</span>
          <VSpacer />
          <VBtn icon="tabler-x" variant="text" @click="closeDialog" />
        </VCardTitle>
        <VDivider />
        <VCardText class="pt-4">
          <p>Setujui pengguna <strong>{{ selectedUser?.full_name }}</strong>?</p>
        </VCardText>
        <VCardActions>
          <VSpacer />
          <VBtn variant="tonal" color="secondary" @click="closeDialog">Batal</VBtn>
          <VBtn color="success" @click="handleAction('approve')">Setujui</VBtn>
        </VCardActions>
      </VCard>
    </VDialog>

    <VDialog v-model="dialog.reject" max-width="450" persistent>
      <VCard>
        <VCardTitle class="d-flex align-center">
          <span class="headline">Konfirmasi Penolakan</span>
          <VSpacer />
          <VBtn icon="tabler-x" variant="text" @click="closeDialog" />
        </VCardTitle>
        <VDivider />
        <VCardText class="pt-4">
          <p>Anda yakin ingin menolak pendaftaran <strong>{{ selectedUser?.full_name }}</strong>?</p>
          <p class="text-caption text-medium-emphasis mt-2">Data pendaftaran akan dihapus secara permanen.</p>
        </VCardText>
        <VCardActions>
          <VSpacer />
          <VBtn variant="tonal" color="secondary" @click="closeDialog">Batal</VBtn>
          <VBtn color="error" @click="handleAction('reject')">Ya, Tolak & Hapus</VBtn>
        </VCardActions>
      </VCard>
    </VDialog>

    <VDialog v-model="dialog.delete" max-width="450" persistent>
      <VCard>
        <VCardTitle class="d-flex align-center">
          <span class="headline">Konfirmasi Penghapusan</span>
          <VSpacer />
          <VBtn icon="tabler-x" variant="text" @click="closeDialog" />
        </VCardTitle>
        <VDivider />
        <VCardText class="pt-4">
          <p>Anda yakin ingin menghapus pengguna <strong>{{ selectedUser?.full_name }}</strong>?</p>
          <p class="text-caption text-medium-emphasis mt-2">Data yang dihapus tidak dapat dikembalikan.</p>
        </VCardText>
        <VCardActions>
          <VSpacer />
          <VBtn variant="tonal" color="secondary" @click="closeDialog">Batal</VBtn>
          <VBtn color="error" @click="handleAction('delete')">Hapus</VBtn>
        </VCardActions>
      </VCard>
    </VDialog>

    <VDialog v-model="dialog.edit" max-width="600" persistent>
      <VCard>
        <VForm ref="formRef" @submit.prevent="handleAction(editedUser.id ? 'update' : 'create')">
          <VCardTitle class="d-flex align-center">
            <span class="headline">{{ formTitle }}</span>
            <VSpacer />
            <VBtn icon="tabler-x" variant="text" @click="closeDialog" />
          </VCardTitle>
          <VDivider />
          <VCardText v-if="editedUser" class="pt-4">
            <VRow>
              <VCol cols="12">
                <AppTextField v-model="editedUser.full_name" label="Nama Lengkap" density="compact" :rules="[v => !!v || 'Nama wajib diisi']" />
              </VCol>
              <VCol cols="12">
                <!-- Menggunakan value untuk tampilan awal, v-model untuk binding input -->
                <AppTextField 
                  :value="editedUser.phone_number_display"
                  @input="editedUser.phone_number = $event.target.value"
                  label="Nomor Telepon" 
                  density="compact" 
                  @blur="normalizePhoneNumberOnBlur" 
                  :rules="[v => !!v || 'Nomor telepon wajib diisi']" 
                />
              </VCol>

              <template v-if="editedUser.role === 'USER'">
                <VCol cols="12" sm="6">
                  <AppSelect v-model="editedUser.blok" :items="availableBloks" label="Blok" clearable density="compact" :rules="[requiredRule]" />
                </VCol>
                <VCol cols="12" sm="6">
                  <AppSelect
                    v-model="editedUser.kamar"
                    :items="availableKamars"
                    label="Kamar"
                    clearable
                    density="compact"
                    :rules="[requiredRule]"
                    item-title="formatKamarDisplay"
                  />
                </VCol>
              </template>

              <VCol v-if="editedUser.role === 'ADMIN'" cols="12">
                <VSwitch v-model="isUserDataInputActive" label="Lengkapi Data Alamat (Blok & Kamar)" density="compact" />
              </VCol>

              <template v-if="editedUser.role === 'ADMIN' && isUserDataInputActive">
                <VCol cols="12" sm="6">
                  <AppSelect v-model="editedUser.blok" :items="availableBloks" label="Blok" clearable density="compact" :rules="[requiredRule]" />
                </VCol>
                <VCol cols="12" sm="6">
                  <AppSelect
                    v-model="editedUser.kamar"
                    :items="availableKamars"
                    label="Kamar"
                    clearable
                    density="compact"
                    :rules="[requiredRule]"
                    item-title="formatKamarDisplay"
                  />
                </VCol>
              </template>

              <VCol v-if="authStore.isSuperAdmin" cols="12" sm="6">
                <AppSelect
                  v-model="editedUser.role"
                  :items="availableRoles"
                  item-title="title"
                  item-value="value"
                  label="Peran"
                  density="compact"
                  :rules="[v => !!v || 'Peran wajib dipilih']"
                  :disabled="editedUser.id === authStore.user?.id"
                />
              </VCol>

              <VCol v-if="editedUser.id" cols="12" sm="6" class="d-flex align-end pt-sm-5 mt-2">
                <VSwitch v-model="editedUser.is_active" label="Akun Aktif" density="compact" />
              </VCol>
            </VRow>
          </VCardText>
          <VDivider />
          <VCardActions class="px-5 pb-4 mt-2">
            <VSpacer />
            <VBtn variant="tonal" color="secondary" @click="closeDialog">Batal</VBtn>
            <div class="d-flex flex-column flex-sm-row ga-2">
                <VBtn type="submit" color="primary">Simpan</VBtn>
                </div>
          </VCardActions>
        </VForm>
      </VCard>
    </VDialog>

    <VSnackbar
      v-model="snackbar.show"
      :color="snackbar.color"
      :timeout="snackbar.timeout"
      location="top end"
    >
      {{ snackbar.text }}
      <template #actions>
        <VBtn
          icon="tabler-x"
          variant="text"
          color="white"
          @click="snackbar.show = false"
        />
      </template>
    </VSnackbar>
  </div>
</template>

<style scoped>
/* Responsive padding */
.v-card-text {
  padding: 16px;
}

@media (max-width: 600px) {
  .v-card-text {
    padding: 12px;
  }
}

/* Tabel desktop */
.text-no-wrap {
  white-space: nowrap;
}

/* Card mobile */
.user-card {
  border-radius: 8px;
  overflow: hidden;
  box-shadow: 0 2px 8px rgba(0,0,0,0.08);
}

.user-name {
  font-size: 1rem;
  line-height: 1.4;
}

.detail-item {
  flex: 1;
  min-width: 120px;
  margin-bottom: 8px;
}

/* Aksi tombol */
.action-buttons {
  flex-wrap: nowrap;
}

.action-btn {
  min-width: 36px;
  height: 36px;
}

/* Chip styling */
.status-chip, .role-chip {
  font-size: 0.75rem;
  font-weight: 500;
}

/* Search field */
.search-field {
  border-radius: 6px;
}

/* Loading state */
.v-skeleton-loader {
  border-radius: 8px;
}

/* Pagination */
.v-pagination {
  margin-top: 20px;
}

/* No data styling */
.text-center {
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
}

.v-dialog .v-dialog-close-btn {
    position: fixed !important;
}
</style>