<script lang="ts" setup>
import type { VForm } from 'vuetify/components'
import type { ChangePasswordRequest, User } from '~/types/auth'
import { useNuxtApp } from '#app'
import { computed, defineAsyncComponent, onMounted, ref, watch } from 'vue'
import { useDisplay } from 'vuetify'
import { useAuthStore } from '~/store/auth'
import { normalize_to_e164 } from '~/utils/formatters'

// --- [PERBAIKAN] Komponen sekarang dipanggil LoginHistoryCard (nama file tetap) ---
const LoginHistoryCard = defineAsyncComponent({
  loader: () => import('~/components/akun/LoginHistoryCard.vue'),
  ssr: false,
})
const UserSpendingChart = defineAsyncComponent({
  loader: () => import('~/components/charts/UserSpendingChart.vue'),
  ssr: false,
})

// --- Inisialisasi & State Management ---
const { $api } = useNuxtApp()
const authStore = useAuthStore()
const display = useDisplay()
const profileLoading = ref(true)
const profileError = ref<string | null>(null)
const securityLoading = ref(false)
const securityAlert = ref<{ type: 'success' | 'error', message: string } | null>(null)
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

// --- Computed Properties ---
const currentUser = computed(() => authStore.currentUser)
const isUser = computed(() => currentUser.value?.role === 'USER')
const isKomandan = computed(() => currentUser.value?.role === 'KOMANDAN')
const isAdminOrSuperAdmin = computed(() => ['ADMIN', 'SUPER_ADMIN'].includes(currentUser.value?.role ?? ''))

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
      const success = await authStore.fetchUser()
      if (!success)
        // DIPERBAIKI: Menggunakan ?? untuk fallback yang aman
        throw new Error(authStore.error ?? 'Gagal memuat data pengguna.')
    }
    populateEditForm()
    if (isUser.value)
      fetchSpendingSummary()
  }
  catch (error: any) {
    profileError.value = error.message
  }
  finally {
    profileLoading.value = false
  }
}
async function saveProfile() {
  if (profileForm.value === null) // Perbaikan: Perbandingan eksplisit
    return
  const { valid } = await profileForm.value.validate()
  if (!valid)
    return

  securityLoading.value = true
  profileAlert.value = null

  const isPrivilegedUser = isAdminOrSuperAdmin.value || isKomandan.value
  const endpoint = isPrivilegedUser ? `/admin/users/me` : `/auth/me/profile`

  const payload: Partial<User> = { full_name: editData.value.full_name }

  if (isPrivilegedUser) {
    try {
      payload.phone_number = normalize_to_e164(editData.value.phone_number)
    }
    catch (e: any) {
      profileAlert.value = { type: 'error', message: e.message || 'Format nomor telepon tidak valid.' }
      securityLoading.value = false
      return
    }
  }

  try {
    const response = await $api<User>(endpoint, { method: 'PUT', body: payload })
    authStore.setUser(response)
    populateEditForm()
    profileAlert.value = { type: 'success', message: 'Profil berhasil diperbarui!' }
  }
  catch (error: any) {
    // DIPERBAIKI: Pemeriksaan tipe eksplisit untuk pesan error
    const errorMessage = (typeof error.data?.message === 'string' && error.data.message) ? error.data.message : 'Terjadi kesalahan'
    profileAlert.value = { type: 'error', message: `Gagal menyimpan profil: ${errorMessage}` }
  }
  finally {
    securityLoading.value = false
  }
}
async function resetHotspotPassword() {
  securityLoading.value = true
  securityAlert.value = null
  if (currentUser.value === null || currentUser.value === undefined) { // Perbaikan: Perbandingan eksplisit
    securityAlert.value = { type: 'error', message: 'Data pengguna tidak ditemukan.' }
    securityLoading.value = false
    return
  }
  const isPrivilegedUser = isAdminOrSuperAdmin.value || isKomandan.value
  const endpoint = isPrivilegedUser
    ? `/admin/users/${currentUser.value.id}/reset-hotspot-password`
    : '/users/me/reset-hotspot-password'

  try {
    const response = await $api<{ message: string }>(endpoint, { method: 'POST' })
    // DIPERBAIKI: Menggunakan ?? untuk fallback yang aman
    securityAlert.value = { type: 'success', message: response.message ?? 'Password hotspot berhasil direset.' }
  }
  catch (error: any) {
    // DIPERBAIKI: Pemeriksaan tipe eksplisit untuk pesan error
    const errorMessage = (typeof error.data?.message === 'string' && error.data.message) ? error.data.message : 'Kesalahan tidak diketahui'
    securityAlert.value = { type: 'error', message: `Gagal mereset password: ${errorMessage}` }
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
  if (!valid)
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
    // DIPERBAIKI: Pemeriksaan tipe eksplisit untuk pesan error
    const errorMessage = (typeof error.data?.message === 'string' && error.data.message) ? error.data.message : 'Gagal mengubah password.'
    passwordAlert.value = { type: 'error', message: errorMessage }
  }
  finally {
    passwordLoading.value = false
  }
}
onMounted(loadInitialData)
watch(() => authStore.currentUser, (newUser) => {
  if (newUser)
    populateEditForm()
}, { deep: true })

