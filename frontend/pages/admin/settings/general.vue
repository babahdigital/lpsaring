<script setup lang="ts">
import type { SettingSchema } from '@/types/api/settings'
import { useCookie } from '#app'
import { computed, onMounted, ref } from 'vue'
import { useAuthStore } from '@/store/auth'
import { useSettingsStore } from '@/store/settings'
// Impor semua enum yang Anda gunakan di template atau script
import { useMaintenanceStore } from '~/store/maintenance'

definePageMeta({
  requiredRole: ['SUPER_ADMIN'],
})

const authStore = useAuthStore()
const settingsStore = useSettingsStore()
const maintenanceStore = useMaintenanceStore()
const { $api } = useNuxtApp()
const snackbar = useSnackbar()

const tab = ref('umum')
const isLoading = ref(true)
const isSaving = ref(false)

// Objek lokal untuk menampung data form
const localSettings = ref<Record<string, string>>({})

// Computed properties untuk VSwitch
const maintenanceModeActive = computed({
  get: () => localSettings.value.MAINTENANCE_MODE_ACTIVE === 'True',
  set: (val: boolean) => { localSettings.value.MAINTENANCE_MODE_ACTIVE = val ? 'True' : 'False' },
})

const whatsappEnabled = computed({
  get: () => localSettings.value.ENABLE_WHATSAPP_NOTIFICATIONS === 'True',
  set: (val: boolean) => {
    localSettings.value.ENABLE_WHATSAPP_NOTIFICATIONS = val ? 'True' : 'False'
    // Jika notifikasi WA utama dimatikan, matikan juga notifikasi login
    if (!val) {
      localSettings.value.ENABLE_WHATSAPP_LOGIN_NOTIFICATION = 'False'
    }
  },
})

// PENAMBAHAN: Computed property untuk saklar notifikasi login
const whatsappLoginNotificationEnabled = computed({
  get: () => localSettings.value.ENABLE_WHATSAPP_LOGIN_NOTIFICATION === 'True',
  set: (val: boolean) => { localSettings.value.ENABLE_WHATSAPP_LOGIN_NOTIFICATION = val ? 'True' : 'False' },
})

/**
 * Fungsi untuk menyimpan pengaturan ke cookies browser.
 */
function syncSettingsToCookies(savedSettings: Record<string, string>) {
  useCookie('vuexy-theme').value = savedSettings.THEME || 'system'
  useCookie('vuexy-skin').value = savedSettings.SKIN || 'bordered'
  useCookie('vuexy-layout').value = savedSettings.LAYOUT || 'horizontal'
  useCookie('vuexy-content-width').value = savedSettings.CONTENT_WIDTH || 'boxed'
}

