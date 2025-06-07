<script lang="ts" setup>
import { ref, watch, computed, onMounted } from 'vue'
import type { VDataTableServer } from 'vuetify/labs/VDataTable'
import { useDisplay } from 'vuetify'
import { useAuthStore } from '@/store/auth'

// Mendefinisikan interface untuk struktur data pengguna
interface User {
  id: string
  full_name: string
  email: string | null
  phone_number: string
  role: 'USER' | 'ADMIN' | 'SUPER_ADMIN'
  approval_status: 'PENDING_APPROVAL' | 'APPROVED' | 'REJECTED'
  is_active: boolean
  created_at: string
  blok: string | null
  kamar: string | null
}

// Mendefinisikan tipe untuk opsi VDataTableServer
type Options = InstanceType<typeof VDataTableServer>['options']

// Menggunakan NuxtApp dan Vuetify display composables
const { $api } = useNuxtApp()
const { mobile, smAndDown } = useDisplay()
const authStore = useAuthStore()

// State reaktif untuk data pengguna dan loading
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

// State reaktif untuk snackbar (notifikasi) dan dialog (modal)
const snackbar = reactive({ show: false, text: '', color: 'info', timeout: 4000 })
const dialog = reactive({ edit: false, delete: false, approve: false })

// State reaktif untuk pengguna yang dipilih dan yang sedang diedit
const selectedUser = ref<User | null>(null)
const editedUser = ref<Partial<User>>({})
const isMounted = ref(false)

// Hook onMounted untuk mengambil data saat komponen dimuat
onMounted(() => {
  isMounted.value = true
  fetchUsers()
})

// --- Header Responsif ---
// Computed property untuk header tabel yang responsif
const headers = computed(() => {
  const base = [
    { title: 'PENGGUNA', key: 'full_name', sortable: true },
    { title: 'STATUS', key: 'approval_status', sortable: true },
    { title: 'PERAN', key: 'role', sortable: true },
    { title: 'AKTIF', key: 'is_active', sortable: true },
    { title: 'TGL DAFTAR', key: 'created_at', sortable: true },
    { title: 'AKSI', key: 'actions', sortable: false, align: 'center', width: '140px' },
  ]
  
  // Jika layar mobile (smAndDown), hanya tampilkan kolom tertentu
  if (smAndDown.value) {
    return base.filter(h => ['full_name', 'approval_status', 'actions'].includes(h.key))
  }
  return base
})

// --- Fetch Data ---
// Fungsi asinkron untuk mengambil data pengguna dari API
async function fetchUsers() {
  // Hanya ambil data jika komponen sudah dimuat
  if (!isMounted.value) return
  
  loading.value = true // Set status loading menjadi true
  try {
    const params = new URLSearchParams() // Buat objek URLSearchParams untuk parameter query
    params.append('page', String(options.value.page)) // Tambahkan parameter halaman
    params.append('itemsPerPage', String(options.value.itemsPerPage)) // Tambahkan parameter jumlah item per halaman
    
    // Tambahkan parameter sortBy dan sortOrder jika ada
    if (options.value.sortBy?.length) {
      params.append('sortBy', options.value.sortBy[0].key)
      params.append('sortOrder', options.value.sortBy[0].order)
    }
    
    // Tambahkan parameter pencarian jika ada
    if (search.value) params.append('search', search.value)
    
    // Lakukan panggilan API untuk mendapatkan data pengguna
    const response = await $api<{ items: User[]; totalItems: number }>(
      `/admin/users?${params.toString()}`
    )
    
    users.value = response.items // Perbarui daftar pengguna
    totalUsers.value = response.totalItems // Perbarui total pengguna
  } catch (error: any) { 
    // Tangani error dan tampilkan snackbar
    showSnackbar(`Gagal mengambil data: ${error.message || 'Server error'}`, 'error')
  } finally { 
    loading.value = false // Set status loading menjadi false setelah selesai
  }
}

// --- Watchers ---
// Watcher untuk memantau perubahan pada `options` dan memanggil `fetchUsers`
watch(() => options.value, fetchUsers, { deep: true })

