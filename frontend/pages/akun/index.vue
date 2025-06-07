<script lang="ts" setup>
import { ref, onMounted, computed, watch, defineAsyncComponent } from 'vue'
import { useNuxtApp } from '#app'
import type { UserMeResponseSchema, UserProfileResponseSchema } from '~/types/api'
import { VForm } from 'vuetify/components/VForm'
import { useDisplay } from 'vuetify'

// --- Tipe Lokal untuk Request Payload ---
// Tipe ini mungkin perlu ditambahkan di file `types/api.ts` Anda agar lebih terpusat
interface UserProfileUpdateRequest {
  full_name: string
  blok: string | null
  kamar: string | null
}
interface AdminProfileUpdateRequest {
  full_name: string
  phone_number: string
}
interface ChangePasswordRequest {
  current_password: string
  new_password: string
}

// Dynamic import untuk chart agar tidak membebani render sisi server
const UserSpendingChart = defineAsyncComponent({
  loader: () => import('~/components/charts/UserSpendingChart.vue'),
  ssr: false,
})

// --- Inisialisasi ---
const { $api } = useNuxtApp()
const authStore = useAuthStore()
const display = useDisplay()

// --- Computed Properties untuk Peran ---
const isUser = computed(() => authStore.user?.role === 'USER')
const isAdmin = computed(() => authStore.user?.role === 'ADMIN')
const isSuperAdmin = computed(() => authStore.user?.role === 'SUPER_ADMIN')

// --- State Management ---

// Profil Umum & Status Halaman
const userProfile = ref<Partial<UserMeResponseSchema>>({})
const pageLoading = ref(true)
const pageError = ref<string | null>(null)

// Form Profil Pengguna (USER)
const userProfileForm = ref<InstanceType<typeof VForm> | null>(null)
const userProfileLoading = ref(false)
const userProfileAlert = ref<{ type: 'success' | 'error' | 'warning'; message: string } | null>(null)
const editUserProfileData = ref<UserProfileUpdateRequest>({ full_name: '', blok: null, kamar: null })
const showBlokKamar = ref(true)

// Form Profil Admin
const adminProfileForm = ref<InstanceType<typeof VForm> | null>(null)
const adminProfileLoading = ref(false)
const adminProfileAlert = ref<{ type: 'success' | 'error' | 'warning'; message: string } | null>(null)
const editAdminProfileData = ref<AdminProfileUpdateRequest>({ full_name: '', phone_number: '' })

// Form Ubah Password (ADMIN/SUPER ADMIN)
const passwordForm = ref<InstanceType<typeof VForm> | null>(null)
const passwordLoading = ref(false)
const passwordAlert = ref<{ type: 'success' | 'error' | 'warning'; message: string } | null>(null)
const passwordData = ref<ChangePasswordRequest>({ current_password: '', new_password: '' })
const confirmPassword = ref('')
const isPasswordVisible = ref(false)

// Keamanan Hotspot (hanya USER)
const securityLoading = ref(false)
const securityAlert = ref<{ type: 'success' | 'error' | 'warning'; message: string } | null>(null)

// Riwayat & Statistik
const loginHistory = ref<Array<{ date: string; ip_address: string; device: string; os: string; icon: string }>>([])
const loginHistoryLoading = ref(false)
const totalSpendingThisPeriod = ref<string>("Rp 0")
const spendingChartData = ref([{ data: [] as number[] }])
const spendingChartCategories = ref<string[]>([])
const spendingChartLoading = ref(false)


// --- Logika Inti & Panggilan API ---

const fetchInitialData = async () => {
  pageLoading.value = true
  pageError.value = null
  try {
    // 1. Ambil data utama pengguna
    const data = await $api<UserMeResponseSchema>('/auth/me', { method: 'GET' })
    userProfile.value = data
    authStore.setUser(data) // Selalu update store dengan data terbaru

    // 2. Siapkan data form berdasarkan peran
    if (data.role === 'USER') {
      editUserProfileData.value = { full_name: data.full_name || '', blok: data.blok || null, kamar: data.kamar || null }
      showBlokKamar.value = !!(data.blok && data.kamar)
      // Panggil API khusus USER
      fetchSpendingSummary()
    } else { // Admin & Super Admin
      editAdminProfileData.value = { full_name: data.full_name || '', phone_number: data.phone_number || '' }
    }
    
    // 3. Panggil API yang umum untuk semua peran
    fetchLoginHistory()

  } catch (error: any) {
    pageError.value = error.data?.message || error.data?.error || 'Gagal memuat data profil.'
  } finally {
    pageLoading.value = false
  }
}

