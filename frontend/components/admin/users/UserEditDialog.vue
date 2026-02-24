<script lang="ts" setup>
import type { VForm } from 'vuetify/components'
import AppSelect from '@core/components/app-form-elements/AppSelect.vue'
import AppTextField from '@core/components/app-form-elements/AppTextField.vue'
import AppDateTimePicker from '@core/components/app-form-elements/AppDateTimePicker.vue'
import CustomRadiosWithIcon from '@core/components/app-form-elements/CustomRadiosWithIcon.vue'
import { computed, nextTick, reactive, ref, watch } from 'vue'
import { useDisplay } from 'vuetify'
import { useSnackbar } from '@/composables/useSnackbar'
import { useAuthStore } from '@/store/auth'
import { TAMPING_OPTION_ITEMS } from '~/utils/constants'
import UserDebtLedgerDialog from '@/components/admin/users/UserDebtLedgerDialog.vue'

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
  total_quota_purchased_mb: number
  total_quota_used_mb: number
  manual_debt_mb?: number
  quota_debt_auto_mb?: number
  quota_debt_manual_mb?: number
  quota_debt_total_mb?: number
  quota_expiry_date: string | null
  is_blocked?: boolean
  blocked_reason?: string | null
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
const isDebtQuotaEnabled = ref(false)

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
    if (formData.debt_date == null || String(formData.debt_date).trim() === '')
      formData.debt_date = getTodayYmd()
    fetchAdminPackages().catch(() => {})
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
      icon: { icon: 'tabler-user', size: '28' },
    },
    {
      title: 'Akses & Kuota',
      desc: 'Akses, inject, dan tunggakan kuota.',
      value: 'akses',
      icon: { icon: 'tabler-shield-check', size: '28' },
    },
  ]
})

const shouldShowDebtSection = computed(() => {
  if (formData.role !== 'USER')
    return false
  return debtTotalMb.value > 0 || isDebtQuotaEnabled.value === true
})

function toNumberOrZero(value: unknown): number {
  if (value === '' || value == null)
    return 0
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : 0
}

const debtAutoMb = computed(() => (props.user?.is_unlimited_user === true ? 0 : Number(props.user?.quota_debt_auto_mb ?? 0)))
const debtManualMb = computed(() => (props.user?.is_unlimited_user === true ? 0 : Number(props.user?.quota_debt_manual_mb ?? props.user?.manual_debt_mb ?? 0)))
const debtTotalMb = computed(() => (props.user?.is_unlimited_user === true ? 0 : Number(props.user?.quota_debt_total_mb ?? (debtAutoMb.value + debtManualMb.value))))

const isInjectBlockedByDebt = computed(() => {
  if (formData.is_unlimited_user === true)
    return false
  if (formData.role !== 'USER')
    return false
  return debtTotalMb.value > 0
})

