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
  is_tamping: boolean
  tamping_type: string | null
  is_unlimited_user: boolean
  mikrotik_user_exists: boolean
  mikrotik_server_name: string | null
  mikrotik_profile_name: string | null
  mikrotik_password: string | null
  password_hash: string | null
  total_quota_purchased_mb: number
  total_quota_used_mb: number
  manual_debt_mb?: number
  quota_debt_auto_mb?: number
  quota_debt_manual_mb?: number
  quota_debt_total_mb?: number
  quota_expiry_date: string | null
  approved_at: string | null

  is_blocked?: boolean
  blocked_reason?: string | null
}

interface PackageItem {
  id: string
  name: string
  price: number
  data_quota_gb?: number | null
  duration_days?: number | null
  is_active?: boolean
}
interface MikrotikOptionsResponse {
  serverOptions: string[]
  profileOptions: string[]
  defaults: {
    server_user: string
    server_komandan: string
    server_admin: string
    server_support: string
    profile_user: string
    profile_komandan: string
    profile_default: string
    profile_active: string
    profile_fup: string
    profile_habis: string
    profile_unlimited: string
    profile_expired: string
    profile_inactive: string
  }
}
interface InactiveCleanupCandidate {
  id: string
  full_name: string
  phone_number: string
  role: 'USER' | 'KOMANDAN' | 'ADMIN' | 'SUPER_ADMIN'
  is_active: boolean
  last_activity_at: string
  days_inactive: number
}
type CleanupActionType = 'deactivate' | 'delete'
interface UserDetailPreviewContext {
  action: CleanupActionType
  days_inactive: number
  threshold_days: number
}
interface InactiveCleanupPreviewResponse {
  thresholds: {
    deactivate_days: number
    delete_days: number
  }
  summary: {
    deactivate_candidates: number
    delete_candidates: number
  }
  items: {
    deactivate_candidates: InactiveCleanupCandidate[]
    delete_candidates: InactiveCleanupCandidate[]
  }
}
type EditPayload = Partial<User> & {
  add_gb?: number
  add_days?: number
  is_unlimited_user?: boolean
  debt_package_id?: string | null
  debt_add_mb?: number
  debt_date?: string | null
  debt_note?: string | null
  debt_clear?: boolean
}
type Options = InstanceType<typeof VDataTableServer>['options']

const { $api } = useNuxtApp()
const { smAndDown } = useDisplay()
const authStore = useAuthStore()
const { add: showSnackbar } = useSnackbar()

const isHydrated = ref(false)
const isMobile = computed(() => (isHydrated.value ? smAndDown.value : false))

const users = ref<User[]>([])
const loading = ref(true)
const hasLoadedOnce = ref(false)
const showInitialSkeleton = computed(() => loading.value === true && hasLoadedOnce.value === false)
const showSilentRefreshing = computed(() => loading.value === true && hasLoadedOnce.value === true)
const totalUsers = ref(0)
const search = ref('')
const options = ref<Options>({ page: 1, itemsPerPage: 10, sortBy: [{ key: 'created_at', order: 'desc' }] })
const roleFilter = ref<string | null>(null)
const statusFilter = ref<string | null>(null)
const tampingFilter = ref<'all' | 'tamping' | 'non_tamping'>('all')
const dialogState = reactive({ view: false, add: false, edit: false, confirm: false })
const selectedUser = ref<User | null>(null)
const editedUser = ref<User | null>(null)
const confirmProps = reactive({ title: '', message: '', color: 'primary', action: async () => {} })
const availableBloks = ref<string[]>([])
const availableKamars = ref<string[]>([])
const isAlamatLoading = ref(false)
const mikrotikOptions = ref<MikrotikOptionsResponse>({
  serverOptions: [],
  profileOptions: [],
  defaults: {
    server_user: 'srv-user',
    server_komandan: 'srv-komandan',
    server_admin: 'srv-admin',
    server_support: 'srv-support',
    profile_user: 'user',
    profile_komandan: 'komandan',
    profile_default: 'default',
    profile_active: 'default',
    profile_fup: 'fup',
    profile_habis: 'habis',
    profile_unlimited: 'unlimited',
    profile_expired: 'expired',
    profile_inactive: 'inactive',
  },
})
const cleanupPreviewLoading = ref(false)
const cleanupPreview = ref<InactiveCleanupPreviewResponse | null>(null)
const selectedUserPreviewContext = ref<UserDetailPreviewContext | null>(null)
const previewActionLoading = ref<Record<string, boolean>>({})

const isCreateBillDialogOpen = ref(false)
const billLoading = ref(false)
const billSelectedUser = ref<User | null>(null)
const billSelectedPackage = ref<PackageItem | null>(null)
const packageList = ref<PackageItem[]>([])

