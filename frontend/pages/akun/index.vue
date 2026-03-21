<script lang="ts" setup>
import type { VForm } from 'vuetify/components'
import type { ChangePasswordRequest, User } from '~/types/auth'
import { useNuxtApp } from '#app'
import { computed, defineAsyncComponent, onMounted, onUnmounted, ref, watch } from 'vue'
import { useDisplay } from 'vuetify'
import { useAuthStore } from '~/store/auth'
import { formatCurrencyIdr, formatDateLongId, normalize_to_e164 } from '~/utils/formatters'

const UserSpendingChart = defineAsyncComponent({
  loader: () => import('~/components/charts/UserSpendingChart.vue'),
})
const DeviceManagerCard = defineAsyncComponent({
  loader: () => import('~/components/akun/DeviceManagerCard.vue'),
})

// --- Inisialisasi & State Management ---
const { $api } = useNuxtApp()
const authStore = useAuthStore()
const display = useDisplay()
const isHydrated = ref(false)
const isMobile = computed(() => (isHydrated.value ? display.smAndDown.value : false))
const deferredWidgetsReady = ref(false)
let deferredTimer: ReturnType<typeof setTimeout> | null = null
const profileLoading = ref(true)
const profileError = ref<string | null>(null)
const securityLoading = ref(false)
const profileForm = ref<InstanceType<typeof VForm> | null>(null)
const profileAlert = ref<{ type: 'success' | 'error', message: string } | null>(null)
const editData = ref({ full_name: '', phone_number: '' })
const totalSpendingThisPeriod = ref<string>('Rp 0')
const spendingChartData = ref([{ data: [] as number[] }])
const spendingChartCategories = ref<string[]>([])
const spendingChartLoading = ref(false)
const spendingAlert = ref<{ type: 'success' | 'error', message: string } | null>(null)
const isPasswordDialogVisible = ref(false)
const passwordFormRef = ref<InstanceType<typeof VForm> | null>(null)
const passwordLoading = ref(false)
const passwordAlert = ref<{ type: 'success' | 'error', message: string } | null>(null)
const passwordData = ref<ChangePasswordRequest>({ current_password: '', new_password: '' })
const confirmPassword = ref('')
const isPasswordVisible = ref(false)

const telegramLoading = ref(false)
const telegramError = ref<string | null>(null)
const telegramStatus = ref<{ linked: boolean; chat_id?: string | null; username?: string | null; linked_at?: string | null } | null>(null)
const telegramLinkUrl = ref<string | null>(null)

// --- Computed Properties ---
type UserWithMeta = User & { created_at?: string }
const currentUser = computed<UserWithMeta | null>(() => authStore.currentUser as UserWithMeta | null)
const isUser = computed(() => currentUser.value?.role === 'USER')
const isKomandan = computed(() => currentUser.value?.role === 'KOMANDAN')
const isAdminOrSuperAdmin = computed(() => ['ADMIN', 'SUPER_ADMIN'].includes(currentUser.value?.role ?? ''))
const showDeviceManager = computed(() => isUser.value || isKomandan.value)

const displayRole = computed(() => {
  if (!currentUser.value)
    return ''
  const roles = {
    USER: 'Pengguna',
    KOMANDAN: 'Komandan',
    ADMIN: 'Admin',
    SUPER_ADMIN: 'Support',
  }
  // DIPERBAIKI: Menggunakan ?? untuk fallback yang aman
  return roles[currentUser.value.role] ?? currentUser.value.role
})

const displayPhoneNumber = computed(() => formatPhoneNumberForDisplay(currentUser.value?.phone_number))
const accountStatusMeta = computed(() => {
  if (!currentUser.value) {
    return { text: '-', color: 'secondary', icon: 'tabler-help' }
  }

  if (currentUser.value.is_active === true)
    return { text: 'Aktif', color: 'success', icon: 'tabler-circle-check' }

  return { text: 'Tidak Aktif', color: 'warning', icon: 'tabler-alert-circle' }
})

function formatQuotaValue(mb?: number | null): string {
  const safe = Number(mb ?? 0)
  if (!Number.isFinite(safe) || safe <= 0)
    return '0 MB'
  if (safe < 1024)
    return `${safe.toLocaleString('id-ID', { maximumFractionDigits: 0 })} MB`
  return `${(safe / 1024).toLocaleString('id-ID', { minimumFractionDigits: 0, maximumFractionDigits: 2 })} GB`
}

