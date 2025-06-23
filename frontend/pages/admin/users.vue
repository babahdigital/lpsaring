<script lang="ts" setup>
import type { VDataTableServer } from 'vuetify/labs/VDataTable'
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useDisplay } from 'vuetify'
import UserActionConfirmDialog from '@/components/admin/users/UserActionConfirmDialog.vue'
import UserAddDialog from '@/components/admin/users/UserAddDialog.vue'

import UserDetailDialog from '@/components/admin/users/UserDetailDialog.vue'
import UserEditDialog from '@/components/admin/users/UserEditDialog.vue'
import { useSnackbar } from '@/composables/useSnackbar'
import { useAuthStore } from '@/store/auth'

interface User {
  id: string
  full_name: string
  phone_number: string
  role: 'USER' | 'KOMANDAN' | 'ADMIN' | 'SUPER_ADMIN'
  approval_status: 'PENDING_APPROVAL' | 'APPROVED' | 'REJECTED'
  is_active: boolean
  created_at: string
  blok: string | null
  kamar: string | null
  is_unlimited_user: boolean
  mikrotik_user_exists: boolean
  mikrotik_server_name: string | null
  mikrotik_profile_name: string | null
  mikrotik_password: string | null
  password_hash: string | null
  total_quota_purchased_mb: number
  total_quota_used_mb: number
  quota_expiry_date: string | null
  approved_at: string | null
}
type EditPayload = Partial<User> & { add_gb?: number, add_days?: number, is_unlimited_user?: boolean }
type Options = InstanceType<typeof VDataTableServer>['options']

const { $api } = useNuxtApp()
const { smAndDown } = useDisplay()
const authStore = useAuthStore()
const { add: showSnackbar } = useSnackbar()

const users = ref<User[]>([])
const loading = ref(true)
const totalUsers = ref(0)
const search = ref('')
const options = ref<Options>({ page: 1, itemsPerPage: 10, sortBy: [{ key: 'created_at', order: 'desc' }] })
const roleFilter = ref<string | null>(null)
const dialogState = reactive({ view: false, add: false, edit: false, confirm: false })
const selectedUser = ref<User | null>(null)
const editedUser = ref<User | null>(null)
const confirmProps = reactive({ title: '', message: '', color: 'primary', action: async () => {} })
const availableBloks = ref<string[]>([])
const availableKamars = ref<string[]>([])
const isAlamatLoading = ref(false)

const formatPhoneNumberDisplay = (phone: string | null) => (phone?.startsWith('+62') ? `0${phone.substring(3)}` : phone)
const formatCreatedAt = (date: string) => new Date(date).toLocaleDateString('id-ID', { day: '2-digit', month: 'short', year: 'numeric' })
const roleMap = { USER: { text: 'User', color: 'info' }, KOMANDAN: { text: 'Komandan', color: 'success' }, ADMIN: { text: 'Admin', color: 'primary' }, SUPER_ADMIN: { text: 'Support', color: 'secondary' } }
const statusMap = { APPROVED: { text: 'Disetujui', color: 'success' }, PENDING_APPROVAL: { text: 'Menunggu', color: 'warning' }, REJECTED: { text: 'Ditolak', color: 'error' } }
const roleFilterOptions = computed(() => {
  const allFilters = [{ text: 'User', value: 'USER' }, { text: 'Komandan', value: 'KOMANDAN' }]
  if (authStore.isAdmin || authStore.isSuperAdmin)
    allFilters.push({ text: 'Admin', value: 'ADMIN' })

  if (authStore.isSuperAdmin)
    allFilters.push({ text: 'Support', value: 'SUPER_ADMIN' })

  return allFilters
})

const headers = computed(() => {
  const base = [
    { title: 'PENGGUNA', key: 'full_name', sortable: true, minWidth: '250px' },
    { title: 'STATUS', key: 'approval_status', sortable: true },
    { title: 'PERAN', key: 'role', sortable: true },
    { title: 'KONEKSI', key: 'is_active', sortable: true, align: 'center' },
    { title: 'TGL DAFTAR', key: 'created_at', sortable: true },
    { title: 'AKSI', key: 'actions', sortable: false, align: 'center', width: '150px' },
  ]
  return smAndDown.value
    ? base.filter(h => h && h.key && ['full_name', 'approval_status', 'actions'].includes(h.key))
    : base
})