// Perbaikan baris 67 (sesuai deskripsi error baris 56): Handle null/undefined secara eksplisit
function formatPhoneNumberDisplay(phone: string | null): string | null {
  if (phone === null || phone === undefined || phone === '') {
    return null // Mengembalikan null atau string kosong sesuai kebutuhan jika phone null/undefined/kosong
  }
  return phone.startsWith('+62') ? `0${phone.substring(3)}` : phone
}
const formatCreatedAt = (date: string) => new Date(date).toLocaleDateString('id-ID', { day: '2-digit', month: 'short', year: 'numeric' })
const formatCurrency = (value: number) => new Intl.NumberFormat('id-ID', { style: 'currency', currency: 'IDR', minimumFractionDigits: 0 }).format(value)
function formatQuotaGb(value?: number | null): string {
  if (value === null || value === undefined)
    return 'N/A'
  if (value === 0)
    return 'Unlimited'
  return `${value} GB`
}
const roleMap: Record<User['role'], { text: string, color: string }> = { USER: { text: 'User', color: 'info' }, KOMANDAN: { text: 'Komandan', color: 'success' }, ADMIN: { text: 'Admin', color: 'primary' }, SUPER_ADMIN: { text: 'Support', color: 'secondary' } }
const statusMap: Record<User['approval_status'], { text: string, color: string }> = { APPROVED: { text: 'Disetujui', color: 'success' }, PENDING_APPROVAL: { text: 'Menunggu', color: 'warning' }, REJECTED: { text: 'Ditolak', color: 'error' } }

const getRoleMeta = (role: User['role']) => roleMap[role]
const getStatusMeta = (status: User['approval_status']) => statusMap[status]

watch(loading, (val) => {
  if (val === false)
    hasLoadedOnce.value = true
}, { immediate: true })
const roleFilterOptions = computed(() => {
  const allFilters = [{ text: 'User', value: 'USER' }, { text: 'Komandan', value: 'KOMANDAN' }]
  if (authStore.isAdmin === true || authStore.isSuperAdmin === true)
    allFilters.push({ text: 'Admin', value: 'ADMIN' })

  if (authStore.isSuperAdmin === true)
    allFilters.push({ text: 'Support', value: 'SUPER_ADMIN' })

  return allFilters
})

const statusFilterOptions = [
  { text: 'Blocked', value: 'blocked' },
  { text: 'Aktif', value: 'aktif' },
  { text: 'Nonaktif (Akun)', value: 'inactive' },
  { text: 'Unlimited', value: 'unlimited' },
  { text: 'Debt', value: 'debt' },
  { text: 'Habis (Kuota Habis)', value: 'habis' },
  { text: 'FUP', value: 'fup' },
  { text: 'Expired', value: 'expired' },
  { text: 'Inactive (Kuota / Tanpa Kuota)', value: 'inactive_quota' },
]

const roleFilterDropdownItems = computed(() => ([
  { title: 'Semua', value: null },
  ...roleFilterOptions.value.map(r => ({ title: r.text, value: r.value })),
]))

const statusFilterDropdownItems = computed(() => ([
  { title: 'Semua', value: null },
  ...statusFilterOptions.map(s => ({ title: s.text, value: s.value })),
]))

const tampingFilterDropdownItems = [
  { title: 'Semua', value: 'all' },
  { title: 'Tamping', value: 'tamping' },
  { title: 'Non-Tamping', value: 'non_tamping' },
]

const headers = computed(() => {
  const base = [
    { title: 'PENGGUNA', key: 'full_name', sortable: true, minWidth: '250px' },
    { title: 'STATUS', key: 'approval_status', sortable: true },
    { title: 'PERAN', key: 'role', sortable: true },
    { title: 'KONEKSI', key: 'is_active', sortable: true, align: 'center' },
    { title: 'TGL DAFTAR', key: 'created_at', sortable: true },
    { title: 'AKSI', key: 'actions', sortable: false, align: 'center', width: '150px' },
  ]
  // Perbaikan baris 81: Perbandingan eksplisit untuk isMobile.value dan pengecekan h.key
  // Menghapus h !== null karena h selalu objek dan truthy.
  return isMobile.value === true
    ? base.filter(h => h.key !== null && h.key !== undefined && ['full_name', 'approval_status', 'actions'].includes(String(h.key)))
    : base
})

useHead({ title: 'Manajemen Pengguna' })
onMounted(() => {
  isHydrated.value = true
  fetchUsers()
  fetchAlamatOptions()
  fetchMikrotikOptions()
  fetchInactiveCleanupPreview()
})
watch([() => options.value, roleFilter, statusFilter, tampingFilter], () => {
  if (options.value !== null && options.value !== undefined) // Perbaikan baris 91
    options.value.page = 1
  fetchUsers()
}, { deep: true })
let searchTimeout: ReturnType<typeof setTimeout>
watch(search, () => {
  clearTimeout(searchTimeout)
  searchTimeout = setTimeout(() => {
    if (options.value !== null && options.value !== undefined) // Perbaikan baris 99
      options.value.page = 1
    fetchUsers()
  }, 500)
})

async function ensurePackagesLoaded() {
  if (packageList.value.length > 0)
    return
  try {
    const resp = await $api<{ items: PackageItem[], totalItems: number }>('/admin/packages', {
      params: { page: 1, itemsPerPage: 100 },
    })
    if (resp && Array.isArray(resp.items))
      packageList.value = resp.items.filter(p => p && (p.is_active ?? true))
  }
  catch {
    packageList.value = []
  }
}