const accountOverviewCards = computed(() => {
  const user = currentUser.value
  if (!user)
    return []

  const purchased = Number(user.total_quota_purchased_mb ?? 0)
  const used = Number(user.total_quota_used_mb ?? 0)
  const remaining = Math.max(0, purchased - used)
  const quotaText = user.is_unlimited_user === true ? 'Unlimited' : formatQuotaValue(remaining)

  return [
    {
      key: 'role',
      label: 'Peran',
      value: displayRole.value,
      caption: user.mikrotik_profile_name || 'Profile belum terset',
      color: 'info',
      icon: 'tabler-shield-check',
    },
    {
      key: 'status',
      label: 'Status',
      value: accountStatusMeta.value.text,
      caption: user.is_blocked ? `Blokir: ${user.blocked_reason || 'Ya'}` : 'Akun dapat digunakan',
      color: accountStatusMeta.value.color,
      icon: accountStatusMeta.value.icon,
    },
    {
      key: 'quota',
      label: 'Sisa Kuota',
      value: quotaText,
      caption: user.is_unlimited_user === true ? 'Akses tanpa batas kuota' : `Terpakai ${formatQuotaValue(used)}`,
      color: user.is_unlimited_user === true ? 'success' : 'primary',
      icon: user.is_unlimited_user === true ? 'tabler-infinity' : 'tabler-database',
    },
    {
      key: 'joined',
      label: 'Terdaftar',
      value: formatDate(user.created_at),
      caption: displayPhoneNumber.value || 'Nomor belum tersedia',
      color: 'secondary',
      icon: 'tabler-calendar-plus',
    },
  ]
})

// --- Fungsi-Fungsi ---
const formatCurrency = (amount: number) => formatCurrencyIdr(amount)

function formatPhoneNumberForDisplay(phone?: string | null): string {
  if (phone === null || phone === undefined || phone === '') // Perbaikan: Handle null, undefined, dan string kosong secara eksplisit
    return ''
  return phone.startsWith('+62') ? `0${phone.substring(3)}` : phone
}
function populateEditForm() {
  if (currentUser.value) {
    // DIPERBAIKI: Menggunakan ?? untuk fallback yang aman
    editData.value.full_name = currentUser.value.full_name ?? ''
    editData.value.phone_number = formatPhoneNumberForDisplay(currentUser.value.phone_number)
  }
}
async function loadInitialData() {
  profileLoading.value = true
  profileError.value = null
  try {
    if (authStore.currentUser === null || authStore.currentUser === undefined) { // Perbaikan: Perbandingan eksplisit
      const success = await authStore.fetchUser('login')
      if (!success)
        // DIPERBAIKI: Menggunakan ?? untuk fallback yang aman
        throw new Error(authStore.error ?? 'Gagal memuat data pengguna.')
    }
    populateEditForm()
    if (isUser.value === true) // Perbaikan: Perbandingan eksplisit
      fetchSpendingSummary()

    loadTelegramStatus()
  }
  catch (error: any) {
    profileError.value = error.message
  }
  finally {
    profileLoading.value = false
  }
}

async function loadTelegramStatus() {
  telegramError.value = null
  telegramLoading.value = true
  try {
    const status = await $api<{ linked: boolean; chat_id?: string | null; username?: string | null; linked_at?: string | null }>(
      '/auth/me/telegram/status',
      { method: 'GET' },
    )
    telegramStatus.value = status
  }
  catch (e: any) {
    telegramStatus.value = null
    telegramError.value = (e?.data?.message as string | undefined) || 'Gagal memuat status Telegram.'
  }
  finally {
    telegramLoading.value = false
  }
}

async function connectTelegram() {
  telegramError.value = null
  telegramLinkUrl.value = null
  telegramLoading.value = true
  try {
    const result = await $api<{ link_url: string; expires_in_seconds: number; bot_username: string }>(
      '/auth/me/telegram/link-token',
      { method: 'POST' },
    )
    telegramLinkUrl.value = result.link_url

    if (import.meta.client) {
      window.open(result.link_url, '_blank', 'noopener,noreferrer')
    }
  }
  catch (e: any) {
    telegramError.value = (e?.data?.message as string | undefined) || 'Gagal membuat link Telegram.'
  }
  finally {
    telegramLoading.value = false
  }
}

