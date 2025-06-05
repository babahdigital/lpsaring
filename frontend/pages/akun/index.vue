<script lang="ts" setup>
import { ref, onMounted, computed, defineAsyncComponent } from 'vue'
import { useNuxtApp } from '#app'
import type { UserMeResponseSchema, UserProfileUpdateRequestSchema, UserProfileResponseSchema } from '~/types/api'
import { VForm } from 'vuetify/components/VForm'
import { useDisplay } from 'vuetify'

// Dynamic import untuk chart (SSR disabled)
const UserSpendingChart = defineAsyncComponent({
  loader: () => import('~/components/charts/UserSpendingChart.vue'),
  ssr: false
})

const { $api } = useNuxtApp()
const authStore = useAuthStore()

// Data states
const userProfile = ref<Partial<UserMeResponseSchema>>({})
const editFullName = ref('')
const profileForm = ref<InstanceType<typeof VForm> | null>(null)
const profileLoading = ref(false)
const profileAlert = ref<{ type: 'success' | 'error' | 'info' | 'warning'; message: string } | null>(null)

const securityLoading = ref(false)
const securityAlert = ref<{ type: 'success' | 'error' | 'info' | 'warning'; message: string } | null>(null)

const loginHistory = ref<Array<{ date: string; ip_address: string; device: string; os: string; icon: string }>>([])
const loginHistoryLoading = ref(false)
const loginHistoryAlert = ref<{ type: 'success' | 'error' | 'info' | 'warning'; message: string } | null>(null)

const totalSpendingThisPeriod = ref<string>("Rp 0")
const spendingChartData = ref([{ data: [] as number[] }])
const spendingChartCategories = ref<string[]>([])
const spendingChartLoading = ref(false)
const spendingAlert = ref<{ type: 'success' | 'error' | 'info' | 'warning'; message: string } | null>(null)

// Menambahkan breakpoint composable
const display = useDisplay()

// Fungsi untuk mengambil data profil pengguna
const fetchUserProfile = async () => {
  profileLoading.value = true
  profileAlert.value = null
  try {
    if (authStore.user && authStore.user.id) {
      userProfile.value = JSON.parse(JSON.stringify(authStore.user))
      editFullName.value = authStore.user.full_name || ''
    } else {
      const data = await $api<UserMeResponseSchema>('/auth/me', { method: 'GET' })
      if (data) {
        userProfile.value = data
        editFullName.value = data.full_name || ''
        authStore.setUser(data)
      } else {
        throw new Error("Data profil tidak ditemukan dari API /auth/me")
      }
    }
  } catch (error: any) {
    profileAlert.value = { type: 'error', message: `Gagal memuat profil: ${error.data?.error || error.data?.message || error.message || 'Kesalahan tidak diketahui'}` }
    userProfile.value = {}
    editFullName.value = ''
  } finally {
    profileLoading.value = false
  }
}

// Fungsi untuk menyimpan perubahan profil
const saveProfile = async () => {
  if (!profileForm.value) return
  const { valid } = await profileForm.value.validate()
  if (!valid) {
    profileAlert.value = { type: 'warning', message: 'Harap periksa kembali input Anda.' }
    return
  }

  profileLoading.value = true
  profileAlert.value = null

  const payload: UserProfileUpdateRequestSchema = {
    full_name: editFullName.value,
    blok: userProfile.value.blok as any,
    kamar: userProfile.value.kamar as any,
  }

  if (!payload.blok || !payload.kamar) {
    profileAlert.value = { type: 'error', message: 'Data Blok atau Kamar tidak lengkap pada profil Anda. Tidak dapat menyimpan.' }
    profileLoading.value = false
    return
  }

  try {
    const response = await $api<UserProfileResponseSchema>('/users/me/profile', {
      method: 'PUT',
      body: payload,
    })
    userProfile.value.full_name = response.full_name
    userProfile.value.updated_at = response.updated_at
    editFullName.value = response.full_name || ''

    if (authStore.user) {
      authStore.setUser({
        ...authStore.user,
        full_name: response.full_name,
        updated_at: response.updated_at
      })
    }
    profileAlert.value = { type: 'success', message: 'Nama Lengkap berhasil diperbarui.' }
  } catch (error: any) {
    profileAlert.value = { type: 'error', message: `Gagal menyimpan profil: ${error.data?.error || error.data?.message || error.message || 'Kesalahan tidak diketahui'}` }
  } finally {
    profileLoading.value = false
  }
}