const debtPackageOptions = computed(() => {
  return adminPackages.value
    .filter(pkg => pkg.is_active === true && Number(pkg.data_quota_gb ?? 0) > 0)
    .map(pkg => ({
      title: `${pkg.name} — ${Number(pkg.data_quota_gb).toLocaleString('id-ID')} GB — Rp ${Number(pkg.price ?? 0).toLocaleString('id-ID')}`,
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
    text: hasDebt ? 'ADA TUNGGAKAN' : 'TIDAK ADA TUNGGAKAN',
    color: hasDebt ? 'warning' : 'success',
    icon: hasDebt ? 'tabler-alert-triangle' : 'tabler-circle-check',
  }
})

function formatMb(value: number) {
  if (!Number.isFinite(value))
    return '0'
  return value.toLocaleString('id-ID', { maximumFractionDigits: 2 })
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
        db_sisa_kuota_mb: (props.user.total_quota_purchased_mb ?? 0) - (props.user.total_quota_used_mb ?? 0),
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
    `Reset login untuk ${props.user.full_name} (${props.user.phone_number})?\n\nAksi ini akan:\n- Menghapus semua refresh token\n- Menghapus semua device (user_devices) agar enroll ulang\n- Membersihkan state MikroTik (cookie, address-list, ip-binding, DHCP lease, ARP, dan sesi aktif)\n\nStatus kuota/paket di database tidak diubah.`,
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
</script>

<template>
  <VDialog :model-value="props.modelValue" fullscreen persistent @update:model-value="onClose">
    <VCard class="d-flex flex-column fill-height rounded-0">
      <VForm ref="formRef" class="d-flex flex-column fill-height" @submit.prevent="onSave">
        <VToolbar color="primary" density="comfortable">
          <VToolbarTitle class="text-white d-flex align-center ga-2">
            <VIcon icon="tabler-user-edit" />
            <span class="headline text-white">Edit Pengguna</span>
          </VToolbarTitle>
          <VSpacer />
          <VBtn icon="tabler-x" variant="text" class="text-white" @click="onClose" />
        </VToolbar>

        <div class="admin-user-edit__container pa-4 pa-md-6 pb-0">
          <CustomRadiosWithIcon
            v-model:selected-radio="tab"
            :radio-content="sectionOptions"
            :grid-column="{ cols: '12', sm: '6' }"
          />
        </div>
        <VDivider class="mt-2" />

        <AppPerfectScrollbar class="flex-grow-1 pa-4 pa-md-6">
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
                  <VSwitch v-if="isTargetAdminOrSuper !== true" v-model="formData.is_unlimited_user" class="admin-switch" label="Akses Internet Unlimited" color="primary" inset />
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
                    hint="Aktifkan untuk menambah/mengelola tunggakan."
                    v-if="formData.role === 'USER'"
                  />
                </VCol>

                <VCol v-if="formData.is_active !== true" cols="12">
                  <VAlert type="warning" variant="tonal" density="compact" icon="tabler-plug-connected-x">
                    Opsi kuota dan akses tidak tersedia karena akun ini sedang <strong>NONAKTIF</strong>.
                  </VAlert>
                </VCol>

                <VCol v-if="isBlocked" cols="12">
                  <VAlert type="error" variant="tonal" density="compact" icon="tabler-ban">
                    Akun ini sedang <strong>DIBLOKIR</strong>. Akses login akan ditolak sampai dibuka kembali.
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
                            {{ liveData.db_sisa_kuota_mb.toFixed(2) }} MB
                          </div>
                        </VCol>
                        <VCol cols="12" sm="6">
                          <div class="text-caption text-disabled">
                            Pemakaian (MikroTik)
                          </div><div class="font-weight-medium">
                            {{ liveData.mt_usage_mb.toFixed(2) }} MB
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

                  <template v-if="shouldShowDebtSection">
                    <VCol cols="12">
                      <div class="text-overline">
                        Tunggakan Kuota
                      </div>
                    </VCol>

                    <VCol cols="12">
                      <VSheet rounded="lg" border class="pa-3">
                        <div class="d-flex justify-space-between align-center mb-2">
                          <div class="text-caption text-disabled">
                            Status Tunggakan
                          </div>
                          <div class="d-flex align-center gap-2">
                            <VBtn
                              v-if="debtTotalMb > 0"
                              icon="tabler-list-details"
                              size="x-small"
                              variant="text"
                              :title="'Lihat riwayat tunggakan'"
                              @click="openDebtLedger"
                            />
                            <VBtn
                              v-if="debtTotalMb > 0"
                              icon="tabler-printer"
                              size="x-small"
                              variant="text"
                              :title="'PDF (cetak / simpan)'"
                              @click="openDebtPdf"
                            />
                            <VChip :color="debtStatusMeta.color" size="x-small" label>
                              <VIcon :icon="debtStatusMeta.icon" start size="16" />
                              {{ debtStatusMeta.text }}
                            </VChip>
                          </div>
                        </div>
                        <VRow dense>
                          <VCol cols="12" sm="4">
                            <div class="text-caption text-disabled">
                              Total Tunggakan
                            </div>
                            <div class="font-weight-medium">
                              {{ formatMb(debtTotalMb) }} MB
                            </div>
                          </VCol>
                          <VCol cols="12" sm="4">
                            <div class="text-caption text-disabled">
                              Tunggakan Otomatis
                            </div>
                            <div class="font-weight-medium">
                              {{ formatMb(debtAutoMb) }} MB
                            </div>
                          </VCol>
                          <VCol cols="12" sm="4">
                            <div class="text-caption text-disabled">
                              Tunggakan Manual
                            </div>
                            <div class="font-weight-medium">
                              {{ formatMb(debtManualMb) }} MB
                            </div>
                          </VCol>
                        </VRow>
                      </VSheet>
                    </VCol>

                    <template v-if="isDebtQuotaEnabled">
                      <VCol cols="12" md="6">
                        <AppSelect v-model="formData.debt_package_id" :items="debtPackageOptions" label="Tambah Tunggakan (Pilih Paket)" prepend-inner-icon="tabler-alert-circle" :loading="isPackagesLoading" />
                      </VCol>

                      <VCol cols="12" md="6">
                        <AppDateTimePicker
                          v-model="formData.debt_date"
                          label="Tanggal Tunggakan"
                          placeholder="Pilih tanggal"
                          prepend-inner-icon="tabler-calendar"
                          :config="{ dateFormat: 'Y-m-d', enableTime: false }"
                        />
                      </VCol>

                      <VCol cols="12">
                        <AppTextField v-model="formData.debt_note" label="Catatan Tunggakan (Opsional)" placeholder="Contoh: advance untuk akses sementara" prepend-inner-icon="tabler-notes" />
                      </VCol>
                    </template>
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
        <VCardActions class="pa-4 d-flex" :class="isMobile ? 'flex-column ga-3' : 'justify-end'">
          <VBtn
            variant="tonal"
            color="secondary"
            :block="isMobile"
            @click="onClose"
          >
            Batal
          </VBtn>
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
</template>

<style scoped>
.admin-user-edit__container {
  width: 100%;
  max-width: 960px;
  margin-inline: auto;
}

.dialog-titlebar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  width: 100%;
}

.dialog-titlebar__title {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}

.dialog-titlebar__actions {
  display: flex;
  align-items: center;
  gap: 8px;
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

.admin-switch :deep(.v-messages__message) {
  line-height: 1.25rem;
}

@media (max-width: 600px) {
  .dialog-titlebar {
    flex-direction: column;
    align-items: flex-start;
  }

  .dialog-titlebar__actions {
    width: 100%;
    justify-content: flex-end;
  }

  .inject-actions {
    flex-direction: column;
    align-items: stretch;
  }

  .inject-actions__buttons {
    width: 100%;
    flex-direction: column;
    align-items: stretch;
  }

  .inject-actions__buttons :deep(.v-btn) {
    width: 100%;
  }
}
</style>