async function disconnectTelegram() {
  telegramError.value = null
  telegramLoading.value = true
  try {
    await $api('/auth/me/telegram/unlink', { method: 'POST' })
    telegramLinkUrl.value = null
    await loadTelegramStatus()
  }
  catch (e: any) {
    telegramError.value = (e?.data?.message as string | undefined) || 'Gagal memutus Telegram.'
  }
  finally {
    telegramLoading.value = false
  }
}
async function saveProfile() {
  if (profileForm.value === null) // Perbaikan: Perbandingan eksplisit
    return
  const { valid } = await profileForm.value.validate()
  if (valid === false) // Perbaikan: Perbandingan eksplisit
    return

  securityLoading.value = true
  profileAlert.value = null

  const isPrivilegedUser = isAdminOrSuperAdmin.value || isKomandan.value
  const endpoint = isPrivilegedUser ? `/admin/users/me` : `/auth/me/profile`

  const payload: Partial<User> = { full_name: editData.value.full_name }

  if (isPrivilegedUser) {
    try {
      // Perbaikan: Menggunakan perbandingan eksplisit untuk `e.message`
      payload.phone_number = normalize_to_e164(editData.value.phone_number)
    }
    catch (e: any) {
      // Baris 119: Memperbaiki penggunaan nilai 'any' dalam kondisi
      profileAlert.value = { type: 'error', message: (typeof e.message === 'string' && e.message !== '') ? e.message : 'Format nomor telepon tidak valid.' }
      securityLoading.value = false
      return
    }
  }

  try {
    const response = await $api<User>(endpoint, { method: 'PUT', body: payload })
    authStore.$patch({ user: response })
    populateEditForm()
    profileAlert.value = { type: 'success', message: 'Profil berhasil diperbarui!' }
  }
  catch (error: any) {
    // Baris 133: Memperbaiki penggunaan nilai 'any' dalam kondisi
    const errorMessage = (typeof error.data?.message === 'string' && error.data.message !== '') ? error.data.message : 'Terjadi kesalahan'
    profileAlert.value = { type: 'error', message: `Gagal menyimpan profil: ${errorMessage}` }
  }
  finally {
    securityLoading.value = false
  }
}
async function fetchSpendingSummary() {
  spendingChartLoading.value = true
  spendingAlert.value = null
  try {
    const response = await $api<{ categories: string[], series: any[], total_this_week: number }>('/users/me/weekly-spending')
    spendingChartCategories.value = response.categories
    spendingChartData.value = response.series
    totalSpendingThisPeriod.value = formatCurrency(response.total_this_week)
  }
  catch (error: any) {
    spendingChartCategories.value = ['Min', 'Sen', 'Sel', 'Rab', 'Kam', 'Jum', 'Sab']
    spendingChartData.value = [{ data: [0, 0, 0, 0, 0, 0, 0] }]
    totalSpendingThisPeriod.value = formatCurrency(0)
    // DIPERBAIKI: Pemeriksaan tipe eksplisit untuk pesan error
    const errorMessage = typeof error.data?.message === 'string' ? error.data.message : 'Kesalahan tidak diketahui'
    spendingAlert.value = { type: 'error', message: `Gagal memuat pengeluaran: ${errorMessage}` }
  }
  finally {
    spendingChartLoading.value = false
  }
}
async function changePassword() {
  if (passwordFormRef.value === null) // Perbaikan: Perbandingan eksplisit
    return
  const { valid } = await passwordFormRef.value.validate()
  if (valid === false) // Perbaikan: Perbandingan eksplisit
    return
  passwordLoading.value = true
  passwordAlert.value = null
  try {
    const response = await $api<{ message: string }>('/auth/me/change-password', { method: 'POST', body: passwordData.value })
    // DIPERBAIKI: Menggunakan ?? untuk fallback yang aman
    passwordAlert.value = { type: 'success', message: response.message ?? 'Password berhasil diubah!' }
    setTimeout(() => {
      isPasswordDialogVisible.value = false
      passwordFormRef.value?.reset()
      passwordData.value = { current_password: '', new_password: '' }
      confirmPassword.value = ''
    }, 1500)
  }
  catch (error: any) {
    // Baris 209: Memperbaiki penggunaan nilai 'any' dalam kondisi
    const errorMessage = (typeof error.data?.message === 'string' && error.data.message !== '') ? error.data.message : 'Gagal mengubah password.'
    passwordAlert.value = { type: 'error', message: errorMessage }
  }
  finally {
    passwordLoading.value = false
  }
}
onMounted(() => {
  isHydrated.value = true
  loadInitialData()
  deferredTimer = setTimeout(() => {
    deferredWidgetsReady.value = true
  }, isMobile.value ? 1200 : 500)
})