// Fungsi untuk mereset password hotspot
const resetHotspotPassword = async () => {
  securityLoading.value = true
  securityAlert.value = null
  try {
    const response = await $api<{ success: boolean; message: string; new_password_for_testing?: string }>('/users/me/reset-hotspot-password', {
      method: 'POST',
    })
    if (response.success) {
      let successMessage = response.message
      if (response.new_password_for_testing && process.dev) {
        successMessage += ` (Password Baru Tes: ${response.new_password_for_testing})`
      }
      securityAlert.value = { type: 'success', message: successMessage }
    } else {
      securityAlert.value = { type: 'error', message: response.message || 'Gagal mereset password hotspot.' }
    }
  } catch (error: any) {
    securityAlert.value = { type: 'error', message: `Gagal mereset password hotspot: ${error.data?.error || error.data?.message || error.message || 'Kesalahan tidak diketahui'}` }
  } finally {
    securityLoading.value = false
  }
}

// Fungsi untuk mengurai User-Agent
const parseUserAgent = (uaString?: string | null): { device: string; os: string; icon: string } => {
  if (!uaString) return { device: 'Tidak diketahui', os: 'Tidak diketahui', icon: 'tabler-device-desktop-question' }
  let device = 'Desktop'
  let os = 'OS Tidak diketahui'
  let icon = 'tabler-device-desktop' // Default icon
  if (/android/i.test(uaString)) { os = 'Android'; device = 'Mobile'; icon = 'tabler-device-mobile' }
  else if (/iphone|ipad|ipod/i.test(uaString)) { os = 'iOS'; device = 'Mobile'; icon = 'tabler-device-mobile' }
  else if (/windows nt/i.test(uaString)) { os = 'Windows'; icon = 'tabler-brand-windows' }
  else if (/macintosh|mac os x/i.test(uaString)) { os = 'macOS'; icon = 'tabler-brand-apple' }
  else if (/linux/i.test(uaString)) { os = 'Linux'; icon = 'tabler-brand-linux' }
  return { device, os, icon }
}

// Fungsi untuk mengambil riwayat login
const fetchLoginHistory = async () => {
  loginHistoryLoading.value = true
  loginHistoryAlert.value = null
  try {
    const response = await $api<{
      success: boolean;
      history: Array<{ login_time: string; ip_address: string | null; user_agent_string: string | null }>;
      message?: string;
    }>('/users/me/login-history', { params: { limit: 3 }, method: 'GET' })

    if (response.success && response.history) {
      loginHistory.value = response.history.map(item => {
        const uaInfo = parseUserAgent(item.user_agent_string)
        return {
          date: formatDate(item.login_time),
          ip_address: item.ip_address || 'N/A',
          device: uaInfo.device,
          os: uaInfo.os,
          icon: uaInfo.icon, // Menggunakan icon OS yang sesuai
        }
      })
      if (loginHistory.value.length === 0) {
        loginHistoryAlert.value = { type: 'info', message: 'Belum ada riwayat akses yang tercatat.' }
      }
    } else {
      throw new Error(response.message || 'Gagal mengambil data riwayat akses.')
    }
  } catch (error: any) {
    loginHistoryAlert.value = { type: 'error', message: `Gagal memuat riwayat akses: ${error.data?.message || error.message || 'Kesalahan tidak diketahui'}` }
    loginHistory.value = []
  } finally {
    loginHistoryLoading.value = false
  }
}

