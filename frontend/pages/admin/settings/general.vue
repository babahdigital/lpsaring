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
      ENABLE_WHATSAPP_LOGIN_NOTIFICATION: 'False', // PENAMBAHAN: Inisialisasi nilai default
      // Tambahkan kunci lain jika perlu
    }

    const fetchedSettings = response.reduce((acc, setting) => {
      acc[setting.setting_key] = setting.setting_value || ''
      return acc
    }, {} as Record<string, string>)

    localSettings.value = { ...initialSettings, ...fetchedSettings }

    settingsStore.setSettingsFromObject(localSettings.value)
  }
  catch (e) {
    console.error('Error fetching settings:', e)
    snackbar.add({ type: 'error', title: 'Gagal Memuat', text: 'Tidak dapat mengambil data pengaturan.' })
  }
  finally {
    isLoading.value = false
  }
})

async function handleSaveChanges() {
  isSaving.value = true
  try {
    const settingsToSave: Record<string, string> = { ...localSettings.value }

    Object.keys(settingsToSave).forEach((key) => {
      if (settingsToSave[key] === null || settingsToSave[key] === '') {
        if (key === 'MAINTENANCE_MODE_MESSAGE' && settingsToSave.MAINTENANCE_MODE_ACTIVE === 'False') {
          return
        }
        delete settingsToSave[key]
      }
    })

    await $api('/api/admin/settings', {
      method: 'PUT',
      body: { settings: settingsToSave },
    })

    syncSettingsToCookies(localSettings.value)
    settingsStore.setSettingsFromObject(localSettings.value)

    const active = localSettings.value.MAINTENANCE_MODE_ACTIVE === 'True'
    const message = localSettings.value.MAINTENANCE_MODE_MESSAGE || ''
    maintenanceStore.setMaintenanceStatus(active, message)

    snackbar.add({
      type: 'success',
      title: 'Berhasil',
      text: 'Pengaturan berhasil diperbarui.',
    })
  }
  catch (e: any) {
    console.error('Gagal menyimpan pengaturan. Detail error:', e.data || e)

    let errorDetails = 'Terjadi kesalahan pada server.'

    if (e.data && e.data.errors && Array.isArray(e.data.errors)) {
      errorDetails = e.data.errors.map((err: any) => {
        if (typeof err === 'object' && err.message) {
          return err.message
        }
        return String(err)
      }).join(' ')
    }
    else if (e.data && e.data.message) {
      errorDetails = e.data.message
    }

    snackbar.add({
      type: 'error',
      title: `Gagal Menyimpan (Error ${e.statusCode || '422'})`,
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
      <VCardItem>
        <VCardTitle>Pengaturan Aplikasi</VCardTitle>
        <VCardSubtitle>Kelola pengaturan umum, tampilan, dan integrasi aplikasi Anda.</VCardSubtitle>
      </VCardItem>

      <VTabs v-model="tab" class="v-tabs-pill">
        <VTab value="umum">
          <VIcon start icon="ri-settings-3-line" />
          Umum & Maintenance
        </VTab>
        <VTab value="tampilan">
          <VIcon start icon="ri-layout-line" />
          Tampilan & Layout
        </VTab>
        <VTab value="integrasi">
          <VIcon start icon="ri-link-m" />
          Integrasi
        </VTab>
      </VTabs>

      <VCardText>
        <VProgressLinear v-if="isLoading" indeterminate class="mb-4" />
        <VWindow v-else v-model="tab" class="disable-tab-transition">
          <VWindowItem value="umum">
            <VForm @submit.prevent="handleSaveChanges">
              <VList class="card-list" :lines="false">
                <VListItem>
                  <VListItemTitle class="font-weight-bold">
                    Mode Maintenance
                  </VListItemTitle>
                </VListItem>

                <VDivider class="my-4" />

                <VRow class="pa-4">
                  <VCol cols="12" md="5">
                    <h6 class="text-h6">
                      Status Mode Maintenance
                    </h6>
                    <p class="text-body-2 text-grey">
                      Aktifkan untuk menampilkan halaman maintenance di seluruh aplikasi, kecuali halaman admin.
                    </p>
                  </VCol>
                  <VCol cols="12" md="7">
                    <VSwitch v-model="maintenanceModeActive" :label="maintenanceModeActive ? 'Mode Maintenance AKTIF' : 'Mode Maintenance TIDAK AKTIF'" color="error" inset />
                  </VCol>
                </VRow>

                <VRow class="pa-4">
                  <VCol cols="12" md="5">
                    <h6 class="text-h6">
                      Pesan Maintenance
                    </h6>
                    <p class="text-body-2 text-grey">
                      Teks yang akan ditampilkan di halaman maintenance.
                    </p>
                  </VCol>
                  <VCol cols="12" md="7">
                    <VTextarea v-model="localSettings.MAINTENANCE_MODE_MESSAGE" label="Pesan Maintenance" placeholder="Contoh: Aplikasi sedang dalam perbaikan..." rows="3" :disabled="!maintenanceModeActive" variant="outlined" density="compact" />
                  </VCol>
                </VRow>

                <VDivider class="my-4" />

                <VListItem>
                  <VListItemTitle class="font-weight-bold">
                    Informasi Umum
                  </VListItemTitle>
                </VListItem>

                <VDivider class="my-4" />

                <VRow class="pa-4">
                  <VCol cols="12" md="5">
                    <h6 class="text-h6">
                      Nama Aplikasi
                    </h6>
                    <p class="text-body-2 text-grey">
                      Nama utama aplikasi yang akan ditampilkan di berbagai tempat.
                    </p>
                  </VCol>
                  <VCol cols="12" md="7">
                    <VTextField v-model="localSettings.APP_NAME" label="Nama Aplikasi" persistent-placeholder placeholder="Contoh: Portal Hotspot Sobigidul" variant="outlined" density="compact" />
                  </VCol>
                </VRow>

                <VRow class="pa-4">
                  <VCol cols="12" md="5">
                    <h6 class="text-h6">
                      Judul di Browser
                    </h6>
                    <p class="text-body-2 text-grey">
                      Teks yang muncul di tab browser.
                    </p>
                  </VCol>
                  <VCol cols="12" md="7">
                    <VTextField v-model="localSettings.APP_BROWSER_TITLE" label="Judul di Browser" persistent-placeholder placeholder="Contoh: Hotspot Sobigidul" variant="outlined" density="compact" />
                  </VCol>
                </VRow>
              </VList>

              <VCardActions class="mt-4 pa-4 d-flex justify-end">
                <VBtn type="submit" :loading="isSaving" prepend-icon="ri-save-line">
                  Simpan Perubahan
                </VBtn>
              </VCardActions>
            </VForm>
          </VWindowItem>

          <VWindowItem value="tampilan">
            <VForm @submit.prevent="handleSaveChanges">
              <VRow>
                <VCol cols="12" md="6">
                  <VCard variant="tonal">
                    <VCardText>
                      <h6 class="text-h6 mb-3">
                        Tema
                      </h6>
                      <VRadioGroup v-model="localSettings.THEME" inline>
                        <VRadio label="Light" value="light" /><VRadio label="Dark" value="dark" /><VRadio label="Sistem" value="system" />
                      </VRadioGroup>
                    </VCardText>
                  </VCard>
                </VCol>
                <VCol cols="12" md="6">
                  <VCard variant="tonal">
                    <VCardText>
                      <h6 class="text-h6 mb-3">
                        Skin
                      </h6>
                      <VRadioGroup v-model="localSettings.SKIN" inline>
                        <VRadio label="Default" value="default" /><VRadio label="Bordered" value="bordered" />
                      </VRadioGroup>
                    </VCardText>
                  </VCard>
                </VCol>
                <VCol cols="12" md="6">
                  <VCard variant="tonal">
                    <VCardText>
                      <h6 class="text-h6 mb-3">
                        Tata Letak (Layout)
                      </h6>
                      <VRadioGroup v-model="localSettings.LAYOUT" inline>
                        <VRadio label="Vertical" value="vertical" /><VRadio label="Horizontal" value="horizontal" />
                      </VRadioGroup>
                    </VCardText>
                  </VCard>
                </VCol>
                <VCol cols="12" md="6">
                  <VCard variant="tonal">
                    <VCardText>
                      <h6 class="text-h6 mb-3">
                        Lebar Konten
                      </h6>
                      <VRadioGroup v-model="localSettings.CONTENT_WIDTH" inline>
                        <VRadio label="Compact" value="boxed" /><VRadio label="Wide" value="fluid" />
                      </VRadioGroup>
                    </VCardText>
                  </VCard>
                </VCol>
              </VRow>
              <VCardActions class="mt-4 pa-4 d-flex justify-end">
                <VBtn type="submit" :loading="isSaving" prepend-icon="ri-save-line">
                  Simpan Perubahan
                </VBtn>
              </VCardActions>
            </VForm>
          </VWindowItem>

          <VWindowItem value="integrasi">
            <VForm @submit.prevent="handleSaveChanges">
              <VList class="card-list" :lines="false">
                <VListItem>
                  <VListItemTitle class="font-weight-bold">
                    WhatsApp (Fonnte)
                  </VListItemTitle>
                </VListItem>

                <VDivider class="my-4" />

                <VRow class="pa-4">
                  <VCol cols="12" md="5">
                    <h6 class="text-h6">
                      Notifikasi WhatsApp
                    </h6>
                    <p class="text-body-2 text-grey">
                      Saklar utama untuk semua fitur notifikasi via WhatsApp.
                    </p>
                  </VCol>
                  <VCol cols="12" md="7">
                    <VSwitch v-model="whatsappEnabled" :label="whatsappEnabled ? 'Notifikasi WhatsApp Aktif' : 'Notifikasi WhatsApp Tidak Aktif'" inset />
                  </VCol>
                </VRow>

                <VRow class="pa-4">
                  <VCol cols="12" md="5">
                    <h6 class="text-h6">
                      Notifikasi Login Admin
                    </h6>
                    <p class="text-body-2 text-grey">
                      Kirim notifikasi saat admin atau super admin login.
                    </p>
                  </VCol>
                  <VCol cols="12" md="7">
                    <VSwitch v-model="whatsappLoginNotificationEnabled" :label="whatsappLoginNotificationEnabled ? 'Notifikasi Login Aktif' : 'Notifikasi Login Tidak Aktif'" :disabled="!whatsappEnabled" inset />
                  </VCol>
                </VRow>

                <VRow class="pa-4">
                  <VCol cols="12" md="5">
                    <h6 class="text-h6">
                      API Key Fonnte
                    </h6>
                    <p class="text-body-2 text-grey">
                      Kunci API dari layanan Fonnte untuk mengirim pesan.
                    </p>
                  </VCol>
                  <VCol cols="12" md="7">
                    <VTextField v-model="localSettings.WHATSAPP_API_KEY" label="API Key WhatsApp (Fonnte)" type="password" persistent-placeholder="Masukkan API Key Fonnte Anda" :disabled="!whatsappEnabled" variant="outlined" density="compact" />
                  </VCol>
                </VRow>

                <VDivider class="my-4" />

                <VListItem>
                  <VListItemTitle class="font-weight-bold">
                    Midtrans
                  </VListItemTitle>
                </VListItem>

                <VDivider class="my-4" />

                <VRow class="pa-4">
                  <VCol cols="12" md="6">
                    <VTextField v-model="localSettings.MIDTRANS_SERVER_KEY" label="Server Key Midtrans" type="password" persistent-placeholder="Masukkan Server Key Midtrans" variant="outlined" density="compact" />
                  </VCol>
                  <VCol cols="12" md="6">
                    <VTextField v-model="localSettings.MIDTRANS_CLIENT_KEY" label="Client Key Midtrans" type="password" persistent-placeholder="Masukkan Client Key Midtrans" variant="outlined" density="compact" />
                  </VCol>
                </VRow>

                <VDivider class="my-4" />

                <VListItem>
                  <VListItemTitle class="font-weight-bold">
                    MikroTik
                  </VListItemTitle>
                </VListItem>

                <VDivider class="my-4" />

                <VRow class="pa-4">
                  <VCol cols="12" md="4">
                    <VTextField v-model="localSettings.MIKROTIK_HOST" label="Host MikroTik" persistent-placeholder="Alamat IP atau domain router" variant="outlined" density="compact" />
                  </VCol>
                  <VCol cols="12" md="4">
                    <VTextField v-model="localSettings.MIKROTIK_USER" label="User MikroTik" persistent-placeholder="Username API MikroTik" variant="outlined" density="compact" />
                  </VCol>
                  <VCol cols="12" md="4">
                    <VTextField v-model="localSettings.MIKROTIK_PASSWORD" label="Password MikroTik" type="password" persistent-placeholder="Password API MikroTik" variant="outlined" density="compact" />
                  </VCol>
                </VRow>
              </VList>

              <VCardActions class="mt-4 pa-4 d-flex justify-end">
                <VBtn type="submit" :loading="isSaving" prepend-icon="ri-save-line">
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
.card-list .v-list-item {
  padding: 0;
}
.v-tabs-pill {
  border-block-end: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}
</style>