<script lang="ts" setup>
import { ref, watch, computed, onMounted, nextTick, reactive } from 'vue'
import type { VDataTableServer } from 'vuetify/labs/VDataTable'
import { useDisplay } from 'vuetify'
import { useAuthStore } from '@/store/auth'
import type { VForm } from 'vuetify/components'
import { differenceInDays, format, isPast, isValid } from 'date-fns'

import AppTextField from '@core/components/app-form-elements/AppTextField.vue'
import AppSelect from '@core/components/app-form-elements/AppSelect.vue'

// --- INTERFACE DIPERBARUI ---
// Menambahkan properti terkait kuota untuk mencerminkan data dari backend
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
  // Properti baru ditambahkan
  total_quota_purchased_mb: number
  total_quota_used_mb: number
  quota_expiry_date: string | null
  is_unlimited_user: boolean
}

// Interface untuk menyimpan detail promo yang diambil dari API
interface PromoDetails {
  id: string
  name: string
  description: string
  bonus_value_mb: number
  bonus_duration_days: number
  start_date: string
  end_date: string | null
}

// Interface untuk menyimpan hasil kalkulasi detail kuota
interface QuotaInfo {
  totalQuotaMB: number
  usedQuotaMB: number
  remainingQuotaMB: number
  percentageUsed: number
  isUnlimited: boolean
  promoName: string | null
  activationDate: string | null
  expiryDate: string | null
  remainingDays: number | null
  status: 'ACTIVE' | 'EXPIRED' | 'NOT_SET' | 'UNLIMITED'
  statusColor: string
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
const dialog = reactive({ view: false, edit: false, delete: false, approve: false, reject: false, customConfirm: false })
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
const isUserDataInputActive = ref(false)

const availableBloks = ref<string[]>([])
const availableKamars = ref<string[]>([])
const activeBonusPromo = ref<PromoDetails | null>(null) // State untuk menyimpan info promo aktif

const confirmMessage = ref('')
const confirmActionCallback = ref<(() => Promise<void>) | null>(null)

onMounted(async () => {
  isMounted.value = true
  await Promise.all([
    fetchUsers(),
    fetchAlamatOptions(),
    fetchActiveBonusPromo(), // Memuat info promo saat komponen dimuat
  ])
})

const formTitle = computed(() => (editedUser.value.id ? 'Edit Pengguna' : 'Tambah Pengguna'))

// --- FUNGSI BARU UNTUK MENGAMBIL PROMO AKTIF ---
async function fetchActiveBonusPromo() {
  try {
    const response = await $api<PromoDetails>('/public/promos/active', { method: 'GET' })
    if (response && response.id) {
      activeBonusPromo.value = response
    }
  }
  catch (error) {
    console.error("Tidak ada promo bonus registrasi aktif atau gagal memuat:", error)
    activeBonusPromo.value = null
  }
}

// --- COMPUTED PROPERTY BARU UNTUK MENGOLAH DETAIL KUOTA ---
const quotaDetails = computed((): QuotaInfo | null => {
  if (!selectedUser.value || selectedUser.value.role !== 'USER')
    return null

  const user = selectedUser.value
  const totalMB = user.total_quota_purchased_mb || 0
  const usedMB = user.total_quota_used_mb || 0
  const remainingMB = Math.max(0, totalMB - usedMB)
  const percentage = totalMB > 0 ? Math.min(100, (usedMB / totalMB) * 100) : 0

  let status: QuotaInfo['status'] = 'NOT_SET'
  let statusColor = 'grey'
  let remainingDays: number | null = null

  if (user.is_unlimited_user) {
    status = 'UNLIMITED'
    statusColor = 'primary'
  }
  else if (user.quota_expiry_date) {
    const expiry = new Date(user.quota_expiry_date)
    if (isValid(expiry)) {
      if (isPast(expiry)) {
        status = 'EXPIRED'
        statusColor = 'error'
        remainingDays = 0
      }
      else {
        status = 'ACTIVE'
        statusColor = 'success'
        remainingDays = differenceInDays(expiry, new Date())
      }
    }
  }
  
  // Set sisa hari untuk user unlimited juga
  if (user.is_unlimited_user && user.quota_expiry_date) {
      const expiry = new Date(user.quota_expiry_date);
      if (isValid(expiry) && !isPast(expiry)) {
          remainingDays = differenceInDays(expiry, new Date());
      } else if (isPast(expiry)) {
          remainingDays = 0;
          status = 'EXPIRED'
          statusColor = 'error'
      }
  }

  let promoName: string | null = null
  if (activeBonusPromo.value && user.approved_at) {
    const approvalDate = new Date(user.approved_at)
    const promoStartDate = new Date(activeBonusPromo.value.start_date)
    const promoEndDate = activeBonusPromo.value.end_date ? new Date(activeBonusPromo.value.end_date) : null

    // Cek apakah user disetujui dalam periode promo
    if (approvalDate >= promoStartDate && (!promoEndDate || approvalDate <= promoEndDate)) {
      // Cek apakah bonus kuota yang diterima user sesuai dengan bonus promo
      if (user.total_quota_purchased_mb === activeBonusPromo.value.bonus_value_mb) {
        promoName = activeBonusPromo.value.name
      }
    }
  }

  // Jika tidak ada promo terdeteksi tapi ada kuota, anggap paket reguler
  if (!promoName && totalMB > 0) {
    promoName = "Paket Reguler"
  }


  return {
    totalQuotaMB: totalMB,
    usedQuotaMB: usedMB,
    remainingQuotaMB: remainingMB,
    percentageUsed: percentage,
    isUnlimited: user.is_unlimited_user,
    promoName: promoName,
    activationDate: user.approved_at ? format(new Date(user.approved_at), 'dd MMMM yyyy') : null,
    expiryDate: user.quota_expiry_date ? format(new Date(user.quota_expiry_date), 'dd MMMM yyyy') : null,
    remainingDays: remainingDays,
    status: status,
    statusColor: statusColor,
  }
})

const availableRoles = computed(() => {
  if (authStore.isSuperAdmin) {
    return [
      { title: 'User Biasa', value: 'USER' },
      { title: 'Admin', value: 'ADMIN' },
    ]
  }
  return [{ title: 'User Biasa', value: 'USER' }]
})

watch(() => editedUser.value.role, (newRole) => {
  if (newRole === 'ADMIN')
    isUserDataInputActive.value = true
  else
    isUserDataInputActive.value = false
})

const headers = computed(() => {
  const base = [
    { title: 'PENGGUNA', key: 'full_name', sortable: true },
    { title: 'STATUS', key: 'approval_status', sortable: true },
    { title: 'PERAN', key: 'role', sortable: true },
    { title: 'AKTIF', key: 'is_active', sortable: true },
    { title: 'TGL DAFTAR', key: 'created_at', sortable: true },
    { title: 'AKSI', key: 'actions', sortable: false, align: 'center', width: '150px' },
  ]
  if (smAndDown.value)
    return base.filter(h => ['full_name', 'approval_status', 'actions'].includes(h.key))

  return base
})

async function fetchUsers() {
  if (!isMounted.value)
    return
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

    // Memastikan `items` sesuai dengan interface User yang telah diperbarui
    const response = await $api<{ items: User[], totalItems: number }>(`/admin/users?${params.toString()}`)
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

async function fetchAlamatOptions() {
  try {
    const response = await $api<any>('/admin/form-options/alamat', { method: 'GET' })
    if (response.success) {
      availableBloks.value = response.bloks || []
      availableKamars.value = response.kamars || []
    }
    else {
      showSnackbar(response.message || 'Gagal memuat opsi alamat.', 'error')
    }
  }
  catch (error: any) {
    console.error("Gagal mengambil opsi alamat:", error)
    showSnackbar('Gagal memuat opsi alamat. Terjadi kesalahan jaringan.', 'error')
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

function normalizePhoneNumber() {
  if (editedUser.value.phone_number) {
    let phone = editedUser.value.phone_number.trim()
    phone = phone.replace(/\s+/g, '').replace(/[^0-9+]/g, '')
    if (phone.startsWith('08'))
      editedUser.value.phone_number = `+628${phone.substring(2)}`
    else if (phone.startsWith('62'))
      editedUser.value.phone_number = `+${phone}`
    else if (phone.startsWith('8'))
      editedUser.value.phone_number = `+62${phone}`
  }
}

const requiredRule = (value: any) => !!value || 'Field ini wajib diisi.'

function openCustomConfirmDialog(message: string, callback: () => Promise<void>) {
  confirmMessage.value = message
  confirmActionCallback.value = callback
  dialog.customConfirm = true
}

function closeDialog() {
  dialog.view = false
  dialog.edit = false
  dialog.delete = false
  dialog.approve = false
  dialog.reject = false
  dialog.customConfirm = false
  nextTick(() => {
    selectedUser.value = null
    editedUser.value = { ...defaultUser }
    isUserDataInputActive.value = false
    formRef.value?.resetValidation()
    confirmMessage.value = ''
    confirmActionCallback.value = null
  })
}

function openDialog(type: 'view' | 'approve' | 'delete' | 'edit' | 'reject', user?: User) {
  if (type === 'edit') {
    if (!user) {
      editedUser.value = { ...defaultUser }
      isUserDataInputActive.value = false
      if (editedUser.value.role === 'ADMIN')
        isUserDataInputActive.value = true

      dialog.edit = true
      return
    }
    selectedUser.value = { ...user }
    const userToEdit = JSON.parse(JSON.stringify(user))
    if (userToEdit.kamar)
      userToEdit.kamar = formatKamarDisplay(userToEdit.kamar)

    if (userToEdit.phone_number)
      userToEdit.phone_number = formatPhoneNumberDisplay(userToEdit.phone_number)

    editedUser.value = userToEdit
    if (editedUser.value.role === 'ADMIN')
      isUserDataInputActive.value = true
    else
      isUserDataInputActive.value = false

    dialog.edit = true
  }
  else {
    if (user) {
      selectedUser.value = { ...user }
      dialog[type] = true
    }
    else {
      showSnackbar('Pengguna tidak ditemukan untuk aksi ini.', 'error')
    }
  }
}

async function handleAction(type: 'approve' | 'delete' | 'update' | 'create' | 'reject') {
  if (type === 'create' || type === 'update') {
    normalizePhoneNumber()
    await nextTick()
    const { valid } = await formRef.value!.validate()
    if (!valid)
      return
  }
  let endpoint = '',
    method: 'PATCH' | 'DELETE' | 'PUT' | 'POST' = 'POST',
    successMessage = '',
    body: object | undefined
  const getPayload = () => {
    const payload: Partial<User> = { ...editedUser.value }
    if (payload.role === 'USER') {
      // Logic for USER role
    }
    else if (payload.role === 'ADMIN') {
      if (!isUserDataInputActive.value) {
        payload.blok = null
        payload.kamar = null
      }
    }
    return payload
  }
  try {
    loading.value = true
    switch (type) {
      case 'approve':
        if (!selectedUser.value)
          return
        endpoint = `/admin/users/${selectedUser.value.id}/approve`
        method = 'PATCH'
        successMessage = 'Pengguna berhasil disetujui.'
        break
      case 'reject':
        if (!selectedUser.value)
          return
        endpoint = `/admin/users/${selectedUser.value.id}/reject`
        method = 'POST'
        successMessage = 'Pendaftaran pengguna ditolak dan data telah dihapus.'
        break
      case 'delete':
        if (!selectedUser.value)
          return
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
    console.error('API Error:', error)
    const errorMsg = error.response?._data?.message || error.data?.message || error.message || 'Terjadi kesalahan tidak dikenal'
    showSnackbar(`Error: ${errorMsg}`, 'error')
  }
  finally {
    loading.value = false
    closeDialog()
  }
}

const resetHotspotPasswordForUser = async () => {
  if (!selectedUser.value || selectedUser.value.role !== 'USER') {
    showSnackbar('Hanya pengguna biasa yang dapat mereset password hotspot.', 'warning')
    return
  }
  openCustomConfirmDialog(
    `Anda yakin ingin mereset password hotspot untuk ${selectedUser.value.full_name}? Password baru akan dikirim via WhatsApp.`,
    async () => {
      try {
        loading.value = true
        const response = await $api<{ success: boolean, message: string }>('/admin/users/' + selectedUser.value!.id + '/reset-hotspot-password', {
          method: 'POST',
        })
        if (response.success) {
          showSnackbar(response.message, 'success')
          fetchUsers()
        }
        else {
          showSnackbar(response.message, 'error')
        }
      }
      catch (error: any) {
        const errorMsg = error.response?._data?.message || error.data?.message || error.message || 'Gagal mereset password hotspot.'
        showSnackbar(`Error: ${errorMsg}`, 'error')
      }
      finally {
        loading.value = false
        // Dialog ditutup oleh fungsi confirm
      }
    },
  )
}

const generateAdminPasswordForAdmin = async () => {
  if (!selectedUser.value || selectedUser.value.role !== 'ADMIN') {
    showSnackbar('Hanya admin yang dapat meng-generate password portal.', 'warning')
    return
  }
  openCustomConfirmDialog(
    `Anda yakin ingin meng-generate ulang password portal untuk ${selectedUser.value.full_name}? Password baru akan dikirim via WhatsApp.`,
    async () => {
      try {
        loading.value = true
        const response = await $api<{ message: string }>('/admin/users/' + selectedUser.value!.id + '/generate-admin-password', {
          method: 'POST',
        })
        showSnackbar(response.message, 'success')
        fetchUsers()
      }
      catch (error: any) {
        const errorMsg = error.response?._data?.message || error.data?.message || error.message || 'Gagal meng-generate password admin.'
        showSnackbar(`Error: ${errorMsg}`, 'error')
      }
      finally {
        loading.value = false
        // Dialog ditutup oleh fungsi confirm
      }
    },
  )
}

const formatSimpleDateTime = (dateString: string | null) => {
  if (!dateString)
    return 'N/A'
  const date = new Date(dateString)
  if (isNaN(date.getTime()))
    return 'Tanggal tidak valid'
  return date.toLocaleDateString('id-ID', { day: '2-digit', month: 'long', year: 'numeric', hour: '2-digit', minute: '2-digit' })
}

const formatKamarDisplay = (kamarValue: string | null) => {
  if (!kamarValue)
    return ''
  // Mengembalikan nilai asli jika itu adalah item dari `availableKamars`
  if (availableKamars.value.includes(kamarValue)) {
      return kamarValue.replace('Kamar_', '');
  }
  return kamarValue;
}

const formatPhoneNumberDisplay = (phoneNumber: string | null) => {
  if (!phoneNumber)
    return 'N/A'
  if (phoneNumber.startsWith('+62'))
    return '0' + phoneNumber.substring(3)

  return phoneNumber
}

// Fungsi untuk memformat ukuran data dari MB ke format yang lebih mudah dibaca (MB/GB)
const formatDataSize = (sizeInMB: number) => {
  if (sizeInMB < 1024)
    return `${sizeInMB.toFixed(2)} MB`
  else
    return `${(sizeInMB / 1024).toFixed(2)} GB`
}

useHead({ title: 'Manajemen Pengguna' })
</script>

<template>
  <div>
    <VCard class="mb-6">
      <VCardText class="d-flex align-center flex-wrap gap-4">
        <div class="d-flex align-center gap-2">
          <VIcon
            icon="tabler-users-group"
            color="primary"
            size="28"
          />
          <h5 class="text-h5">
            Manajemen Pengguna
          </h5>
        </div>
        <VSpacer />
        <div
          class="d-flex align-center gap-4"
          :style="{ width: smAndDown ? '100%' : 'auto' }"
        >
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
          <VBtn
            prepend-icon="tabler-plus"
            @click="openDialog('edit')"
          >
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
            <VBtn
              icon
              variant="text"
              color="secondary"
              size="small"
              @click="openDialog('view', item)"
              class="action-btn"
            >
              <VIcon icon="tabler-eye" />
              <VTooltip activator="parent">
                Lihat Detail
              </VTooltip>
            </VBtn>

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
                <VTooltip activator="parent">
                  Setujui
                </VTooltip>
              </VBtn>
              <VBtn
                icon
                variant="text"
                color="error"
                size="small"
                @click="openDialog('reject', item)"
                class="action-btn"
              >
                <VIcon icon="tabler-trash-x-filled" />
                <VTooltip activator="parent">
                  Tolak & Hapus
                </VTooltip>
              </VBtn>
            </template>

            <VBtn
              v-if="item.id !== authStore.user?.id && (authStore.isSuperAdmin || (authStore.isAdmin && item.role === 'USER'))"
              icon
              variant="text"
              color="primary"
              size="small"
              @click="openDialog('edit', item)"
              class="action-btn"
            >
              <VIcon icon="tabler-pencil" />
              <VTooltip activator="parent">
                Edit
              </VTooltip>
            </VBtn>
            
            <VBtn
              v-if="item.id !== authStore.user?.id && item.approval_status !== 'PENDING_APPROVAL' && (authStore.isSuperAdmin || (authStore.isAdmin && item.role === 'USER'))"
              icon
              variant="text"
              color="error"
              size="small"
              @click="openDialog('delete', item)"
              class="action-btn"
            >
              <VIcon icon="tabler-trash" />
              <VTooltip activator="parent">
                Hapus
              </VTooltip>
            </VBtn>
          </div>
        </template>
        
        <template #loading>
          <tr
            v-for="i in options.itemsPerPage"
            :key="i"
          >
            <td
              v-for="j in headers.length"
              :key="j"
            >
              <VSkeletonLoader type="text" />
            </td>
          </tr>
        </template>
        
        <template #no-data>
          <div class="py-8 text-center">
            <VIcon
              icon="tabler-database-off"
              size="48"
              class="mb-2"
            />
            <p>Tidak ada data pengguna</p>
          </div>
        </template>
      </VDataTableServer>
    </VCard>

    <div v-else>
      <VCard
        v-if="loading"
        class="mb-4"
      >
        <VCardText>
          <VSkeletonLoader type="card" />
        </VCardText>
      </VCard>

      <template v-else>
        <div
          v-if="users.length === 0"
          class="text-center py-8"
        >
          <VIcon
            icon="tabler-database-off"
            size="48"
            class="mb-2"
          />
          <p>Tidak ada data pengguna</p>
        </div>

        <VCard
          v-for="user in users"
          :key="user.id"
          class="mb-4 user-card"
        >
          <VCardText>
            <div class="d-flex justify-space-between align-center mb-2">
              <div>
                <div class="font-weight-bold user-name">
                  {{ user.full_name }}
                </div>
                <div class="text-caption text-medium-emphasis">
                  {{ formatPhoneNumberDisplay(user.phone_number) }}
                </div>
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
            
            <VDivider class="my-3" />
            
            <div class="d-flex justify-end gap-2 action-buttons">
              <VBtn
                icon
                variant="text"
                color="secondary"
                size="small"
                @click="openDialog('view', user)"
                class="action-btn"
              >
                <VIcon icon="tabler-eye" />
                <VTooltip activator="parent">
                  Lihat Detail
                </VTooltip>
              </VBtn>

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
                  <VTooltip activator="parent">
                    Setujui
                  </VTooltip>
                </VBtn>
                <VBtn
                  icon
                  variant="text"
                  color="error"
                  size="small"
                  @click="openDialog('reject', user)"
                  class="action-btn"
                >
                  <VIcon icon="tabler-trash-x-filled" />
                  <VTooltip activator="parent">
                    Tolak & Hapus
                  </VTooltip>
                </VBtn>
              </template>
              
              <VBtn
                v-if="user.id !== authStore.user?.id && (authStore.isSuperAdmin || (authStore.isAdmin && user.role === 'USER'))"
                icon
                variant="text"
                color="primary"
                size="small"
                @click="openDialog('edit', user)"
                class="action-btn"
              >
                <VIcon icon="tabler-pencil" />
                <VTooltip activator="parent">
                  Edit
                </VTooltip>
              </VBtn>
              
              <VBtn
                v-if="user.id !== authStore.user?.id && user.approval_status !== 'PENDING_APPROVAL' && (authStore.isSuperAdmin || (authStore.isAdmin && user.role === 'USER'))"
                icon
                variant="text"
                color="error"
                size="small"
                @click="openDialog('delete', user)"
                class="action-btn"
              >
                <VIcon icon="tabler-trash" />
                <VTooltip activator="parent">
                  Hapus
                </VTooltip>
              </VBtn>
            </div>
          </VCardText>
        </VCard>
      </template>
      
      <div
        class="d-flex justify-center mt-4"
        v-if="!loading && users.length > 0"
      >
        <VPagination
          v-model="options.page"
          :length="Math.ceil(totalUsers / options.itemsPerPage)"
          :total-visible="smAndDown ? 5 : 7"
          density="comfortable"
        />
      </div>
    </div>
    
    <!-- --- DIALOG VIEW YANG TELAH DISEMPURNAKAN --- -->
    <VDialog
      v-model="dialog.view"
      max-width="600"
      scrollable
    >
      <VCard v-if="selectedUser">
        <DialogCloseBtn @click="closeDialog" />
        <VCardTitle class="text-h6 d-flex align-center pa-4 bg-primary text-white">
          <VIcon
            start
            icon="tabler-user-circle"
          />
          Detail Pengguna
        </VCardTitle>
        <VDivider />
        <VCardText class="pt-4">
          <!-- INFORMASI DASAR PENGGUNA -->
          <div class="text-overline mb-2">
            Informasi Dasar
          </div>
          <VList
            lines="two"
            density="compact"
          >
            <VListItem>
              <template #prepend>
                <VIcon icon="tabler-user" />
              </template>
              <VListItemTitle class="font-weight-semibold">
                {{ selectedUser.full_name }}
              </VListItemTitle>
            </VListItem>
            <VListItem>
              <template #prepend>
                <VIcon icon="tabler-phone" />
              </template>
              <VListItemTitle>{{ formatPhoneNumberDisplay(selectedUser.phone_number) }}</VListItemTitle>
            </VListItem>
            <VListItem>
              <template #prepend>
                <VIcon icon="tabler-shield-check" />
              </template>
              <VListItemTitle>
                <VChip
                  :color="roleMap[selectedUser.role]?.color"
                  size="small"
                >
                  {{ roleMap[selectedUser.role]?.text }}
                </VChip>
              </VListItemTitle>
            </VListItem>
            <VListItem>
              <template #prepend>
                <VIcon icon="tabler-checkup-list" />
              </template>
              <VListItemTitle>
                <VChip
                  :color="statusMap[selectedUser.approval_status]?.color"
                  size="small"
                  label
                >
                  {{ statusMap[selectedUser.approval_status]?.text }}
                </VChip>
              </VListItemTitle>
            </VListItem>
            <VListItem>
              <template #prepend>
                <VIcon
                  :color="selectedUser.is_active ? 'success' : 'error'"
                  :icon="selectedUser.is_active ? 'tabler-plug-connected' : 'tabler-plug-connected-x'"
                />
              </template>
              <VListItemTitle>{{ selectedUser.is_active ? 'Aktif' : 'Tidak Aktif' }}</VListItemTitle>
            </VListItem>
            <VListItem v-if="selectedUser.blok && selectedUser.kamar">
              <template #prepend>
                <VIcon icon="tabler-building-community" />
              </template>
              <VListItemTitle>Blok {{ selectedUser.blok }}, Kamar {{ formatKamarDisplay(selectedUser.kamar) }}</VListItemTitle>
            </VListItem>
          </VList>

          <!-- BAGIAN INFORMASI KUOTA DIPERBARUI -->
          <template v-if="selectedUser.role === 'USER' && quotaDetails">
            <VDivider class="my-4" />
            <div class="text-overline mb-2">
              Informasi Kuota
            </div>
            
            <!-- Tampilan jika pengguna unlimited -->
            <div v-if="quotaDetails.isUnlimited">
              <VAlert
                variant="tonal"
                color="success"
                icon="tabler-infinity"
                class="mb-4"
              >
                <h6 class="text-h6">
                  Langganan Unlimited Aktif
                </h6>
                <div>Nikmati koneksi internet tanpa batas kuota.</div>
              </VAlert>
              <VList
                  lines="one"
                  density="compact"
              >
                <VListItem
                  v-if="quotaDetails.expiryDate"
                  prepend-icon="tabler-calendar-due"
                >
                  <VListItemTitle>Masa Berlaku Hingga</VListItemTitle>
                  <VListItemSubtitle>{{ quotaDetails.expiryDate }}</VListItemSubtitle>
                </VListItem>
                <VListItem
                  v-if="quotaDetails.remainingDays !== null"
                  :prepend-icon="quotaDetails.status === 'EXPIRED' ? 'tabler-calendar-x' : 'tabler-hourglass-high'"
                >
                  <VListItemTitle>Sisa Masa Aktif</VListItemTitle>
                  <VListItemSubtitle>
                    <VChip
                      :color="quotaDetails.statusColor"
                      size="x-small"
                      label
                      class="px-2"
                    >
                      {{ quotaDetails.status === 'EXPIRED' ? 'Telah Berakhir' : `${quotaDetails.remainingDays} hari lagi` }}
                    </VChip>
                  </VListItemSubtitle>
                </VListItem>
              </VList>
            </div>

            <!-- Tampilan jika pengguna punya kuota (tapi tidak unlimited) -->
            <div v-else-if="quotaDetails.totalQuotaMB > 0">
              <VList
                lines="one"
                density="compact"
              >
                <VListItem prepend-icon="tabler-database">
                  <VListItemTitle>Total Kuota</VListItemTitle>
                  <VListItemSubtitle>{{ formatDataSize(quotaDetails.totalQuotaMB) }}</VListItemSubtitle>
                </VListItem>
                <VListItem prepend-icon="tabler-database-import">
                  <VListItemTitle>Kuota Terpakai</VListItemTitle>
                  <VListItemSubtitle>{{ formatDataSize(quotaDetails.usedQuotaMB) }}</VListItemSubtitle>
                </VListItem>
                <VListItem prepend-icon="tabler-database-export">
                  <VListItemTitle>Sisa Kuota</VListItemTitle>
                  <VListItemSubtitle class="font-weight-bold">
                    {{ formatDataSize(quotaDetails.remainingQuotaMB) }}
                  </VListItemSubtitle>
                </VListItem>

                <VDivider class="my-1" />

                <VListItem
                  v-if="quotaDetails.promoName"
                  prepend-icon="tabler-ticket"
                >
                  <VListItemTitle>Paket/Promo</VListItemTitle>
                  <VListItemSubtitle>{{ quotaDetails.promoName }}</VListItemSubtitle>
                </VListItem>
                <VListItem
                  v-if="quotaDetails.activationDate"
                  prepend-icon="tabler-calendar-play"
                >
                  <VListItemTitle>Tanggal Aktif</VListItemTitle>
                  <VListItemSubtitle>{{ quotaDetails.activationDate }}</VListItemSubtitle>
                </VListItem>
                <VListItem
                  v-if="quotaDetails.expiryDate"
                  prepend-icon="tabler-calendar-due"
                >
                  <VListItemTitle>Masa Berlaku Hingga</VListItemTitle>
                  <VListItemSubtitle>{{ quotaDetails.expiryDate }}</VListItemSubtitle>
                </VListItem>
                <VListItem
                  v-if="quotaDetails.remainingDays !== null"
                  :prepend-icon="quotaDetails.status === 'EXPIRED' ? 'tabler-calendar-x' : 'tabler-hourglass-high'"
                >
                  <VListItemTitle>Sisa Masa Aktif</VListItemTitle>
                  <VListItemSubtitle>
                    <VChip
                      :color="quotaDetails.statusColor"
                      size="x-small"
                      label
                      class="px-2"
                    >
                      {{ quotaDetails.status === 'EXPIRED' ? 'Telah Berakhir' : `${quotaDetails.remainingDays} hari lagi` }}
                    </VChip>
                  </VListItemSubtitle>
                </VListItem>
              </VList>
            </div>
            
            <!-- Tampilan jika pengguna belum punya paket sama sekali -->
            <div v-else>
              <VAlert
                variant="tonal"
                color="warning"
                icon="tabler-alert-circle"
                density="compact"
              >
                Pengguna belum memiliki paket kuota aktif.
              </VAlert>
            </div>
          </template>
          
          <VDivider class="my-4" />

          <!-- INFORMASI LOG -->
          <div class="text-overline mb-2">
            Informasi Pendaftaran
          </div>
          <VList
            lines="two"
            density="compact"
          >
            <VListItem>
              <template #prepend>
                <VIcon icon="tabler-calendar-plus" />
              </template>
              <VListItemSubtitle>Tanggal Pendaftaran</VListItemSubtitle>
              <VListItemTitle>{{ formatSimpleDateTime(selectedUser.created_at) }}</VListItemTitle>
            </VListItem>
            <VListItem v-if="selectedUser.approval_status === 'APPROVED'">
              <template #prepend>
                <VIcon icon="tabler-calendar-check" />
              </template>
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
          
          <VSpacer />
          <VBtn
            variant="tonal"
            color="secondary"
            @click="closeDialog"
            class="my-1"
          >
            Tutup
          </VBtn>
        </VCardActions>
      </VCard>
    </VDialog>

    <!-- Dialog Approve -->
    <VDialog
      v-model="dialog.approve"
      max-width="400"
      persistent
    >
      <VCard>
        <VCardTitle class="d-flex align-center">
          <span class="headline">Konfirmasi Persetujuan</span>
          <VSpacer />
          <VBtn
            icon="tabler-x"
            variant="text"
            @click="closeDialog"
          />
        </VCardTitle>
        <VDivider />
        <VCardText class="pt-4">
          <p>Setujui pengguna <strong>{{ selectedUser?.full_name }}</strong>?</p>
        </VCardText>
        <VCardActions>
          <VSpacer />
          <VBtn
            variant="tonal"
            color="secondary"
            @click="closeDialog"
          >
            Batal
          </VBtn>
          <VBtn
            color="success"
            @click="handleAction('approve')"
          >
            Setujui
          </VBtn>
        </VCardActions>
      </VCard>
    </VDialog>

    <!-- Dialog Reject -->
    <VDialog
      v-model="dialog.reject"
      max-width="450"
      persistent
    >
      <VCard>
        <VCardTitle class="d-flex align-center">
          <span class="headline">Konfirmasi Penolakan</span>
          <VSpacer />
          <VBtn
            icon="tabler-x"
            variant="text"
            @click="closeDialog"
          />
        </VCardTitle>
        <VDivider />
        <VCardText class="pt-4">
          <p>Anda yakin ingin menolak pendaftaran <strong>{{ selectedUser?.full_name }}</strong>?</p>
          <p class="text-caption text-medium-emphasis mt-2">
            Data pendaftaran akan dihapus secara permanen.
          </p>
        </VCardText>
        <VCardActions>
          <VSpacer />
          <VBtn
            variant="tonal"
            color="secondary"
            @click="closeDialog"
          >
            Batal
          </VBtn>
          <VBtn
            color="error"
            @click="handleAction('reject')"
          >
            Ya, Tolak & Hapus
          </VBtn>
        </VCardActions>
      </VCard>
    </VDialog>

    <!-- Dialog Delete -->
    <VDialog
      v-model="dialog.delete"
      max-width="450"
      persistent
    >
      <VCard>
        <VCardTitle class="d-flex align-center">
          <span class="headline">Konfirmasi Penghapusan</span>
          <VSpacer />
          <VBtn
            icon="tabler-x"
            variant="text"
            @click="closeDialog"
          />
        </VCardTitle>
        <VDivider />
        <VCardText class="pt-4">
          <p>Anda yakin ingin menghapus pengguna <strong>{{ selectedUser?.full_name }}</strong>?</p>
          <p class="text-caption text-medium-emphasis mt-2">
            Data yang dihapus tidak dapat dikembalikan.
          </p>
        </VCardText>
        <VCardActions>
          <VSpacer />
          <VBtn
            variant="tonal"
            color="secondary"
            @click="closeDialog"
          >
            Batal
          </VBtn>
          <VBtn
            color="error"
            @click="handleAction('delete')"
          >
            Hapus
          </VBtn>
        </VCardActions>
      </VCard>
    </VDialog>

    <!-- Dialog Edit/Create -->
    <VDialog
      v-model="dialog.edit"
      max-width="600"
      persistent
    >
      <VCard>
        <VForm
          ref="formRef"
          @submit.prevent="handleAction(editedUser.id ? 'update' : 'create')"
        >
          <VCardTitle class="d-flex align-center">
            <span class="headline">{{ formTitle }}</span>
            <VSpacer />
            <VBtn
              icon="tabler-x"
              variant="text"
              @click="closeDialog"
            />
          </VCardTitle>
          <VDivider />
          <VCardText
            v-if="editedUser"
            class="pt-4"
          >
            <VRow>
              <VCol cols="12">
                <AppTextField
                  v-model="editedUser.full_name"
                  label="Nama Lengkap"
                  density="compact"
                  :rules="[requiredRule]"
                />
              </VCol>
              <VCol cols="12">
                <AppTextField
                  v-model="editedUser.phone_number"
                  label="Nomor Telepon"
                  placeholder="Contoh: 081234567890"
                  density="compact"
                  @blur="normalizePhoneNumber"
                  :rules="[requiredRule]"
                />
              </VCol>

              <template v-if="editedUser.role === 'USER'">
                <VCol
                  cols="12"
                  sm="6"
                >
                  <AppSelect
                    v-model="editedUser.blok"
                    :items="availableBloks"
                    label="Blok"
                    clearable
                    density="compact"
                    :rules="[requiredRule]"
                  />
                </VCol>
                <VCol
                  cols="12"
                  sm="6"
                >
                  <AppSelect
                    v-model="editedUser.kamar"
                    :items="availableKamars"
                    label="Kamar"
                    clearable
                    density="compact"
                    :rules="[requiredRule]"
                    :item-title="item => formatKamarDisplay(item)"
                    :item-value="item => item"
                  />
                </VCol>
              </template>

              <VCol
                v-if="editedUser.role === 'ADMIN'"
                cols="12"
              >
                <VSwitch
                  v-model="isUserDataInputActive"
                  label="Lengkapi Data Alamat (Blok & Kamar)"
                  density="compact"
                />
              </VCol>

              <template v-if="editedUser.role === 'ADMIN' && isUserDataInputActive">
                <VCol
                  cols="12"
                  sm="6"
                >
                  <AppSelect
                    v-model="editedUser.blok"
                    :items="availableBloks"
                    label="Blok"
                    clearable
                    density="compact"
                    :rules="[requiredRule]"
                  />
                </VCol>
                <VCol
                  cols="12"
                  sm="6"
                >
                  <AppSelect
                    v-model="editedUser.kamar"
                    :items="availableKamars"
                    label="Kamar"
                    clearable
                    density="compact"
                    :rules="[requiredRule]"
                    :item-title="item => formatKamarDisplay(item)"
                    :item-value="item => item"
                  />
                </VCol>
              </template>

              <VCol
                v-if="authStore.isSuperAdmin"
                cols="12"
                sm="6"
              >
                <AppSelect
                  v-model="editedUser.role"
                  :items="availableRoles"
                  item-title="title"
                  item-value="value"
                  label="Peran"
                  density="compact"
                  :rules="[requiredRule]"
                  :disabled="editedUser.id === authStore.user?.id"
                />
              </VCol>

              <VCol
                v-if="editedUser.id"
                cols="12"
                sm="6"
                class="d-flex align-end pt-sm-5 mt-2"
              >
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
            <VBtn
              variant="tonal"
              color="secondary"
              @click="closeDialog"
            >
              Batal
            </VBtn>
            <div class="d-flex flex-column flex-sm-row ga-2">
              <VBtn
                type="submit"
                color="primary"
              >
                Simpan
              </VBtn>
            </div>
          </VCardActions>
        </VForm>
      </VCard>
    </VDialog>

    <!-- Dialog Konfirmasi Kustom -->
    <VDialog
      v-model="dialog.customConfirm"
      max-width="450"
      persistent
    >
      <VCard>
        <VCardTitle class="d-flex align-center">
          <span class="headline">Konfirmasi Aksi</span>
          <VSpacer />
          <VBtn
            icon="tabler-x"
            variant="text"
            @click="closeDialog"
          />
        </VCardTitle>
        <VDivider />
        <VCardText class="pt-4">
          <p>{{ confirmMessage }}</p>
        </VCardText>
        <VCardActions>
          <VSpacer />
          <VBtn
            variant="tonal"
            color="secondary"
            @click="closeDialog"
          >
            Batal
          </VBtn>
          <VBtn
            color="primary"
            @click="() => { 
              if (confirmActionCallback) { 
                confirmActionCallback(); 
              } 
              // Menutup dialog di-handle di dalam callback atau di finally block
            }"
          >
            Ya
          </VBtn>
        </VCardActions>
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

/* No data styling */
.text-center {
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
}

.v-dialog .v-dialog-close-btn {
    position: fixed !important;
}
</style>