// Fungsi untuk mengambil ringkasan pengeluaran
const fetchSpendingSummary = async () => {
  spendingChartLoading.value = true
  spendingAlert.value = null
  try {
    const response = await $api<{
      categories: string[]
      series: Array<{ name?: string; data: number[] }>
      total_this_week: number
      success?: boolean
      message?: string
    }>('/users/me/weekly-spending', { method: 'GET' })

    if (response && response.categories && response.series) {
      spendingChartCategories.value = response.categories
      spendingChartData.value = response.series
      totalSpendingThisPeriod.value = formatCurrency(response.total_this_week)
      if (response.series[0]?.data.length === 0 && response.categories.length > 0) {
        spendingAlert.value = { type: 'info', message: 'Belum ada data pengeluaran untuk minggu ini.' }
      } else if (response.categories.length === 0) {
        spendingAlert.value = { type: 'info', message: 'Data periode pengeluaran tidak tersedia.' }
      }
    } else {
      spendingChartCategories.value = ['Sen', 'Sel', 'Rab', 'Kam', 'Jum', 'Sab', 'Min']
      spendingChartData.value = [{ data: [0, 0, 0, 0, 0, 0, 0] }]
      totalSpendingThisPeriod.value = formatCurrency(0)
      spendingAlert.value = { type: 'info', message: response?.message || 'Data pengeluaran belum tersedia saat ini.' }
    }
  } catch (error: any) {
    console.error("Error fetching spending summary:", error)
    spendingChartCategories.value = ['Sen', 'Sel', 'Rab', 'Kam', 'Jum', 'Sab', 'Min']
    spendingChartData.value = [{ data: [0, 0, 0, 0, 0, 0, 0] }]
    totalSpendingThisPeriod.value = formatCurrency(0)
    spendingAlert.value = { type: 'error', message: `Gagal memuat ringkasan pengeluaran: ${error.data?.message || error.message}` }
  } finally {
    spendingChartLoading.value = false
  }
}

onMounted(() => {
  fetchUserProfile()
  fetchLoginHistory()
  fetchSpendingSummary()
})

// Validation rules
const requiredRule = (value: any) => !!value || 'Field ini wajib diisi.'
const nameLengthRule = (value: string) => (value && value.length >= 2) || 'Nama minimal 2 karakter.'