let searchTimeout: ReturnType<typeof setTimeout>
// Watcher untuk memantau perubahan pada `search` dengan debounce
watch(search, () => {
  clearTimeout(searchTimeout) // Hapus timeout sebelumnya
  searchTimeout = setTimeout(() => {
    options.value.page = 1 // Reset halaman ke 1 saat pencarian
    fetchUsers() // Panggil fetchUsers setelah jeda
  }, 500)
})

// --- Helpers ---
// Fungsi untuk menampilkan snackbar notifikasi
function showSnackbar(text: string, color = 'info') {
  snackbar.text = text
  snackbar.color = color
  snackbar.show = true
}

// Map untuk mengelola tampilan status persetujuan
const statusMap = {
  APPROVED: { text: 'Disetujui', color: 'success', variant: 'outlined' },
  PENDING_APPROVAL: { text: 'Menunggu', color: 'warning', variant: 'outlined' },
  REJECTED: { text: 'Ditolak', color: 'error', variant: 'outlined' }
}

// Map untuk mengelola tampilan peran pengguna
const roleMap = {
  USER: { text: 'User', color: 'info', variant: 'tonal' },
  ADMIN: { text: 'Admin', color: 'primary', variant: 'tonal' },
  SUPER_ADMIN: { text: 'Super Admin', color: 'purple', variant: 'tonal' }
}

// Fungsi untuk menormalisasi nomor telepon saat input kehilangan fokus
function normalizePhoneNumberOnBlur() {
  if (editedUser.value.phone_number) {
    const phone = editedUser.value.phone_number
    let cleaned = phone.replace(/\D/g, '') // Hapus semua karakter non-digit
    
    // Ubah '08' menjadi '62'
    if (cleaned.startsWith('08')) {
      cleaned = '62' + cleaned.substring(1)
    }
    
    // Tambahkan '+' jika dimulai dengan '62'
    if (cleaned.startsWith('62')) {
      editedUser.value.phone_number = '+' + cleaned
    }
  }
}

// Fungsi untuk membuka dialog berdasarkan tipe dan data pengguna
function openDialog(type: 'approve' | 'delete' | 'edit', user: User) {
  selectedUser.value = { ...user } // Salin data pengguna yang dipilih
  if (type === 'edit') {
    editedUser.value = JSON.parse(JSON.stringify(user)) // Salin data pengguna untuk diedit
  }
  dialog[type] = true // Buka dialog yang sesuai
}

// Fungsi asinkron untuk menangani aksi (setujui, hapus, perbarui)
async function handleAction(type: 'approve' | 'delete' | 'update') {
  if (!selectedUser.value) return // Hentikan jika tidak ada pengguna yang dipilih
  
  const user = selectedUser.value
  let endpoint = '', 
      method: 'PATCH'|'DELETE'|'PUT' = 'PATCH', 
      successMessage = '', 
      body: object | undefined

  // Tentukan endpoint, metode, pesan sukses, dan body berdasarkan tipe aksi
  switch (type) {
    case 'approve': 
      endpoint = `/admin/users/${user.id}/approve`
      successMessage = 'Pengguna berhasil disetujui.'
      break
    case 'delete': 
      endpoint = `/admin/users/${user.id}`
      method = 'DELETE'
      successMessage = 'Pengguna berhasil dihapus.'
      break
    case 'update': 
      endpoint = `/admin/users/${user.id}`
      method = 'PUT'
      successMessage = 'Data pengguna diperbarui.'
      body = editedUser.value
      break
  }
  
  try {
    // Lakukan panggilan API
    await $api(endpoint, { method, body })
    showSnackbar(successMessage, 'success') // Tampilkan notifikasi sukses
    await fetchUsers() // Ambil data pengguna terbaru
  } catch (error: any) {
    // Tangani error dan tampilkan notifikasi error
    showSnackbar(`Error: ${error.data?.error || 'Terjadi kesalahan'}`, 'error')
  } finally {
    // Tutup semua dialog dan reset selectedUser
    dialog.approve = false
    dialog.delete = false
    dialog.edit = false
    selectedUser.value = null
  }
}

