<script lang="ts" setup>
import { ref, onMounted, computed, defineAsyncComponent } from 'vue'
import { useNuxtApp } from '#app'
import { useAuthStore } from '~/store/auth'
import type { UserMeResponseSchema, UserProfileUpdateRequestSchema, UserProfileResponseSchema, ChangePasswordRequest } from '~/types/api'
import { VForm } from 'vuetify/components/VForm'
import { useDisplay } from 'vuetify'

const UserSpendingChart = defineAsyncComponent({
  loader: () => import('~/components/charts/UserSpendingChart.vue'),
  ssr: false
})

const { $api } = useNuxtApp()
const authStore = useAuthStore()
const display = useDisplay()

const userProfile = ref<Partial<UserMeResponseSchema>>({})
const profileLoading = ref(true)
const profileError = ref<string | null>(null)
const securityLoading = ref(false)
const securityAlert = ref<{ type: 'success' | 'error' | 'info' | 'warning'; message: string } | null>(null)
const loginHistory = ref<Array<{ date: string; ip_address: string; device: string; os: string; icon: string }>>([])
const loginHistoryLoading = ref(false)
const loginHistoryAlert = ref<{ type: 'success' | 'error' | 'info' | 'warning'; message: string } | null>(null)

const editFullName = ref('')
const profileForm = ref<InstanceType<typeof VForm> | null>(null)
const profileAlert = ref<{ type: 'success' | 'error'; message: string } | null>(null)
const totalSpendingThisPeriod = ref<string>("Rp 0")
const spendingChartData = ref([{ data: [] as number[] }])
const spendingChartCategories = ref<string[]>([])
const spendingChartLoading = ref(false)
const spendingAlert = ref<{ type: 'success' | 'error' | 'info' | 'warning'; message: string } | null>(null)

const isEditingBlokKamar = ref(false)
const adminProfileForm = ref<InstanceType<typeof VForm> | null>(null)
const adminProfileLoading = ref(false)
const adminProfileAlert = ref<{ type: 'success' | 'error'; message: string } | null>(null)
const adminEditData = ref<Partial<UserProfileUpdateRequestSchema>>({
    full_name: '',
    phone_number: '',
    blok: null,
    kamar: null
})
const availableBloks = ref<string[]>([])
const availableKamars = ref<string[]>([])
const isPasswordDialogVisible = ref(false)
const passwordFormRef = ref<InstanceType<typeof VForm> | null>(null)
const passwordLoading = ref(false)
const passwordAlert = ref<{ type: 'success' | 'error'; message: string } | null>(null)
const passwordData = ref<ChangePasswordRequest>({ current_password: '', new_password: '' })
const confirmPassword = ref('')
const isPasswordVisible = ref(false)

const isUser = computed(() => userProfile.value?.role === 'USER')
const isAdminOrSuperAdmin = computed(() => userProfile.value?.role === 'ADMIN' || userProfile.value?.role === 'SUPER_ADMIN')

const fetchUserProfile = async () => {
  profileLoading.value = true
  profileError.value = null
  try {
    const data = await $api<UserMeResponseSchema>('/auth/me', { method: 'GET' })
    if (data && data.id) {
      userProfile.value = data
      authStore.setUser(data)
      if (isUser.value) {
        editFullName.value = data.full_name || ''
      } else if (isAdminOrSuperAdmin.value) {
        adminEditData.value.full_name = data.full_name || ''
        adminEditData.value.phone_number = data.phone_number || ''
        adminEditData.value.blok = data.blok || null
        adminEditData.value.kamar = data.kamar || null
      }
    } else {
      throw new Error("Data profil tidak valid dari API")
    }
  } catch (error: any) {
    profileError.value = `Gagal memuat profil: ${error.data?.error || error.data?.message || error.message || 'Kesalahan tidak diketahui'}`
    userProfile.value = {}
  } finally {
    profileLoading.value = false
  }
}