useHead({ title: 'Manajemen Pengguna' })
onMounted(() => {
  fetchUsers()
  fetchAlamatOptions()
})
watch([() => options.value, roleFilter], () => {
  if (options.value)
    options.value.page = 1
  fetchUsers()
}, { deep: true })
let searchTimeout: ReturnType<typeof setTimeout>
watch(search, () => {
  clearTimeout(searchTimeout)
  searchTimeout = setTimeout(() => {
    if (options.value)
      options.value.page = 1
    fetchUsers()
  }, 500)
})

async function fetchUsers() {
  loading.value = true
  try {
    const params = new URLSearchParams()
    if (options.value) {
      params.append('page', String(options.value.page))
      params.append('itemsPerPage', String(options.value.itemsPerPage))
      if (options.value.sortBy?.length) {
        params.append('sortBy', options.value.sortBy[0].key)
        params.append('sortOrder', options.value.sortBy[0].order)
      }
    }
    if (search.value)
      params.append('search', search.value)
    if (roleFilter.value)
      params.append('role', roleFilter.value)
    const response = await $api<{ items: User[], totalItems: number }>(`/admin/users?${params.toString()}`)
    users.value = response.items
    totalUsers.value = response.totalItems
  }
  catch (error: any) {
    showSnackbar({ type: 'error', title: 'Gagal Mengambil Data', text: error.data?.message || 'Terjadi kesalahan pada server.' })
  }
  finally {
    loading.value = false
  }
}
async function fetchAlamatOptions() {
  if (availableBloks.value.length > 0)
    return
  isAlamatLoading.value = true
  try {
    const response = await $api<{ bloks: string[], kamars: string[] }>('/admin/form-options/alamat')
    availableBloks.value = response.bloks
    availableKamars.value = response.kamars
  }
  catch (error: any) {
    showSnackbar({ type: 'error', title: 'Gagal Memuat Alamat', text: error.data?.message || 'Terjadi error saat memuat pilihan alamat.' })
  }
  finally {
    isAlamatLoading.value = false
  }
}
function openAddUserDialog() {
  dialogState.add = true
}
function openEditDialog(user: User) {
  editedUser.value = { ...user }
  dialogState.edit = true
}
function openViewDialog(user: User) {
  selectedUser.value = user
  dialogState.view = true
}
function openConfirmDialog(props: { title: string, message: string, color?: string, action: () => Promise<void> }) {
  confirmProps.title = props.title
  confirmProps.message = props.message
  confirmProps.color = props.color || 'primary'
  confirmProps.action = props.action
  dialogState.confirm = true
}
function closeAllDialogs() {
  dialogState.view = false
  dialogState.add = false
  dialogState.edit = false
  dialogState.confirm = false
}
async function handleSaveUser(payload: EditPayload) {
  const isUpdate = !!payload.id
  const endpoint = isUpdate ? `/admin/users/${payload.id}` : '/admin/users'
  const method = isUpdate ? 'PUT' : 'POST'
  await performAction(endpoint, method, isUpdate ? 'Data pengguna berhasil diperbarui.' : 'Pengguna baru berhasil dibuat.', { body: payload }, isUpdate ? payload.id : undefined)
}
function handleApprove(user: User) {
  openConfirmDialog({
    title: 'Konfirmasi Persetujuan',
    message: `Anda yakin ingin menyetujui pengguna <strong>${user.full_name}</strong>? Akun akan diaktifkan dan notifikasi akan dikirim.`,
    color: 'success',
    action: async () => await performAction(`/admin/users/${user.id}/approve`, 'PATCH', 'Pengguna berhasil disetujui.'),
  })
}
// [PERBAIKAN] Fungsi handleReject ditambahkan
function handleReject(user: User) {
  openConfirmDialog({
    title: 'Konfirmasi Penolakan',
    message: `Anda yakin ingin menolak & menghapus pendaftaran <strong>${user.full_name}</strong>? Notifikasi penolakan akan dikirim. Aksi ini tidak dapat dibatalkan.`,
    color: 'error',
    action: async () => await performAction(`/admin/users/${user.id}/reject`, 'POST', 'Pendaftaran pengguna ditolak dan data telah dihapus.'),
  })
}
function handleDelete(user: User) {
  openConfirmDialog({
    title: 'Konfirmasi Penghapusan',
    message: `Anda yakin ingin menghapus atau menonaktifkan pengguna <strong>${user.full_name}</strong>?`,
    color: 'error',
    action: async () => await performAction(`/admin/users/${user.id}`, 'DELETE', 'Aksi terhadap pengguna berhasil dilakukan.'),
  })
}
function handleResetHotspot(userId: string) {
  openConfirmDialog({
    title: 'Reset Password Hotspot',
    message: 'Password hotspot baru akan dibuat dan dikirim ke pengguna via WhatsApp. Lanjutkan?',
    color: 'warning',
    action: async () => await performAction(`/admin/users/${userId}/reset-hotspot-password`, 'POST', 'Password hotspot berhasil direset.'),
  })
}
function handleGenerateAdminPass(userId: string) {
  openConfirmDialog({
    title: 'Reset Password Portal',
    message: 'Password portal baru akan dibuat dan dikirim ke admin via WhatsApp. Lanjutkan?',
    color: 'info',
    action: async () => await performAction(`/admin/users/${userId}/generate-admin-password`, 'POST', 'Password portal berhasil direset.'),
  })
}
async function performAction(endpoint: string, method: 'PATCH' | 'POST' | 'DELETE' | 'PUT', successMessage: string, options: { body?: object } = {}, updatedItemId?: string) {
  loading.value = true
  try {
    const response = await $api<any>(endpoint, { method, ...options })
    showSnackbar({ type: 'success', title: 'Berhasil', text: successMessage })
    closeAllDialogs()
    await fetchUsers()
    if (dialogState.view && selectedUser.value && selectedUser.value.id === updatedItemId && response && response.user)
      selectedUser.value = { ...selectedUser.value, ...response.user }
  }
  catch (error: any) {
    const errorMessage = error.data?.message || 'Operasi gagal. Silakan coba lagi.'
    showSnackbar({ type: 'error', title: 'Terjadi Kesalahan', text: errorMessage })
  }
  finally {
    loading.value = false
  }
}
</script>