const saveUserProfile = async () => {
  if (!userProfileForm.value) return
  const { valid } = await userProfileForm.value.validate()
  if (!valid) return

  userProfileLoading.value = true
  userProfileAlert.value = null

  // Pastikan blok/kamar null jika switch off
  const payload: UserProfileUpdateRequest = {
    ...editUserProfileData.value,
    blok: showBlokKamar.value ? editUserProfileData.value.blok : null,
    kamar: showBlokKamar.value ? editUserProfileData.value.kamar : null,
  }

  try {
    const response = await $api<UserProfileResponseSchema>('/users/me/profile', { method: 'PUT', body: payload })
    
    // Update data di store dan state lokal
    if (authStore.user) {
        authStore.setUser({ ...authStore.user, ...response })
    }
    Object.assign(userProfile.value, response)

    userProfileAlert.value = { type: 'success', message: 'Profil berhasil diperbarui.' }
  } catch (error: any) {
    userProfileAlert.value = { type: 'error', message: `Gagal menyimpan: ${error.data?.message || 'Kesalahan tidak diketahui'}` }
  } finally {
    userProfileLoading.value = false
  }
}

const saveAdminProfile = async () => {
  if (!adminProfileForm.value) return
  const { valid } = await adminProfileForm.value.validate()
  if (!valid) return

  adminProfileLoading.value = true
  adminProfileAlert.value = null
  try {
    const response = await $api<UserMeResponseSchema>('/admin/users/me', { method: 'PUT', body: editAdminProfileData.value })
    authStore.setUser(response)
    Object.assign(userProfile.value, response)
    adminProfileAlert.value = { type: 'success', message: 'Profil admin berhasil diperbarui.' }
  } catch (error: any) {
    adminProfileAlert.value = { type: 'error', message: `Gagal menyimpan: ${error.data?.message || 'Kesalahan tidak diketahui'}` }
  } finally {
    adminProfileLoading.value = false
  }
}

const changePassword = async () => {
  if (!passwordForm.value) return
  const { valid } = await passwordForm.value.validate()
  if (!valid) return

  passwordLoading.value = true
  passwordAlert.value = null
  try {
    const response = await $api('/auth/me/change-password', {
      method: 'POST',
      body: passwordData.value,
    })
    passwordAlert.value = { type: 'success', message: (response as any)?.message || 'Password berhasil diubah!' }
    passwordForm.value.reset()
    confirmPassword.value = ''
  } catch (error: any) {
    passwordAlert.value = { type: 'error', message: `Gagal mengubah password: ${error.data?.message || 'Kesalahan tidak diketahui'}` }
  } finally {
    passwordLoading.value = false
  }
}

const resetHotspotPassword = async () => {
  securityLoading.value = true
  securityAlert.value = null
  try {
    const response = await $api<{ success: boolean; message: string; }>('/users/me/reset-hotspot-password', { method: 'POST' })
    securityAlert.value = { type: response.success ? 'success' : 'error', message: response.message || 'Gagal mereset password.' }
  } catch (error: any) {
    securityAlert.value = { type: 'error', message: `Gagal mereset: ${error.data?.message || 'Kesalahan tidak diketahui'}` }
  } finally {
    securityLoading.value = false
  }
}

const parseUserAgent = (uaString?: string | null): { device: string; os: string; icon: string } => {
  if (!uaString) return { device: 'Tidak diketahui', os: 'Tidak diketahui', icon: 'tabler-device-desktop-question' }
  let device = 'Desktop'; let os = 'OS Tidak diketahui'; let icon = 'tabler-device-desktop'
  if (/android/i.test(uaString)) { os = 'Android'; device = 'Mobile'; icon = 'tabler-device-mobile' }
  else if (/iphone|ipad|ipod/i.test(uaString)) { os = 'iOS'; device = 'Mobile'; icon = 'tabler-device-mobile' }
  else if (/windows nt/i.test(uaString)) { os = 'Windows'; icon = 'tabler-brand-windows' }
  else if (/macintosh|mac os x/i.test(uaString)) { os = 'macOS'; icon = 'tabler-brand-apple' }
  else if (/linux/i.test(uaString)) { os = 'Linux'; icon = 'tabler-brand-linux' }
  return { device, os, icon }
}

