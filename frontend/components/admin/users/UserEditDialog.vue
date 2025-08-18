<script lang="ts" setup>
import type { VForm } from 'vuetify/components'

import AppSelect from '@core/components/app-form-elements/AppSelect.vue'
import AppTextField from '@core/components/app-form-elements/AppTextField.vue'
import { useRuntimeConfig } from '#app'
import { computed, nextTick, reactive, ref, watch } from 'vue'

import { useSnackbar } from '@/composables/useSnackbar'
import { useAuthStore } from '@/store/auth'

const props = defineProps<{
  modelValue: boolean
  user: User | null
  availableBloks: string[]
  availableKamars: string[]
  loading: boolean
  isAlamatLoading: boolean
}>()
const emit = defineEmits(['update:modelValue', 'save', 'resetHotspot', 'generateAdminPass'])
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
  is_unlimited_user: boolean
  mikrotik_server_name: string | null
  mikrotik_profile_name: string | null
  total_quota_purchased_mb: number
  total_quota_used_mb: number
  quota_expiry_date: string | null
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
    is_unlimited_user: false,
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
const adminAccessType = ref<'admin' | 'komandan' | null>(null)
const isCheckingMikrotik = ref(false)
const liveData = ref<LiveData | null>(null)

const isRestrictedAdmin = computed(() => authStore.isAdmin && !authStore.isSuperAdmin)

const canAdminInject = computed(() => {
  if (authStore.isSuperAdmin)
    return true
  if (isRestrictedAdmin.value && formData.role === 'KOMANDAN')
    return true
  return false
})

const isSaveDisabled = computed(() => {
  if (isRestrictedAdmin.value !== true)
    return false
  return formData.role === 'ADMIN' || formData.role === 'SUPER_ADMIN'
})

const isTargetAdminOrSuper = computed(() => formData.role === 'ADMIN' || formData.role === 'SUPER_ADMIN')

const superAdminProfileOptions = ['admin', 'user', 'expired', 'komandan', 'support', 'unlimited', 'inactive']
const superAdminServerOptions = ['srv-admin', 'srv-komandan', 'srv-support', 'srv-user']
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

    if (authStore.isAdmin && !authStore.isSuperAdmin) {
      if (formData.mikrotik_server_name === 'srv-admin')
        adminAccessType.value = 'admin'
      else if (formData.mikrotik_server_name === 'srv-komandan')
        adminAccessType.value = 'komandan'
      else adminAccessType.value = null
    }
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
  const runtimeConfig = useRuntimeConfig()

  // Use values from environment via runtimeConfig
  const profileAktif = runtimeConfig.public.profileAktifName || 'profile-aktif'
  const _profileUnlimited = runtimeConfig.public.profileUnlimitedName || 'profile-unlimited'

  switch (role) {
    case 'USER':
      if (formData.is_unlimited_user !== true) {
        formData.mikrotik_profile_name = profileAktif
      }
      formData.mikrotik_server_name = formData.mikrotik_server_name || 'srv-user'
      break
    case 'KOMANDAN':
      if (formData.is_unlimited_user !== true) {
        formData.mikrotik_profile_name = profileAktif
      }
      formData.mikrotik_server_name = formData.mikrotik_server_name || 'srv-komandan'
      break
    case 'ADMIN':
    case 'SUPER_ADMIN':
      formData.mikrotik_profile_name = profileAktif
      formData.mikrotik_server_name = formData.mikrotik_server_name || 'srv-admin'
      break
  }
}

watch(() => formData.role, (newRole) => {
  if (newRole === 'ADMIN' || newRole === 'SUPER_ADMIN') {
    formData.is_unlimited_user = true
    formData.blok = null
    formData.kamar = null
  }
  setDefaultMikrotikConfig(newRole)
})

watch(() => formData.is_unlimited_user, (isUnlimited, wasUnlimited) => {
  if (isUnlimited === wasUnlimited)
    return

  // Get runtime config for profile names
  const runtimeConfig = useRuntimeConfig()
  const profileUnlimited = runtimeConfig.public.profileUnlimitedName || 'profile-unlimited'

  if (isUnlimited) {
    formData.mikrotik_profile_name = profileUnlimited
    formData.add_gb = 0
  }
  else {
    setDefaultMikrotikConfig(formData.role)
  }
})

