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
import { useSettingsStore } from '@/store/settings'

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

interface PublicUpdateSubmission {
  id: string
  full_name: string
  role: 'KOMANDAN' | 'TAMPING'
  blok: string | null
  kamar: string | null
  tamping_type?: string | null
  phone_number: string | null
  approval_status: 'PENDING' | 'APPROVED' | 'REJECTED'
  created_at: string
  rejection_reason?: string | null
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
const settingsStore = useSettingsStore()
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
const updateSubmissionLoading = ref(false)
const updateSubmissionItems = ref<PublicUpdateSubmission[]>([])
const updateSubmissionTotal = ref(0)

const isCreateBillDialogOpen = ref(false)
const billLoading = ref(false)
const billSelectedUser = ref<User | null>(null)
const billSelectedPackage = ref<PackageItem | null>(null)
const packageList = ref<PackageItem[]>([])

type BillPaymentMethod = 'qris' | 'va' | 'gopay' | 'shopeepay'
const billPaymentMethod = ref<BillPaymentMethod>('qris')
const billVaBank = ref<'bni' | 'bca' | 'bri' | 'mandiri' | 'permata' | 'cimb'>('bni')

function parseCsvList(value: unknown): string[] {
  const raw = (value ?? '').toString().trim()
  if (raw === '')
    return []
  const parts = raw.split(',').map(p => p.trim().toLowerCase()).filter(Boolean)
  return Array.from(new Set(parts))
}

const enabledCoreApiMethods = computed(() => {
  const parsed = parseCsvList(settingsStore.getSetting('CORE_API_ENABLED_PAYMENT_METHODS', 'qris,gopay,va'))
  const allowed = new Set(['qris', 'gopay', 'va', 'shopeepay'])
  const normalized = parsed.filter(x => allowed.has(x))
  return normalized.length > 0 ? normalized : ['qris', 'gopay', 'va']
})

const enabledCoreApiVaBanks = computed(() => {
  const parsed = parseCsvList(settingsStore.getSetting('CORE_API_ENABLED_VA_BANKS', 'bca,bni,bri,mandiri,permata,cimb'))
  const allowed = new Set(['bca', 'bni', 'bri', 'mandiri', 'permata', 'cimb'])
  const normalized = parsed.filter(x => allowed.has(x))
  return normalized.length > 0 ? normalized : ['bca', 'bni', 'bri', 'mandiri', 'permata', 'cimb']
})

const billPaymentMethodOptions = computed(() => {
  const labels: Record<string, string> = {
    qris: 'QRIS',
    va: 'VA',
    gopay: 'GoPay',
    shopeepay: 'ShopeePay',
  }
  return enabledCoreApiMethods.value
    .map(m => ({ title: labels[m] ?? m, value: m }))
    .filter(x => typeof x.value === 'string' && x.value !== '')
})

const billVaBankOptions = computed(() => {
  const labels: Record<string, string> = {
    bni: 'BNI',
    bca: 'BCA',
    bri: 'BRI',
    mandiri: 'Mandiri',
    permata: 'Permata',
    cimb: 'CIMB Niaga',
  }
  return enabledCoreApiVaBanks.value
    .map(b => ({ title: labels[b] ?? b.toUpperCase(), value: b }))
    .filter(x => typeof x.value === 'string' && x.value !== '')
})

const userNoDataMessage = computed(() => {
  const q = String(search.value || '').trim()
  return q !== '' ? 'Tidak ada data pengguna yang cocok.' : 'Tidak ada data pengguna.'
})

// Perbaikan baris 67 (sesuai deskripsi error baris 56): Handle null/undefined secara eksplisit
function formatPhoneNumberDisplay(phone: string | null): string | null {
  if (phone === null || phone === undefined || phone === '') {
    return null // Mengembalikan null atau string kosong sesuai kebutuhan jika phone null/undefined/kosong
  }
  return phone.startsWith('+62') ? `0${phone.substring(3)}` : phone
}
const formatCreatedAt = (date: string) => new Date(date).toLocaleDateString('id-ID', { day: '2-digit', month: 'short', year: 'numeric' })
const formatDateTime = (date: string) => new Date(date).toLocaleString('id-ID', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' })
const formatCurrency = (value: number) => new Intl.NumberFormat('id-ID', { style: 'currency', currency: 'IDR', minimumFractionDigits: 0 }).format(value)
function formatQuotaGb(value?: number | null): string {
  if (value === null || value === undefined)
    return 'N/A'
  if (value === 0)
    return 'Unlimited'
  return `${value} GB`
}

function formatQuotaFromMb(mb: number): string {
  const safe = Number(mb)
  if (!Number.isFinite(safe) || safe <= 0)
    return '0 MB'
  if (safe < 1024)
    return `${Math.round(safe)} MB`

  const gb = safe / 1024
  const formatted = gb < 10
    ? gb.toFixed(1)
    : gb.toFixed(0)
  return `${formatted.replace(/\.0$/, '')} GB`
}

function getUserDebtTotalMb(user: User): number {
  if (user.is_unlimited_user === true)
    return 0
  const direct = Number(user.quota_debt_total_mb ?? 0)
  if (Number.isFinite(direct) && direct > 0)
    return direct
  const autoMb = Number(user.quota_debt_auto_mb ?? 0)
  const manualMb = Number(user.quota_debt_manual_mb ?? user.manual_debt_mb ?? 0)
  return (Number.isFinite(autoMb) ? autoMb : 0) + (Number.isFinite(manualMb) ? manualMb : 0)
}

type UserProfileLabel = 'Aktif' | 'Blocked' | 'FUP' | 'Habis' | 'Expired' | 'Unlimited' | 'Nonaktif'
function getUserProfileMeta(user: User): { text: UserProfileLabel, color: string, icon: string, tooltip?: string } {
  if (user.is_blocked === true)
    return { text: 'Blocked', color: 'error', icon: 'tabler-lock', tooltip: user.blocked_reason ?? undefined }

  if (user.is_unlimited_user === true)
    return { text: 'Unlimited', color: 'success', icon: 'tabler-infinity' }

  if (user.is_active === false)
    return { text: 'Nonaktif', color: 'secondary', icon: 'tabler-user-off' }

  const profile = String(user.mikrotik_profile_name ?? '').trim()
  const d = mikrotikOptions.value?.defaults
  const profileLower = profile.toLowerCase()
  const match = (v?: string | null) => String(v ?? '').trim().toLowerCase() !== '' && profileLower === String(v ?? '').trim().toLowerCase()

  if (match(d?.profile_fup))
    return { text: 'FUP', color: 'info', icon: 'tabler-chart-arrows-vertical' }
  if (match(d?.profile_habis))
    return { text: 'Habis', color: 'warning', icon: 'tabler-battery-off' }

  const now = new Date()
  if (match(d?.profile_expired))
    return { text: 'Expired', color: 'error', icon: 'tabler-calendar-x' }
  if (typeof user.quota_expiry_date === 'string' && user.quota_expiry_date !== '') {
    const expiry = new Date(user.quota_expiry_date)
    if (!Number.isNaN(expiry.getTime()) && expiry.getTime() < now.getTime())
      return { text: 'Expired', color: 'error', icon: 'tabler-calendar-x' }
  }

  if (match(d?.profile_unlimited))
    return { text: 'Unlimited', color: 'success', icon: 'tabler-infinity' }
  if (match(d?.profile_inactive))
    return { text: 'Nonaktif', color: 'secondary', icon: 'tabler-user-off' }
  if (match(d?.profile_active) || match(d?.profile_default))
    return { text: 'Aktif', color: 'success', icon: 'tabler-circle-check' }

  return { text: 'Aktif', color: 'success', icon: 'tabler-circle-check', tooltip: profile !== '' ? `Profile: ${profile}` : undefined }
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
    { title: 'PROFILE', key: 'profile', sortable: false, minWidth: '160px' },
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
  fetchUpdateSubmissions()
  fetchAlamatOptions()
  fetchMikrotikOptions()
  fetchInactiveCleanupPreview()
})

async function fetchUpdateSubmissions() {
  updateSubmissionLoading.value = true
  try {
    const params = new URLSearchParams()
    params.append('status', 'PENDING')
    params.append('page', '1')
    params.append('itemsPerPage', '20')
    const response = await $api<{ items: PublicUpdateSubmission[], totalItems: number }>(`/admin/update-submissions?${params.toString()}`)
    updateSubmissionItems.value = Array.isArray(response.items) ? response.items : []
    updateSubmissionTotal.value = Number(response.totalItems || 0)
  }
  catch (error: any) {
    const errorMessage = (typeof error.data?.message === 'string' && error.data.message !== '')
      ? error.data.message
      : 'Gagal memuat pengajuan role update.'
    showSnackbar({ type: 'warning', title: 'Approval Klaim Role', text: errorMessage })
  }
  finally {
    updateSubmissionLoading.value = false
  }
}

function resetToFirstPageAndFetchUsers() {
  if (options.value == null) {
    fetchUsers()
    return
  }

  if (options.value.page !== 1) {
    options.value.page = 1
    return
  }

  fetchUsers()
}

watch(options, () => {
  fetchUsers()
}, { deep: true })

watch([roleFilter, statusFilter, tampingFilter], () => {
  resetToFirstPageAndFetchUsers()
})
let searchTimeout: ReturnType<typeof setTimeout>
watch(search, () => {
  clearTimeout(searchTimeout)
  searchTimeout = setTimeout(() => {
    resetToFirstPageAndFetchUsers()
  }, 500)
})

async function ensurePackagesLoaded() {
  if (packageList.value.length > 0)
    return
  try {
    const resp = await $api<{ items: PackageItem[], totalItems: number }>('/admin/packages', {
      params: { page: 1, itemsPerPage: 100, sortBy: 'price', sortOrder: 'asc' },
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
  const methods = enabledCoreApiMethods.value
  billPaymentMethod.value = (methods.includes('qris') ? 'qris' : (methods[0] as BillPaymentMethod))
  const banks = enabledCoreApiVaBanks.value
  billVaBank.value = (banks.includes('bni') ? 'bni' : (banks[0] as any))
  isCreateBillDialogOpen.value = true
  await ensurePackagesLoaded()
}

watch([enabledCoreApiMethods, enabledCoreApiVaBanks], () => {
  const methods = enabledCoreApiMethods.value
  if (!methods.includes(billPaymentMethod.value))
    billPaymentMethod.value = (methods.includes('qris') ? 'qris' : (methods[0] as BillPaymentMethod))

  const banks = enabledCoreApiVaBanks.value
  if (!banks.includes(billVaBank.value))
    billVaBank.value = (banks.includes('bni') ? 'bni' : (banks[0] as any))
})

async function createBillForSelectedUser() {
  if (!billSelectedUser.value || !billSelectedPackage.value) {
    showSnackbar({ type: 'warning', title: 'Lengkapi Data', text: 'Pilih paket terlebih dahulu.' })
    return
  }

  if (billPaymentMethod.value === 'va' && !billVaBank.value) {
    showSnackbar({ type: 'warning', title: 'Lengkapi Data', text: 'Pilih bank untuk VA.' })
    return
  }

  billLoading.value = true
  try {
    const payload: Record<string, any> = {
      user_id: billSelectedUser.value.id,
      package_id: billSelectedPackage.value.id,
      payment_method: billPaymentMethod.value,
    }
    if (billPaymentMethod.value === 'va')
      payload.va_bank = billVaBank.value

    const resp = await $api<{ message: string, order_id: string, status: string, status_url?: string, whatsapp_sent?: boolean }>('/admin/transactions/bill', {
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
      : 'Gagal membuat tagihan.'
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
function handleApproveRoleClaim(item: PublicUpdateSubmission) {
  openConfirmDialog({
    title: 'Setujui Klaim Role',
    message: `Setujui klaim <strong>${item.role}</strong> untuk <strong>${item.full_name}</strong>? Data user akan disesuaikan dengan blok/kamar pengajuan.`,
    color: 'success',
    action: async () => {
      await performUpdateSubmissionAction(
        `/admin/update-submissions/${item.id}/approve`,
        'POST',
        'Pengajuan klaim role berhasil disetujui.',
      )
    },
  })
}

function handleRejectRoleClaim(item: PublicUpdateSubmission) {
  openConfirmDialog({
    title: 'Tolak Klaim Role',
    message: `Tolak klaim role untuk <strong>${item.full_name}</strong>?`,
    color: 'error',
    action: async () => {
      await performUpdateSubmissionAction(
        `/admin/update-submissions/${item.id}/reject`,
        'POST',
        'Pengajuan klaim role berhasil ditolak.',
      )
    },
  })
}

async function performUpdateSubmissionAction(endpoint: string, method: 'POST', successMessage: string) {
  loading.value = true
  try {
    await $api(endpoint, { method })
    showSnackbar({ type: 'success', title: 'Berhasil', text: successMessage })
    closeAllDialogs()
    await fetchUpdateSubmissions()
    await fetchUsers()
  }
  catch (error: any) {
    const errorMessage = (typeof error.data?.message === 'string' && error.data.message !== '')
      ? error.data.message
      : 'Operasi approval klaim role gagal.'
    showSnackbar({ type: 'error', title: 'Terjadi Kesalahan', text: errorMessage })
  }
  finally {
    loading.value = false
  }
}

async function performAction(endpoint: string, method: 'PATCH' | 'POST' | 'DELETE' | 'PUT', successMessage: string, options: { body?: object } = {}, updatedItemId?: string) {
  loading.value = true
  try {
    const response = await $api<any>(endpoint, { method, ...options })
    showSnackbar({ type: 'success', title: 'Berhasil', text: successMessage })
    closeAllDialogs()
    await fetchUpdateSubmissions()
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
        <VCardTitle class="admin-users__cleanup-title">
          <div class="admin-users__cleanup-titleText">
            <VIcon icon="tabler-shield-check" class="me-2" />
            <span>Approval Klaim Komandan / Tamping</span>
          </div>

          <VBtn
            class="admin-users__cleanup-refresh"
            size="small"
            variant="tonal"
            color="info"
            :block="isMobile"
            :loading="updateSubmissionLoading"
            @click="fetchUpdateSubmissions"
          >
            Refresh
          </VBtn>
        </VCardTitle>
      </VCardItem>
      <VCardText>
        <VChip color="warning" variant="tonal" size="small" label class="mb-3">
          Menunggu Approval: {{ updateSubmissionTotal }}
        </VChip>

        <VList density="compact" border rounded>
          <VListItem
            v-for="item in updateSubmissionItems"
            :key="item.id"
            :title="item.full_name"
            :subtitle="`${formatPhoneNumberDisplay(item.phone_number) ?? '-'} • ${item.blok}/${item.kamar} • ${formatDateTime(item.created_at)}`"
          >
            <template #append>
              <div class="d-flex align-center gap-1">
                <VChip size="x-small" color="primary" label>{{ item.role }}</VChip>
                <VBtn icon size="x-small" variant="text" color="success" @click="handleApproveRoleClaim(item)">
                  <VIcon icon="tabler-check" size="16" />
                  <VTooltip activator="parent">Setujui Klaim</VTooltip>
                </VBtn>
                <VBtn icon size="x-small" variant="text" color="error" @click="handleRejectRoleClaim(item)">
                  <VIcon icon="tabler-x" size="16" />
                  <VTooltip activator="parent">Tolak Klaim</VTooltip>
                </VBtn>
              </div>
            </template>
          </VListItem>

          <VListItem v-if="updateSubmissionItems.length === 0 && updateSubmissionLoading === false" title="Belum ada pengajuan klaim role yang menunggu approval." />
        </VList>
      </VCardText>
    </VCard>

    <VCard class="rounded-lg mb-6">
      <VCardItem>
        <VCardTitle class="admin-users__cleanup-title">
          <div class="admin-users__cleanup-titleText">
            <VIcon icon="tabler-user-x" class="me-2" />
            <span>Preview Cleanup Nonaktif</span>
          </div>

          <VBtn
            class="admin-users__cleanup-refresh"
            size="small"
            variant="tonal"
            color="info"
            :block="isMobile"
            :loading="cleanupPreviewLoading"
            @click="fetchInactiveCleanupPreview"
          >
            Refresh
          </VBtn>
        </VCardTitle>
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
        <VCardSubtitle class="admin-users__subtitle">Kelola semua akun yang terdaftar di sistem.</VCardSubtitle>
        <template v-if="!isMobile" #append>
          <div class="admin-users__toolbar">
            <div class="admin-users__search">
              <AppTextField
                v-model="search"
                placeholder="Cari (Nama/No. HP)..."
                prepend-inner-icon="tabler-search"
                clearable
                density="comfortable"
                hide-details
              />
            </div>

            <VBtn
              prepend-icon="tabler-plus"
              height="56"
              class="admin-users__addBtn"
              @click="openAddUserDialog()"
            >
              Tambah Akun
            </VBtn>
          </div>
        </template>
      </VCardItem>

      <!-- Mobile: 3 baris (Search di bawah judul, tombol di bawah search) -->
      <VCardText v-if="isHydrated && isMobile" class="pt-0">
        <div class="admin-users__toolbarMobile">
          <AppTextField
            v-model="search"
            placeholder="Cari (Nama/No. HP)..."
            prepend-inner-icon="tabler-search"
            clearable
            density="comfortable"
            hide-details
          />

          <VBtn
            prepend-icon="tabler-plus"
            :height="44"
            block
            class="admin-users__addBtnMobile"
            @click="openAddUserDialog()"
          >
            Tambah Akun
          </VBtn>
        </div>
      </VCardText>
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
              <div v-if="getUserDebtTotalMb(item) > 0" class="mt-1">
                <VTooltip :text="`Debt: ${getUserDebtTotalMb(item)} MB`" location="top">
                  <template #activator="{ props: tooltipProps }">
                    <VChip v-bind="tooltipProps" color="warning" size="x-small" label prepend-icon="tabler-alert-triangle">
                      Debt {{ formatQuotaFromMb(getUserDebtTotalMb(item)) }}
                    </VChip>
                  </template>
                </VTooltip>
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

        <template #item.profile="{ item }">
          <div class="d-flex flex-column ga-1 py-2">
            <VTooltip v-if="getUserProfileMeta(item).tooltip" :text="getUserProfileMeta(item).tooltip" location="top">
              <template #activator="{ props: tooltipProps }">
                <VChip v-bind="tooltipProps" :color="getUserProfileMeta(item).color" size="x-small" label>
                  <VIcon :icon="getUserProfileMeta(item).icon" start size="16" />
                  {{ getUserProfileMeta(item).text }}
                </VChip>
              </template>
            </VTooltip>
            <VChip v-else :color="getUserProfileMeta(item).color" size="x-small" label>
              <VIcon :icon="getUserProfileMeta(item).icon" start size="16" />
              {{ getUserProfileMeta(item).text }}
            </VChip>

            <VTooltip v-if="getUserDebtTotalMb(item) > 0" :text="`Debt: ${getUserDebtTotalMb(item)} MB`" location="top">
              <template #activator="{ props: tooltipProps }">
                <VChip v-bind="tooltipProps" color="warning" size="x-small" label prepend-icon="tabler-alert-triangle">
                  Debt {{ formatQuotaFromMb(getUserDebtTotalMb(item)) }}
                </VChip>
              </template>
            </VTooltip>
          </div>
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
                  Buat Tagihan
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
            <VIcon icon="tabler-database-off" size="32" class="mb-2" />
            <p>{{ userNoDataMessage }}</p>
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

      <div v-if="isMobile" class="pa-4">
        <div v-if="showInitialSkeleton" class="pa-5">
          <VCard v-for="i in 3" :key="i" class="mb-3">
            <VSkeletonLoader type="list-item-two-line" />
          </VCard>
        </div>
        <div v-else-if="users.length === 0 && loading === false" class="py-8 text-center text-medium-emphasis">
          <VIcon icon="tabler-database-off" size="32" class="mb-2" />
          <p>{{ userNoDataMessage }}</p>
        </div>
        <VCard v-for="user in users" v-else :key="user.id" class="mb-3">
          <VCardText>
            <div class="admin-users__mobile-cardHeader">
              <div class="admin-users__mobile-user">
                <VAvatar size="32" class="me-3" :color="getRoleMeta(user.role).color" variant="tonal">
                  <span class="text-sm font-weight-medium">{{ user.full_name.substring(0, 2).toUpperCase() }}</span>
                </VAvatar>
                <div class="d-flex flex-column admin-users__mobile-userText">
                  <span class="font-weight-medium text-high-emphasis text-truncate">{{ user.full_name }}</span>
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
              <VChip class="admin-users__mobile-status" :color="getStatusMeta(user.approval_status).color" size="small" label>
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
                  Buat Tagihan
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
              <span class="font-weight-medium">Buat Tagihan</span>
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

          <VSelect
            v-model="billPaymentMethod"
            :items="billPaymentMethodOptions"
            item-title="title"
            item-value="value"
            label="Metode Pembayaran"
            variant="outlined"
            density="comfortable"
            class="mt-4"
            :disabled="billLoading"
          />

          <VSelect
            v-if="billPaymentMethod === 'va'"
            v-model="billVaBank"
            :items="billVaBankOptions"
            item-title="title"
            item-value="value"
            label="Bank VA"
            variant="outlined"
            density="comfortable"
            class="mt-4"
            :disabled="billLoading"
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
          <VBtn color="primary" :loading="billLoading" @click="createBillForSelectedUser">
            Kirim Tagihan
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

<style scoped>
.admin-users__cleanup-title {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  width: 100%;
}

.admin-users__cleanup-titleText {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.admin-users__cleanup-titleText span {
  white-space: normal;
  line-height: 1.25rem;
}

.admin-users__cleanup-refresh {
  flex-shrink: 0;
}

.admin-users__toolbarMobile {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.admin-users__subtitle {
  overflow: visible;
  text-overflow: clip;
  white-space: normal;
}

.admin-users__addBtnMobile {
  align-self: stretch;
}

.admin-users__toolbar {
  display: flex;
  align-items: center;
  gap: 16px;
}

.admin-users__toolbar--mobile {
  flex-direction: column;
  align-items: stretch;
  width: 100%;
  gap: 12px;
}

.admin-users__search {
  width: 300px;
}

.admin-users__toolbar--mobile .admin-users__search {
  width: 100%;
}

.admin-users__addBtn {
  min-width: 160px;
}

.admin-users__toolbar--mobile .admin-users__addBtn {
  width: 100%;
}

.admin-users__mobile-cardHeader {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.admin-users__mobile-user {
  display: flex;
  align-items: center;
  min-width: 0;
  flex: 1 1 auto;
  gap: 12px;
}

.admin-users__mobile-userText {
  min-width: 0;
}

.admin-users__mobile-status {
  flex: 0 0 auto;
  white-space: nowrap;
}

/* Make mobile icon buttons easier to tap */
@media (max-width: 600px) {
  :deep(.v-card-actions) {
    padding-block: 8px;
  }

  :deep(.v-card-actions .v-btn) {
    min-height: 40px;
    min-width: 40px;
  }
}
</style>