onUnmounted(() => {
  if (deferredTimer != null)
    clearTimeout(deferredTimer)
  deferredTimer = null
})
watch(() => authStore.currentUser, (newUser) => {
  if (newUser)
    populateEditForm()
}, { deep: true })

// DIPERBAIKI: Aturan validasi menggunakan perbandingan eksplisit
const requiredRule = (v: any) => (v !== null && v !== undefined && v !== '') || 'Wajib diisi.' // Perbaikan: Perbandingan eksplisit dengan null, undefined, dan string kosong
const nameLengthRule = (v: string) => (v !== null && v !== undefined && v.length >= 2) || 'Nama minimal 2 karakter.' // Perbaikan: Perbandingan eksplisit
const phoneRule = (v: string) => {
  try {
    normalize_to_e164(v)
    return true
  }
  catch (error: any) {
    return error instanceof Error && error.message !== ''
      ? error.message
      : 'Format nomor telepon tidak valid.'
  }
}
const passwordLengthRule = (v: string) => (v !== null && v !== undefined && v.length >= 6) || 'Password minimal 6 karakter.' // Perbaikan: Perbandingan eksplisit
const passwordMatchRule = (v: string) => v === passwordData.value.new_password || 'Password tidak cocok.'
function formatDate(dateString?: string | Date | null) {
  if (dateString === null || dateString === undefined || dateString === '') // Perbaikan: Handle null, undefined, dan string kosong secara eksplisit
    return 'N/A'
  const formatted = formatDateLongId(dateString, 7)
  return formatted === '-' ? 'N/A' : formatted
}

useHead({ title: 'Pengaturan Akun' })
</script>