const saveProfile = async () => {
  if (!profileForm.value) return
  const { valid } = await profileForm.value.validate()
  if (!valid) return

  profileAlert.value = null;
  const payload: Partial<UserProfileUpdateRequestSchema> = { full_name: editFullName.value }
  try {
    const response = await $api<UserProfileResponseSchema>('/auth/me/profile', { method: 'PUT', body: payload })
    userProfile.value.full_name = response.full_name
    editFullName.value = response.full_name || ''
    authStore.setUser({ ...authStore.user, ...response })
    profileAlert.value = { type: 'success', message: 'Nama Lengkap berhasil diperbarui.' }
  } catch (error: any) {
    profileAlert.value = { type: 'error', message: `Gagal menyimpan profil: ${error.data?.message || 'Terjadi kesalahan'}` }
  }
}

const saveAdminProfile = async () => {
  if (!adminProfileForm.value) return;
  const { valid } = await adminProfileForm.value.validate();
  if (!valid) return;
  adminProfileLoading.value = true;
  adminProfileAlert.value = null;
  
  const payload: Partial<UserProfileUpdateRequestSchema> = {
    full_name: adminEditData.value.full_name,
    phone_number: adminEditData.value.phone_number,
  };
  if(isEditingBlokKamar.value) {
    payload.blok = adminEditData.value.blok || null;
    payload.kamar = adminEditData.value.kamar || null;
  }

  try {
    const response = await $api<UserProfileResponseSchema>('/admin/users/me', { method: 'PUT', body: payload });
    userProfile.value = { ...userProfile.value, ...response };
    authStore.setUser({ ...authStore.user, ...response });
    adminProfileAlert.value = { type: 'success', message: 'Profil berhasil diperbarui!' };
  } catch (error: any) {
    adminProfileAlert.value = { type: 'error', message: `Gagal memperbarui profil: ${error.data?.message || 'Terjadi kesalahan.'}` };
  } finally {
    adminProfileLoading.value = false;
  }
};

const fetchAlamatOptions = async () => {
  try {
    const response = await $api<any>('/admin/form-options/alamat', { method: 'GET' });
    if (response.success) {
      availableBloks.value = response.bloks || [];
      availableKamars.value = response.kamars || [];
    } else {
        throw new Error(response.message || 'Gagal memuat opsi alamat.');
    }
  } catch (error: any) {
    console.error("Gagal mengambil opsi alamat:", error);
    adminProfileAlert.value = { type: 'error', message: `Gagal memuat opsi alamat: ${error.message}` };
  }
};

const resetHotspotPassword = async () => {
  securityLoading.value = true
  securityAlert.value = null
  try {
    const response = await $api<{ success: boolean; message: string; }>('/users/me/reset-hotspot-password', { method: 'POST' })
    securityAlert.value = { type: response.success ? 'success' : 'error', message: response.message }
  } catch (error: any) {
    securityAlert.value = { type: 'error', message: `Gagal mereset password: ${error.data?.error || error.data?.message || 'Kesalahan tidak diketahui'}` }
  } finally {
    securityLoading.value = false
  }
}

const parseUserAgent = (uaString?: string | null): { device: string; os: string; icon: string } => {
    if (!uaString) return { device: 'Tidak diketahui', os: 'Tidak diketahui', icon: 'tabler-device-desktop-question' };
    let device = 'Desktop';
    let os = 'OS Tidak diketahui';
    let icon = 'tabler-device-desktop';
    if (/android/i.test(uaString)) { os = 'Android'; device = 'Mobile'; icon = 'tabler-device-mobile'; }
    else if (/iphone|ipad|ipod/i.test(uaString)) { os = 'iOS'; device = 'Mobile'; icon = 'tabler-device-mobile'; }
    else if (/windows nt/i.test(uaString)) { os = 'Windows'; icon = 'tabler-brand-windows'; }
    else if (/macintosh|mac os x/i.test(uaString)) { os = 'macOS'; icon = 'tabler-brand-apple'; }
    else if (/linux/i.test(uaString)) { os = 'Linux'; icon = 'tabler-brand-linux'; }
    return { device, os, icon };
};