<template>
  <div>
    <VCard class="mb-6 rounded-lg">
      <VCardItem>
        <template #prepend>
          <VIcon icon="tabler-users-group" color="primary" size="32" class="me-2" />
        </template>
        <VCardTitle class="text-h4">
          Manajemen Pengguna
        </VCardTitle>
        <VCardSubtitle>Kelola semua akun yang terdaftar di sistem.</VCardSubtitle>
        <template #append>
          <div class="d-flex align-center gap-4" :style="{ width: smAndDown ? '100%' : 'auto' }">
            <div :style="{ width: smAndDown ? 'calc(100% - 130px)' : '300px' }">
              <AppTextField v-model="search" placeholder="Cari (Nama/No. HP)..." prepend-inner-icon="tabler-search" clearable density="compact" hide-details />
            </div>
            <VBtn prepend-icon="tabler-plus" @click="openAddUserDialog()">
              Tambah Akun
            </VBtn>
          </div>
        </template>
      </VCardItem>
      <VDivider v-if="!smAndDown" />
      <VCardText v-if="!smAndDown">
        <VRow align="center" no-gutters>
          <VCol cols="12" md="auto" class="text-no-wrap me-md-4 mb-2 mb-md-0">
            <span class="text-body-2 text-disabled">Fokus pada peran:</span>
          </VCol>
          <VCol cols="12" md="auto">
            <VChipGroup v-model="roleFilter" mandatory selected-class="text-primary">
              <VChip :value="null" size="small" label>
                Semua
              </VChip>
              <VChip v-for="role in roleFilterOptions" :key="role.value" :value="role.value" size="small" label>
                {{ role.text }}
              </VChip>
            </VChipGroup>
          </VCol>
        </VRow>
      </VCardText>
    </VCard>

    <VCard class="rounded-lg">
      <VDataTableServer v-if="!smAndDown" v-model:options="options" :headers="headers" :items="users" :items-length="totalUsers" :loading="loading" item-value="id" class="text-no-wrap">
        <template #item.full_name="{ item }">
          <div class="d-flex align-center py-2">
            <VAvatar size="38" class="me-3" :color="roleMap[item.role]?.color" variant="tonal">
              <span class="text-h6">{{ item.full_name.substring(0, 1).toUpperCase() }}</span>
            </VAvatar>
            <div class="d-flex flex-column">
              <span class="font-weight-semibold text-high-emphasis">{{ item.full_name }}</span>
              <small class="text-medium-emphasis">{{ formatPhoneNumberDisplay(item.phone_number) }}</small>
            </div>
            <VTooltip v-if="item.is_unlimited_user" location="top">
              <template #activator="{ props: tooltipProps }">
                <VIcon v-bind="tooltipProps" icon="tabler-infinity" color="success" size="small" class="ms-2" />
              </template>
              <span>Akses Unlimited Aktif</span>
            </VTooltip>
          </div>
        </template>
        <template #item.approval_status="{ item }">
          <VChip :color="statusMap[item.approval_status]?.color" size="small" label>
            {{ statusMap[item.approval_status]?.text }}
          </VChip>
        </template>
        <template #item.role="{ item }">
          <VChip :color="roleMap[item.role]?.color" size="small" label>
            {{ roleMap[item.role]?.text }}
          </VChip>
        </template>
        <template #item.is_active="{ item }">
          <VTooltip :text="item.is_active ? 'Aktif' : 'Tidak Aktif'">
            <template #activator="{ props: tooltipProps }">
              <VIcon v-bind="tooltipProps" :color="item.is_active ? 'success' : 'error'" :icon="item.is_active ? 'tabler-plug-connected' : 'tabler-plug-connected-x'" size="22" />
            </template>
          </VTooltip>
        </template>
        <template #item.created_at="{ item }">
          {{ formatCreatedAt(item.created_at) }}
        </template>
        <template #item.actions="{ item }">
          <div class="d-flex gap-1 justify-center">
            <VBtn icon variant="text" color="secondary" size="small" @click="openViewDialog(item)">
              <VIcon icon="tabler-eye" /><VTooltip activator="parent">
                Lihat Detail
              </VTooltip>
            </VBtn>
            <template v-if="item.approval_status === 'PENDING_APPROVAL'">
              <VBtn icon variant="text" color="success" size="small" @click="handleApprove(item)">
                <VIcon icon="tabler-check" /><VTooltip activator="parent">
                  Setujui
                </VTooltip>
              </VBtn>
              <VBtn icon variant="text" color="error" size="small" @click="handleReject(item)">
                <VIcon icon="tabler-x" /><VTooltip activator="parent">
                  Tolak & Hapus
                </VTooltip>
              </VBtn>
            </template>
            <template v-else>
              <VBtn v-if="(authStore.isSuperAdmin || authStore.isAdmin)" icon variant="text" color="primary" size="small" @click="openEditDialog(item)">
                <VIcon icon="tabler-pencil" /><VTooltip activator="parent">
                  Edit
                </VTooltip>
              </VBtn>
              <VBtn v-if="item.id !== authStore.user?.id && (authStore.isSuperAdmin || (authStore.isAdmin && item.role !== 'ADMIN' && item.role !== 'SUPER_ADMIN'))" icon variant="text" color="error" size="small" @click="handleDelete(item)">
                <VIcon icon="tabler-trash" /><VTooltip activator="parent">
                  Hapus
                </VTooltip>
              </VBtn>
            </template>
          </div>
        </template>
        <template #no-data>
          <div class="py-8 text-center text-medium-emphasis">
            <VIcon icon="tabler-database-off" size="32" class="mb-2" /><p>Tidak ada data pengguna yang cocok.</p>
          </div>
        </template>
      </VDataTableServer>
      <div v-else class="pa-4">
        <div v-if="users.length === 0 && !loading" class="py-8 text-center text-medium-emphasis">
          <VIcon icon="tabler-database-off" size="32" class="mb-2" /><p>Tidak ada data pengguna.</p>
        </div>
        <VCard v-for="user in users" v-else :key="user.id" class="mb-3">
          <VCardText>
            <div class="d-flex justify-space-between">
              <div class="d-flex align-center py-2">
                <VAvatar size="32" class="me-3" :color="roleMap[user.role]?.color" variant="tonal">
                  <span class="text-sm font-weight-medium">{{ user.full_name.substring(0, 2).toUpperCase() }}</span>
                </VAvatar>
                <div class="d-flex flex-column">
                  <span class="font-weight-medium text-high-emphasis">{{ user.full_name }}</span><small class="text-medium-emphasis">{{ formatPhoneNumberDisplay(user.phone_number) }}</small>
                </div>
              </div>
              <VChip :color="statusMap[user.approval_status]?.color" size="small" label>
                {{ statusMap[user.approval_status]?.text }}
              </VChip>
            </div>
          </VCardText>
          <VDivider />
          <VCardActions class="justify-center">
            <div class="d-flex gap-1">
              <VBtn icon variant="text" color="secondary" size="small" @click="openViewDialog(user)">
                <VIcon icon="tabler-eye" /><VTooltip activator="parent">
                  Lihat Detail
                </VTooltip>
              </VBtn>
              <template v-if="user.approval_status === 'PENDING_APPROVAL'">
                <VBtn icon variant="text" color="success" size="small" @click="handleApprove(user)">
                  <VIcon icon="tabler-check" /><VTooltip activator="parent">
                    Setujui
                  </VTooltip>
                </VBtn>
                <VBtn icon variant="text" color="error" size="small" @click="handleReject(user)">
                  <VIcon icon="tabler-x" /><VTooltip activator="parent">
                    Tolak & Hapus
                  </VTooltip>
                </VBtn>
              </template>
              <template v-else>
                <VBtn v-if="(authStore.isSuperAdmin || authStore.isAdmin)" icon variant="text" color="primary" size="small" @click="openEditDialog(user)">
                  <VIcon icon="tabler-pencil" /><VTooltip activator="parent">
                    Edit
                  </VTooltip>
                </VBtn>
                <VBtn v-if="user.id !== authStore.user?.id && (authStore.isSuperAdmin || (authStore.isAdmin && user.role !== 'ADMIN' && user.role !== 'SUPER_ADMIN'))" icon variant="text" color="error" size="small" @click="handleDelete(user)">
                  <VIcon icon="tabler-trash" /><VTooltip activator="parent">
                    Hapus
                  </VTooltip>
                </VBtn>
              </template>
            </div>
          </VCardActions>
        </VCard>
      </div>
    </VCard>

    <UserDetailDialog v-model="dialogState.view" :user="selectedUser" />
    <UserAddDialog v-model="dialogState.add" :loading="loading" :available-bloks="availableBloks" :available-kamars="availableKamars" :is-alamat-loading="isAlamatLoading" @save="handleSaveUser" />
    <UserEditDialog v-if="dialogState.edit && editedUser" v-model="dialogState.edit" :user="editedUser" :loading="loading" :available-bloks="availableBloks" :available-kamars="availableKamars" :is-alamat-loading="isAlamatLoading" @save="handleSaveUser" @reset-hotspot="handleResetHotspot" @generate-admin-pass="handleGenerateAdminPass" />
    <UserActionConfirmDialog v-model="dialogState.confirm" :title="confirmProps.title" :message="confirmProps.message" :color="confirmProps.color" :loading="loading" @confirm="confirmProps.action" />
  </div>
</template>