async function openCreateBillDialogForUser(user: User) {
  billSelectedUser.value = user
  billSelectedPackage.value = null
  isCreateBillDialogOpen.value = true
  await ensurePackagesLoaded()
}

async function createQrisBillForSelectedUser() {
  if (!billSelectedUser.value || !billSelectedPackage.value) {
    showSnackbar({ type: 'warning', title: 'Lengkapi Data', text: 'Pilih paket terlebih dahulu.' })
    return
  }

  billLoading.value = true
  try {
    const payload = {
      user_id: billSelectedUser.value.id,
      package_id: billSelectedPackage.value.id,
    }
    const resp = await $api<{ message: string, order_id: string, status: string, qr_code_url?: string | null, whatsapp_sent?: boolean }>('/admin/transactions/qris', {
      method: 'POST',
      body: payload,
    })

    const sent = resp.whatsapp_sent !== false
    showSnackbar({
      type: sent ? 'success' : 'warning',
      title: sent ? 'Berhasil' : 'Perlu Perhatian',
      text: `${resp.message} (${resp.order_id})`,
    })
    isCreateBillDialogOpen.value = false
    await fetchUsers()
  }
  catch (error: any) {
    const message = (typeof error?.data?.message === 'string' && error.data.message !== '')
      ? error.data.message
      : 'Gagal membuat tagihan QRIS.'
    const midtransMsg = (typeof error?.data?.midtrans_status_message === 'string' && error.data.midtrans_status_message !== '')
      ? error.data.midtrans_status_message
      : ''

    showSnackbar({
      type: 'error',
      title: 'Gagal',
      text: midtransMsg ? `${message} (${midtransMsg})` : message,
    })
  }
  finally {
    billLoading.value = false
  }
}

async function fetchUsers() {
  loading.value = true
  try {
    const params = new URLSearchParams()
    if (options.value !== null && options.value !== undefined) { // Perbaikan baris 109
      params.append('page', String(options.value.page))
      params.append('itemsPerPage', String(options.value.itemsPerPage))
      if (Array.isArray(options.value.sortBy) && options.value.sortBy.length > 0) { // Perbaikan baris 112
        const [sortItem] = options.value.sortBy
        if (sortItem?.key) {
          params.append('sortBy', sortItem.key)
          params.append('sortOrder', sortItem.order ?? 'asc')
        }
      }
    }
    if (search.value !== null && search.value !== '') // Perbaikan baris 119
      params.append('search', search.value)

    const allowedRoles = new Set(roleFilterOptions.value.map(r => r.value))
    if (roleFilter.value !== null && roleFilter.value !== '' && allowedRoles.has(roleFilter.value))
      params.append('role', roleFilter.value)

    const allowedStatuses = new Set(statusFilterOptions.map(s => s.value))
    if (statusFilter.value !== null && statusFilter.value !== '' && allowedStatuses.has(String(statusFilter.value)))
      params.append('status', String(statusFilter.value))

    if (tampingFilter.value === 'tamping')
      params.append('tamping', '1')
    else if (tampingFilter.value === 'non_tamping')
      params.append('tamping', '0')

    const response = await $api<{ items: User[], totalItems: number }>(`/admin/users?${params.toString()}`)
    users.value = response.items
    totalUsers.value = response.totalItems
  }
  catch (error: any) {
    const errorMessage = (typeof error.data?.message === 'string' && error.data.message !== '') ? error.data.message : 'Terjadi kesalahan pada server.' // Perbaikan baris 142
    showSnackbar({ type: 'error', title: 'Gagal Mengambil Data', text: errorMessage })
  }
  finally {
    loading.value = false
  }
}