const fetchLoginHistory = async () => {
  loginHistoryLoading.value = true
  loginHistoryAlert.value = null
  try {
    const response = await $api<any>('/users/me/login-history', { params: { limit: 3 }, method: 'GET' })
    if (response.success && response.history) {
      loginHistory.value = response.history.map((item: any) => ({
        date: formatDate(item.login_time),
        ip_address: item.ip_address || 'N/A',
        ...parseUserAgent(item.user_agent_string)
      }))
      if (loginHistory.value.length === 0) {
        loginHistoryAlert.value = { type: 'info', message: 'Belum ada riwayat akses.' }
      }
    } else {
      throw new Error(response.message || 'Format data riwayat tidak valid.')
    }
  } catch (error: any) {
    loginHistoryAlert.value = { type: 'error', message: `Gagal memuat riwayat: ${error.data?.message || error.message}` }
    loginHistory.value = []
  } finally {
    loginHistoryLoading.value = false
  }
}

const fetchSpendingSummary = async () => {
  spendingChartLoading.value = true
  spendingAlert.value = null
  try {
    const response = await $api<any>('/users/me/weekly-spending', { method: 'GET' })
    if (response && response.categories && response.series) {
      spendingChartCategories.value = response.categories
      spendingChartData.value = response.series
      totalSpendingThisPeriod.value = formatCurrency(response.total_this_week)
    } else {
      throw new Error(response.message || 'Data pengeluaran tidak lengkap.')
    }
  } catch (error: any) {
    spendingChartCategories.value = ['Sen', 'Sel', 'Rab', 'Kam', 'Jum', 'Sab', 'Min']
    spendingChartData.value = [{ data: [0, 0, 0, 0, 0, 0, 0] }]
    totalSpendingThisPeriod.value = formatCurrency(0)
    spendingAlert.value = { type: 'error', message: `Gagal memuat pengeluaran: ${error.data?.message || error.message}` }
  } finally {
    spendingChartLoading.value = false
  }
}

const changePassword = async () => {
  if (!passwordFormRef.value) return;
  const { valid } = await passwordFormRef.value.validate();
  if (!valid) return;

  passwordLoading.value = true;
  passwordAlert.value = null;
  try {
    const response = await $api<any>('/auth/me/change-password', { method: 'POST', body: passwordData.value });
    passwordAlert.value = { type: 'success', message: response.message || 'Password berhasil diubah!' };
    setTimeout(() => {
      isPasswordDialogVisible.value = false;
      passwordFormRef.value?.reset();
      passwordData.value = { current_password: '', new_password: '' }
      confirmPassword.value = ''
    }, 1500);
  } catch (error: any) {
    passwordAlert.value = { type: 'error', message: error.data?.message || 'Gagal mengubah password.' };
  } finally {
    passwordLoading.value = false;
  }
};

onMounted(async () => {
  await fetchUserProfile()
  if (userProfile.value.id) {
    fetchLoginHistory()
    if (isUser.value) {
      fetchSpendingSummary()
    }
    if (isAdminOrSuperAdmin.value) {
      fetchAlamatOptions();
    }
  }
})