<template>
  <VContainer fluid>
    <div v-if="profileLoading" class="py-10">
      <VProgressLinear indeterminate color="primary" rounded height="6" />
      <div class="text-center mt-4 text-disabled">
        Memuat data akun...
      </div>
    </div>

    <div v-else-if="profileError" class="text-center py-16">
      <VIcon icon="tabler-alert-triangle" size="64" color="error" />
      <p class="text-h6 mt-4">
        Gagal Memuat Data
      </p>
      <p class="text-body-1 mt-2">
        {{ profileError }}
      </p>
      <VBtn color="primary" class="mt-4" prepend-icon="tabler-reload" @click="loadInitialData">
        Coba Lagi
      </VBtn>
    </div>

    <VRow v-else-if="currentUser !== null" class="ga-0">
      <VCol cols="12" lg="8">
        <VRow class="ga-0">
          <VCol cols="12">
            <VCard class="account-profile-card">
              <VCardItem>
                <VCardTitle class="text-h5">
                  Profil Akun
                </VCardTitle>
                <VCardSubtitle>Kelola informasi profil Anda di sini.</VCardSubtitle>
              </VCardItem>
              <VCardText>
                <VAlert v-if="profileAlert" :type="profileAlert.type" variant="tonal" density="compact" closable class="mb-4" @update:model-value="profileAlert = null">
                  {{ profileAlert.message }}
                </VAlert>
                <VForm ref="profileForm" @submit.prevent="saveProfile">
                  <VRow>
                    <VCol cols="12" md="6">
                      <AppTextField v-model="editData.full_name" label="Nama Lengkap" prepend-inner-icon="tabler-user" :rules="[requiredRule, nameLengthRule]" />
                    </VCol>
                    <VCol cols="12" md="6">
                      <AppTextField v-model="editData.phone_number" label="Nomor Telepon (Username)" prepend-inner-icon="tabler-phone" :rules="[requiredRule, phoneRule]" :disabled="!isAdminOrSuperAdmin && !isKomandan" :readonly="!isAdminOrSuperAdmin && !isKomandan" />
                    </VCol>
                    <VCol v-if="isUser && currentUser.is_tamping" cols="12" md="6">
                      <AppTextField :model-value="currentUser.tamping_type || 'N/A'" label="Tamping" readonly disabled prepend-inner-icon="tabler-building-bank" />
                    </VCol>
                    <VCol v-if="isUser && !currentUser.is_tamping" cols="12" md="6">
                      <AppTextField :model-value="currentUser.blok || 'N/A'" label="Blok" readonly disabled prepend-inner-icon="tabler-building" />
                    </VCol>
                    <VCol v-if="isUser && !currentUser.is_tamping" cols="12" md="6">
                      <AppTextField :model-value="currentUser.kamar || 'N/A'" label="Kamar" readonly disabled prepend-inner-icon="tabler-door" />
                    </VCol>
                  </VRow>
                  <VBtn class="mt-4" color="primary" type="submit" :loading="securityLoading" prepend-icon="tabler-device-floppy">
                    Simpan Perubahan
                  </VBtn>
                </VForm>
              </VCardText>
            </VCard>
          </VCol>

          <VCol v-if="isAdminOrSuperAdmin" cols="12">
            <VCard>
              <VCardItem>
                <VCardTitle class="text-h5">
                  Keamanan
                </VCardTitle>
                <VCardSubtitle>Kelola kredensial dan akses keamanan akun Anda.</VCardSubtitle>
              </VCardItem>
              <VCardText>
                <div class="d-flex flex-wrap ga-4">
                  <VBtn color="secondary" variant="tonal" prepend-icon="tabler-key" @click="isPasswordDialogVisible = true">
                    Ubah Password Portal
                  </VBtn>
                </div>
              </VCardText>
            </VCard>
          </VCol>

          <VCol cols="12">
            <!-- Telegram card dipindahkan ke kolom kanan (menggantikan Riwayat Akses) -->
          </VCol>

          <VCol v-if="showDeviceManager" cols="12">
            <DeviceManagerCard />
          </VCol>

          <VCol v-if="isUser" cols="12">
            <VCard>
              <VCardText class="pb-2">
                <div class="ringkasan-header">
                  <div class="ringkasan-title-wrap">
                    <h3 class="text-h5 mb-1">
                      Ringkasan Pengeluaran
                    </h3>
                    <p class="text-body-2 text-medium-emphasis mb-0">
                      Grafik pengeluaran Anda dalam seminggu terakhir.
                    </p>
                  </div>

                  <div class="ringkasan-summary text-right">
                    <div class="text-h5 font-weight-bold text-success">
                      {{ totalSpendingThisPeriod }}
                    </div>
                    <div class="text-caption">
                      Minggu Ini
                    </div>
                  </div>
                </div>
              </VCardText>
              <VCardText>
                <div v-if="spendingChartLoading" class="text-center py-4">
                  <VProgressCircular indeterminate />
                </div>
                <VAlert v-if="spendingAlert" :type="spendingAlert.type" variant="tonal" density="compact" closable class="mb-4" @update:model-value="spendingAlert = null">
                  {{ spendingAlert.message }}
                </VAlert>
                <div :style="{ height: isMobile ? '200px' : '250px' }">
                  <ClientOnly>
                    <UserSpendingChart
                      v-if="deferredWidgetsReady && spendingChartData[0]?.data.length > 0"
                      :series-data="spendingChartData"
                      :categories="spendingChartCategories"
                    />
                  </ClientOnly>
                  <div v-if="!deferredWidgetsReady" class="d-flex align-center justify-center fill-height">
                    <VProgressCircular indeterminate size="28" />
                  </div>
                </div>
              </VCardText>
            </VCard>
          </VCol>
        </VRow>
      </VCol>

      <VCol cols="12" lg="4">
        <VRow class="ga-0">
          <VCol cols="12">
            <VCard class="account-overview-card">
              <VCardText class="pa-5">
                <div class="account-overview-hero">
                  <div class="account-overview-hero__identity">
                    <VAvatar color="primary" rounded size="54" class="account-overview-hero__avatar">
                      <VIcon size="30" icon="tabler-user-circle" />
                    </VAvatar>
                    <div class="account-overview-hero__copy">
                      <h5 class="text-h5 font-weight-bold mb-1">
                        {{ currentUser.full_name }}
                      </h5>
                      <div class="text-body-2 text-medium-emphasis">
                        {{ displayPhoneNumber || 'Nomor belum tersedia' }}
                      </div>
                    </div>
                  </div>
                  <VChip :color="accountStatusMeta.color" size="small" label>
                    <VIcon :icon="accountStatusMeta.icon" start size="16" />
                    {{ accountStatusMeta.text }}
                  </VChip>
                </div>

                <div class="account-overview-grid mt-5">
                  <div v-for="item in accountOverviewCards" :key="item.key" class="account-overview-stat">
                    <div class="account-overview-stat__head">
                      <VAvatar size="34" :color="item.color" variant="tonal">
                        <VIcon :icon="item.icon" size="18" />
                      </VAvatar>
                      <div class="account-overview-stat__label">
                        {{ item.label }}
                      </div>
                    </div>
                    <div class="account-overview-stat__value">
                      {{ item.value }}
                    </div>
                    <div class="account-overview-stat__caption">
                      {{ item.caption }}
                    </div>
                  </div>
                </div>
              </VCardText>
            </VCard>
          </VCol>

          <VCol cols="12">
            <VCard>
              <VCardItem>
                <VCardTitle class="text-h5">
                  Telegram
                </VCardTitle>
                <VCardSubtitle>Hubungkan Telegram agar sistem bisa mengirim notifikasi ke akun Anda.</VCardSubtitle>
              </VCardItem>
              <VCardText>
                <VAlert v-if="telegramError" type="error" variant="tonal" density="compact" closable class="mb-4" @update:model-value="telegramError = null">
                  {{ telegramError }}
                </VAlert>

                <VAlert
                  v-if="telegramStatus?.linked === true"
                  type="success"
                  variant="tonal"
                  density="compact"
                  class="mb-4"
                >
                  Telegram sudah terhubung.
                  <span v-if="telegramStatus.username"> (@{{ telegramStatus.username }})</span>
                </VAlert>
                <VAlert
                  v-else
                  type="info"
                  variant="tonal"
                  density="compact"
                  class="mb-4"
                >
                  Klik "Connect Telegram" lalu tekan Start di bot Telegram.
                </VAlert>

                <div class="d-flex flex-wrap ga-3">
                  <VBtn
                    color="primary"
                    variant="tonal"
                    prepend-icon="tabler-brand-telegram"
                    :loading="telegramLoading"
                    :disabled="telegramLoading"
                    @click="connectTelegram"
                  >
                    Connect Telegram
                  </VBtn>

                  <VBtn
                    color="secondary"
                    variant="text"
                    prepend-icon="tabler-refresh"
                    :loading="telegramLoading"
                    :disabled="telegramLoading"
                    @click="loadTelegramStatus"
                  >
                    Refresh Status
                  </VBtn>

                  <VBtn
                    v-if="telegramStatus?.linked === true"
                    color="error"
                    variant="text"
                    prepend-icon="tabler-unlink"
                    :loading="telegramLoading"
                    :disabled="telegramLoading"
                    @click="disconnectTelegram"
                  >
                    Disconnect
                  </VBtn>
                </div>

                <div v-if="telegramLinkUrl" class="mt-4">
                  <div class="text-caption text-medium-emphasis mb-1">Link connect (berlaku singkat):</div>
                  <VTextField
                    :model-value="telegramLinkUrl"
                    readonly
                    variant="outlined"
                    density="comfortable"
                  />
                </div>
              </VCardText>
            </VCard>
          </VCol>
        </VRow>
      </VCol>
    </VRow>

    <VDialog v-if="isHydrated" v-model="isPasswordDialogVisible" max-width="500px" persistent>
      <VCard>
        <VCardTitle class="pa-4">
          <div class="dialog-titlebar">
            <div class="dialog-titlebar__title">
              <span class="text-h6">Ubah Password Portal</span>
            </div>
            <div class="dialog-titlebar__actions">
              <VBtn icon="tabler-x" variant="text" @click="isPasswordDialogVisible = false" />
            </div>
          </div>
        </VCardTitle>
        <VDivider />
        <VCardText class="pt-4">
          <VAlert v-if="passwordAlert" :type="passwordAlert.type" variant="tonal" density="compact" closable class="mb-4" @update:model-value="passwordAlert = null">
            {{ passwordAlert.message }}
          </VAlert>
          <VForm ref="passwordFormRef" @submit.prevent="changePassword">
            <VRow>
              <VCol cols="12">
                <AppTextField v-model="passwordData.current_password" label="Password Saat Ini" :type="isPasswordVisible ? 'text' : 'password'" :append-inner-icon="isPasswordVisible ? 'tabler-eye-off' : 'tabler-eye'" :rules="[requiredRule]" density="comfortable" autocomplete="current-password" @click:append-inner="isPasswordVisible = !isPasswordVisible" />
              </VCol>
              <VCol cols="12">
                <AppTextField v-model="passwordData.new_password" label="Password Baru" :type="isPasswordVisible ? 'text' : 'password'" :rules="[requiredRule, passwordLengthRule]" density="comfortable" autocomplete="new-password" />
              </VCol>
              <VCol cols="12">
                <AppTextField v-model="confirmPassword" label="Konfirmasi Password Baru" :type="isPasswordVisible ? 'text' : 'password'" :rules="[requiredRule, passwordMatchRule]" density="comfortable" autocomplete="new-password" />
              </VCol>
            </VRow>
          </VForm>
        </VCardText>
        <VCardActions>
          <VSpacer />
          <VBtn color="secondary" variant="text" :disabled="passwordLoading" @click="isPasswordDialogVisible = false">
            Batal
          </VBtn>
          <VBtn color="primary" variant="elevated" :loading="passwordLoading" @click="changePassword">
            Simpan Password
          </VBtn>
        </VCardActions>
      </VCard>
    </VDialog>
  </VContainer>
