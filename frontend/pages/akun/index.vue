<script lang="ts" setup>
import type { VForm } from 'vuetify/components'
import type { ChangePasswordRequest, User } from '~/types/auth'
import { useNuxtApp } from '#app'
import { computed, defineAsyncComponent, onMounted, onUnmounted, ref, watch } from 'vue'
import { useDisplay } from 'vuetify'
import { useAuthStore } from '~/store/auth'
import { normalize_to_e164 } from '~/utils/formatters'

// --- [PERBAIKAN] Komponen sekarang dipanggil LoginHistoryCard (nama file tetap) ---
const LoginHistoryCard = defineAsyncComponent({
  loader: () => import('~/components/akun/LoginHistoryCard.vue'),
})
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

// --- Fungsi-Fungsi ---
const formatCurrency = (amount: number) => new Intl.NumberFormat('id-ID', { style: 'currency', currency: 'IDR', minimumFractionDigits: 0 }).format(amount)

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
  return new Date(dateString).toLocaleString('id-ID', { year: 'numeric', month: 'long', day: 'numeric' })
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
            <VCard>
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
                    density="compact"
                  />
                </div>
              </VCardText>
            </VCard>
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
            <VCard>
              <VCardText>
                <div class="d-flex align-center mb-4">
                  <VAvatar color="primary" rounded size="50" class="me-4">
                    <VIcon size="30" icon="tabler-user-circle" />
                  </VAvatar>
                  <div>
                    <h5 class="text-h5 font-weight-bold">
                      {{ currentUser.full_name }}
                    </h5>
                    <div class="text-caption">
                      {{ currentUser.phone_number }}
                    </div>
                  </div>
                </div>
                <VDivider />
                <VList lines="two" density="compact" class="mt-2">
                  <VListItem>
                    <template #prepend>
                      <VIcon icon="tabler-shield-check" class="me-3" color="info" />
                    </template>
                    <VListItemTitle>Peran</VListItemTitle>
                    <template #append>
                      <VChip size="small" label color="info">
                        {{ displayRole }}
                      </VChip>
                    </template>
                  </VListItem>
                  <VListItem>
                    <template #prepend>
                      <VIcon icon="tabler-id-badge-2" class="me-3" :color="currentUser.is_active ? 'success' : 'warning'" />
                    </template>
                    <VListItemTitle>Status</VListItemTitle>
                    <template #append>
                      <VChip :color="currentUser.is_active ? 'success' : 'warning'" size="small" label>
                        {{ currentUser.is_active ? 'Aktif' : 'Tidak Aktif' }}
                      </VChip>
                    </template>
                  </VListItem>
                  <VListItem>
                    <template #prepend>
                      <VIcon icon="tabler-calendar-plus" class="me-3" color="secondary" />
                    </template>
                    <VListItemTitle>Terdaftar</VListItemTitle>
                    <template #append>
                      <span class="text-body-2">{{ formatDate(currentUser.created_at) }}</span>
                    </template>
                  </VListItem>
                </VList>
              </VCardText>
            </VCard>
          </VCol>

          <VCol cols="12">
            <VCard>
              <VCardItem>
                <VCardTitle class="text-h5">
                  Riwayat Akses
                </VCardTitle>
                <VCardSubtitle>Aktivitas login terakhir pada akun Anda.</VCardSubtitle>
              </VCardItem>
              <ClientOnly>
                <LoginHistoryCard v-if="deferredWidgetsReady" />
              </ClientOnly>
              <div v-if="!deferredWidgetsReady" class="text-center py-4">
                <VProgressCircular indeterminate size="28" />
              </div>
            </VCard>
          </VCol>
        </VRow>
      </VCol>
    </VRow>

    <VDialog v-if="isHydrated" v-model="isPasswordDialogVisible" max-width="500px" persistent>
      <VCard>
        <VCardTitle class="d-flex align-center">
          Ubah Password Portal
          <VSpacer />
          <VBtn icon="tabler-x" variant="text" @click="isPasswordDialogVisible = false" />
        </VCardTitle>
        <VDivider />
        <VCardText class="pt-4">
          <VAlert v-if="passwordAlert" :type="passwordAlert.type" variant="tonal" density="compact" closable class="mb-4" @update:model-value="passwordAlert = null">
            {{ passwordAlert.message }}
          </VAlert>
          <VForm ref="passwordFormRef" @submit.prevent="changePassword">
            <VRow>
              <VCol cols="12">
                <AppTextField v-model="passwordData.current_password" label="Password Saat Ini" :type="isPasswordVisible ? 'text' : 'password'" :append-inner-icon="isPasswordVisible ? 'tabler-eye-off' : 'tabler-eye'" :rules="[requiredRule]" density="compact" autocomplete="current-password" @click:append-inner="isPasswordVisible = !isPasswordVisible" />
              </VCol>
              <VCol cols="12">
                <AppTextField v-model="passwordData.new_password" label="Password Baru" :type="isPasswordVisible ? 'text' : 'password'" :rules="[requiredRule, passwordLengthRule]" density="compact" autocomplete="new-password" />
              </VCol>
              <VCol cols="12">
                <AppTextField v-model="confirmPassword" label="Konfirmasi Password Baru" :type="isPasswordVisible ? 'text' : 'password'" :rules="[requiredRule, passwordMatchRule]" density="compact" autocomplete="new-password" />
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
  .ringkasan-header {
    flex-direction: column;
  }

  .ringkasan-summary {
    width: 100%;
    text-align: left !important;
  }
}
</style>
