<script lang="ts" setup>
import type { VForm } from 'vuetify/components'
import AppSelect from '@core/components/app-form-elements/AppSelect.vue'
import AppTextField from '@core/components/app-form-elements/AppTextField.vue'
import AppDateTimePicker from '@core/components/app-form-elements/AppDateTimePicker.vue'
import { computed, nextTick, reactive, ref, watch } from 'vue'
import { useDisplay } from 'vuetify'
import { useSnackbar } from '@/composables/useSnackbar'
import { useAuthStore } from '@/store/auth'
import { TAMPING_OPTION_ITEMS } from '~/utils/constants'
import UserDebtLedgerDialog from '@/components/admin/users/UserDebtLedgerDialog.vue'
import UserQuotaHistoryDialog from '@/components/admin/users/UserQuotaHistoryDialog.vue'

const props = defineProps<{
  modelValue: boolean
  user: User | null
  availableBloks: string[]
  availableKamars: string[]
  loading: boolean
  isAlamatLoading: boolean
  mikrotikOptions: {
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
}>()
const emit = defineEmits(['update:modelValue', 'save'])
const { $api } = useNuxtApp()
const tab = ref('info')
const { add: showSnackbar } = useSnackbar()
const isResetLoginLoading = ref(false)
const isResetPasswordLoading = ref(false)

interface User {
  id: string
  full_name: string
  phone_number: string
  role: 'USER' | 'KOMANDAN' | 'ADMIN' | 'SUPER_ADMIN'
  is_active: boolean
  blok: string | null
  kamar: string | null
  is_tamping: boolean
  tamping_type: string | null
  is_unlimited_user: boolean
  mikrotik_server_name: string | null
  mikrotik_profile_name: string | null
  mikrotik_user_exists?: boolean
  total_quota_purchased_mb: number
  total_quota_used_mb: number
  manual_debt_mb?: number
  quota_debt_auto_mb?: number
  quota_debt_manual_mb?: number
  quota_debt_total_mb?: number
  quota_expiry_date: string | null
  is_blocked?: boolean
  blocked_reason?: string | null
  last_login_at?: string | null
  device_count?: number
}

interface LiveData {
  isAvailable: boolean
  db_sisa_kuota_mb: number
  db_expiry_date: string | null
  mt_usage_mb: number
  mt_profile: string
}

const authStore = useAuthStore()
const display = useDisplay()
const isMobile = computed(() => display.smAndDown.value)
const formRef = ref<InstanceType<typeof VForm> | null>(null)

interface AdminPackage {
  id: string
  name: string
  price: number
  is_active: boolean
  data_quota_gb: number
}

const adminPackages = ref<AdminPackage[]>([])
const isPackagesLoading = ref(false)

function getInitialFormData(): Partial<User & { add_gb: number | null, add_days: number | null, unlimited_time: boolean, debt_package_id: string | null, debt_date: string | null, debt_note: string | null }> {
  return {
    full_name: '',
    phone_number: '',
    role: 'USER',
    is_active: true,
    blok: null,
    kamar: null,
    is_tamping: false,
    tamping_type: null,
    is_unlimited_user: false,
    is_blocked: false,
    blocked_reason: null,
    mikrotik_server_name: null,
    mikrotik_profile_name: null,
    total_quota_purchased_mb: 0,
    total_quota_used_mb: 0,
    quota_expiry_date: null,
    add_gb: null,
    add_days: null,
    unlimited_time: false,
    debt_package_id: null,
    debt_date: null,
    debt_note: null,
  }
}

const formData = reactive(getInitialFormData())
const isCheckingMikrotik = ref(false)
const liveData = ref<LiveData | null>(null)
const isDebtLedgerOpen = ref(false)
const isQuotaHistoryOpen = ref(false)
const isDebtWhatsappSending = ref(false)
const isDebtQuotaEnabled = ref(false)
const SA_QUOTA_MB_PER_GB = 1024

// --- SuperAdmin: koreksi kuota langsung ---
const saQuotaForm = reactive<{
  set_purchased_mb: number | null
  set_used_mb: number | null
  reason: string
}>({
  set_purchased_mb: null,
  set_used_mb: null,
  reason: '',
})
const saQuotaInputUnit = ref<'gb' | 'mb'>('gb')
const isSaQuotaLoading = ref(false)
const isSaQuotaAutoFilling = ref(false)

function normalizeNullableNumber(value: unknown): number | null {
  if (value === '' || value == null)
    return null
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

function inputValueToMb(value: unknown, unit: 'gb' | 'mb'): number | null {
  const parsed = normalizeNullableNumber(value)
  if (parsed === null)
    return null
  if (unit === 'gb')
    return Math.max(0, Math.round(parsed * SA_QUOTA_MB_PER_GB))
  return Math.max(0, Math.round(parsed))
}

function mbToInputValue(valueMb: number | null, unit: 'gb' | 'mb'): number | null {
  if (valueMb === null || !Number.isFinite(valueMb))
    return null
  if (unit === 'gb')
    return Number((valueMb / SA_QUOTA_MB_PER_GB).toFixed(2))
  return Math.round(valueMb)
}

function formatQuotaValueByUnit(valueMb: number | null | undefined, unit: 'gb' | 'mb'): string {
  const parsed = Number(valueMb ?? 0)
  if (!Number.isFinite(parsed))
    return unit === 'gb' ? '0 GB' : '0 MB'
  if (unit === 'gb')
    return `${(parsed / SA_QUOTA_MB_PER_GB).toLocaleString('id-ID', { minimumFractionDigits: 0, maximumFractionDigits: 2 })} GB`
  return `${Math.round(parsed).toLocaleString('id-ID')} MB`
}

const saQuotaPurchasedInput = computed({
  get: () => mbToInputValue(saQuotaForm.set_purchased_mb, saQuotaInputUnit.value),
  set: value => {
    saQuotaForm.set_purchased_mb = inputValueToMb(value, saQuotaInputUnit.value)
  },
})

const saQuotaUsedInput = computed({
  get: () => mbToInputValue(saQuotaForm.set_used_mb, saQuotaInputUnit.value),
  set: value => {
    saQuotaForm.set_used_mb = inputValueToMb(value, saQuotaInputUnit.value)
  },
})

const saQuotaUnitLabel = computed(() => saQuotaInputUnit.value.toUpperCase())
const saQuotaUnitHint = computed(() => (saQuotaInputUnit.value === 'gb'
  ? 'Mode default untuk input operasional. Sistem tetap menyimpan nilai dalam MB.'
  : 'Mode lanjutan untuk koreksi presisi langsung dalam MB.'))
const saQuotaRemainingMb = computed(() => Math.max(0, Number(formData.total_quota_purchased_mb ?? 0) - Number(formData.total_quota_used_mb ?? 0)))
const saQuotaPurchasedCurrentText = computed(() => `Saat ini ${formatQuotaValueByUnit(formData.total_quota_purchased_mb, saQuotaInputUnit.value)}`)
const saQuotaUsedCurrentText = computed(() => `Saat ini ${formatQuotaValueByUnit(Number(formData.total_quota_used_mb), saQuotaInputUnit.value)}`)

async function autoFillSaQuotaFromDb() {
  if (!props.user?.id)
    return
  isSaQuotaAutoFilling.value = true
  try {
    const res = await $api<{
      db_quota_purchased_mb?: number | null
      db_quota_used_mb?: number | null
      db_quota_remaining_mb?: number | null
    }>(`/admin/users/${props.user.id}/mikrotik-status`)
    if (res.db_quota_purchased_mb != null)
      saQuotaForm.set_purchased_mb = Math.round(res.db_quota_purchased_mb)
    if (res.db_quota_used_mb != null)
      saQuotaForm.set_used_mb = Math.round(res.db_quota_used_mb)
    showSnackbar({ type: 'info', title: 'Auto-fill', text: 'Nilai kuota diisi dari database saat ini.' })
  }
  catch {
    showSnackbar({ type: 'error', title: 'Gagal', text: 'Gagal mengambil nilai quota dari server.' })
  }
  finally {
    isSaQuotaAutoFilling.value = false
  }
}

async function applyDirectQuotaAdjust() {
  if (!props.user?.id)
    return
  if (!saQuotaForm.reason.trim()) {
    showSnackbar({ type: 'error', title: 'Validasi', text: 'Alasan koreksi wajib diisi.' })
    return
  }
  if (saQuotaForm.set_purchased_mb === null && saQuotaForm.set_used_mb === null) {
    showSnackbar({ type: 'error', title: 'Validasi', text: 'Isi setidaknya satu nilai untuk dikoreksi.' })
    return
  }
  const payload: Record<string, unknown> = { reason: saQuotaForm.reason }
  if (saQuotaForm.set_purchased_mb !== null)
    payload.set_purchased_mb = saQuotaForm.set_purchased_mb
  if (saQuotaForm.set_used_mb !== null)
    payload.set_used_mb = saQuotaForm.set_used_mb

  isSaQuotaLoading.value = true
  try {
    const res = await $api<{ message: string; total_quota_purchased_mb: number; total_quota_used_mb: number; remaining_mb: number }>(
      `/admin/users/${props.user.id}/quota-adjust`,
      { method: 'POST', body: payload },
    )
    showSnackbar({ type: 'success', title: 'Berhasil', text: `Koreksi berhasil. Sisa: ${formatDataSize(Number(res.remaining_mb ?? 0))}` })
    if (res.total_quota_purchased_mb !== undefined)
      formData.total_quota_purchased_mb = res.total_quota_purchased_mb
    if (res.total_quota_used_mb !== undefined)
      formData.total_quota_used_mb = res.total_quota_used_mb
    saQuotaForm.set_purchased_mb = null
    saQuotaForm.set_used_mb = null
    saQuotaForm.reason = ''
  }
  catch (e: unknown) {
    showSnackbar({ type: 'error', title: 'Gagal', text: (e as { data?: { message?: string } })?.data?.message ?? 'Gagal menyimpan koreksi.' })
  }
  finally {
    isSaQuotaLoading.value = false
  }
}

function getTodayYmd(): string {
  const now = new Date()
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`
}

const isRestrictedAdmin = computed(() => authStore.isAdmin && !authStore.isSuperAdmin)

const canAdminInject = computed(() => {
  if (authStore.isSuperAdmin)
    return true
  if (isRestrictedAdmin.value && (formData.role === 'USER' || formData.role === 'KOMANDAN'))
    return true
  return false
})

const isSaveDisabled = computed(() => {
  if (isRestrictedAdmin.value !== true)
    return false
  return formData.role === 'ADMIN' || formData.role === 'SUPER_ADMIN'
})

const isTargetAdminOrSuper = computed(() => formData.role === 'ADMIN' || formData.role === 'SUPER_ADMIN')
const isBlocked = computed(() => formData.is_blocked === true)

const tampingOptions = TAMPING_OPTION_ITEMS

const fallbackMikrotikDefaults = {
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
}
const mikrotikDefaults = computed(() => ({
  ...fallbackMikrotikDefaults,
  ...(props.mikrotikOptions?.defaults ?? {}),
}))
const roleOptions = computed(() => {
  const roles: Array<User['role']> = ['USER', 'KOMANDAN', 'ADMIN', 'SUPER_ADMIN']
  return roles.map(role => ({ title: role.replace('_', ' '), value: role }))
})

watch(() => props.user, (newUser) => {
  if (newUser) {
    const isEditingAdminOrSuper = newUser.role === 'ADMIN' || newUser.role === 'SUPER_ADMIN'
    Object.assign(formData, getInitialFormData(), newUser, {
      kamar: newUser.kamar != null ? newUser.kamar.replace('Kamar_', '') : null,
      add_gb: null,
      add_days: null,
      unlimited_time: Boolean((isEditingAdminOrSuper || newUser.is_unlimited_user) && !newUser.quota_expiry_date),
      debt_package_id: null,
      debt_date: null,
      debt_note: null,
      is_unlimited_user: isEditingAdminOrSuper || newUser.is_unlimited_user,
    })
  }
}, { immediate: true })

watch(() => isDebtQuotaEnabled.value, (enabled) => {
  if (enabled === true) {
    formData.unlimited_time = false
    if (formData.debt_date == null || String(formData.debt_date).trim() === '')
      formData.debt_date = getTodayYmd()
    fetchAdminPackages().catch(() => {})
  }
  else {
    formData.debt_package_id = null
    formData.debt_date = null
    formData.debt_note = null
  }
})

watch(() => formData.unlimited_time, (v) => {
  if (v === true)
    formData.add_days = null
})

const sectionOptions = computed(() => {
  return [
    {
      title: 'Info Pengguna',
      desc: 'Data dasar, peran, dan alamat.',
      value: 'info',
      icon: 'tabler-user',
    },
    {
      title: 'Akses & Kuota',
      desc: 'Akses, inject, dan tunggakan kuota.',
      value: 'akses',
      icon: 'tabler-shield-check',
    },
  ]
})

const canToggleUnlimited = computed(() => {
  if (isTargetAdminOrSuper.value)
    return false
  if (formData.role !== 'USER' && formData.role !== 'KOMANDAN')
    return false
  if (isDebtQuotaEnabled.value === true)
    return false
  if (formData.role === 'USER' && debtTotalMb.value > 0)
    return false
  return true
})

const canToggleDebt = computed(() => {
  if (formData.role !== 'USER')
    return false
  return true
})

const shouldShowDebtSection = computed(() => {
  if (formData.role !== 'USER')
    return false
  return debtManualMb.value > 0 || debtTotalMb.value > 0 || isDebtQuotaEnabled.value === true
})

function toNumberOrZero(value: unknown): number {
  if (value === '' || value == null)
    return 0
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : 0
}

const debtAutoMb = computed(() => (props.user?.is_unlimited_user === true ? 0 : Number(props.user?.quota_debt_auto_mb ?? 0)))
const debtManualMb = computed(() => Number(props.user?.quota_debt_manual_mb ?? props.user?.manual_debt_mb ?? 0))
const debtTotalMb = computed(() => {
  if (props.user?.is_unlimited_user === true)
    return debtManualMb.value
  return Number(props.user?.quota_debt_total_mb ?? (debtAutoMb.value + debtManualMb.value))
})
const hasUnlimitedManualDebt = computed(() => props.user?.is_unlimited_user === true && debtManualMb.value > 0)
const debtTotalDisplay = computed(() => (hasUnlimitedManualDebt.value ? 'Unlimited' : formatDataSize(debtTotalMb.value)))
const debtManualDisplay = computed(() => (hasUnlimitedManualDebt.value ? 'Unlimited' : formatDataSize(debtManualMb.value)))
const debtAutoDisplay = computed(() => formatDataSize(debtAutoMb.value))

const isInjectBlockedByDebt = computed(() => {
  if (formData.is_unlimited_user === true)
    return false
  if (formData.role !== 'USER')
    return false
  return debtTotalMb.value > 0
})

const debtPackageOptions = computed(() => {
  return adminPackages.value
    .filter(pkg => pkg.is_active === true)
    .map(pkg => ({
      title: Number(pkg.data_quota_gb) === 0
        ? `${pkg.name} — Unlimited — Rp ${Number(pkg.price ?? 0).toLocaleString('id-ID')}`
        : `${pkg.name} — ${Number(pkg.data_quota_gb).toLocaleString('id-ID')} GB — Rp ${Number(pkg.price ?? 0).toLocaleString('id-ID')}`,
      value: pkg.id,
    }))
})

async function fetchAdminPackages() {
  if (isPackagesLoading.value)
    return
  isPackagesLoading.value = true
  try {
    const resp = await $api<{ items: AdminPackage[] }>(`/admin/packages?page=1&itemsPerPage=100&sortBy=price&sortOrder=asc`)
    adminPackages.value = Array.isArray(resp.items) ? resp.items : []
  }
  catch {
    adminPackages.value = []
  }
  finally {
    isPackagesLoading.value = false
  }
}

const debtStatusMeta = computed(() => {
  const hasDebt = debtTotalMb.value > 0
  return {
    text: hasDebt ? (hasUnlimitedManualDebt.value ? 'ADA TUNGGAKAN MANUAL' : 'ADA TUNGGAKAN') : 'TIDAK ADA TUNGGAKAN',
    color: hasDebt ? 'warning' : 'success',
    icon: hasDebt ? 'tabler-alert-triangle' : 'tabler-circle-check',
  }
})

function formatMb(value: number) {
  if (!Number.isFinite(value))
    return '0'
  return value.toLocaleString('id-ID', { maximumFractionDigits: 2 })
}

function formatDataSize(sizeInMB: number): string {
  if (!Number.isFinite(sizeInMB) || Number.isNaN(sizeInMB))
    return '0 MB'
  const options = { minimumFractionDigits: 2, maximumFractionDigits: 2 }
  if (sizeInMB < 1)
    return `${(sizeInMB * 1024).toLocaleString('id-ID', options)} KB`
  else if (sizeInMB < 1024)
    return `${sizeInMB.toLocaleString('id-ID', options)} MB`
  else
    return `${(sizeInMB / 1024).toLocaleString('id-ID', options)} GB`
}

watch(() => props.modelValue, (isOpen) => {
  if (isOpen) {
    liveData.value = null
    isDebtQuotaEnabled.value = false
    // Best-effort load package list for debt selection.
    fetchAdminPackages().catch(() => {})
    // PERBAIKAN: Memindahkan isi arrow function ke baris baru
    nextTick(() => {
      formRef.value?.resetValidation()
    })
  }
})

watch(() => props.user?.id, () => {
  if (props.modelValue && props.user?.id)
    void 0
})

function setDefaultMikrotikConfig(role: User['role'] | undefined) {
  const defaults = mikrotikDefaults.value
  switch (role) {
    case 'USER':
      if (formData.is_unlimited_user !== true) {
        formData.mikrotik_profile_name = defaults.profile_active || defaults.profile_user
      }
      formData.mikrotik_server_name = defaults.server_user
      break
    case 'KOMANDAN':
      if (formData.is_unlimited_user !== true) {
        formData.mikrotik_profile_name = defaults.profile_komandan || defaults.profile_active || defaults.profile_user
      }
      formData.mikrotik_server_name = defaults.server_komandan || defaults.server_user
      break
    case 'ADMIN':
    case 'SUPER_ADMIN':
      formData.mikrotik_profile_name = defaults.profile_unlimited
      formData.mikrotik_server_name = defaults.server_user
      break
  }
}

watch(() => formData.role, (newRole) => {
  if (newRole === 'ADMIN' || newRole === 'SUPER_ADMIN') {
    formData.is_unlimited_user = true
    formData.blok = null
    formData.kamar = null
    formData.is_tamping = false
    formData.tamping_type = null
  }
  else if (newRole === 'KOMANDAN') {
    formData.blok = null
    formData.kamar = null
    formData.is_tamping = false
    formData.tamping_type = null
  }
  setDefaultMikrotikConfig(newRole)
})

watch(() => formData.is_tamping, (isTamping) => {
  if (isTamping) {
    formData.blok = null
    formData.kamar = null
  }
  else {
    formData.tamping_type = null
  }
})

watch(() => formData.is_unlimited_user, (isUnlimited, wasUnlimited) => {
  if (isUnlimited === wasUnlimited)
    return

  if (isUnlimited) {
    isDebtQuotaEnabled.value = false
    formData.mikrotik_profile_name = mikrotikDefaults.value.profile_unlimited
    formData.add_gb = 0
  }
  else {
    setDefaultMikrotikConfig(formData.role)
  }
})

watch(() => formData.is_active, (isActive, wasActive) => {
  if (isActive === wasActive)
    return

  if (!isActive) {
    formData.mikrotik_profile_name = mikrotikDefaults.value.profile_inactive
  }
  else {
    if (formData.is_unlimited_user === true) {
      formData.mikrotik_profile_name = mikrotikDefaults.value.profile_unlimited
    }
    else {
      setDefaultMikrotikConfig(formData.role)
    }
  }
})

async function checkAndApplyMikrotikStatus() {
  if (!props.user)
    return
  isCheckingMikrotik.value = true
  liveData.value = null
  try {
    const response = await $api<{ exists_on_mikrotik: boolean, details: any, message?: string, live_available?: boolean }>(`/admin/users/${props.user.id}/mikrotik-status`)

    if (response.live_available === false) {
      showSnackbar({ type: 'info', title: 'Mode Lokal', text: response.message || 'Live check MikroTik tidak tersedia. Menampilkan data dari database.' })
      return
    }

    if (response.exists_on_mikrotik === true && response.details != null) {
      formData.mikrotik_server_name = response.details.server
      formData.mikrotik_profile_name = response.details.profile
      const usage_bytes = Number.parseInt(response.details['bytes-in'] || '0') + Number.parseInt(response.details['bytes-out'] || '0')
      liveData.value = {
        isAvailable: true,
        db_sisa_kuota_mb: Math.max(0, (props.user.total_quota_purchased_mb ?? 0) - (props.user.total_quota_used_mb ?? 0)),
        db_expiry_date: props.user.quota_expiry_date,
        mt_usage_mb: usage_bytes / (1024 * 1024),
        mt_profile: response.details.profile,
      }
      showSnackbar({ type: 'success', title: 'Sukses', text: 'Data live dari MikroTik berhasil dimuat.' })
    }
    else {
      showSnackbar({ type: 'warning', title: 'Informasi', text: response.message || 'Pengguna tidak ditemukan di MikroTik.' })
    }
  }
  catch (error: any) {
    showSnackbar({ type: 'error', title: 'Gagal', text: error.data?.message || 'Gagal terhubung ke server Mikrotik.' })
  }
  finally {
    isCheckingMikrotik.value = false
  }
}

async function resetUserLogin() {
  if (!props.user)
    return

  const ok = window.confirm(
    `Reset login untuk ${props.user.full_name} (${props.user.phone_number})?\n\nAksi ini akan:\n- Menghapus semua refresh token\n- Menghapus semua device (user_devices) agar enroll ulang\n- Membersihkan state MikroTik (address-list terkelola, ip-binding, DHCP lease, dan ARP)\n\nStatus kuota/paket di database tidak diubah.`,
  )
  if (!ok)
    return

  isResetLoginLoading.value = true
  try {
    const res = await $api<any>(`/admin/users/${props.user.id}/reset-login`, { method: 'POST' })
    showSnackbar({ type: 'success', title: 'Berhasil', text: res?.message || 'Reset login berhasil.' })
  }
  catch (error: any) {
    showSnackbar({ type: 'error', title: 'Gagal', text: error.data?.message || 'Reset login gagal.' })
  }
  finally {
    isResetLoginLoading.value = false
  }
}

async function resetUserPassword() {
  if (!props.user)
    return

  const ok = window.confirm(
    `Reset password untuk ${props.user.full_name} (${props.user.phone_number})?\n\nSistem akan:\n- Membuat password baru berupa 6 angka acak\n- Menyimpan hash password baru ke database\n- Mengirim password baru ke WhatsApp pengguna\n\nPassword lama tidak dapat dikembalikan.`,
  )
  if (!ok)
    return

  isResetPasswordLoading.value = true
  try {
    const res = await $api<{ message: string, whatsapp_sent: boolean }>(`/admin/users/${props.user.id}/reset-password`, { method: 'POST' })
    showSnackbar({ type: 'success', title: 'Password Direset', text: res?.message || 'Password berhasil direset.' })
  }
  catch (error: any) {
    showSnackbar({ type: 'error', title: 'Gagal', text: error.data?.message || 'Gagal mereset password.' })
  }
  finally {
    isResetPasswordLoading.value = false
  }
}

async function onSave() {
  if (!formRef.value)
    return
  const { valid } = await formRef.value.validate()
  if (valid) {
    const payload: any = { ...formData }

    payload.add_gb = toNumberOrZero(payload.add_gb)
    payload.add_days = toNumberOrZero(payload.add_days)

    if (payload.role !== 'USER') {
      isDebtQuotaEnabled.value = false
    }

    if (isDebtQuotaEnabled.value !== true) {
      payload.debt_package_id = null
      payload.debt_date = null
      payload.debt_note = null
    }

    const defaults = mikrotikDefaults.value

    if (payload.is_active !== true) {
      payload.mikrotik_profile_name = defaults.profile_inactive
    }
    else if (payload.role === 'ADMIN' || payload.role === 'SUPER_ADMIN') {
      payload.is_unlimited_user = true
      payload.mikrotik_profile_name = defaults.profile_unlimited
    }
    else if (payload.is_unlimited_user === true) {
      payload.mikrotik_profile_name = defaults.profile_unlimited
    }
    else if (payload.role === 'KOMANDAN') {
      payload.mikrotik_profile_name = defaults.profile_komandan || defaults.profile_active || defaults.profile_user
    }
    else {
      payload.mikrotik_profile_name = defaults.profile_active || defaults.profile_user
    }

    if (payload.role === 'KOMANDAN') {
      payload.mikrotik_server_name = defaults.server_komandan || defaults.server_user
      // Debt tidak berlaku untuk komandan
      payload.debt_package_id = null
      payload.debt_date = null
      payload.debt_note = null
    }
    else {
      payload.mikrotik_server_name = defaults.server_user
    }

    if (payload.is_unlimited_user === true && payload.unlimited_time === true)
      payload.add_days = 0

    if (payload.role === 'ADMIN' || payload.role === 'SUPER_ADMIN') {
      payload.is_unlimited_user = true
      payload.add_gb = 0
      payload.add_days = 0
    }

    emit('save', payload)
  }
}

function onClose() {
  emit('update:modelValue', false)
}

function openDebtLedger() {
  if (!props.user)
    return
  isDebtLedgerOpen.value = true
}

function openDebtPdf() {
  if (!props.user)
    return
  window.open(`/api/admin/users/${props.user.id}/debts/export?format=pdf`, '_blank', 'noopener')
}

async function sendDebtWhatsapp() {
  if (!props.user)
    return

  isDebtWhatsappSending.value = true
  try {
    const resp = await $api<{ message?: string }>(`/admin/users/${props.user.id}/debts/send-whatsapp`, { method: 'POST' })
    showSnackbar({ type: 'success', title: 'Tunggakan', text: resp?.message || 'Ringkasan tunggakan berhasil diantrikan ke WhatsApp.' })
  }
  catch (error: any) {
    showSnackbar({ type: 'warning', title: 'Tunggakan', text: error?.data?.message || 'Gagal mengirim ringkasan tunggakan ke WhatsApp.' })
  }
  finally {
    isDebtWhatsappSending.value = false
  }
}

function openQuotaHistory() {
  if (!props.user)
    return
  isQuotaHistoryOpen.value = true
}
</script>

<template>
  <VDialog :model-value="props.modelValue" fullscreen persistent @update:model-value="onClose">
    <VCard class="d-flex flex-column fill-height rounded-0">
      <VForm ref="formRef" class="d-flex flex-column fill-height" @submit.prevent="onSave">
        <div class="admin-user-edit__topbar bg-primary text-white">
          <div class="admin-user-edit__topbar-main">
            <div class="admin-user-edit__topbar-titleWrap">
              <div class="admin-user-edit__topbar-icon">
                <VIcon icon="tabler-user-edit" size="22" />
              </div>
              <div class="admin-user-edit__topbar-copy">
                <div class="admin-user-edit__topbar-title">
                  Edit Pengguna
                </div>
              </div>
            </div>
            <VBtn icon="tabler-x" variant="text" class="text-white admin-user-edit__topbar-close" @click="onClose" />
          </div>
        </div>

        <div class="admin-user-edit__container pa-4 pa-md-6 pb-0">
          <div class="admin-user-edit__section-grid" role="tablist" aria-label="Navigasi edit pengguna">
            <button
              v-for="section in sectionOptions"
              :key="section.value"
              type="button"
              class="admin-user-edit__section-btn"
              :class="{ 'admin-user-edit__section-btn--active': tab === section.value }"
              :aria-selected="tab === section.value"
              @click="tab = section.value"
            >
              <VIcon :icon="section.icon" class="admin-user-edit__section-icon" />
              <div class="admin-user-edit__section-title">
                {{ section.title }}
              </div>
              <div class="admin-user-edit__section-desc">
                {{ section.desc }}
              </div>
              <span class="admin-user-edit__section-indicator" />
            </button>
          </div>
        </div>
        <VDivider class="mt-2" />

        <AppPerfectScrollbar class="admin-user-edit__scroll flex-grow-1 pa-4 pa-md-6" :native-scroll="isMobile">
          <div class="admin-user-edit__container">
            <VWindow v-model="tab" class="mt-2">
            <VWindowItem value="info">
              <VRow>
                <VCol cols="12">
                  <AppTextField
                    v-model="formData.full_name"
                    label="Nama Lengkap"
                    placeholder="Masukkan nama lengkap"
                    :disabled="isRestrictedAdmin"
                    prepend-inner-icon="tabler-user"
                  />
                </VCol>
                <VCol cols="12" md="6">
                  <AppTextField :model-value="props.user?.phone_number?.startsWith('+62') ? `0${props.user.phone_number.substring(3)}` : props.user?.phone_number" label="Nomor Telepon" disabled prepend-inner-icon="tabler-phone" />
                </VCol>
                <VCol cols="12" md="6">
                  <AppSelect v-model="formData.role" :items="roleOptions" label="Peran" :disabled="!authStore.isSuperAdmin" prepend-inner-icon="tabler-shield-check" />
                </VCol>
                <VCol v-if="formData.role === 'USER'" cols="12">
                  <VSwitch v-model="formData.is_tamping" label="Tamping" color="primary" inset :disabled="isRestrictedAdmin" />
                </VCol>
                <VCol v-if="formData.role === 'USER' && formData.is_tamping" cols="12" md="6">
                  <AppSelect v-model="formData.tamping_type" :items="tampingOptions" label="Jenis Tamping" placeholder="Pilih jenis tamping" :disabled="isRestrictedAdmin" prepend-inner-icon="tabler-building-bank" />
                </VCol>
                <VCol v-if="formData.role === 'USER' && !formData.is_tamping" cols="12" md="6">
                  <AppSelect v-model="formData.blok" :items="props.availableBloks" :loading="props.isAlamatLoading" label="Blok" placeholder="Pilih blok" :disabled="isRestrictedAdmin" prepend-inner-icon="tabler-building" />
                </VCol>
                <VCol v-if="formData.role === 'USER' && !formData.is_tamping" cols="12" md="6">
                  <AppSelect v-model="formData.kamar" :items="props.availableKamars" :loading="props.isAlamatLoading" label="Kamar" placeholder="Pilih kamar" :disabled="isRestrictedAdmin" prepend-inner-icon="tabler-door" />
                </VCol>
              </VRow>
            </VWindowItem>

            <VWindowItem value="akses">
              <VRow>
                <VCol cols="12">
                  <VRow>
                    <VCol cols="12" md="6">
                      <VSwitch v-model="formData.is_active" class="admin-switch" label="Akun Aktif" color="success" inset hint="Matikan untuk putus akses." />
                    </VCol>
                    <VCol cols="12" md="6">
                      <VSwitch v-model="formData.is_blocked" class="admin-switch" label="Blokir Akun" color="error" inset hint="Blokir = login ditolak." />
                    </VCol>
                  </VRow>
                </VCol>

                <VCol v-if="isBlocked" cols="12">
                  <AppTextField v-model="formData.blocked_reason" label="Alasan Blokir" placeholder="Contoh: Pelanggaran aturan penggunaan" prepend-inner-icon="tabler-alert-triangle" />
                </VCol>

                <VCol v-if="canAdminInject && formData.is_active === true" cols="12" md="6">
                  <VSwitch
                    v-if="isTargetAdminOrSuper !== true"
                    v-model="formData.is_unlimited_user"
                    class="admin-switch"
                    label="Akses Internet Unlimited"
                    color="primary"
                    inset
                    :disabled="!canToggleUnlimited"
                    :hint="!canToggleUnlimited && formData.role === 'USER' && debtTotalMb > 0 ? 'Inactive saat tunggakan masih ada.' : (!canToggleUnlimited && isDebtQuotaEnabled ? 'Inactive saat mode tunggakan aktif.' : undefined)"
                    persistent-hint
                  />
                  <VAlert v-else type="info" variant="tonal" density="compact" icon="tabler-shield-check">
                    Peran <strong>{{ formData.role }}</strong> secara otomatis mendapatkan akses <strong>Unlimited</strong>.
                  </VAlert>
                </VCol>

                <VCol v-if="canAdminInject && formData.is_active === true && isTargetAdminOrSuper !== true && formData.is_unlimited_user === true" cols="12" md="6">
                  <VSwitch
                    v-model="formData.unlimited_time"
                    class="admin-switch"
                    label="Unlimited Time (tanpa masa aktif/expiry)"
                    color="primary"
                    inset
                    hint="Jika aktif, expiry dikosongkan."
                  />
                </VCol>

                <VCol v-if="canAdminInject && formData.is_active === true && isTargetAdminOrSuper !== true" cols="12" md="6">
                  <VSwitch
                    v-model="isDebtQuotaEnabled"
                    class="admin-switch"
                    label="Tunggakan Kuota"
                    color="primary"
                    inset
                    :hint="!canToggleDebt ? 'Inactive saat mode unlimited aktif.' : 'Aktifkan untuk menambah/mengelola tunggakan.'"
                    persistent-hint
                    :disabled="!canToggleDebt"
                    v-if="formData.role === 'USER'"
                  />
                </VCol>

                <VCol v-if="formData.is_active !== true" cols="12">
                  <VAlert type="warning" variant="tonal" density="compact" icon="tabler-plug-connected-x">
                    Opsi kuota dan akses tidak tersedia karena akun ini sedang <strong>INACTIVE</strong>.
                  </VAlert>
                </VCol>

                <VCol v-if="isBlocked" cols="12">
                  <VAlert type="error" variant="tonal" density="compact" icon="tabler-ban">
                    Akun ini sedang <strong>BLOKIR</strong>. Akses login akan ditolak sampai dibuka kembali.
                  </VAlert>
                </VCol>

                <template v-if="canAdminInject && formData.is_active === true">
                  <VCol cols="12">
                    <VDivider class="my-2" />
                  </VCol>

                  <VCol cols="12" class="inject-actions">
                    <div class="text-overline">
                      Inject Kuota & Masa Aktif
                    </div>
                    <div class="inject-actions__buttons">
                      <VBtn
                        v-if="canAdminInject"
                        size="small" variant="tonal" color="warning"
                        :loading="isResetLoginLoading" prepend-icon="tabler-logout"
                        @click="resetUserLogin"
                      >
                        Reset Login
                      </VBtn>
                      <VBtn
                        v-if="canAdminInject"
                        size="small" variant="tonal" color="info"
                        :loading="isCheckingMikrotik" prepend-icon="tabler-refresh-dot"
                        @click="checkAndApplyMikrotikStatus"
                      >
                        Cek Live Mikrotik
                      </VBtn>
                    </div>
                  </VCol>

                  <VCol v-if="liveData" cols="12">
                    <VSheet rounded="lg" border class="pa-3 mb-4">
                      <VRow dense>
                        <VCol cols="12" sm="6">
                          <div class="text-caption text-disabled">
                            Sisa Kuota (DB)
                          </div><div class="font-weight-medium">
                            <span v-if="props.user?.is_unlimited_user">Tidak Terbatas</span>
                            <span v-else>{{ formatDataSize(liveData.db_sisa_kuota_mb) }}</span>
                          </div>
                        </VCol>
                        <VCol cols="12" sm="6">
                          <div class="text-caption text-disabled">
                            Pemakaian (MikroTik)
                          </div><div class="font-weight-medium">
                            {{ formatDataSize(liveData.mt_usage_mb) }}
                          </div>
                        </VCol>
                        <VCol cols="12">
                          <div class="text-caption text-disabled">
                            Masa Aktif (DB)
                          </div><div class="font-weight-medium">
                            {{ liveData.db_expiry_date != null ? new Date(liveData.db_expiry_date).toLocaleString('id-ID', { dateStyle: 'long', timeStyle: 'short' }) : 'Tidak ada' }}
                          </div>
                        </VCol>
                      </VRow>
                    </VSheet>
                  </VCol>

                  <VCol v-if="formData.is_unlimited_user !== true" cols="12" md="6">
                    <AppTextField
                      v-model="formData.add_gb"
                      label="Tambah Kuota (GB)"
                      type="number"
                      placeholder="Contoh: 10"
                      prepend-inner-icon="tabler-database-plus"
                      :disabled="isInjectBlockedByDebt"
                    />
                  </VCol>

                  <VCol v-if="formData.unlimited_time !== true" cols="12" md="6">
                    <AppTextField
                      v-model="formData.add_days"
                      label="Tambah Masa Aktif (Hari)"
                      type="number"
                      placeholder="Contoh: 30"
                      prepend-inner-icon="tabler-calendar-plus"
                      :disabled="isInjectBlockedByDebt"
                    />
                  </VCol>

                  <VCol v-if="isInjectBlockedByDebt" cols="12">
                    <VAlert type="warning" variant="tonal" density="compact" icon="tabler-alert-triangle">
                      Inject kuota dinonaktifkan karena user masih memiliki tunggakan.
                      Gunakan <strong>Tunggakan Kuota → Tambah Tunggakan (Pilih Paket)</strong> untuk memberi akses (advance),
                      atau lunasi/clear tunggakan terlebih dahulu.
                    </VAlert>
                  </VCol>

                    <VCol cols="12">
                      <VSheet rounded="lg" border class="pa-3 admin-user-edit__action-card">
                        <div class="admin-user-edit__card-header">
                          <div class="admin-user-edit__card-copy">
                            <div class="text-caption text-disabled">
                              Riwayat Mutasi Kuota
                            </div>
                            <div class="font-weight-medium">
                              Lihat pemakaian, pembelian, koreksi, dan reset baseline perangkat.
                            </div>
                          </div>
                          <div class="admin-user-edit__card-actions">
                            <VBtn
                              size="small"
                              variant="tonal"
                              prepend-icon="tabler-list-details"
                              @click="openQuotaHistory"
                            >
                              Lihat Riwayat
                            </VBtn>
                          </div>
                        </div>
                      </VSheet>
                    </VCol>

                  <template v-if="shouldShowDebtSection">
                    <VCol cols="12">
                      <VSheet rounded="lg" border class="pa-3 admin-user-edit__action-card">
                        <div class="admin-user-edit__card-header">
                          <div>
                            <div class="text-caption text-disabled">
                              Tunggakan Kuota
                            </div>
                            <div class="font-weight-medium">
                              Ringkasan tunggakan, tindak lanjut, dan akses detail riwayat pembayaran.
                            </div>
                          </div>
                          <div class="admin-user-edit__card-actions">
                            <VChip :color="debtStatusMeta.color" size="small" label>
                              <VIcon :icon="debtStatusMeta.icon" start size="16" />
                              {{ debtStatusMeta.text }}
                            </VChip>
                            <VBtn
                              size="small"
                              variant="tonal"
                              prepend-icon="tabler-list-details"
                              @click="openDebtLedger"
                            >
                              Detail Tunggakan
                            </VBtn>
                            <VBtn
                              v-if="debtTotalMb > 0"
                              size="small"
                              color="error"
                              variant="tonal"
                              class="admin-user-edit__inline-action"
                              prepend-icon="tabler-file-type-pdf"
                              @click="openDebtPdf"
                            >
                              PDF
                            </VBtn>
                            <VBtn
                              v-if="debtTotalMb > 0"
                              size="small"
                              color="success"
                              variant="tonal"
                              class="admin-user-edit__inline-action"
                              prepend-icon="tabler-brand-whatsapp"
                              :loading="isDebtWhatsappSending"
                              @click="sendDebtWhatsapp"
                            >
                              WhatsApp
                            </VBtn>
                          </div>
                        </div>
                        <div class="admin-user-edit__stat-grid mt-3">
                          <div class="admin-user-edit__stat-card">
                            <div class="text-caption text-disabled">
                              Total Tunggakan
                            </div>
                            <div class="font-weight-medium">
                              {{ debtTotalDisplay }}
                            </div>
                          </div>
                          <div class="admin-user-edit__stat-card">
                            <div class="text-caption text-disabled">
                              Tunggakan Otomatis
                            </div>
                            <div class="font-weight-medium">
                              {{ debtAutoDisplay }}
                            </div>
                          </div>
                          <div class="admin-user-edit__stat-card">
                            <div class="text-caption text-disabled">
                              Tunggakan Manual
                            </div>
                            <div class="font-weight-medium">
                              {{ debtManualDisplay }}
                            </div>
                          </div>
                        </div>
                      </VSheet>
                    </VCol>

                    <template v-if="isDebtQuotaEnabled">
                      <VCol cols="12">
                        <VCard variant="outlined" rounded="lg" class="admin-user-edit__detail-card">
                          <VCardText class="pa-4">
                            <div class="text-subtitle-2 font-weight-medium">
                              Tambah Tunggakan Baru
                            </div>
                            <div class="text-caption text-medium-emphasis mt-1">
                              Pilih paket, tetapkan tanggal pencatatan, lalu simpan perubahan untuk menambah advance/tunggakan baru.
                            </div>
                          </VCardText>
                        </VCard>
                      </VCol>

                      <VCol cols="12" md="6">
                        <AppSelect
                          v-model="formData.debt_package_id"
                          :items="debtPackageOptions"
                          label="Tambah Tunggakan (Pilih Paket)"
                          placeholder="Silakan pilih paket"
                          prepend-inner-icon="tabler-alert-circle"
                          :loading="isPackagesLoading"
                          density="comfortable"
                          hide-details
                        />
                      </VCol>

                      <VCol cols="12" md="6">
                        <AppDateTimePicker
                          v-model="formData.debt_date"
                          label="Tanggal Tunggakan"
                          placeholder="Pilih tanggal"
                          prepend-inner-icon="tabler-calendar"
                          density="comfortable"
                          hide-details
                          :config="{ dateFormat: 'Y-m-d', enableTime: false, static: false, position: 'below' }"
                        />
                      </VCol>

                      <VCol cols="12" md="6">
                        <VAlert type="info" variant="tonal" density="compact" icon="tabler-calendar-due" class="text-caption">
                          Jatuh tempo: <strong>akhir bulan</strong> (otomatis)
                        </VAlert>
                      </VCol>

                      <VCol cols="12">
                        <AppTextField
                          v-model="formData.debt_note"
                          label="Catatan Tunggakan (Opsional)"
                          placeholder="Contoh: advance untuk akses sementara"
                          prepend-inner-icon="tabler-notes"
                          density="comfortable"
                          hide-details
                        />
                      </VCol>
                    </template>
                  </template>

                  <!-- === Koreksi Kuota Langsung — Super Admin Only === -->
                  <template v-if="authStore.isSuperAdmin">
                    <VCol cols="12">
                      <VDivider class="my-2" />
                    </VCol>

                    <VCol cols="12">
                      <VSheet rounded="lg" border class="pa-4 admin-user-edit__action-card admin-user-edit__quota-adjust-card">
                        <div class="admin-user-edit__card-header">
                          <div>
                            <div class="text-overline d-flex align-center gap-1">
                              <VIcon icon="tabler-shield-bolt" size="18" color="warning" />
                              Koreksi Kuota Langsung
                              <VChip color="warning" size="x-small" label class="ml-1">
                                SuperAdmin
                              </VChip>
                            </div>
                            <div class="text-body-2 mt-2 text-medium-emphasis">
                              Ubah nilai kuota beli dan kuota terpakai secara langsung. Input default memakai GB, lalu sistem tetap menyimpan hasil koreksi dalam MB.
                            </div>
                          </div>
                          <div class="admin-user-edit__card-actions">
                            <VBtn
                              size="small"
                              color="info"
                              variant="tonal"
                              prepend-icon="tabler-refresh"
                              :loading="isSaQuotaAutoFilling"
                              @click="autoFillSaQuotaFromDb"
                            >
                              Ambil dari DB
                            </VBtn>
                          </div>
                        </div>

                        <div class="admin-user-edit__stat-grid mt-4">
                          <div class="admin-user-edit__stat-card">
                            <div class="text-caption text-disabled">
                              Kuota Dibeli
                            </div>
                            <div class="font-weight-medium">
                              {{ formatQuotaValueByUnit(formData.total_quota_purchased_mb, saQuotaInputUnit) }}
                            </div>
                          </div>
                          <div class="admin-user-edit__stat-card">
                            <div class="text-caption text-disabled">
                              Kuota Terpakai
                            </div>
                            <div class="font-weight-medium">
                              {{ formatQuotaValueByUnit(Number(formData.total_quota_used_mb), saQuotaInputUnit) }}
                            </div>
                          </div>
                          <div class="admin-user-edit__stat-card">
                            <div class="text-caption text-disabled">
                              Sisa Kuota
                            </div>
                            <div class="font-weight-medium">
                              {{ formatQuotaValueByUnit(saQuotaRemainingMb, saQuotaInputUnit) }}
                            </div>
                          </div>
                        </div>

                        <div class="sa-unit-selector mt-4">
                          <VBtn
                            size="small"
                            class="sa-unit-selector__btn"
                            :color="saQuotaInputUnit === 'gb' ? 'warning' : 'secondary'"
                            :variant="saQuotaInputUnit === 'gb' ? 'flat' : 'outlined'"
                            @click="saQuotaInputUnit = 'gb'"
                          >
                            GB untuk operasional
                          </VBtn>
                          <VBtn
                            size="small"
                            class="sa-unit-selector__btn"
                            :color="saQuotaInputUnit === 'mb' ? 'warning' : 'secondary'"
                            :variant="saQuotaInputUnit === 'mb' ? 'flat' : 'outlined'"
                            @click="saQuotaInputUnit = 'mb'"
                          >
                            MB untuk presisi
                          </VBtn>
                        </div>
                        <div class="text-caption text-medium-emphasis mt-2">
                          {{ saQuotaUnitHint }}
                        </div>
                      </VSheet>
                    </VCol>

                    <VCol cols="12" md="6">
                      <AppTextField
                        v-model.number="saQuotaPurchasedInput"
                        :label="`Total Kuota Dibeli (${saQuotaUnitLabel})`"
                        type="number"
                        :placeholder="saQuotaInputUnit === 'gb' ? 'Contoh: 13.5' : 'Contoh: 13824'"
                        prepend-inner-icon="tabler-database"
                        :step="saQuotaInputUnit === 'gb' ? 0.01 : 1"
                        min="0"
                        :hint="saQuotaPurchasedCurrentText"
                        persistent-hint
                      />
                    </VCol>

                    <VCol cols="12" md="6">
                      <AppTextField
                        v-model.number="saQuotaUsedInput"
                        :label="`Kuota Terpakai (${saQuotaUnitLabel})`"
                        type="number"
                        :placeholder="saQuotaInputUnit === 'gb' ? 'Contoh: 2.1' : 'Contoh: 2150'"
                        prepend-inner-icon="tabler-database-minus"
                        :step="saQuotaInputUnit === 'gb' ? 0.01 : 1"
                        min="0"
                        :hint="saQuotaUsedCurrentText"
                        persistent-hint
                      />
                    </VCol>

                    <VCol cols="12">
                      <AppTextField
                        v-model="saQuotaForm.reason"
                        label="Alasan / Catatan Koreksi"
                        placeholder="Wajib diisi. Contoh: Koreksi inflasi bug lock_ttl 2026-03-09"
                        prepend-inner-icon="tabler-notes"
                      />
                    </VCol>

                    <VCol cols="12">
                      <VBtn
                        color="warning"
                        variant="tonal"
                        :loading="isSaQuotaLoading"
                        :disabled="!saQuotaForm.reason || (saQuotaForm.set_purchased_mb === null && saQuotaForm.set_used_mb === null)"
                        prepend-icon="tabler-adjustments"
                        @click="applyDirectQuotaAdjust"
                      >
                        Simpan Koreksi Kuota
                      </VBtn>
                    </VCol>
                  </template>

                  <VCol cols="12">
                    <VDivider class="my-2" />
                  </VCol>
                </template>
              </VRow>
            </VWindowItem>
            </VWindow>
          </div>
        </AppPerfectScrollbar>

        <VDivider />
        <VCardActions class="pa-4 d-flex" :class="isMobile ? 'flex-column ga-3' : 'justify-space-between'">
          <div class="d-flex" :class="isMobile ? 'flex-column ga-2 w-100' : 'ga-2'">
            <VBtn
              variant="tonal"
              color="secondary"
              :block="isMobile"
              @click="onClose"
            >
              Batal
            </VBtn>
            <VBtn
              v-if="(authStore.isAdmin || authStore.isSuperAdmin) && isTargetAdminOrSuper"
              variant="tonal"
              color="warning"
              :block="isMobile"
              :loading="isResetPasswordLoading"
              prepend-icon="tabler-key"
              @click="resetUserPassword"
            >
              Reset Password
            </VBtn>
          </div>
          <VBtn
            type="submit"
            color="primary"
            :block="isMobile"
            :loading="props.loading"
            :disabled="isSaveDisabled"
            prepend-icon="tabler-device-floppy"
          >
            Simpan Perubahan
          </VBtn>
        </VCardActions>
      </VForm>
    </VCard>
  </VDialog>

  <UserDebtLedgerDialog v-model="isDebtLedgerOpen" :user="props.user" />
  <UserQuotaHistoryDialog v-model="isQuotaHistoryOpen" :user="props.user" />
</template>

<style scoped>
.admin-user-edit__container {
  width: 100%;
  max-width: 960px;
  margin-inline: auto;
}

.admin-user-edit__topbar {
  padding: 16px 20px 14px;
  background: linear-gradient(135deg, rgb(var(--v-theme-primary)) 0%, rgba(var(--v-theme-primary), 0.82) 100%);
  box-shadow: inset 0 -1px 0 rgba(255, 255, 255, 0.08);
}

.admin-user-edit__topbar-main {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.admin-user-edit__topbar-titleWrap {
  display: flex;
  align-items: center;
  gap: 14px;
  min-width: 0;
  flex: 1 1 auto;
}

.admin-user-edit__topbar-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 42px;
  height: 42px;
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.14);
  flex: 0 0 auto;
}

.admin-user-edit__topbar-copy {
  min-width: 0;
}

.admin-user-edit__topbar-title {
  font-size: 1.2rem;
  font-weight: 700;
  line-height: 1.25;
  letter-spacing: 0.01em;
}

.admin-user-edit__topbar-subtitle {
  margin-top: 4px;
  max-width: 760px;
  font-size: 0.92rem;
  line-height: 1.5;
  opacity: 0.86;
}

.admin-user-edit__topbar-close {
  flex: 0 0 auto;
  margin-top: -4px;
}

.admin-user-edit__scroll {
  min-height: 0;
}

.admin-user-edit__scroll:deep(.app-perfect-scrollbar--native) {
  min-height: 0;
}

.admin-user-edit__action-card {
  background: rgba(var(--v-theme-surface), 0.72);
  border-color: rgba(var(--v-theme-on-surface), 0.08) !important;
  box-shadow: 0 18px 38px rgba(15, 23, 42, 0.06);
}

.admin-user-edit__card-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.admin-user-edit__card-copy {
  min-width: 0;
  flex: 1 1 auto;
}

.admin-user-edit__card-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  flex-wrap: wrap;
}

.admin-user-edit__inline-action {
  min-width: 104px;
}

.admin-user-edit__stat-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

.admin-user-edit__stat-card {
  border: 1px solid rgba(var(--v-theme-on-surface), 0.08);
  border-radius: 14px;
  padding: 14px 16px;
  background: rgba(var(--v-theme-surface), 0.96);
}

.admin-user-edit__detail-card {
  border-style: dashed;
  box-shadow: 0 0 0 1px rgba(var(--v-theme-primary), 0.18) inset;
}

.admin-user-edit__section-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.admin-user-edit__section-btn {
  position: relative;
  display: flex;
  min-height: 128px;
  flex-direction: column;
  align-items: flex-start;
  gap: 8px;
  padding: 18px 18px 16px;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.08);
  border-radius: 20px;
  background:
    linear-gradient(180deg, rgba(var(--v-theme-surface), 0.98) 0%, rgba(var(--v-theme-surface), 0.88) 100%),
    linear-gradient(135deg, rgba(var(--v-theme-primary), 0.08) 0%, rgba(var(--v-theme-on-surface), 0.02) 100%);
  box-shadow: 0 18px 40px rgba(15, 23, 42, 0.06);
  text-align: left;
  transition: transform 0.18s ease, box-shadow 0.18s ease, border-color 0.18s ease;
}

.admin-user-edit__section-btn:hover {
  transform: translateY(-1px);
  box-shadow: 0 20px 44px rgba(15, 23, 42, 0.08);
}

.admin-user-edit__section-btn--active {
  border-color: rgba(var(--v-theme-primary), 0.28);
  box-shadow: 0 22px 52px rgba(var(--v-theme-primary), 0.14);
}

.admin-user-edit__section-icon {
  font-size: 28px;
  color: rgb(var(--v-theme-primary));
}

.admin-user-edit__section-title {
  font-size: 1.05rem;
  font-weight: 600;
  line-height: 1.25;
  text-align: left;
}

.admin-user-edit__section-desc {
  font-size: 0.88rem;
  line-height: 1.45;
  text-align: left;
  color: rgba(var(--v-theme-on-surface), 0.64);
}

.admin-user-edit__section-btn--active .admin-user-edit__section-desc {
  color: rgba(var(--v-theme-on-surface), 0.78);
}

.admin-user-edit__section-indicator {
  width: 14px;
  height: 14px;
  border-radius: 999px;
  border: 2px solid rgba(var(--v-theme-on-surface), 0.24);
  background: transparent;
  transition: border-color 0.2s ease, background-color 0.2s ease, box-shadow 0.2s ease;
}

.admin-user-edit__section-btn--active .admin-user-edit__section-indicator {
  border-color: rgba(var(--v-theme-primary), 0.92);
  background: rgb(var(--v-theme-primary));
  box-shadow: 0 0 0 4px rgba(var(--v-theme-primary), 0.18);
}

.inject-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.inject-actions__buttons {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.sa-unit-selector {
  display: inline-flex;
  flex-wrap: wrap;
  gap: 8px;
}

.sa-unit-selector__btn {
  min-width: 184px;
}

.admin-switch :deep(.v-messages__message) {
  line-height: 1.25rem;
}

@media (max-width: 600px) {
  .admin-user-edit__topbar {
    padding: 14px 14px 12px;
  }

  .admin-user-edit__topbar-main {
    align-items: flex-start;
    gap: 10px;
  }

  .admin-user-edit__topbar-titleWrap {
    gap: 10px;
  }

  .admin-user-edit__topbar-icon {
    width: 36px;
    height: 36px;
    border-radius: 12px;
  }

  .admin-user-edit__topbar-title {
    font-size: 1.02rem;
  }

  .admin-user-edit__topbar-subtitle {
    font-size: 0.8rem;
  }

  .admin-user-edit__topbar-meta {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 8px;
  }

  .admin-user-edit__meta-pill {
    width: 100%;
    min-height: 0;
    padding: 8px 10px;
    gap: 6px;
    border-radius: 12px;
    font-size: 0.78rem;
  }

  .admin-user-edit__meta-pillCopy span:last-child {
    display: -webkit-box;
    overflow: hidden;
    line-clamp: 2;
    -webkit-box-orient: vertical;
    -webkit-line-clamp: 2;
    white-space: normal;
  }

  .admin-user-edit__meta-pillCopy small {
    display: none;
  }

  .admin-user-edit__meta-pillLabel {
    font-size: 0.62rem;
  }

  .admin-user-edit__meta-pill--status {
    display: none;
  }

  .admin-user-edit__section-grid {
    gap: 12px;
  }

  .admin-user-edit__section-btn {
    min-height: 94px;
    gap: 6px;
    padding: 14px 10px;
  }

  .admin-user-edit__section-icon {
    font-size: 22px;
  }

  .admin-user-edit__section-title {
    font-size: 0.95rem;
  }

  .admin-user-edit__section-desc {
    display: none;
  }

  .admin-user-edit__section-indicator {
    width: 12px;
    height: 12px;
  }

  .inject-actions {
    flex-direction: column;
    align-items: stretch;
  }

  .admin-user-edit__card-header {
    flex-direction: column;
  }

  .admin-user-edit__card-actions {
    width: 100%;
    justify-content: stretch;
  }

  .admin-user-edit__card-actions :deep(.v-btn),
  .admin-user-edit__card-actions :deep(.v-chip) {
    width: 100%;
    justify-content: center;
  }

  .admin-user-edit__inline-action {
    min-width: 0;
  }

  .admin-user-edit__stat-grid {
    grid-template-columns: 1fr;
  }

  .inject-actions__buttons {
    width: 100%;
    flex-direction: column;
    align-items: stretch;
  }

  .inject-actions__buttons :deep(.v-btn) {
    width: 100%;
  }

  .sa-unit-selector {
    width: 100%;
  }

  .sa-unit-selector :deep(.v-btn) {
    flex: 1 1 0;
  }

  .sa-unit-selector__btn {
    min-width: 0;
  }
}
</style>