</template>

<style scoped>
.account-profile-card,
.account-overview-card {
  border: 1px solid rgba(var(--v-theme-on-surface), 0.08);
}

.account-overview-hero {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.account-overview-hero__identity {
  display: flex;
  align-items: center;
  gap: 14px;
  min-width: 0;
}

.account-overview-hero__avatar {
  flex: 0 0 auto;
}

.account-overview-hero__copy {
  min-width: 0;
}

.account-overview-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.account-overview-stat {
  padding: 14px 16px;
  border-radius: 16px;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.08);
  background: rgba(var(--v-theme-surface), 0.72);
}

.account-overview-stat__head {
  display: flex;
  align-items: center;
  gap: 10px;
}

.account-overview-stat__label {
  font-size: 0.78rem;
  font-weight: 700;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: rgba(var(--v-theme-on-surface), 0.56);
}

.account-overview-stat__value {
  margin-top: 12px;
  font-size: 1.02rem;
  font-weight: 700;
  line-height: 1.3;
}

.account-overview-stat__caption {
  margin-top: 4px;
  font-size: 0.8rem;
  line-height: 1.4;
  color: rgba(var(--v-theme-on-surface), 0.62);
}

.ringkasan-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 0.75rem;
}

.ringkasan-title-wrap {
  flex: 1;
  min-width: 0;
}

.ringkasan-summary {
  flex-shrink: 0;
}

@media (max-width: 599.98px) {
  .account-overview-hero {
    flex-direction: column;
  }

  .account-overview-grid {
    grid-template-columns: 1fr;
  }

  .ringkasan-header {
    flex-direction: column;
  }

  .dialog-titlebar {
    flex-direction: column;
    align-items: stretch;
  }

  .dialog-titlebar__actions {
    justify-content: flex-end;
    width: 100%;
  }

  .ringkasan-summary {
    width: 100%;
    text-align: left !important;
  }
}

.dialog-titlebar {
  display: flex;
  align-items: center;
  gap: 12px;
}

.dialog-titlebar__title {
  display: flex;
  align-items: center;
  gap: 10px;
  flex: 1;
  min-width: 0;
}

.dialog-titlebar__actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}
</style>