// DIPERBAIKI: Aturan validasi menggunakan perbandingan eksplisit
const requiredRule = (v: any) => (v !== null && v !== undefined && v !== '') || 'Wajib diisi.' // Perbaikan: Perbandingan eksplisit dengan null, undefined, dan string kosong
const nameLengthRule = (v: string) => (v !== null && v !== undefined && v.length >= 2) || 'Nama minimal 2 karakter.' // Perbaikan: Perbandingan eksplisit
const phoneRule = (v: string) => /^(?:\+62|0)8[1-9]\d{7,12}$/.test(v) || 'Format nomor telepon tidak valid.'
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

    <VRow v-else-if="currentUser !== null" class="ga-0"> <VCol cols="12" lg="8">
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
                    <VCol v-if="isUser" cols="12" md="6">
                      <AppTextField :model-value="currentUser.blok || 'N/A'" label="Blok" readonly disabled prepend-inner-icon="tabler-building" />
                    </VCol>
                    <VCol v-if="isUser" cols="12" md="6">
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

          <VCol cols="12">
            <VCard>
              <VCardItem>
                <VCardTitle class="text-h5">
                  Keamanan
                </VCardTitle>
                <VCardSubtitle>Kelola kredensial dan akses keamanan akun Anda.</VCardSubtitle>
              </VCardItem>
              <VCardText>
                <VAlert v-if="securityAlert" :type="securityAlert.type" variant="tonal" density="compact" closable class="mb-4" @update:model-value="securityAlert = null">
                  {{ securityAlert.message }}
                </VAlert>
                <div class="d-flex flex-wrap ga-4">
                  <VBtn v-if="isAdminOrSuperAdmin" color="secondary" variant="tonal" prepend-icon="tabler-key" @click="isPasswordDialogVisible = true">
                    Ubah Password Portal
                  </VBtn>
                  <VBtn color="warning" variant="tonal" :loading="securityLoading" prepend-icon="tabler-wifi" @click="resetHotspotPassword">
                    Reset Password Hotspot
                  </VBtn>
                </div>
              </VCardText>
            </VCard>
          </VCol>

          <VCol v-if="isUser" cols="12">
            <VCard>
              <VCardItem>
                <VCardTitle class="text-h5">
                  Ringkasan Pengeluaran
                </VCardTitle>
                <VCardSubtitle>Grafik pengeluaran Anda dalam seminggu terakhir.</VCardSubtitle>
                <template #append>
                  <div class="text-right">
                    <div class="text-h5 font-weight-bold text-success">
                      {{ totalSpendingThisPeriod }}
                    </div>
                    <div class="text-caption">
                      Minggu Ini
                    </div>
                  </div>
                </template>
              </VCardItem>
              <VCardText>
                <div v-if="spendingChartLoading" class="text-center py-4">
                  <VProgressCircular indeterminate />
                </div>
                <VAlert v-if="spendingAlert" :type="spendingAlert.type" variant="tonal" density="compact" closable class="mb-4" @update:model-value="spendingAlert = null">
                  {{ spendingAlert.message }}
                </VAlert>
                <div :style="{ height: display.smAndDown ? '200px' : '250px' }">
                  <UserSpendingChart v-if="spendingChartData[0]?.data.length > 0" :series-data="spendingChartData" :categories="spendingChartCategories" />
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
              <LoginHistoryCard />
            </VCard>
          </VCol>
        </VRow>
      </VCol>
    </VRow>

    <VDialog v-model="isPasswordDialogVisible" max-width="500px" persistent>
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