const requiredRule = (value: any) => !!value || 'Field ini wajib diisi.'
const nameLengthRule = (value: string) => (value && value.length >= 2) || 'Nama minimal 2 karakter.'
const phoneRule = (value: string) => {
    if (!value) return 'Nomor telepon wajib diisi.';
    const phoneRegex = /^(?:\+62|0)8[1-9][0-9]{7,12}$/;
    return phoneRegex.test(value) || 'Format nomor telepon Indonesia tidak valid.';
}
const passwordLengthRule = (v: string) => (v && v.length >= 6) || 'Password minimal 6 karakter.'
const passwordMatchRule = (v: string) => v === passwordData.value.new_password || 'Password tidak cocok.'
const formatDate = (dateString?: string | Date | null) => {
  if (!dateString) return 'N/A'
  const isMobile = display.smAndDown.value
  const options: Intl.DateTimeFormatOptions = isMobile
    ? { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' }
    : { year: 'numeric', month: 'long', day: 'numeric', hour: '2-digit', minute: '2-digit' }
  try { return new Date(dateString).toLocaleString('id-ID', options) } catch (e) { return String(dateString) }
}
const displayBlok = computed(() => `Blok ${userProfile.value.blok || 'N/A'}`)
const displayKamar = computed(() => `Kamar ${userProfile.value.kamar || 'N/A'}`)
const formatCurrency = (amount: number) => new Intl.NumberFormat('id-ID', { style: 'currency', currency: 'IDR', minimumFractionDigits: 0 }).format(amount)
useHead({ title: 'Edit Profile' })
</script>

<template>
  <VContainer fluid class="pa-sm-4 pa-2">
    <div v-if="profileLoading">
      <VRow>
        <VCol cols="12" md="7" lg="8" class="pr-md-3">
          <VSheet rounded="lg" class="pa-4 mb-4">
            <VSkeletonLoader type="heading" width="40%" class="mb-6" />
            <VSkeletonLoader type="text" class="mb-3" />
            <VSkeletonLoader type="text" class="mb-3" />
            <VSkeletonLoader type="text" class="mb-5" />
            <VSkeletonLoader type="button" height="40" />
          </VSheet>
          <VSheet rounded="lg" class="pa-4">
            <VSkeletonLoader type="heading" width="50%" class="mb-5" />
            <VSkeletonLoader type="text" width="80%" class="mb-5" />
            <VSkeletonLoader type="button" width="30%" height="40" />
          </VSheet>
        </VCol>
        <VCol cols="12" md="5" lg="4" class="pl-md-3">
          <VSheet rounded="lg" class="pa-4 mb-4">
            <VSkeletonLoader type="heading" width="60%" class="mb-4" />
            <VSkeletonLoader type="image" height="150" />
          </VSheet>
          <VSheet rounded="lg" class="pa-4">
            <VSkeletonLoader type="heading" width="50%" class="mb-4" />
            <VSkeletonLoader type="text" class="mb-3" />
            <VSkeletonLoader type="text" class="mb-3" />
            <VSkeletonLoader type="text" />
          </VSheet>
        </VCol>
      </VRow>
    </div>
    
    <div v-else-if="profileError" class="text-center py-16">
      <VIcon icon="tabler-alert-triangle" size="64" color="error" />
      <p class="text-h6 mt-4">Gagal Memuat Data</p>
      <p class="text-body-1 mt-2">{{ profileError }}</p>
      <VBtn color="primary" class="mt-4" @click="fetchUserProfile">Coba Lagi</VBtn>
    </div>

    <div v-else>
      <VRow v-if="isUser" class="flex-column-reverse flex-md-row">
        <VCol cols="12" md="7" lg="8" class="pr-md-3">
          <VRow>
            <VCol cols="12">
              <VCard class="mb-4">
                <VCardTitle class="text-h6 text-sm-h5">Profil Saya</VCardTitle>
                <VCardSubtitle class="text-caption text-sm-body-2">Perbarui nama lengkap Anda</VCardSubtitle>
                <VCardText class="pt-2">
                  <VAlert v-if="profileAlert" :type="profileAlert.type" variant="tonal" density="compact" closable class="mb-4" @update:model-value="profileAlert = null">
                    {{ profileAlert.message }}
                  </VAlert>
                  <VForm ref="profileForm" @submit.prevent="saveProfile">
                    <VRow dense>
                      <VCol cols="12">
                        <AppTextField v-model="editFullName" prepend-inner-icon="tabler-user" label="Nama Lengkap" placeholder="Masukkan nama lengkap Anda" density="compact" :rules="[requiredRule, nameLengthRule]" />
                      </VCol>
                      <VCol cols="12">
                        <AppTextField :model-value="userProfile.phone_number || 'N/A'" prepend-inner-icon="tabler-device-mobile" label="Nomor WhatsApp" density="compact" readonly disabled />
                      </VCol>
                      <VCol cols="12" sm="6">
                        <AppTextField :model-value="displayBlok" prepend-inner-icon="tabler-building-cottage" label="Blok Tempat Tinggal" density="compact" readonly disabled />
                      </VCol>
                      <VCol cols="12" sm="6">
                        <AppTextField :model-value="displayKamar" prepend-inner-icon="tabler-door" label="Nomor Kamar" density="compact" readonly disabled />
                      </VCol>
                    </VRow>
                    <VCardActions class="mt-4 pa-0">
                      <VBtn block color="primary" type="submit" prepend-icon="tabler-device-floppy">Simpan Nama</VBtn>
                    </VCardActions>
                  </VForm>
                </VCardText>
              </VCard>
            </VCol>
            <VCol cols="12">
              <VCard>
                <VCardTitle class="text-h6 text-sm-h5">Keamanan Akun</VCardTitle>
                <VCardText>
                  <VAlert v-if="securityAlert" :type="securityAlert.type" variant="tonal" density="compact" closable class="mb-4" @update:model-value="securityAlert = null">
                    {{ securityAlert.message }}
                  </VAlert>
                  <p class="mb-2 text-body-2">Password hotspot adalah 6 digit angka. Jika lupa, Anda dapat meresetnya. Password baru akan dikirim melalui WhatsApp.</p>
                  <VBtn color="warning" variant="tonal" @click="resetHotspotPassword" :loading="securityLoading" :disabled="securityLoading" prepend-icon="tabler-key">
                    Reset Password Hotspot
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
                  <div v-if="spendingChartLoading" class="text-center py-4">
                    <VProgressCircular indeterminate />
                  </div>
                  <template v-else>
                    <VAlert v-if="spendingAlert" :type="spendingAlert.type" variant="tonal" density="compact" closable class="mb-4" @update:model-value="spendingAlert = null">
                      {{ spendingAlert.message }}
                    </VAlert>
                    <div class="d-flex justify-space-between align-center mb-3">
                      <h5 class="text-h5">Minggu Ini:</h5>
                      <h5 class="text-h5 font-weight-bold text-success">{{ totalSpendingThisPeriod }}</h5>
                    </div>
                    <div class="chart-container" :style="{ height: display.smAndDown ? '200px' : '250px' }">
                      <UserSpendingChart v-if="spendingChartData[0]?.data.length > 0" :series-data="spendingChartData" :categories="spendingChartCategories" />
                    </div>
                  </template>
                </VCardText>
              </VCard>
            </VCol>
            <VCol cols="12">
              <VCard class="mb-4">
                <VCardTitle class="text-h6 text-sm-h5">Informasi Akun</VCardTitle>
                <VDivider />
                <VList lines="two" density="compact">
                  <VListItem title="Status Akun">
                    <template #prepend><VIcon icon="tabler-id-badge-2" class="me-3" /></template>
                    <template #append>
                      <VChip v-if="userProfile.approval_status" :color="userProfile.approval_status === 'APPROVED' && userProfile.is_active ? 'success' : 'warning'" size="small" label>
                        {{ userProfile.approval_status === 'APPROVED' && userProfile.is_active ? 'Aktif' : 'Menunggu Persetujuan' }}
                      </VChip>
                    </template>
                  </VListItem>
                  <VListItem title="Peran">
                    <template #prepend><VIcon icon="tabler-shield-check" class="me-3" /></template>
                    <template #append><VChip size="small" label color="info">{{ userProfile.role }}</VChip></template>
                  </VListItem>
                  <VListItem title="Tanggal Terdaftar">
                    <template #prepend><VIcon icon="tabler-calendar-plus" class="me-3" /></template>
                    <template #append><span class="text-body-2">{{ formatDate(userProfile.created_at) }}</span></template>
                  </VListItem>
                </VList>
              </VCard>
            </VCol>
            <VCol cols="12">
              <VCard>
                <VCardTitle class="text-h6 text-sm-h5">Riwayat Akses</VCardTitle>
                <VCardSubtitle class="text-caption text-sm-body-2">Aktivitas login terakhir</VCardSubtitle>
                <VCardText class="pa-0">
                  <div v-if="loginHistoryLoading" class="text-center pa-4"><VProgressCircular indeterminate /></div>
                  <VAlert v-else-if="loginHistoryAlert" :type="loginHistoryAlert.type" variant="text" density="compact" class="mx-4 my-2">
                    {{ loginHistoryAlert.message }}
                  </VAlert>
                  <VList v-else-if="loginHistory.length > 0" nav :lines="false" density="compact">
                    <VListItem v-for="(item, index) in loginHistory" :key="index">
                      <template #prepend><VIcon :icon="item.icon" size="22"/></template>
                      <VListItemTitle class="font-weight-medium text-subtitle-2">{{ item.date }}</VListItemTitle>
                      <VListItemSubtitle class="text-caption">IP: {{ item.ip_address }} | {{ item.device }} ({{ item.os }})</VListItemSubtitle>
                    </VListItem>
                  </VList>
                </VCardText>
              </VCard>
            </VCol>
          </VRow>
        </VCol>
      </VRow>

      <VRow v-else-if="isAdminOrSuperAdmin" class="flex-column-reverse flex-md-row">
        <VCol cols="12" md="7" lg="8" class="pr-md-3">
          <VRow>
            <VCol cols="12">
              <VCard>
                <VCardTitle class="text-h6 text-sm-h5">Profil {{ userProfile.role }}</VCardTitle>
                <VCardSubtitle class="text-caption text-sm-body-2">Ubah informasi dan keamanan akun portal Anda</VCardSubtitle>
                <VCardText class="pt-4">
                  <VAlert v-if="adminProfileAlert" :type="adminProfileAlert.type" variant="tonal" density="compact" closable class="mb-4" @update:model-value="adminProfileAlert = null">
                    {{ adminProfileAlert.message }}
                  </VAlert>
                  <VForm ref="adminProfileForm" @submit.prevent="saveAdminProfile">
                    <VRow dense>
                        <VCol cols="12">
                            <AppTextField v-model="adminEditData.full_name" label ="Nama Lengkap" prepend-inner-icon="tabler-user" :rules="[requiredRule, nameLengthRule]" :disabled="adminProfileLoading" />
                        </VCol>
                        <VCol cols="12">
                            <AppTextField v-model="adminEditData.phone_number" label="Nomor Telepon (Username)" prepend-inner-icon="tabler-phone" :rules="[requiredRule, phoneRule]" :disabled="adminProfileLoading" />
                        </VCol>
                        <VCol cols="12" class="mt-2">
                            <VSwitch v-model="isEditingBlokKamar" label="Ubah Data Alamat (Blok & Kamar)" color="primary" inset :disabled="adminProfileLoading"/>
                        </VCol>
                        <VCol v-if="isEditingBlokKamar" cols="12" sm="6">
                            <VSelect
                                v-model="adminEditData.blok"
                                :items="availableBloks"
                                label="Blok"
                                prepend-inner-icon="tabler-building-cottage"
                                :disabled="adminProfileLoading"
                                clearable
                                placeholder="Pilih Blok"
                                density="compact"
                            />
                        </VCol>
                        <VCol v-if="isEditingBlokKamar" cols="12" sm="6">
                            <VSelect
                                v-model="adminEditData.kamar"
                                :items="availableKamars"
                                label="Kamar"
                                prepend-inner-icon="tabler-door"
                                :disabled="adminProfileLoading"
                                clearable
                                placeholder="Pilih Kamar"
                                density="compact"
                            />
                        </VCol>
                    </VRow>
                    <VCardActions class="mt-4 pa-0">
                      <VBtn type="submit" color="primary" :loading="adminProfileLoading" prepend-icon="tabler-device-floppy" class="me-2 mb-2 mb-sm-0">Simpan Perubahan</VBtn>
                      <VBtn color="secondary" @click="isPasswordDialogVisible = true" prepend-icon="tabler-key">Ubah Password</VBtn>
                    </VCardActions>
                  </VForm>
                </VCardText>
              </VCard>
            </VCol>
          </VRow>
        </VCol>
        
        <VCol cols="12" md="5" lg="4" class="pl-md-3 mb-4 mb-md-0">
          <VRow>
            <VCol cols="12">
              <VCard>
                <VCardTitle class="text-h6 text-sm-h5">Informasi & Riwayat</VCardTitle>
                <VDivider />
                <VList lines="two" density="compact">
                  <VListItem title="Status Akun">
                    <template #prepend><VIcon icon="tabler-id-badge-2" class="me-3" /></template>
                    <template #append><VChip :color="userProfile.is_active ? 'success' : 'error'" size="small" label>{{ userProfile.is_active ? 'Aktif' : 'Tidak Aktif' }}</VChip></template>
                  </VListItem>
                  <VListItem title="Peran">
                    <template #prepend><VIcon icon="tabler-shield-check" class="me-3" /></template>
                    <template #append><VChip size="small" label color="info">{{ userProfile.role }}</VChip></template>
                  </VListItem>
                  <VListItem title="Tanggal Terdaftar">
                    <template #prepend><VIcon icon="tabler-calendar-plus" class="me-3" /></template>
                    <template #append><span class="text-body-2">{{ formatDate(userProfile.created_at) }}</span></template>
                  </VListItem>
                </VList>
                <VDivider />
                <VListSubheader>RIWAYAT LOGIN TERAKHIR</VListSubheader>
                <VCardText class="pa-0">
                  <div v-if="loginHistoryLoading" class="text-center pa-4"><VProgressCircular indeterminate /></div>
                  <VAlert v-else-if="loginHistoryAlert" :type="loginHistoryAlert.type" variant="text" density="compact" class="mx-4 my-2">
                      {{ loginHistoryAlert.message }}
                  </VAlert>
                  <VList v-else-if="loginHistory.length > 0" nav :lines="false" density="compact">
                    <VListItem v-for="(item, index) in loginHistory" :key="index">
                      <template #prepend><VIcon :icon="item.icon" size="22"/></template>
                      <VListItemTitle class="font-weight-medium text-subtitle-2">{{ item.date }}</VListItemTitle>
                      <VListItemSubtitle class="text-caption">IP: {{ item.ip_address }} | {{ item.device }} ({{ item.os }})</VListItemSubtitle>
                    </VListItem>
                  </VList>
                </VCardText>
              </VCard>
            </VCol>
          </VRow>
        </VCol>
      </VRow>
    </div>

    <VDialog v-model="isPasswordDialogVisible" max-width="500px" persistent content-class="dialog-z-index">
      <VCard>
        <VCardTitle class="d-flex align-center">
          Ubah Password Portal
          <VSpacer />
          <VBtn icon="tabler-x" variant="text" @click="isPasswordDialogVisible = false" />
        </VCardTitle>
        <VDivider />
        <VCardText class="pt-4">
          <VAlert v-if="passwordAlert" :type="passwordAlert.type" variant="tonal" density="compact" closable class="mb-4" @update:model-value="passwordAlert = null">{{ passwordAlert.message }}</VAlert>
          <VForm ref="passwordFormRef" @submit.prevent="changePassword">
            <VRow dense>
              <VCol cols="12">
                <AppTextField v-model="passwordData.current_password" label="Password Saat Ini" :type="isPasswordVisible ? 'text' : 'password'" :append-inner-icon="isPasswordVisible ? 'tabler-eye-off' : 'tabler-eye'" @click:append-inner="isPasswordVisible = !isPasswordVisible" :rules="[requiredRule]" density="compact" autocomplete="current-password" />
              </VCol>
              <VCol cols="12">
                <AppTextField v-model="passwordData.new_password" label="Password Baru" :type="isPasswordVisible ? 'text' : 'password'" :rules="[requiredRule, passwordLengthRule]" density="compact" autocomplete="new-password" />
              </VCol>
              <VCol cols="12">
                <AppTextField v-model="confirmPassword" label="Konfirmasi Password Baru" :type="isPasswordVisible ? 'text' : 'password'" :rules="[requiredRule, passwordMatchRule]" density="compact" autocomplete="new-password"/>
              </VCol>
            </VRow>
          </VForm>
        </VCardText>
        <VCardActions>
          <VSpacer />
          <VBtn color="secondary" variant="text" @click="isPasswordDialogVisible = false" :disabled="passwordLoading">Batal</VBtn>
          <VBtn color="primary" variant="elevated" @click="changePassword" :loading="passwordLoading">Simpan Password</VBtn>
        </VCardActions>
      </VCard>
    </VDialog>
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
  padding: 8px 16px;
  
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

  .v-list-item__prepend {
    margin-inline-end: 16px !important;
    .v-icon {
      margin-inline-end: 0 !important;
    }
  }
}

.v-list-subheader {
  font-weight: 600;
  font-size: 0.875rem;
  padding-top: 16px;
  padding-bottom: 8px;
  padding-left: 16px;
  padding-right: 16px;
}

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
  .v-card-actions .v-btn {
    width: 100%;
    margin-bottom: 8px;
    
    &:last-child {
      margin-bottom: 0;
    }
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

:deep(.dialog-z-index) {
  z-index: 2500 !important;
}
</style>