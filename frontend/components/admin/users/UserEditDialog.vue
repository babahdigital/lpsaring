<script lang="ts" setup>
import type { VForm } from 'vuetify/components'
import AppSelect from '@core/components/app-form-elements/AppSelect.vue'
import AppTextField from '@core/components/app-form-elements/AppTextField.vue'
import { computed, nextTick, reactive, ref, watch } from 'vue'
import { useSnackbar } from '@/composables/useSnackbar'
import { useAuthStore } from '@/store/auth'
import { TAMPING_OPTION_ITEMS } from '~/utils/constants'

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
const formRef = ref<InstanceType<typeof VForm> | null>(null)

function getInitialFormData(): Partial<User & { add_gb: number, add_days: number }> {
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
    add_gb: 0,
    add_days: 0,
  }
}

const formData = reactive(getInitialFormData())
const isCheckingMikrotik = ref(false)
const liveData = ref<LiveData | null>(null)

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
      add_gb: 0,
      add_days: 0,
      is_unlimited_user: isEditingAdminOrSuper || newUser.is_unlimited_user,
    })
  }
}, { immediate: true })

watch(() => props.modelValue, (isOpen) => {
  if (isOpen) {
    liveData.value = null
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
    case 'KOMANDAN':
      if (formData.is_unlimited_user !== true) {
        formData.mikrotik_profile_name = defaults.profile_active || defaults.profile_user
      }
      formData.mikrotik_server_name = defaults.server_user
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

async function onSave() {
  if (!formRef.value)
    return
  const { valid } = await formRef.value.validate()
  if (valid) {
    const payload = { ...formData }

    if (payload.is_unlimited_user === true) {
      payload.mikrotik_profile_name = mikrotikDefaults.value.profile_unlimited
    }

    if (payload.is_unlimited_user !== true)
      payload.mikrotik_profile_name = mikrotikDefaults.value.profile_active || mikrotikDefaults.value.profile_user

    payload.mikrotik_server_name = mikrotikDefaults.value.server_user

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
</script>

<template>
  <VDialog :model-value="props.modelValue" max-width="700px" persistent scrollable @update:model-value="onClose">
    <VCard>
      <VForm ref="formRef" @submit.prevent="onSave">
        <VCardTitle class="pa-4 d-flex align-center bg-primary rounded-t-lg">
          <VIcon icon="tabler-user-edit" start />
          <span class="headline text-white">Edit Pengguna</span>
          <VSpacer />
          <VBtn icon="tabler-x" variant="text" size="small" class="text-white" @click="onClose" />
        </VCardTitle>

        <VTabs v-model="tab" grow class="rounded-0">
          <VTab value="info">
            Info Pengguna
          </VTab>
          <VTab value="akses">
            Akses & Kuota
          </VTab>
        </VTabs>
        <VDivider />

        <VCardText class="pa-5" style="max-height: 65vh; overflow-y: auto;">
          <VWindow v-model="tab" class="mt-2">
            <VWindowItem value="info">
              <VRow>
                <VCol cols="12">
                  <AppTextField v-model="formData.full_name" label="Nama Lengkap" :disabled="isRestrictedAdmin" prepend-inner-icon="tabler-user" />
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
                  <AppSelect v-model="formData.tamping_type" :items="tampingOptions" label="Jenis Tamping" :disabled="isRestrictedAdmin" prepend-inner-icon="tabler-building-bank" />
                </VCol>
                <VCol v-if="formData.role === 'USER' && !formData.is_tamping" cols="12" md="6">
                  <AppSelect v-model="formData.blok" :items="props.availableBloks" :loading="props.isAlamatLoading" label="Blok" :disabled="isRestrictedAdmin" prepend-inner-icon="tabler-building" />
                </VCol>
                <VCol v-if="formData.role === 'USER' && !formData.is_tamping" cols="12" md="6">
                  <AppSelect v-model="formData.kamar" :items="props.availableKamars" :loading="props.isAlamatLoading" label="Kamar" :disabled="isRestrictedAdmin" prepend-inner-icon="tabler-door" />
                </VCol>
              </VRow>
            </VWindowItem>

            <VWindowItem value="akses">
              <VRow>
                <VCol cols="12">
                  <VSwitch v-model="formData.is_active" label="Akun Aktif" color="success" inset hint="Menonaktifkan akan memutus akses pengguna." persistent-hint />
                </VCol>

                <VCol cols="12">
                  <VSwitch v-model="formData.is_blocked" label="Blokir Akun" color="error" inset hint="Blokir berbeda dengan nonaktif. Akun tetap tercatat, tetapi akses ditolak." persistent-hint />
                </VCol>

                <VCol v-if="isBlocked" cols="12">
                  <AppTextField v-model="formData.blocked_reason" label="Alasan Blokir" placeholder="Contoh: Pelanggaran aturan penggunaan" prepend-inner-icon="tabler-alert-triangle" />
                </VCol>

                <VCol v-if="canAdminInject && formData.is_active === true" cols="12">
                  <VSwitch v-if="isTargetAdminOrSuper !== true" v-model="formData.is_unlimited_user" label="Akses Internet Unlimited" color="primary" inset />
                  <VAlert v-else type="info" variant="tonal" density="compact" icon="tabler-shield-check">
                    Peran <strong>{{ formData.role }}</strong> secara otomatis mendapatkan akses <strong>Unlimited</strong>.
                  </VAlert>
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

                  <VCol cols="12" class="d-flex justify-space-between align-center">
                    <div class="text-overline">
                      Inject Kuota & Masa Aktif
                    </div>
                    <VBtn
                      v-if="canAdminInject"
                      size="small" variant="tonal" color="info"
                      :loading="isCheckingMikrotik" prepend-icon="tabler-refresh-dot"
                      @click="checkAndApplyMikrotikStatus"
                    >
                      Cek Live Mikrotik
                    </VBtn>
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
                    <AppTextField v-model.number="formData.add_gb" label="Tambah Kuota (GB)" type="number" prepend-inner-icon="tabler-database-plus" />
                  </VCol>

                  <VCol cols="12" md="6">
                    <AppTextField v-model.number="formData.add_days" label="Tambah Masa Aktif (Hari)" type="number" prepend-inner-icon="tabler-calendar-plus" />
                  </VCol>

                  <VCol cols="12">
                    <VDivider class="my-2" />
                  </VCol>
                </template>
              </VRow>
            </VWindowItem>
          </VWindow>
        </VCardText>
        <VDivider />

        <VCardActions class="pa-4 d-flex">
          <VSpacer />
          <VBtn variant="tonal" color="secondary" @click="onClose">
            Batal
          </VBtn>
          <VBtn type="submit" color="primary" :loading="props.loading" :disabled="isSaveDisabled" prepend-icon="tabler-device-floppy">
            Simpan Perubahan
          </VBtn>
        </VCardActions>
      </VForm>
    </VCard>
  </VDialog>
</template>