const fetchLoginHistory = async () => {
  loginHistoryLoading.value = true
  try {
    const response = await $api<{success: boolean, history: any[]}>('/users/me/login-history', { params: { limit: 5 }, method: 'GET' })
    if (response.success && response.history) {
      loginHistory.value = response.history.map((item:any) => ({ 
          date: formatDate(item.login_time), 
          ...parseUserAgent(item.user_agent_string), 
          ip_address: item.ip_address || 'N/A' 
      }))
    }
  } catch (e) {
    //
  } finally { 
    loginHistoryLoading.value = false 
  }
}

const fetchSpendingSummary = async () => {
  if (!isUser.value) return
  spendingChartLoading.value = true
  try {
    const response = await $api<any>('/users/me/weekly-spending', { method: 'GET' })
    if (response && response.categories && response.series) {
        spendingChartCategories.value = response.categories
        spendingChartData.value = response.series
        totalSpendingThisPeriod.value = formatCurrency(response.total_this_week)
    }
  } catch (e) {
    //
  } finally { 
      spendingChartLoading.value = false 
  }
}

onMounted(fetchInitialData)

watch(showBlokKamar, (isAsrama) => {
  if (!isAsrama) {
    editUserProfileData.value.blok = null
    editUserProfileData.value.kamar = null
  }
})

// --- Validasi & Helper ---
const requiredRule = (v: any) => !!v || 'Wajib diisi.'
const nameLengthRule = (v: string) => (v && v.length >= 2) || 'Minimal 2 karakter.'
const phoneFormatRule = (v: string) => /^\+628[1-9][0-9]{7,11}$/.test(v) || 'Format harus +62xxxxxxxxxx.'
const passwordLengthRule = (v: string) => (v && v.length >= 6) || 'Password minimal 6 karakter.'
const passwordMatchRule = (v: string) => v === passwordData.value.new_password || 'Password tidak sama.'