// Format tanggal lebih ringkas untuk mobile
const formatDate = (dateString?: string | Date | null) => {
  if (!dateString) return 'N/A'
  
  const isMobile = display.smAndDown.value
  const options: Intl.DateTimeFormatOptions = isMobile 
    ? { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' }
    : { year: 'numeric', month: 'long', day: 'numeric', hour: '2-digit', minute: '2-digit' }
  
  try { 
    return new Date(dateString).toLocaleString('id-ID', options) 
  } catch (e) { 
    return String(dateString) 
  }
}

// Computed properties untuk menampilkan blok dan kamar
const displayBlok = computed(() => {
  if (!userProfile.value || !userProfile.value.blok) return 'N/A'
  return `Blok ${userProfile.value.blok}`
})

const displayKamar = computed(() => {
  if (!userProfile.value || !userProfile.value.kamar) return 'N/A'
  return `Kamar ${userProfile.value.kamar}`
})

// Fungsi untuk format mata uang
const formatCurrency = (amount: number) => {
  return new Intl.NumberFormat('id-ID', { style: 'currency', currency: 'IDR', minimumFractionDigits: 0 }).format(amount)
}

definePageMeta({
  // middleware: ['auth']
})
</script>

<template>
  <VContainer fluid class="pa-sm-4 pa-2">
    <VRow class="flex-column-reverse flex-md-row">
      <VCol cols="12" md="7" lg="8" class="pr-md-3">
        <VRow>
          <VCol cols="12">
            <VCard class="mb-4">
              <VCardTitle class="text-h6 text-sm-h5">Profil Saya</VCardTitle>
              <VCardSubtitle class="text-caption text-sm-body-2">Perbarui nama lengkap Anda</VCardSubtitle>
              
              <VCardText class="pt-2 pb-0">
                <VAlert
                  v-if="profileAlert"
                  :type="profileAlert.type"
                  variant="tonal"
                  density="compact"
                  closable
                  class="mb-4"
                  @update:model-value="profileAlert = null"
                >
                  {{ profileAlert.message }}
                </VAlert>
                
                <VForm ref="profileForm" @submit.prevent="saveProfile">
                  <VRow dense>
                    <VCol cols="12">
                      <AppTextField
                        v-model="editFullName"
                        prepend-inner-icon="tabler-user"
                        label="Nama Lengkap"
                        placeholder="Masukkan nama lengkap Anda"
                        density="compact"
                        :rules="[requiredRule, nameLengthRule]"
                        :loading="profileLoading"
                        :disabled="profileLoading"
                      />
                    </VCol>
                    <VCol cols="12">
                      <AppTextField
                        :model-value="userProfile.phone_number || 'N/A'"
                        prepend-inner-icon="tabler-device-mobile"
                        label="Nomor WhatsApp"
                        placeholder="Nomor WhatsApp Anda"
                        density="compact"
                        readonly
                        disabled
                      >
                        <template #append-inner>
                          <VIcon icon="tabler-info-circle" size="small">
                            <VTooltip
                              location="top"
                              transition="scale-transition"
                              activator="parent"
                            >
                              <span>Nomor WhatsApp tidak dapat diubah melalui halaman ini.</span>
                            </VTooltip>
                          </VIcon>
                        </template>
                      </AppTextField>
                    </VCol>
                    <VCol cols="12" sm="6">
                      <AppTextField
                        :model-value="displayBlok"
                        prepend-inner-icon="tabler-building-cottage"
                        label="Blok Tempat Tinggal"
                        placeholder="Blok Anda"
                        density="compact"
                        readonly
                        disabled
                      >
                        <template #append-inner>
                          <VIcon icon="tabler-info-circle" size="small">
                            <VTooltip
                              location="top"
                              transition="scale-transition"
                              activator="parent"
                            >
                              <span>Informasi Blok tidak dapat diubah melalui halaman ini.</span>
                            </VTooltip>
                          </VIcon>
                        </template>
                      </AppTextField>
                    </VCol>
                    <VCol cols="12" sm="6">
                      <AppTextField
                        :model-value="displayKamar"
                        prepend-inner-icon="tabler-door"
                        label="Nomor Kamar"
                        placeholder="Nomor Kamar Anda"
                        density="compact"
                        readonly
                        disabled
                      >
                        <template #append-inner>
                          <VIcon icon="tabler-info-circle" size="small">
                            <VTooltip
                              location="top"
                              transition="scale-transition"
                              activator="parent"
                            >
                              <span>Informasi Kamar tidak dapat diubah melalui halaman ini.</span>
                            </VTooltip>
                          </VIcon>
                        </template>
                      </AppTextField>
                    </VCol>
                  </VRow>
                  
                  <VCardActions class="mt-2 pa-0">
                    <VBtn
                      block
                      color="primary"
                      type="submit"
                      :loading="profileLoading"
                      :disabled="profileLoading"
                      prepend-icon="tabler-device-floppy"
                    >
                      Simpan Nama
                    </VBtn>
                  </VCardActions>
                </VForm>
              </VCardText>
            </VCard>
          </VCol>

          <VCol cols="12">
            <VCard>
              <VCardTitle class="text-h6 text-sm-h5">Keamanan Akun</VCardTitle>
              <VCardText>
                <VAlert
                  v-if="securityAlert"
                  :type="securityAlert.type"
                  variant="tonal"
                  density="compact"
                  closable
                  class="mb-4"
                  @update:model-value="securityAlert = null"
                >
                  {{ securityAlert.message }}
                </VAlert>
                <p class="mb-2 text-body-2">
                  Password hotspot Anda adalah 6 digit angka. Jika lupa atau ingin menggantinya,
                  Anda dapat meresetnya. Password baru akan dikirimkan melalui WhatsApp.
                </p>
                <VBtn
                  color="warning"
                  variant="tonal"
                  @click="resetHotspotPassword"
                  :loading="securityLoading"
                  :disabled="securityLoading"
                  prepend-icon="tabler-key"
                >
                  Reset Password Hotspot
                  <VTooltip
                    location="top"
                    transition="scale-transition"
                    activator="parent"
                  >
                    <span>Akan membuat password hotspot baru (6 digit angka) dan dikirim via WhatsApp.</span>
                  </VTooltip>
                </VBtn>
              </VCardText>
            </VCard>
          </VCol>
        </VRow>
      </VCol>

      <VCol cols="12" md="5" lg="4" class="pl-md-3 mb-4 mb-md-0">
        <VRow>
          <VCol cols="12">
            <VCard class="mb-4">
              <VCardTitle class="text-h6 text-sm-h5">Ringkasan Pengeluaran</VCardTitle>
              <VCardSubtitle class="text-caption text-sm-body-2">Belanja paket minggu ini</VCardSubtitle>
              
              <VCardText>
                <VAlert
                  v-if="spendingAlert"
                  :type="spendingAlert.type"
                  variant="tonal"
                  density="compact"
                  closable
                  class="mb-4"
                  @update:model-value="spendingAlert = null"
                >
                  {{ spendingAlert.message }}
                </VAlert>
                <div v-if="spendingChartLoading" class="text-center py-4">
                  <VProgressCircular indeterminate color="primary" />
                  <p class="text-caption mt-2">Memuat data pengeluaran...</p>
                </div>
                <template v-else>
                  <div class="d-flex justify-space-between align-center mb-3">
                    <h5 class="text-h5">Minggu Ini:</h5>
                    <h5 class="text-h5 font-weight-bold text-success">{{ totalSpendingThisPeriod }}</h5>
                  </div>
                  <div class="chart-container" :style="{ height: display.smAndDown ? '200px' : '250px' }">
                    <UserSpendingChart
                      v-if="spendingChartData[0] && spendingChartData[0].data.length > 0 && spendingChartCategories.length > 0"
                      :series-data="spendingChartData"
                      :categories="spendingChartCategories"
                      title=""
                    />
                  </div>
                </template>
              </VCardText>
            </VCard>
          </VCol>

          <VCol cols="12">
            <VCard class="mb-4">
              <VCardTitle class="text-h6 text-sm-h5">Informasi Akun</VCardTitle>
              <VDivider />
              <VCardText v-if="profileLoading && !userProfile.id" class="text-center py-4">
                <VProgressCircular indeterminate color="primary" />
              </VCardText>
              <VList v-else lines="two" density="compact">
                <VListItem title="Status Akun">
                  <template #prepend>
                    <VIcon icon="tabler-id-badge-2" class="me-3" />
                      <VTooltip location="start" transition="scale-transition" activator="parent">
                        <span>Status persetujuan dan keaktifan akun Anda.</span>
                    </VTooltip>
                  </template>
                  <template #append>
                    <VChip
                      v-if="userProfile.approval_status"
                      :color="userProfile.approval_status === 'APPROVED' && userProfile.is_active ? 'success' : userProfile.approval_status === 'PENDING_APPROVAL' ? 'warning' : 'error'"
                      size="small" label
                    >
                      {{ userProfile.approval_status === 'APPROVED' && userProfile.is_active ? 'Aktif' :
                          userProfile.approval_status === 'PENDING_APPROVAL' ? 'Menunggu Persetujuan' :
                          userProfile.approval_status === 'REJECTED' ? 'Ditolak' :
                          !userProfile.is_active && userProfile.approval_status === 'APPROVED' ? 'Tidak Aktif (Hub. Admin)' : 'Tidak Diketahui' }}
                    </VChip>
                    <VChip v-else size="small" label>N/A</VChip>
                  </template>
                </VListItem>
                <VListItem title="Peran">
                  <template #prepend>
                    <VIcon icon="tabler-shield-check" class="me-3" />
                    <VTooltip location="start" transition="scale-transition" activator="parent">
                        <span>Peran Anda dalam sistem.</span>
                    </VTooltip>
                  </template>
                  <template #append>
                    <VChip size="small" label color="info">{{ userProfile.role || 'N/A' }}</VChip>
                  </template>
                </VListItem>
                <VListItem title="Tanggal Terdaftar">
                  <template #prepend>
                    <VIcon icon="tabler-calendar-plus" class="me-3" />
                  </template>
                  <template #append>
                    <span class="text-body-2">{{ formatDate(userProfile.created_at) }}</span>
                  </template>
                </VListItem>
                <VListItem title="Terakhir Login Portal">
                  <template #prepend>
                    <VIcon icon="tabler-login" class="me-3" />
                  </template>
                  <template #append>
                    <span class="text-body-2">{{ formatDate(userProfile.last_login_at) }}</span>
                  </template>
                </VListItem>
                <VListItem title="Perangkat Registrasi">
                  <template #prepend>
                    <VIcon icon="tabler-device-desktop-analytics" class="me-3" />
                    <VTooltip location="start" transition="scale-transition" activator="parent">
                        <span>Perangkat yang digunakan saat pertama kali mendaftar.</span>
                    </VTooltip>
                  </template>
                  <template #append>
                    <span class="text-body-2">
                        {{ userProfile.device_brand || 'N/A' }} {{ userProfile.device_model || '' }}
                    </span>
                  </template>
                </VListItem>
              </VList>
            </VCard>
          </VCol>

          <VCol cols="12">
            <VCard>
              <VCardTitle class="text-h6 text-sm-h5">Riwayat Akses</VCardTitle>
              <VCardSubtitle class="text-caption text-sm-body-2">Aktivitas login terakhir</VCardSubtitle>
              
              <VCardText class="pa-0">
                <VAlert
                  v-if="loginHistoryAlert"
                  :type="loginHistoryAlert.type"
                  variant="tonal"
                  density="compact"
                  closable
                  class="mb-4 mx-4"
                  @update:model-value="loginHistoryAlert = null"
                >
                  {{ loginHistoryAlert.message }}
                </VAlert>
                <div v-if="loginHistoryLoading" class="text-center pa-4">
                  <VProgressCircular indeterminate color="primary" />
                  <p class="text-caption mt-2">Memuat riwayat akses...</p>
                </div>
                <VList v-else-if="loginHistory.length > 0" nav :lines="false" density="compact">
                  <VListItem
                    v-for="(item, index) in loginHistory"
                    :key="index"
                    :value="item.date + item.ip_address"
                  >
                    <template #prepend>
                      <VIcon :icon="item.icon" size="22"/>
                    </template>
                    
                    <VListItemTitle class="font-weight-medium text-subtitle-2">
                      {{ item.date }}
                    </VListItemTitle>
                    
                    <VListItemSubtitle class="text-caption">
                      IP: {{ item.ip_address }} | {{ item.device }} ({{ item.os }})
                    </VListItemSubtitle>
                  </VListItem>
                </VList>
              </VCardText>
            </VCard>
          </VCol>
        </VRow>
      </VCol>
    </VRow>
  </VContainer>
</template>

<style lang="scss" scoped>
.v-card {
  border-radius: 12px;
  overflow: hidden;
  box-shadow: 0 4px 6px rgba(0, 0, 0, 0.05);
  
  &-title {
    padding: 16px 16px 8px;
    
    @media (min-width: 600px) {
      padding: 20px 20px 10px;
    }
  }
  
  &-subtitle {
    padding: 0 16px 12px;
    
    @media (min-width: 600px) {
      padding: 0 20px 16px;
    }
  }
  
  &-text {
    padding: 8px 16px 16px;
    
    @media (min-width: 600px) {
      padding: 12px 20px 20px;
    }
  }
}

.chart-container {
  position: relative;
  width: 100%;
  margin-top: 12px;
}

.v-list-item {
  min-height: 56px;
  padding: 8px 16px; /* Menyesuaikan padding agar mirip contoh list */
  
  &__title {
    font-size: 0.875rem;
    line-height: 1.3;
  }
  
  &__subtitle {
    opacity: 0.8;
    font-size: 0.75rem;
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
  }

  // Menyesuaikan posisi ikon prepend
  .v-list-item__prepend {
    margin-inline-end: 16px !important; // Memastikan jarak setelah ikon
    .v-icon {
      margin-inline-end: 0 !important; // Menghilangkan margin bawaan ikon
    }
  }
}

// Responsive text adjustments
.text-h6 {
  font-size: 1.1rem !important;
  
  @media (min-width: 960px) {
    font-size: 1.25rem !important;
  }
}

.text-caption {
  font-size: 0.7rem;
  
  @media (min-width: 600px) {
    font-size: 0.8rem;
  }
}

// Mobile specific
@media (max-width: 599px) {
  .v-container {
    padding-left: 8px;
    padding-right: 8px;
  }
  
  .v-row {
    margin-left: -4px;
    margin-right: -4px;
  }
  
  .v-col {
    padding-left: 4px;
    padding-right: 4px;
  }
  
  .v-btn {
    font-size: 0.85rem;
    padding: 0 12px;
    height: 36px;
  }
}

.v-list-item-subtitle {
  white-space: normal;
  line-height: 1.4;
}

:deep(.v-field__append-inner) {
  align-items: center;
  padding-inline-start: 8px;
}
</style>