async function handleMobileUsersPageUpdate(page: number) {
  if (options.value != null)
    options.value.page = page
  await fetchUsers()
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
    const errorMessage = (typeof error.data?.message === 'string' && error.data.message !== '') ? error.data.message : 'Terjadi error saat memuat pilihan alamat.' // Perbaikan baris 162
    showSnackbar({ type: 'error', title: 'Gagal Memuat Alamat', text: errorMessage })
  }
  finally {
    isAlamatLoading.value = false
  }
}
async function fetchMikrotikOptions() {
  try {
    const response = await $api<MikrotikOptionsResponse>('/admin/form-options/mikrotik')
    if (response?.serverOptions)
      mikrotikOptions.value.serverOptions = response.serverOptions
    if (response?.profileOptions)
      mikrotikOptions.value.profileOptions = response.profileOptions
    if (response?.defaults)
      mikrotikOptions.value.defaults = { ...mikrotikOptions.value.defaults, ...response.defaults }
  }
  catch (error: any) {
    const errorMessage = (typeof error.data?.message === 'string' && error.data.message !== '')
      ? error.data.message
      : 'Gagal memuat opsi Mikrotik.'
    showSnackbar({ type: 'warning', title: 'Mikrotik', text: errorMessage })
  }
}
async function fetchInactiveCleanupPreview() {
  cleanupPreviewLoading.value = true
  try {
    cleanupPreview.value = await $api<InactiveCleanupPreviewResponse>('/admin/users/inactive-cleanup-preview?limit=10')
  }
  catch (error: any) {
    const errorMessage = (typeof error.data?.message === 'string' && error.data.message !== '')
      ? error.data.message
      : 'Gagal memuat preview cleanup pengguna tidak aktif.'
    showSnackbar({ type: 'warning', title: 'Preview Cleanup', text: errorMessage })
  }
  finally {
    cleanupPreviewLoading.value = false
  }
}
function buildPreviewContext(action: CleanupActionType, daysInactive: number): UserDetailPreviewContext {
  const thresholdDays = action === 'delete'
    ? (cleanupPreview.value?.thresholds?.delete_days ?? 0)
    : (cleanupPreview.value?.thresholds?.deactivate_days ?? 0)

  return {
    action,
    days_inactive: daysInactive,
    threshold_days: thresholdDays,
  }
}
function getPreviewActionKey(candidateId: string, action: CleanupActionType): string {
  return `${action}:${candidateId}`
}
function isPreviewActionLoading(candidateId: string, action: CleanupActionType): boolean {
  return previewActionLoading.value[getPreviewActionKey(candidateId, action)] === true
}
function setPreviewActionLoading(candidateId: string, action: CleanupActionType, isLoading: boolean) {
  const key = getPreviewActionKey(candidateId, action)
  previewActionLoading.value = {
    ...previewActionLoading.value,
    [key]: isLoading,
  }
}
function canManageCandidate(role: User['role']): boolean {
  if (authStore.isSuperAdmin === true)
    return true

  return authStore.isAdmin === true && role !== 'ADMIN' && role !== 'SUPER_ADMIN'
}
async function resolvePreviewCandidateUser(candidate: InactiveCleanupCandidate): Promise<User | null> {
  const localUser = users.value.find(user => user.id === candidate.id)
  if (localUser)
    return localUser

  const params = new URLSearchParams()
  params.append('search', candidate.phone_number)
  params.append('itemsPerPage', '20')
  params.append('page', '1')
  params.append('role', candidate.role)

  const response = await $api<{ items: User[] }>(`/admin/users?${params.toString()}`)
  return response.items.find(user => user.id === candidate.id)
    || response.items.find(user => user.phone_number === candidate.phone_number)
    || null
}
function openLayeredCleanupConfirm(user: User, action: CleanupActionType, daysInactive: number) {
  const actionLabel = action === 'delete' ? 'Delete' : 'Deactivate'
  const color = action === 'delete' ? 'error' : 'warning'

  openConfirmDialog({
    title: `Konfirmasi ${actionLabel}`,
    message: `Proses cleanup untuk <strong>${user.full_name}</strong> akan dijalankan (tidak aktif ${daysInactive} hari). Lanjut ke verifikasi akhir?`,
    color,
    action: async () => {
      dialogState.confirm = false
      await Promise.resolve()

      openConfirmDialog({
        title: 'Konfirmasi Terakhir',
        message: `Aksi ini akan memproses nonaktifkan/hapus sesuai kebijakan sistem untuk <strong>${user.full_name}</strong>. Lanjutkan?`,
        color,
        action: async () => await performAction(`/admin/users/${user.id}`, 'DELETE', 'Proses cleanup pengguna berhasil dijalankan.'),
      })
    },
  })
}
async function openPreviewCandidate(candidate: InactiveCleanupCandidate, action: CleanupActionType) {
  const previewContext = buildPreviewContext(action, candidate.days_inactive)

  try {
    const matchedUser = await resolvePreviewCandidateUser(candidate)

    if (matchedUser) {
      openViewDialog(matchedUser, previewContext)
      return
    }

    showSnackbar({ type: 'warning', title: 'Data Tidak Ditemukan', text: 'User tidak ada di halaman saat ini. Coba refresh data pengguna.' })
  }
  catch (error: any) {
    const errorMessage = (typeof error.data?.message === 'string' && error.data.message !== '')
      ? error.data.message
      : 'Gagal membuka detail user dari preview cleanup.'
    showSnackbar({ type: 'error', title: 'Terjadi Kesalahan', text: errorMessage })
  }
}