const formatDate = (dateString?: string | Date | null) => {
    if (!dateString) return 'N/A'
    const options: Intl.DateTimeFormatOptions = display.smAndDown.value ? { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' } : { year: 'numeric', month: 'long', day: 'numeric', hour: '2-digit', minute: '2-digit' }
    try { return new Date(dateString).toLocaleString('id-ID', options) } catch (e) { return 'Invalid Date' }
}
const formatCurrency = (amount: number) => new Intl.NumberFormat('id-ID', { style: 'currency', currency: 'IDR', minimumFractionDigits: 0 }).format(amount)

const blokItems = ['A', 'B', 'C', 'D', 'E', 'F']
const kamarItems = ['1', '2', '3', '4', '5', '6']
</script>

<template>
  <VContainer fluid class="pa-sm-4 pa-2">
    <div v-if="pageLoading" class="text-center py-16">
      <VProgressCircular indeterminate color="primary" size="64" />
      <p class="mt-4 text-body-1">Memuat data profil...</p>
    </div>

    <div v-else-if="pageError" class="text-center py-16">
      <VIcon icon="tabler-alert-triangle" size="64" color="error" />
      <p class="text-h6 mt-4">Gagal Memuat Data</p>
      <p class="text-body-1 mt-2">{{ pageError }}</p>
      <VBtn color="primary" class="mt-4" @click="fetchInitialData">Coba Lagi</VBtn>
    </div>

    <div v-else-if="userProfile.id">
      
      <template v-if="isUser">
        <VRow class="flex-column-reverse flex-md-row">
          <VCol cols="12" md="7" lg="8">
            <VCard class="mb-4">
              <VCardTitle>Profil Pengguna</VCardTitle>
              <VCardText>
                <VAlert v-if="userProfileAlert" :type="userProfileAlert.type" variant="tonal" density="compact" closable class="mb-4" @update:model-value="userProfileAlert = null">{{ userProfileAlert.message }}</VAlert>
                <VForm ref="userProfileForm" @submit.prevent="saveUserProfile">
                  <VRow dense>
                    <VCol cols="12">
                      <AppTextField v-model="editUserProfileData.full_name" label="Nama Lengkap" :rules="[requiredRule, nameLengthRule]" :loading="userProfileLoading" density="comfortable" prepend-inner-icon="tabler-user" />
                    </VCol>
                    <VCol cols="12">
                      <VSwitch v-model="showBlokKamar" label="Saya tinggal di asrama" color="primary" density="comfortable" />
                    </VCol>
                    <template v-if="showBlokKamar">
                      <VCol cols="12" sm="6">
                        <AppSelect v-model="editUserProfileData.blok" label="Blok" :items="blokItems" :rules="showBlokKamar ? [requiredRule] : []" :loading="userProfileLoading" density="comfortable" prepend-inner-icon="tabler-building-cottage" />
                      </VCol>
                      <VCol cols="12" sm="6">
                        <AppSelect v-model="editUserProfileData.kamar" label="Kamar" :items="kamarItems" :rules="showBlokKamar ? [requiredRule] : []" :loading="userProfileLoading" density="comfortable" prepend-inner-icon="tabler-door" />
                      </VCol>
                    </template>
                  </VRow>
                  <VCardActions class="mt-4 pa-0">
                    <VBtn block color="primary" type="submit" :loading="userProfileLoading" size="large">Simpan Profil</VBtn>
                  </VCardActions>
                </VForm>
              </VCardText>
            </VCard>
            <VCard>
              <VCardTitle>Keamanan Hotspot</VCardTitle>
              <VCardText>
                <VAlert v-if="securityAlert" :type="securityAlert.type" variant="tonal" closable class="mb-4" @update:model-value="securityAlert = null">{{ securityAlert.message }}</VAlert>
                <p class="mb-4 text-body-2">Lupa password hotspot? Reset untuk mendapatkan password baru (6 digit angka) via WhatsApp.</p>
                <VBtn block color="warning" variant="tonal" @click="resetHotspotPassword" :loading="securityLoading" size="large">Reset Password Hotspot</VBtn>
              </VCardText>
            </VCard>
          </VCol>
          <VCol cols="12" md="5" lg="4">
            <VCard class="mb-4">
              <VCardTitle>Ringkasan Pengeluaran</VCardTitle>
              <VCardSubtitle>7 hari terakhir</VCardSubtitle>
              <VCardText>
                <div v-if="spendingChartLoading" class="text-center py-4"><VProgressCircular indeterminate /></div>
                <template v-else>
                  <div class="d-flex justify-space-between align-center mb-3">
                    <h5 class="text-h6">Total:</h5>
                    <h5 class="text-h6 text-success">{{ totalSpendingThisPeriod }}</h5>
                  </div>
                  <div :style="{ height: '220px' }">
                    <UserSpendingChart :series-data="spendingChartData" :categories="spendingChartCategories" />
                  </div>
                </template>
              </VCardText>
            </VCard>
             <VCard class="mb-4">
                <VCardTitle>Informasi & Riwayat</VCardTitle>
                <VDivider />
                <VList lines="two" density="comfortable">
                    <VListItem title="Status Akun">
                        <template #prepend><VIcon icon="tabler-id-badge-2" class="mx-3" /></template>
                        <template #append><VChip :color="userProfile.is_active ? 'success' : 'error'" size="small" label>{{ userProfile.is_active ? 'Aktif' : 'Tidak Aktif' }}</VChip></template>
                    </VListItem>
                    <VListItem title="Tanggal Terdaftar">
                        <template #prepend><VIcon icon="tabler-calendar-plus" class="mx-3" /></template>
                        <template #append><span class="text-body-2">{{ formatDate(userProfile.created_at) }}</span></template>
                    </VListItem>
                </VList>
                <VDivider/>
                <div v-if="loginHistoryLoading" class="text-center pa-4"><VProgressCircular indeterminate size="24" /></div>
                <VList v-else-if="loginHistory.length > 0" nav density="compact">
                    <VListItem v-for="(item, index) in loginHistory" :key="index">
                        <template #prepend><VIcon :icon="item.icon" size="22" class="mx-3" /></template>
                        <VListItemTitle class="font-weight-medium">{{ item.date }}</VListItemTitle>
                        <VListItemSubtitle class="text-caption">IP: {{ item.ip_address }} | {{ item.os }}</VListItemSubtitle>
                    </VListItem>
                </VList>
                <VCardText v-else class="text-center text-caption text-disabled py-4">Belum ada riwayat akses tercatat.</VCardText>
            </VCard>
          </VCol>
        </VRow>
      </template>

      <template v-else-if="isAdmin || isSuperAdmin">
        <VRow>
          <VCol cols="12" md="7" lg="8">
            <VCard class="mb-4">
              <VCardTitle>Profil {{ isSuperAdmin ? 'Super Admin' : 'Admin' }}</VCardTitle>
              <VCardText>
                <VAlert v-if="adminProfileAlert" :type="adminProfileAlert.type" variant="tonal" density="compact" closable class="mb-4" @update:model-value="adminProfileAlert = null">{{ adminProfileAlert.message }}</VAlert>
                <VForm ref="adminProfileForm" @submit.prevent="saveAdminProfile">
                  <VRow dense>
                    <VCol cols="12">
                      <AppTextField v-model="editAdminProfileData.full_name" label="Nama Lengkap" :rules="[requiredRule, nameLengthRule]" :loading="adminProfileLoading" prepend-inner-icon="tabler-user" density="comfortable" />
                    </VCol>
                    <VCol cols="12">
                      <AppTextField v-model="editAdminProfileData.phone_number" label="Nomor Telepon (Username)" :rules="[requiredRule, phoneFormatRule]" :loading="adminProfileLoading" prepend-inner-icon="tabler-phone" placeholder="+62..." density="comfortable" />
                    </VCol>
                  </VRow>
                  <VCardActions class="mt-4 pa-0">
                    <VBtn block color="primary" type="submit" :loading="adminProfileLoading" size="large">Simpan Perubahan</VBtn>
                  </VCardActions>
                </VForm>
              </VCardText>
            </VCard>
            <VCard>
              <VCardTitle>Ubah Password Portal</VCardTitle>
              <VCardText>
                <VAlert v-if="passwordAlert" :type="passwordAlert.type" variant="tonal" density="compact" closable class="mb-4" @update:model-value="passwordAlert = null">{{ passwordAlert.message }}</VAlert>
                <VForm ref="passwordForm" @submit.prevent="changePassword">
                  <VRow dense>
                    <VCol cols="12">
                      <AppTextField v-model="passwordData.current_password" label="Password Saat Ini" :type="isPasswordVisible ? 'text' : 'password'" :append-inner-icon="isPasswordVisible ? 'tabler-eye-off' : 'tabler-eye'" @click:append-inner="isPasswordVisible = !isPasswordVisible" :rules="[requiredRule]" density="comfortable" />
                    </VCol>
                    <VCol cols="12" sm="6">
                      <AppTextField v-model="passwordData.new_password" label="Password Baru" :type="isPasswordVisible ? 'text' : 'password'" :rules="[requiredRule, passwordLengthRule]" density="comfortable" />
                    </VCol>
                    <VCol cols="12" sm="6">
                      <AppTextField v-model="confirmPassword" label="Konfirmasi Password Baru" :type="isPasswordVisible ? 'text' : 'password'" :rules="[requiredRule, passwordMatchRule]" density="comfortable" />
                    </VCol>
                  </VRow>
                  <VCardActions class="mt-4 pa-0">
                    <VBtn block color="primary" type="submit" :loading="passwordLoading" size="large">Ubah Password</VBtn>
                  </VCardActions>
                </VForm>
              </VCardText>
            </VCard>
          </VCol>
          <VCol cols="12" md="5" lg="4">
            <VCard class="mb-4">
              <VCardTitle>Informasi Akun</VCardTitle>
              <VDivider />
              <VList lines="two" density="comfortable">
                <VListItem title="Status Akun">
                  <template #prepend><VIcon icon="tabler-id-badge-2" class="mx-3" /></template>
                  <template #append><VChip :color="userProfile.is_active ? 'success' : 'error'" size="small" label>{{ userProfile.is_active ? 'Aktif' : 'Tidak Aktif' }}</VChip></template>
                </VListItem>
                <VListItem title="Peran Akun">
                  <template #prepend><VIcon icon="tabler-shield-check" class="mx-3" /></template>
                  <template #append><VChip color="info" size="small" label>{{ userProfile.role }}</VChip></template>
                </VListItem>
                <VListItem title="Tanggal Terdaftar">
                  <template #prepend><VIcon icon="tabler-calendar-plus" class="mx-3" /></template>
                  <template #append><span class="text-body-2">{{ formatDate(userProfile.created_at) }}</span></template>
                </VListItem>
              </VList>
            </VCard>
            <VCard>
              <VCardTitle>Riwayat Akses</VCardTitle>
              <VDivider />
              <div v-if="loginHistoryLoading" class="text-center pa-4"><VProgressCircular indeterminate /></div>
              <VList v-else-if="loginHistory.length > 0" nav density="compact">
                <VListItem v-for="(item, index) in loginHistory" :key="index">
                  <template #prepend><VIcon :icon="item.icon" size="22" class="mx-3" /></template>
                  <VListItemTitle class="font-weight-medium">{{ item.date }}</VListItemTitle>
                  <VListItemSubtitle class="text-caption">IP: {{ item.ip_address }} | {{ item.os }}</VListItemSubtitle>
                </VListItem>
              </VList>
              <VCardText v-else class="text-center text-caption text-disabled py-4">Belum ada riwayat akses tercatat.</VCardText>
            </VCard>
          </VCol>
        </VRow>
      </template>

    </div>
  </VContainer>
</template>

<style lang="scss" scoped>
.v-list-item {
  padding-inline: 16px;
}
.v-list-item-subtitle {
  white-space: normal;
}
</style>