// Mengatur judul halaman
useHead({ title: 'Manajemen Pengguna' })
</script>

<template>
  <div>
    <VCard class="mb-6">
      <VCardText class="d-flex align-center flex-wrap gap-4">
        <div class="d-flex align-center gap-2">
          <VIcon icon="tabler-users-group" color="primary" size="28" />
          <h5 class="text-h5">Manajemen Pengguna</h5>
        </div>
        <VSpacer />
        <div :style="{ width: smAndDown ? '100%' : '300px' }">
          <AppTextField 
            v-model="search" 
            placeholder="Cari Pengguna..." 
            prepend-inner-icon="tabler-search" 
            clearable 
            density="comfortable"
            class="search-field"
          />
        </div>
      </VCardText>
    </VCard>

    <!-- Desktop View -->
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
        <!-- Nama & Telepon -->
        <template #item.full_name="{ item }">
          <div class="d-flex flex-column py-2">
            <span class="font-weight-medium text-high-emphasis">{{ item.full_name }}</span>
            <small class="text-medium-emphasis">{{ item.phone_number }}</small>
          </div>
        </template>
        
        <!-- Status Approval -->
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
        
        <!-- Role -->
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
        
        <!-- Status Aktif -->
        <template #item.is_active="{ item }">
          <VTooltip :text="item.is_active ? 'Aktif' : 'Tidak Aktif'">
            <template #activator="{ props }">
              <VIcon 
                v-bind="props" 
                :color="item.is_active ? 'success' : 'error'" 
                :icon="item.is_active ? 'tabler-circle-check-filled' : 'tabler-circle-x-filled'" 
                size="22"
                style="left: 8px;"
              />
            </template>
          </VTooltip>
        </template>
        
        <!-- Tanggal Daftar -->
        <template #item.created_at="{ item }">
          {{ new Date(item.created_at).toLocaleDateString('id-ID', { 
            day: '2-digit', 
            month: 'short', 
            year: 'numeric' 
          }) }}
        </template>
        
        <!-- Aksi -->
        <template #item.actions="{ item }">
          <div class="d-flex gap-1 justify-center action-buttons">
            <template v-if="item.approval_status === 'PENDING_APPROVAL'">
              <VBtn 
                icon 
                variant="text" 
                color="success" 
                size="small" 
                @click="openDialog('approve', item)"
                class="action-btn"
              >
                <VIcon icon="tabler-check" />
                <VTooltip activator="parent">Setujui</VTooltip>
              </VBtn>
              <VBtn 
                icon 
                variant="text" 
                color="error" 
                size="small" 
                @click="openDialog('delete', item)"
                class="action-btn"
              >
                <VIcon icon="tabler-trash-x-filled" />
                <VTooltip activator="parent">Tolak & Hapus</VTooltip>
              </VBtn>
            </template>
            <VBtn 
              icon 
              variant="text" 
              color="primary" 
              size="small" 
              @click="openDialog('edit', item)"
              class="action-btn"
            >
              <VIcon icon="tabler-pencil" />
              <VTooltip activator="parent">Edit</VTooltip>
            </VBtn>
            <VBtn 
              v-if="item.approval_status !== 'PENDING_APPROVAL'" 
              icon 
              variant="text" 
              color="error" 
              size="small" 
              @click="openDialog('delete', item)"
              class="action-btn"
            >
              <VIcon icon="tabler-trash" />
              <VTooltip activator="parent">Hapus</VTooltip>
            </VBtn>
          </div>
        </template>
        
        <!-- Loading State -->
        <template #loading>
          <tr v-for="i in options.itemsPerPage" :key="i">
            <td v-for="j in headers.length" :key="j">
              <VSkeletonLoader type="text" />
            </td>
          </tr>
        </template>
        
        <!-- No Data -->
        <template #no-data>
          <div class="py-8 text-center">
            <VIcon icon="tabler-database-off" size="48" class="mb-2" />
            <p>Tidak ada data pengguna</p>
          </div>
        </template>
      </VDataTableServer>
    </VCard>

    <!-- Mobile View -->
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
            <!-- Header -->
            <div class="d-flex justify-space-between align-center mb-2">
              <div>
                <div class="font-weight-bold user-name">{{ user.full_name }}</div>
                <div class="text-caption text-medium-emphasis">{{ user.phone_number }}</div>
              </div>
              <VChip 
                :color="statusMap[user.approval_status]?.color" 
                :variant="statusMap[user.approval_status]?.variant" 
                size="small"
                class="status-chip"
              >
                {{ statusMap[user.approval_status]?.text }}
              </VChip>
            </div>
            
            <VDivider class="my-2" />
            
            <!-- Detail -->
            <div class="d-flex flex-wrap justify-space-between gap-2">
              <div class="detail-item">
                <div class="text-caption text-medium-emphasis">Peran</div>
                <VChip 
                  :color="roleMap[user.role]?.color" 
                  :variant="roleMap[user.role]?.variant" 
                  size="small"
                  class="mt-1 role-chip"
                >
                  {{ roleMap[user.role]?.text }}
                </VChip>
              </div>
              
              <div class="detail-item">
                <div class="text-caption text-medium-emphasis">Status</div>
                <div class="d-flex align-center mt-1">
                  <VIcon 
                    :color="user.is_active ? 'success' : 'error'" 
                    :icon="user.is_active ? 'tabler-circle-check-filled' : 'tabler-circle-x-filled'" 
                    size="18"
                    class="mr-1"
                  />
                  <span>{{ user.is_active ? 'Aktif' : 'Nonaktif' }}</span>
                </div>
              </div>
              
              <div class="detail-item">
                <div class="text-caption text-medium-emphasis">Tanggal Daftar</div>
                <div class="mt-1">
                  {{ new Date(user.created_at).toLocaleDateString('id-ID', { 
                    day: '2-digit', 
                    month: 'short', 
                    year: 'numeric' 
                  }) }}
                </div>
              </div>
            </div>
            
            <VDivider class="my-3" />
            
            <!-- Actions -->
            <div class="d-flex justify-end gap-2 action-buttons">
              <template v-if="user.approval_status === 'PENDING_APPROVAL'">
                <VBtn 
                  icon 
                  variant="text" 
                  color="success" 
                  size="small"
                  @click="openDialog('approve', user)"
                  class="action-btn"
                >
                  <VIcon icon="tabler-check" />
                  <VTooltip activator="parent">Setujui</VTooltip>
                </VBtn>
                <VBtn 
                  icon 
                  variant="text" 
                  color="error" 
                  size="small"
                  @click="openDialog('delete', user)"
                  class="action-btn"
                >
                  <VIcon icon="tabler-trash-x-filled" />
                  <VTooltip activator="parent">Tolak & Hapus</VTooltip>
                </VBtn>
              </template>
              <VBtn 
                icon 
                variant="text" 
                color="primary" 
                size="small"
                @click="openDialog('edit', user)"
                class="action-btn"
              >
                <VIcon icon="tabler-pencil" />
                <VTooltip activator="parent">Edit</VTooltip>
              </VBtn>
              <VBtn 
                v-if="user.approval_status !== 'PENDING_APPROVAL'" 
                icon 
                variant="text" 
                color="error" 
                size="small"
                @click="openDialog('delete', user)"
                class="action-btn"
              >
                <VIcon icon="tabler-trash" />
                <VTooltip activator="parent">Hapus</VTooltip>
              </VBtn>
            </div>
          </VCardText>
        </VCard>
      </template>
      
      <!-- Pagination Mobile -->
      <div class="d-flex justify-center mt-4">
        <VPagination
          v-model="options.page"
          :length="Math.ceil(totalUsers / options.itemsPerPage)"
          :total-visible="smAndDown ? 5 : 7"
          density="comfortable"
        />
      </div>
    </div>

    <!-- Dialog Approve -->
    <VDialog v-model="dialog.approve" max-width="400" persistent>
      <VCard>
        <VCardTitle class="d-flex align-center">
          <span class="headline">Konfirmasi Persetujuan</span>
          <VSpacer />
          <VBtn icon="tabler-x" variant="text" @click="dialog.approve = false" />
        </VCardTitle>
        <VDivider />
        <VCardText class="pt-4">
          <p>Setujui pengguna <strong>{{ selectedUser?.full_name }}</strong>?</p>
        </VCardText>
        <VCardActions>
          <VSpacer />
          <VBtn variant="tonal" color="secondary" @click="dialog.approve = false">
            Batal
          </VBtn>
          <VBtn color="success" @click="handleAction('approve')">
            Setujui
          </VBtn>
        </VCardActions>
      </VCard>
    </VDialog>

    <!-- Dialog Delete -->
    <VDialog v-model="dialog.delete" max-width="450" persistent>
      <VCard>
        <VCardTitle class="d-flex align-center">
          <span class="headline">Konfirmasi Penghapusan</span>
          <VSpacer />
          <VBtn icon="tabler-x" variant="text" @click="dialog.delete = false" />
        </VCardTitle>
        <VDivider />
        <VCardText class="pt-4">
          <p>Anda yakin ingin menghapus pengguna <strong>{{ selectedUser?.full_name }}</strong>?</p>
          <p class="text-caption text-medium-emphasis mt-2">
            Data yang dihapus tidak dapat dikembalikan
          </p>
        </VCardText>
        <VCardActions>
          <VSpacer />
          <VBtn variant="tonal" color="secondary" @click="dialog.delete = false">
            Batal
          </VBtn>
          <VBtn color="error" @click="handleAction('delete')">
            Hapus
          </VBtn>
        </VCardActions>
      </VCard>
    </VDialog>

    <!-- Dialog Edit -->
    <VDialog v-model="dialog.edit" max-width="600" persistent>
      <VCard>
        <VCardTitle class="d-flex align-center">
          <span class="headline">Edit Pengguna</span>
          <VSpacer />
          <VBtn icon="tabler-x" variant="text" @click="dialog.edit = false" />
        </VCardTitle>
        <VDivider />
        <VCardText v-if="editedUser" class="pt-4">
          <VRow>
            <VCol cols="12">
              <AppTextField 
                v-model="editedUser.full_name" 
                label="Nama Lengkap" 
                density="compact"
              />
            </VCol>
            <VCol cols="12">
              <AppTextField 
                v-model="editedUser.phone_number" 
                label="Nomor Telepon" 
                density="compact"
                @blur="normalizePhoneNumberOnBlur" 
              />
            </VCol>
            <VCol cols="12" sm="6">
              <AppSelect 
                v-model="editedUser.blok" 
                :items="['A', 'B', 'C', 'D', 'E', 'F']" 
                label="Blok" 
                clearable 
                density="compact"
              />
            </VCol>
            <VCol cols="12" sm="6">
              <AppSelect 
                v-model="editedUser.kamar" 
                :items="['1','2','3','4','5','6']" 
                label="Kamar" 
                clearable 
                density="compact"
              />
            </VCol>
            
            <VCol v-if="authStore.isSuperAdmin" cols="12" sm="6">
              <AppSelect 
                v-model="editedUser.role" 
                :items="['USER', 'ADMIN', 'SUPER_ADMIN']" 
                label="Peran" 
                density="compact"
              />
            </VCol>

            <VCol cols="12" sm="6" class="d-flex align-center">
              <VSwitch 
                v-model="editedUser.is_active" 
                label="Akun Aktif" 
                density="compact"
              />
            </VCol>
          </VRow>
        </VCardText>
        <VDivider />
        <VCardActions class="px-5 pb-4 mt-2">
          <VSpacer />
          <VBtn variant="tonal" color="secondary" @click="dialog.edit = false">
            Batal
          </VBtn>
          <VBtn color="primary" @click="handleAction('update')">
            Simpan Perubahan
          </VBtn>
        </VCardActions>
      </VCard>
    </VDialog>

    <!-- Notifikasi -->
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
  /* Hapus atau komentari baris ini agar mengikuti tema */
  /* background-color: #fff; */ 
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
</style>