async function handlePreviewEditCandidate(candidate: InactiveCleanupCandidate) {
  try {
    const matchedUser = await resolvePreviewCandidateUser(candidate)
    if (!matchedUser) {
      showSnackbar({ type: 'warning', title: 'Data Tidak Ditemukan', text: 'User tidak ditemukan. Coba refresh data pengguna.' })
      return
    }
    openEditDialog(matchedUser)
  }
  catch (error: any) {
    const errorMessage = (typeof error.data?.message === 'string' && error.data.message !== '')
      ? error.data.message
      : 'Gagal membuka edit user dari preview cleanup.'
    showSnackbar({ type: 'error', title: 'Terjadi Kesalahan', text: errorMessage })
  }
}
async function handlePreviewCleanupAction(candidate: InactiveCleanupCandidate, action: CleanupActionType) {
  if (isPreviewActionLoading(candidate.id, action))
    return

  if (!canManageCandidate(candidate.role)) {
    showSnackbar({ type: 'warning', title: 'Akses Ditolak', text: 'Anda tidak memiliki izin untuk memproses kandidat ini.' })
    return
  }

  try {
    setPreviewActionLoading(candidate.id, action, true)
    const matchedUser = await resolvePreviewCandidateUser(candidate)
    if (!matchedUser) {
      showSnackbar({ type: 'warning', title: 'Data Tidak Ditemukan', text: 'User tidak ditemukan. Coba refresh data pengguna.' })
      return
    }

    openLayeredCleanupConfirm(matchedUser, action, candidate.days_inactive)
  }
  catch (error: any) {
    const errorMessage = (typeof error.data?.message === 'string' && error.data.message !== '')
      ? error.data.message
      : 'Gagal memproses aksi cleanup dari preview.'
    showSnackbar({ type: 'error', title: 'Terjadi Kesalahan', text: errorMessage })
  }
  finally {
    setPreviewActionLoading(candidate.id, action, false)
  }
}
function openAddUserDialog() {
  dialogState.add = true
}
function openEditDialog(user: User) {
  editedUser.value = { ...user }
  dialogState.edit = true
}
function openViewDialog(user: User, previewContext: UserDetailPreviewContext | null = null) {
  selectedUserPreviewContext.value = previewContext
  selectedUser.value = user
  dialogState.view = true
}
function openConfirmDialog(props: { title: string, message: string, color?: string, action: () => Promise<void> }) {
  confirmProps.title = props.title
  confirmProps.message = props.message
  confirmProps.color = props.color ?? 'primary' // Perbaikan baris 165: Menggunakan nullish coalescing operator
  confirmProps.action = props.action
  dialogState.confirm = true
}
function closeAllDialogs() {
  dialogState.view = false
  dialogState.add = false
  dialogState.edit = false
  dialogState.confirm = false
  selectedUserPreviewContext.value = null
}
async function handleSaveUser(payload: EditPayload) {
  const isUpdate = payload.id !== undefined && payload.id !== null && payload.id !== '' // Perbaikan baris 173
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
async function performAction(endpoint: string, method: 'PATCH' | 'POST' | 'DELETE' | 'PUT', successMessage: string, options: { body?: object } = {}, updatedItemId?: string) {
  loading.value = true
  try {
    const response = await $api<any>(endpoint, { method, ...options })
    showSnackbar({ type: 'success', title: 'Berhasil', text: successMessage })
    closeAllDialogs()
    await fetchUsers()
    await fetchInactiveCleanupPreview()
    // Perbaikan baris 226: Menambahkan perbandingan eksplisit dan pengecekan untuk response
    if (dialogState.view === true && selectedUser.value !== null && selectedUser.value.id === updatedItemId && response !== null && response.user !== undefined) {
      selectedUser.value = { ...selectedUser.value, ...response.user }
    }
  }
  catch (error: any) {
    const errorMessage = (typeof error.data?.message === 'string' && error.data.message !== '') ? error.data.message : 'Operasi gagal. Silakan coba lagi.' // Perbaikan baris 230
    showSnackbar({ type: 'error', title: 'Terjadi Kesalahan', text: errorMessage })
  }
  finally {
    loading.value = false
  }
}
</script>

<template>
  <div>
    <VCard class="rounded-lg mb-6">
      <VCardItem>
        <VCardTitle class="d-flex align-center flex-wrap gap-2">
          <VIcon icon="tabler-user-x" class="me-2" />
          Preview Cleanup User Tidak Aktif
        </VCardTitle>
        <template #append>
          <VBtn
            size="small"
            variant="tonal"
            color="info"
            :loading="cleanupPreviewLoading"
            @click="fetchInactiveCleanupPreview"
          >
            Refresh
          </VBtn>
        </template>
      </VCardItem>
      <VCardText>
        <div class="d-flex flex-wrap gap-2 mb-3">
          <VChip color="warning" size="small" label>
            Deactivate ≥ {{ cleanupPreview?.thresholds?.deactivate_days ?? '-' }} hari
          </VChip>
          <VChip color="error" size="small" label>
            Delete ≥ {{ cleanupPreview?.thresholds?.delete_days ?? '-' }} hari
          </VChip>
          <VChip color="warning" variant="tonal" size="small" label>
            Kandidat Deactivate: {{ cleanupPreview?.summary?.deactivate_candidates ?? 0 }}
          </VChip>
          <VChip color="error" variant="tonal" size="small" label>
            Kandidat Delete: {{ cleanupPreview?.summary?.delete_candidates ?? 0 }}
          </VChip>
        </div>

        <VRow>
          <VCol cols="12" md="6">
            <div class="text-subtitle-2 mb-2">Top Kandidat Deactivate</div>
            <VList density="compact" border rounded>
              <VListItem
                v-for="item in (cleanupPreview?.items?.deactivate_candidates ?? [])"
                :key="`deact-${item.id}`"
                :title="item.full_name"
                :subtitle="`${formatPhoneNumberDisplay(item.phone_number) ?? '-'} • ${item.days_inactive} hari`"
                link
                @click="openPreviewCandidate(item, 'deactivate')"
              >
                <template #append>
                  <div class="d-flex align-center gap-1">
                    <VChip size="x-small" color="warning" label>{{ item.role }}</VChip>
                    <VBtn
                      v-if="canManageCandidate(item.role)"
                      icon
                      size="x-small"
                      variant="text"
                      color="primary"
                      @click.stop="handlePreviewEditCandidate(item)"
                    >
                      <VIcon icon="tabler-edit" size="16" />
                      <VTooltip activator="parent">Edit User</VTooltip>
                    </VBtn>
                    <VBtn
                      v-if="canManageCandidate(item.role)"
                      icon
                      size="x-small"
                      variant="text"
                      color="warning"
                      :loading="isPreviewActionLoading(item.id, 'deactivate')"
                      :disabled="isPreviewActionLoading(item.id, 'deactivate')"
                      @click.stop="handlePreviewCleanupAction(item, 'deactivate')"
                    >
                      <VIcon icon="tabler-user-off" size="16" />
                      <VTooltip activator="parent">Proses Deactivate</VTooltip>
                    </VBtn>
                  </div>
                </template>
              </VListItem>
              <VListItem v-if="(cleanupPreview?.items?.deactivate_candidates?.length ?? 0) === 0" title="Tidak ada kandidat" />
            </VList>
          </VCol>

          <VCol cols="12" md="6">
            <div class="text-subtitle-2 mb-2">Top Kandidat Delete</div>
            <VList density="compact" border rounded>
              <VListItem
                v-for="item in (cleanupPreview?.items?.delete_candidates ?? [])"
                :key="`del-${item.id}`"
                :title="item.full_name"
                :subtitle="`${formatPhoneNumberDisplay(item.phone_number) ?? '-'} • ${item.days_inactive} hari`"
                link
                @click="openPreviewCandidate(item, 'delete')"
              >
                <template #append>
                  <div class="d-flex align-center gap-1">
                    <VChip size="x-small" color="error" label>{{ item.role }}</VChip>
                    <VBtn
                      v-if="canManageCandidate(item.role)"
                      icon
                      size="x-small"
                      variant="text"
                      color="primary"
                      @click.stop="handlePreviewEditCandidate(item)"
                    >
                      <VIcon icon="tabler-edit" size="16" />
                      <VTooltip activator="parent">Edit User</VTooltip>
                    </VBtn>
                    <VBtn
                      v-if="canManageCandidate(item.role)"
                      icon
                      size="x-small"
                      variant="text"
                      color="error"
                      :loading="isPreviewActionLoading(item.id, 'delete')"
                      :disabled="isPreviewActionLoading(item.id, 'delete')"
                      @click.stop="handlePreviewCleanupAction(item, 'delete')"
                    >
                      <VIcon icon="tabler-trash" size="16" />
                      <VTooltip activator="parent">Proses Delete</VTooltip>
                    </VBtn>
                  </div>
                </template>
              </VListItem>
              <VListItem v-if="(cleanupPreview?.items?.delete_candidates?.length ?? 0) === 0" title="Tidak ada kandidat" />
            </VList>
          </VCol>
        </VRow>
      </VCardText>
    </VCard>

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
          <div class="d-flex align-center gap-4" :style="{ width: isMobile ? '100%' : 'auto' }">
            <div :style="{ width: isMobile ? 'calc(100% - 130px)' : '300px' }">
              <AppTextField v-model="search" placeholder="Cari (Nama/No. HP)..." prepend-inner-icon="tabler-search" clearable density="comfortable" hide-details />
            </div>
            <VBtn prepend-icon="tabler-plus" height="56" style="min-width: 130px" @click="openAddUserDialog()">
              Tambah Akun
            </VBtn>
          </div>
        </template>
      </VCardItem>
      <VDivider v-if="!isMobile" />
      <VCardText v-if="isHydrated && !isMobile">
        <VRow align="center" class="mt-1" dense>
          <VCol cols="12" md="4">
            <AppSelect
              v-model="roleFilter"
              :items="roleFilterDropdownItems"
              item-title="title"
              item-value="value"
              label="Peran"
              density="comfortable"
              clearable
              hide-details
            />
          </VCol>
          <VCol cols="12" md="4">
            <AppSelect
              v-model="statusFilter"
              :items="statusFilterDropdownItems"
              item-title="title"
              item-value="value"
              label="Status"
              density="comfortable"
              clearable
              hide-details
            />
          </VCol>
          <VCol cols="12" md="4">
            <AppSelect
              v-model="tampingFilter"
              :items="tampingFilterDropdownItems"
              item-title="title"
              item-value="value"
              label="Tamping"
              density="comfortable"
              hide-details
            />
          </VCol>
        </VRow>
      </VCardText>
    </VCard>

    <VCard class="rounded-lg">
      <VProgressLinear v-if="showSilentRefreshing" indeterminate color="primary" height="2" />

      <VCardText v-if="!isMobile" class="py-4 px-6">
        <DataTableToolbar
          v-model:items-per-page="options.itemsPerPage"
          :show-search="false"
          @update:items-per-page="() => (options.page = 1)"
        />
      </VCardText>

      <VDataTableServer v-if="!isMobile" v-model:options="options" :headers="headers" :items="users" :items-length="totalUsers" :loading="showInitialSkeleton" item-value="id" class="text-no-wrap" hide-default-footer>
        <template #item.full_name="{ item }">
          <div class="d-flex align-center py-2">
            <VAvatar size="38" class="me-3" :color="getRoleMeta(item.role as User['role']).color" variant="tonal">
              <span class="text-h6">{{ item.full_name.substring(0, 1).toUpperCase() }}</span>
            </VAvatar>
            <div class="d-flex flex-column">
              <span class="font-weight-semibold text-high-emphasis">{{ item.full_name }}</span>
              <small class="text-medium-emphasis">{{ formatPhoneNumberDisplay(item.phone_number) }}</small>
              <div v-if="item.is_tamping" class="mt-1">
                <VChip color="primary" size="x-small" label prepend-icon="tabler-building-bank">
                  <span>
                    Tamping
                    <span v-if="item.tamping_type"> • {{ item.tamping_type }}</span>
                  </span>
                </VChip>
              </div>
              <div v-if="(item.quota_debt_total_mb ?? 0) > 0" class="mt-1">
                <VChip color="warning" size="x-small" label prepend-icon="tabler-alert-triangle">
                  Hutang
                </VChip>
              </div>
            </div>
            <VTooltip v-if="item.is_unlimited_user === true" location="top">
              <template #activator="{ props: tooltipProps }">
                <VIcon v-bind="tooltipProps" icon="tabler-infinity" color="success" size="small" class="ms-2" />
              </template>
              <span>Akses Unlimited Aktif</span>
            </VTooltip>
          </div>
        </template>
        <template #item.approval_status="{ item }">
          <VChip :color="getStatusMeta(item.approval_status as User['approval_status']).color" size="small" label>
            {{ getStatusMeta(item.approval_status as User['approval_status']).text }}
          </VChip>
        </template>
        <template #item.role="{ item }">
          <VChip :color="getRoleMeta(item.role as User['role']).color" size="small" label>
            {{ getRoleMeta(item.role as User['role']).text }}
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
              <VBtn icon variant="text" color="primary" size="small" @click="openCreateBillDialogForUser(item)">
                <VIcon icon="tabler-qrcode" /><VTooltip activator="parent">
                  Buat Tagihan QRIS
                </VTooltip>
              </VBtn>
              <VBtn v-if="(authStore.isSuperAdmin === true || authStore.isAdmin === true)" icon variant="text" color="primary" size="small" @click="openEditDialog(item)">
                <VIcon icon="tabler-pencil" /><VTooltip activator="parent">
                  Edit
                </VTooltip>
              </VBtn>
              <VBtn v-if="item.id !== authStore.currentUser?.id && (authStore.isSuperAdmin === true || (authStore.isAdmin === true && item.role !== 'ADMIN' && item.role !== 'SUPER_ADMIN'))" icon variant="text" color="error" size="small" @click="handleDelete(item)">
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

      <TablePagination
        v-if="!isMobile && totalUsers > 0"
        :page="options.page"
        :items-per-page="options.itemsPerPage"
        :total-items="totalUsers"
        @update:page="handleMobileUsersPageUpdate"
      />
      <div v-else class="pa-4">
        <div v-if="showInitialSkeleton" class="pa-5">
          <VCard v-for="i in 3" :key="i" class="mb-3">
            <VSkeletonLoader type="list-item-two-line" />
          </VCard>
        </div>
        <div v-else-if="users.length === 0 && loading === false" class="py-8 text-center text-medium-emphasis">
          <VIcon icon="tabler-database-off" size="32" class="mb-2" /><p>Tidak ada data pengguna.</p>
        </div>
        <VCard v-for="user in users" v-else :key="user.id" class="mb-3">
          <VCardText>
            <div class="d-flex justify-space-between">
              <div class="d-flex align-center py-2">
                <VAvatar size="32" class="me-3" :color="getRoleMeta(user.role).color" variant="tonal">
                  <span class="text-sm font-weight-medium">{{ user.full_name.substring(0, 2).toUpperCase() }}</span>
                </VAvatar>
                <div class="d-flex flex-column">
                  <span class="font-weight-medium text-high-emphasis">{{ user.full_name }}</span>
                  <small class="text-medium-emphasis">{{ formatPhoneNumberDisplay(user.phone_number) }}</small>
                  <div v-if="user.is_tamping" class="mt-1">
                    <VChip color="primary" size="x-small" label prepend-icon="tabler-building-bank">
                      <span>
                        Tamping
                        <span v-if="user.tamping_type"> • {{ user.tamping_type }}</span>
                      </span>
                    </VChip>
                  </div>
                </div>
              </div>
              <VChip :color="getStatusMeta(user.approval_status).color" size="small" label>
                {{ getStatusMeta(user.approval_status).text }}
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
                <VBtn icon variant="text" color="primary" size="small" @click="openCreateBillDialogForUser(user)">
                  <VIcon icon="tabler-qrcode" /><VTooltip activator="parent">
                    Buat Tagihan QRIS
                  </VTooltip>
                </VBtn>
                <VBtn v-if="(authStore.isSuperAdmin === true || authStore.isAdmin === true)" icon variant="text" color="primary" size="small" @click="openEditDialog(user)">
                  <VIcon icon="tabler-pencil" /><VTooltip activator="parent">
                    Edit
                  </VTooltip>
                </VBtn>
                <VBtn v-if="user.id !== authStore.currentUser?.id && (authStore.isSuperAdmin === true || (authStore.isAdmin === true && user.role !== 'ADMIN' && user.role !== 'SUPER_ADMIN'))" icon variant="text" color="error" size="small" @click="handleDelete(user)">
                  <VIcon icon="tabler-trash" /><VTooltip activator="parent">
                    Hapus
                  </VTooltip>
                </VBtn>
              </template>
            </div>
          </VCardActions>
        </VCard>

        <TablePagination
          v-if="totalUsers > 0"
          :page="options.page"
          :items-per-page="options.itemsPerPage"
          :total-items="totalUsers"
          @update:page="handleMobileUsersPageUpdate"
        />
      </div>
    </VCard>

    <VDialog v-if="isHydrated" v-model="isCreateBillDialogOpen" max-width="640px">
      <VCard>
        <VCardTitle class="pa-4">
          <div class="dialog-titlebar">
            <div class="dialog-titlebar__title">
              <span class="font-weight-medium">Buat Tagihan QRIS</span>
            </div>
            <div class="dialog-titlebar__actions">
              <VBtn icon variant="text" @click="isCreateBillDialogOpen = false">
                <VIcon icon="tabler-x" />
              </VBtn>
            </div>
          </div>
        </VCardTitle>
        <VDivider />

        <VCardText class="pa-4">
          <VTextField
            :model-value="billSelectedUser?.full_name || ''"
            label="Pengguna"
            variant="outlined"
            density="comfortable"
            readonly
          />
          <VAutocomplete
            v-model="billSelectedPackage"
            :items="packageList"
            item-title="name"
            return-object
            label="Paket"
            variant="outlined"
            density="comfortable"
            clearable
            class="mt-4"
            :disabled="billLoading"
          >
            <template #item="{ props, item }">
              <VListItem v-bind="props">
                <VListItemTitle>{{ item.raw.name }}</VListItemTitle>
                <VListItemSubtitle class="text-medium-emphasis">
                  Kuota: <span class="font-weight-medium">{{ formatQuotaGb(item.raw.data_quota_gb) }}</span>
                  <span class="mx-1">•</span>
                  Harga: <span class="font-weight-medium">{{ formatCurrency(item.raw.price) }}</span>
                </VListItemSubtitle>
              </VListItem>
            </template>

            <template #selection="{ item }">
              <span class="text-no-wrap">
                {{ item.raw.name }} — {{ formatQuotaGb(item.raw.data_quota_gb) }} — {{ formatCurrency(item.raw.price) }}
              </span>
            </template>
          </VAutocomplete>

          <div v-if="billSelectedPackage" class="mt-3 text-medium-emphasis">
            <div>Kuota: {{ formatQuotaGb(billSelectedPackage.data_quota_gb) }}</div>
            <div>Harga: {{ formatCurrency(billSelectedPackage.price) }}</div>
          </div>
        </VCardText>

        <VCardActions class="pa-4">
          <VSpacer />
          <VBtn variant="text" :disabled="billLoading" @click="isCreateBillDialogOpen = false">
            Batal
          </VBtn>
          <VBtn color="primary" :loading="billLoading" @click="createQrisBillForSelectedUser">
            Kirim QRIS
          </VBtn>
        </VCardActions>
      </VCard>
    </VDialog>

    <UserDetailDialog v-model="dialogState.view" :user="selectedUser" :preview-context="selectedUserPreviewContext" />
    <UserAddDialog v-model="dialogState.add" :loading="loading" :available-bloks="availableBloks" :available-kamars="availableKamars" :is-alamat-loading="isAlamatLoading" @save="handleSaveUser" />
    <UserEditDialog v-if="dialogState.edit === true && editedUser !== null" v-model="dialogState.edit" :user="editedUser" :loading="loading" :available-bloks="availableBloks" :available-kamars="availableKamars" :is-alamat-loading="isAlamatLoading" :mikrotik-options="mikrotikOptions" @save="handleSaveUser" />
    <UserActionConfirmDialog v-model="dialogState.confirm" :title="confirmProps.title" :message="confirmProps.message" :color="confirmProps.color" :loading="loading" @confirm="confirmProps.action" />
  </div>
</template>