onMounted(async () => {
  if (!authStore.isSuperAdmin)
    return navigateTo('/admin/dashboard', { replace: true })

  isLoading.value = true
  try {
    const response = await $api<SettingSchema[]>('/api/admin/settings')

    // Inisialisasi semua kemungkinan nilai agar tidak 'undefined'
    const initialSettings: Record<string, string> = {
      MAINTENANCE_MODE_ACTIVE: 'False',
      ENABLE_WHATSAPP_NOTIFICATIONS: 'False',
      ENABLE_WHATSAPP_LOGIN_NOTIFICATION: 'False',
      APP_NAME: '',
      APP_BROWSER_TITLE: '',
      THEME: 'system',
      SKIN: 'bordered',
      LAYOUT: 'horizontal',
      CONTENT_WIDTH: 'boxed',
      WHATSAPP_API_KEY: '',
      MIDTRANS_SERVER_KEY: '',
      MIDTRANS_CLIENT_KEY: '',
      MIKROTIK_HOST: '',
      MIKROTIK_USER: '',
      MIKROTIK_PASSWORD: '',
      MAINTENANCE_MODE_MESSAGE: '',
    }

    const fetchedSettings = response.reduce((acc, setting) => {
      // Baris 77: Mengatasi "Unexpected nullable string value in conditional"
      // Memastikan setting_value selalu string.
      acc[setting.setting_key] = String(setting.setting_value ?? '')
      return acc
    }, {} as Record<string, string>)

    localSettings.value = { ...initialSettings, ...fetchedSettings }

    settingsStore.setSettingsFromObject(localSettings.value)
  }
  catch (e: any) { // Tetap gunakan any untuk 'e' karena bisa beragam tipe error
    // Baris 127: Mengatasi "Unexpected any value in conditional"
    // Menggunakan operator nullish coalescing (??) untuk penanganan fallback yang eksplisit.
    console.error('Gagal menyimpan pengaturan. Detail error:', e.data ?? e)

    let errorDetails = 'Terjadi kesalahan pada server.'

    // Baris 131: Mengatasi "Unexpected any value in conditional"
    // Menggunakan pengecekan eksplisit dengan `!!` atau `!== null && !== undefined`
    // Serta memastikan `e.data.errors` ada sebelum memanggil `Array.isArray`.
    if (!!e.data && !!e.data.errors && Array.isArray(e.data.errors)) {
      errorDetails = e.data.errors.map((err: any) => {
        // Baris 133: Mengatasi "Unexpected any value in conditional"
        // Memastikan `err.message` ada sebelum menggunakannya.
        if (typeof err === 'object' && !!err.message) {
          return err.message
        }
        return String(err)
      }).join(' ')
    }
    // Baris 139: Mengatasi "Unexpected any value in conditional"
    // Pengecekan eksplisit untuk `e.data` dan `e.data.message`.
    else if (!!e.data && !!e.data.message) {
      errorDetails = e.data.message
    }

    snackbar.add({
      type: 'error',
      title: `Gagal Menyimpan (Error ${String(e.statusCode ?? '422')})`, // Baris 145: Mengatasi "Unexpected any value in conditional"
      text: errorDetails,
    })
  }
  finally {
    isSaving.value = false
  }
}
useHead({ title: 'Setting Aplikasi' })
</script>

<template>
  <div>
    <VCard>
      <VCardItem class="pb-4">
        <VCardTitle>Pengaturan Aplikasi</VCardTitle>
        <VCardSubtitle>Kelola pengaturan umum, tampilan, dan integrasi aplikasi Anda.</VCardSubtitle>
      </VCardItem>

      <VTabs v-model="tab" class="px-4">
        <VTab value="umum">
          <VIcon start icon="mdi-cog-outline" />
          Umum & Maintenance
        </VTab>
        <VTab value="tampilan">
          <VIcon start icon="mdi-view-dashboard-outline" />
          Tampilan & Layout
        </VTab>
        <VTab value="integrasi">
          <VIcon start icon="mdi-link-variant" />
          Integrasi
        </VTab>
      </VTabs>
      <VDivider />

      <VCardText>
        <VProgressLinear v-if="isLoading" indeterminate class="mb-4" />
        <VWindow v-else v-model="tab" class="disable-tab-transition" :style="{ 'min-height': '400px' }">
          <VWindowItem value="umum">
            <VForm @submit.prevent="handleSaveChanges">
              <div class="d-flex flex-column gap-y-4">
                <VListSubheader>Mode Maintenance</VListSubheader>
                <VListItem lines="three">
                  <VRow no-gutters align="center">
                    <VCol cols="12" md="4">
                      <VListItemTitle class="mb-1">
                        Status Mode Maintenance
                      </VListItemTitle>
                      <VListItemSubtitle>
                        Aktifkan untuk menampilkan halaman maintenance di seluruh aplikasi, kecuali halaman admin.
                      </VListItemSubtitle>
                    </VCol>
                    <VCol cols="12" md="8" class="d-flex justify-start justify-md-end">
                      <VSwitch v-model="maintenanceModeActive" :label="maintenanceModeActive ? 'AKTIF' : 'TIDAK AKTIF'" color="error" inset />
                    </VCol>
                  </VRow>
                </VListItem>

                <VListItem lines="three">
                  <VRow no-gutters align="center">
                    <VCol cols="12" md="4">
                      <VListItemTitle class="mb-1">
                        Pesan Maintenance
                      </VListItemTitle>
                      <VListItemSubtitle>
                        Teks yang akan ditampilkan di halaman maintenance.
                      </VListItemSubtitle>
                    </VCol>
                    <VCol cols="12" md="8">
                      <VTextarea v-model="localSettings.MAINTENANCE_MODE_MESSAGE" label="Pesan Maintenance" placeholder="Contoh: Aplikasi sedang dalam perbaikan..." rows="3" :disabled="!maintenanceModeActive" variant="outlined" density="compact" />
                    </VCol>
                  </VRow>
                </VListItem>

                <VDivider class="my-2" />
                <VListSubheader>Informasi Umum</VListSubheader>

                <VListItem>
                  <VRow no-gutters align="center">
                    <VCol cols="12" md="4">
                      <VListItemTitle class="mb-1">
                        Nama Aplikasi
                      </VListItemTitle>
                      <VListItemSubtitle>
                        Nama utama aplikasi yang akan ditampilkan.
                      </VListItemSubtitle>
                    </VCol>
                    <VCol cols="12" md="8">
                      <VTextField v-model="localSettings.APP_NAME" label="Nama Aplikasi" persistent-placeholder placeholder="Contoh: Portal Hotspot Sobigidul" variant="outlined" density="compact" />
                    </VCol>
                  </VRow>
                </VListItem>

                <VListItem>
                  <VRow no-gutters align="center">
                    <VCol cols="12" md="4">
                      <VListItemTitle class="mb-1">
                        Judul di Browser
                      </VListItemTitle>
                      <VListItemSubtitle>
                        Teks yang muncul di tab browser.
                      </VListItemSubtitle>
                    </VCol>
                    <VCol cols="12" md="8">
                      <VTextField v-model="localSettings.APP_BROWSER_TITLE" label="Judul di Browser" persistent-placeholder placeholder="Contoh: Hotspot Sobigidul" variant="outlined" density="compact" />
                    </VCol>
                  </VRow>
                </VListItem>
              </div>

              <VCardActions class="mt-6 px-0">
                <VSpacer />
                <VBtn type="submit" :loading="isSaving" prepend-icon="mdi-content-save-outline">
                  Simpan Perubahan
                </VBtn>
              </VCardActions>
            </VForm>
          </VWindowItem>

          <VWindowItem value="tampilan">
            <VForm @submit.prevent="handleSaveChanges">
              <div class="d-flex flex-column gap-y-4">
                <VListItem>
                  <VRow no-gutters align="center">
                    <VCol cols="12" md="4">
                      <VListItemTitle>Tema</VListItemTitle>
                    </VCol>
                    <VCol cols="12" md="8">
                      <VRadioGroup v-model="localSettings.THEME" inline>
                        <VRadio label="Light" value="light" />
                        <VRadio label="Dark" value="dark" />
                        <VRadio label="Sistem" value="system" />
                      </VRadioGroup>
                    </VCol>
                  </VRow>
                </VListItem>

                <VListItem>
                  <VRow no-gutters align="center">
                    <VCol cols="12" md="4">
                      <VListItemTitle>Skin</VListItemTitle>
                    </VCol>
                    <VCol cols="12" md="8">
                      <VRadioGroup v-model="localSettings.SKIN" inline>
                        <VRadio label="Default" value="default" />
                        <VRadio label="Bordered" value="bordered" />
                      </VRadioGroup>
                    </VCol>
                  </VRow>
                </VListItem>

                <VListItem>
                  <VRow no-gutters align="center">
                    <VCol cols="12" md="4">
                      <VListItemTitle>Tata Letak (Layout)</VListItemTitle>
                    </VCol>
                    <VCol cols="12" md="8">
                      <VRadioGroup v-model="localSettings.LAYOUT" inline>
                        <VRadio label="Vertical" value="vertical" />
                        <VRadio label="Horizontal" value="horizontal" />
                      </VRadioGroup>
                    </VCol>
                  </VRow>
                </VListItem>

                <VListItem>
                  <VRow no-gutters align="center">
                    <VCol cols="12" md="4">
                      <VListItemTitle>Lebar Konten</VListItemTitle>
                    </VCol>
                    <VCol cols="12" md="8">
                      <VRadioGroup v-model="localSettings.CONTENT_WIDTH" inline>
                        <VRadio label="Compact" value="boxed" />
                        <VRadio label="Wide" value="fluid" />
                      </VRadioGroup>
                    </VCol>
                  </VRow>
                </VListItem>
              </div>
              <VCardActions class="mt-6 px-0">
                <VSpacer />
                <VBtn type="submit" :loading="isSaving" prepend-icon="mdi-content-save-outline">
                  Simpan Perubahan
                </VBtn>
              </VCardActions>
            </VForm>
          </VWindowItem>

          <VWindowItem value="integrasi">
            <VForm @submit.prevent="handleSaveChanges">
              <div class="d-flex flex-column gap-y-4">
                <VListSubheader>WhatsApp (Fonnte)</VListSubheader>

                <VListItem lines="three">
                  <VRow no-gutters align="center">
                    <VCol cols="12" md="4">
                      <VListItemTitle class="mb-1">
                        Notifikasi WhatsApp
                      </VListItemTitle>
                      <VListItemSubtitle>
                        Saklar utama untuk semua fitur notifikasi via WhatsApp.
                      </VListItemSubtitle>
                    </VCol>
                    <VCol cols="12" md="8" class="d-flex justify-start justify-md-end">
                      <VSwitch v-model="whatsappEnabled" :label="whatsappEnabled ? 'Aktif' : 'Tidak Aktif'" inset />
                    </VCol>
                  </VRow>
                </VListItem>

                <VListItem lines="three">
                  <VRow no-gutters align="center">
                    <VCol cols="12" md="4">
                      <VListItemTitle class="mb-1">
                        Notifikasi Login Admin
                      </VListItemTitle>
                      <VListItemSubtitle>
                        Kirim notifikasi saat admin atau super admin login.
                      </VListItemSubtitle>
                    </VCol>
                    <VCol cols="12" md="8" class="d-flex justify-start justify-md-end">
                      <VSwitch v-model="whatsappLoginNotificationEnabled" :label="whatsappLoginNotificationEnabled ? 'Aktif' : 'Tidak Aktif'" :disabled="!whatsappEnabled" inset />
                    </VCol>
                  </VRow>
                </VListItem>

                <VListItem>
                  <VRow no-gutters align="center">
                    <VCol cols="12" md="4">
                      <VListItemTitle class="mb-1">
                        API Key Fonnte
                      </VListItemTitle>
                      <VListItemSubtitle>Kunci API dari Fonnte.</VListItemSubtitle>
                    </VCol>
                    <VCol cols="12" md="8">
                      <VTextField v-model="localSettings.WHATSAPP_API_KEY" label="API Key WhatsApp (Fonnte)" type="password" persistent-placeholder="Masukkan API Key Fonnte Anda" :disabled="!whatsappEnabled" variant="outlined" density="compact" />
                    </VCol>
                  </VRow>
                </VListItem>

                <VDivider class="my-2" />
                <VListSubheader>Midtrans</VListSubheader>

                <VListItem>
                  <VRow no-gutters align="center">
                    <VCol cols="12" md="4">
                      <VListItemTitle class="mb-1">
                        Kunci Midtrans
                      </VListItemTitle>
                      <VListItemSubtitle>Kunci Server & Client untuk integrasi pembayaran.</VListItemSubtitle>
                    </VCol>
                    <VCol cols="12" md="8">
                      <VRow>
                        <VCol cols="12" sm="6">
                          <VTextField v-model="localSettings.MIDTRANS_SERVER_KEY" label="Server Key Midtrans" type="password" persistent-placeholder="Masukkan Server Key" variant="outlined" density="compact" />
                        </VCol>
                        <VCol cols="12" sm="6">
                          <VTextField v-model="localSettings.MIDTRANS_CLIENT_KEY" label="Client Key Midtrans" type="password" persistent-placeholder="Masukkan Client Key" variant="outlined" density="compact" />
                        </VCol>
                      </VRow>
                    </VCol>
                  </VRow>
                </VListItem>

                <VDivider class="my-2" />
                <VListSubheader>MikroTik</VListSubheader>
                <VListItem>
                  <VRow no-gutters align="center">
                    <VCol cols="12" md="4">
                      <VListItemTitle class="mb-1">
                        Kredensial MikroTik
                      </VListItemTitle>
                      <VListItemSubtitle>Detail koneksi API untuk router MikroTik Anda.</VListItemSubtitle>
                    </VCol>
                    <VCol cols="12" md="8">
                      <VRow>
                        <VCol cols="12" sm="4">
                          <VTextField v-model="localSettings.MIKROTIK_HOST" label="Host MikroTik" persistent-placeholder="Alamat IP/domain" variant="outlined" density="compact" />
                        </VCol>
                        <VCol cols="12" sm="4">
                          <VTextField v-model="localSettings.MIKROTIK_USER" label="User MikroTik" persistent-placeholder="Username API" variant="outlined" density="compact" />
                        </VCol>
                        <VCol cols="12" sm="4">
                          <VTextField v-model="localSettings.MIKROTIK_PASSWORD" label="Password MikroTik" type="password" persistent-placeholder="Password API" variant="outlined" density="compact" />
                        </VCol>
                      </VRow>
                    </VCol>
                  </VRow>
                </VListItem>
              </div>
              <VCardActions class="mt-6 px-0">
                <VSpacer />
                <VBtn type="submit" :loading="isSaving" prepend-icon="mdi-content-save-outline">
                  Simpan Perubahan
                </VBtn>
              </VCardActions>
            </VForm>
          </VWindowItem>
        </VWindow>
      </VCardText>
    </VCard>
  </div>
</template>

<style scoped>
.gap-y-4 {
  gap: 1rem 0;
}
</style>