watch(() => formData.is_active, (isActive, wasActive) => {
  if (isActive === wasActive)
    return

  // Get runtime config for profile names
  const runtimeConfig = useRuntimeConfig()
  const profileUnlimited = runtimeConfig.public.profileUnlimitedName || 'profile-unlimited'
  const profileInactive = runtimeConfig.public.profileInactiveName || 'inactive'

  if (!isActive) {
    formData.mikrotik_profile_name = profileInactive
  }
  else {
    if (formData.is_unlimited_user === true) {
      formData.mikrotik_profile_name = profileUnlimited
    }
    else {
      setDefaultMikrotikConfig(formData.role)
    }
  }
})

watch(adminAccessType, (newType) => {
  if (authStore.isAdmin && !authStore.isSuperAdmin) {
    if (newType === 'admin') {
      formData.mikrotik_profile_name = 'komandan'
      formData.mikrotik_server_name = 'srv-admin'
    }
    else if (newType === 'komandan') {
      formData.mikrotik_profile_name = 'komandan'
      formData.mikrotik_server_name = 'srv-komandan'
    }
  }
})

async function checkAndApplyMikrotikStatus() {
  if (!props.user)
    return
  isCheckingMikrotik.value = true
  liveData.value = null
  try {
    const response = await $api<{ exists_on_mikrotik: boolean, details: any, message?: string }>(`/admin/users/${props.user.id}/mikrotik-status`)
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

    if (payload.is_unlimited_user === true && payload.mikrotik_profile_name !== 'unlimited') {
      if (!authStore.isSuperAdmin) {
        payload.mikrotik_profile_name = 'unlimited'
      }
    }

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
                <VCol v-if="formData.role === 'USER'" cols="12" md="6">
                  <AppSelect v-model="formData.blok" :items="props.availableBloks" :loading="props.isAlamatLoading" label="Blok" :disabled="isRestrictedAdmin" prepend-inner-icon="tabler-building" />
                </VCol>
                <VCol v-if="formData.role === 'USER'" cols="12" md="6">
                  <AppSelect v-model="formData.kamar" :items="props.availableKamars" :loading="props.isAlamatLoading" label="Kamar" :disabled="isRestrictedAdmin" prepend-inner-icon="tabler-door" />
                </VCol>
              </VRow>
            </VWindowItem>

            <VWindowItem value="akses">
              <VRow>
                <VCol cols="12">
                  <VSwitch v-model="formData.is_active" label="Akun Aktif" color="success" inset hint="Menonaktifkan akan memutus akses pengguna." persistent-hint />
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

                <template v-if="canAdminInject && formData.is_active === true">
                  <VCol cols="12">
                    <VDivider class="my-2" />
                  </VCol>

                  <VCol cols="12" class="d-flex justify-space-between align-center">
                    <div class="text-overline">
                      Inject Kuota & Masa Aktif
                    </div>
                    <VBtn
                      v-if="authStore.isSuperAdmin"
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

                  <VCol v-if="isTargetAdminOrSuper !== true" cols="12" md="6">
                    <AppTextField v-model.number="formData.add_days" label="Tambah Masa Aktif (Hari)" type="number" prepend-inner-icon="tabler-calendar-plus" />
                  </VCol>

                  <VCol cols="12">
                    <VDivider class="my-2" />
                  </VCol>

                  <VCol v-if="authStore.isSuperAdmin" cols="12">
                    <div class="text-overline mb-3">
                      Pengaturan Mikrotik
                    </div>

                    <VRow>
                      <VCol cols="12" md="6">
                        <AppSelect v-model="formData.mikrotik_server_name" :items="superAdminServerOptions" label="Server Mikrotik" clearable prepend-inner-icon="tabler-server" />
                      </VCol>
                      <VCol cols="12" md="6">
                        <AppSelect v-model="formData.mikrotik_profile_name" :items="superAdminProfileOptions" label="Profil Mikrotik" clearable prepend-inner-icon="tabler-network" />
                      </VCol>
                    </VRow>
                  </VCol>
                </template>
              </VRow>
            </VWindowItem>
          </VWindow>
        </VCardText>
        <VDivider />

        <VCardActions class="pa-4 d-flex">
          <div v-if="props.user && formData.is_active === true && isTargetAdminOrSuper === true">
            <VBtn color="warning" variant="text" prepend-icon="tabler-key" @click="$emit('generateAdminPass', props.user.id)">
              Reset Password Portal
            </VBtn>
          </div>
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
