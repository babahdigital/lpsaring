<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import type { SettingSchema } from '@/types/api/settings'

import { useMaintenanceStore } from '~/store/maintenance'
import { useSettingsStore } from '~/store/settings'
import { Layout as AppLayout, ContentWidth, NavbarType, Skins, Theme } from '~/types/enums'

definePageMeta({
  requiredRole: ['SUPER_ADMIN'],
})

const settingsStore = useSettingsStore()
const maintenanceStore = useMaintenanceStore()
const { $api } = useNuxtApp()
const snackbar = useSnackbar()

const tab = ref('umum')
const isLoading = ref(true)
const isSaving = ref(false)
// Field-level validation errors (key -> message)
const fieldErrors = ref<Record<string, string>>({})
// Simpan key error pertama untuk highlight
const firstErrorKey = ref<string | null>(null)

// Helper untuk dapatkan error messages by key (dipakai untuk binding dinamis)
function fieldErr(key: string) {
  return fieldErrors.value[key] ? [fieldErrors.value[key]] : []
}

// [PERBAIKAN] `localSettings` sekarang adalah salinan dari `settingsStore.settings`
const localSettings = ref<Record<string, any>>({})

const maintenanceModeActive = computed({
  get: () => localSettings.value.MAINTENANCE_MODE_ACTIVE === 'True',
  set: (val: boolean) => { localSettings.value.MAINTENANCE_MODE_ACTIVE = val ? 'True' : 'False' },
})

const whatsappEnabled = computed({
  get: () => localSettings.value.ENABLE_WHATSAPP_NOTIFICATIONS === 'True',
  set: (val: boolean) => {
    localSettings.value.ENABLE_WHATSAPP_NOTIFICATIONS = val ? 'True' : 'False'
  },
})

onMounted(async () => {
  isLoading.value = true
  try {
    const raw = await $api<any>('/admin/settings')
    let arr: SettingSchema[] = []
    if (Array.isArray(raw)) {
      arr = raw
    }
    else if (raw && Array.isArray(raw.data)) {
      // Beberapa endpoint mungkin wrap data di dalam { data: [...] }
      arr = raw.data
    }
    else if (raw && raw.results && Array.isArray(raw.results)) {
      arr = raw.results
    }
    else if (raw && !Array.isArray(raw) && typeof raw === 'object') {
      // Cek apakah object numerik-key (0,1,2,...) yang sebenarnya array yang diserialisasi berbeda
      const keys = Object.keys(raw).filter(k => k !== 'success' && k !== 'message')
      const numericKeys = keys.filter(k => /^\d+$/.test(k))
      if (numericKeys.length && numericKeys.length === keys.length) {
        // Rekonstruksi ke array
        const maxIndex = Math.max(...numericKeys.map(k => Number(k)))
        const tmp: any[] = []
        for (let i = 0; i <= maxIndex; i++) {
          if (raw[i])
            tmp.push(raw[i])
        }
        arr = tmp as SettingSchema[]
        console.info('[SETTINGS] Reconstructed array from numeric-key object. Length=', arr.length)
      }
      else {
        console.warn('[SETTINGS] Unexpected response shape (no numeric array pattern). Fallback only. Raw=', raw)
        snackbar.add({ type: 'warning', title: 'Format Tidak Dikenal', text: 'Format respons pengaturan tidak standar.' })
      }
    }
    else {
      console.warn('[SETTINGS] Response kosong / tidak dikenali:', raw)
    }

    const fetchedSettings = arr.reduce((acc, setting) => {
      if (setting && typeof setting.setting_key === 'string')
        acc[setting.setting_key] = setting.setting_value ?? ''
      return acc
    }, {} as Record<string, string>)

    localSettings.value = { ...settingsStore.settings, ...fetchedSettings }
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
  fieldErrors.value = {}
  try {
    // Kirim hanya diff: key yang berubah dari state store saat ini
    const original = settingsStore.settings || {}
    const diff: Record<string, any> = {}
    Object.keys(localSettings.value).forEach((k) => {
      if (localSettings.value[k] !== original[k])
        diff[k] = localSettings.value[k]
    })
    if (Object.keys(diff).length === 0) {
      snackbar.add({ type: 'info', title: 'Tidak Ada Perubahan', text: 'Tidak ada pengaturan yang berubah.' })
      isSaving.value = false
      return
    }
    await $api('/admin/settings', {
      method: 'PUT',
      body: { settings: diff },
    })

    // Update state global setelah berhasil menyimpan
    settingsStore.setSettings(localSettings.value)
    maintenanceStore.setMaintenanceStatus(
      localSettings.value.MAINTENANCE_MODE_ACTIVE === 'True',
      localSettings.value.MAINTENANCE_MODE_MESSAGE ?? '',
    )

    snackbar.add({ type: 'success', title: 'Berhasil', text: 'Pengaturan berhasil diperbarui.' })
  }
  catch (e: any) {
    console.error('Gagal menyimpan pengaturan. Detail error:', e.data ?? e)
    if (e?.status === 422 && (e.validationErrors || e.data?.data?.errors || e.data?.errors)) {
      // Format baru: data.errors = [{field, message}, ...]
      const raw = e.validationErrors || e.data?.data?.errors || e.data?.errors || []
      const mapped: Record<string, string> = {}
      if (Array.isArray(raw)) {
        raw.forEach((item: any) => {
          if (item && item.field)
            mapped[item.field] = item.message || 'Tidak valid'
        })
      }
      else if (raw && typeof raw === 'object') {
        // fallback format key: messages
        Object.entries(raw).forEach(([k, v]: any) => {
          if (Array.isArray(v))
            mapped[k] = v.join(', ')
          else if (typeof v === 'string')
            mapped[k] = v
        })
      }
      fieldErrors.value = mapped
      firstErrorKey.value = Object.keys(mapped)[0] || null
      snackbar.add({ type: 'error', title: 'Validasi Gagal', text: e.message || 'Periksa input yang salah.' })
      // Scroll ke field pertama
      if (firstErrorKey.value) {
        requestAnimationFrame(() => {
          const el = document.querySelector(`[name="${firstErrorKey.value}"]`) || document.querySelector(`[data-setting-key="${firstErrorKey.value}"]`)
          if (el && 'scrollIntoView' in el) {
            el.scrollIntoView({ behavior: 'smooth', block: 'center' })
            ;(el as HTMLElement).classList.add('field-error-highlight')
            setTimeout(() => (el as HTMLElement).classList.remove('field-error-highlight'), 1800)
          }
        })
      }
    }
    else {
      const errorDetails = e.data?.message || e.message || 'Terjadi kesalahan pada server.'
      snackbar.add({ type: 'error', title: 'Gagal Menyimpan', text: errorDetails })
    }
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

      <VTabs
        v-model="tab"
        class="px-4"
      >
        <VTab value="umum">
          <VIcon
            start
            icon="tabler:settings"
          />
          Umum & Maintenance
        </VTab>
        <VTab value="tampilan">
          <VIcon
            start
            icon="tabler:layout-dashboard"
          />
          Tampilan & Layout
        </VTab>
        <VTab value="integrasi">
          <VIcon
            start
            icon="tabler:link"
          />
          Integrasi
        </VTab>
      </VTabs>
      <VDivider />

      <VCardText>
        <VProgressLinear
          v-if="isLoading"
          indeterminate
          class="mb-4"
        />
        <VWindow
          v-else
          v-model="tab"
          class="disable-tab-transition"
          :style="{ 'min-height': '400px' }"
        >
          <VWindowItem value="umum">
            <VForm @submit.prevent="handleSaveChanges">
              <div class="d-flex flex-column gap-y-4">
                <VListSubheader>Mode Maintenance</VListSubheader>
                <VListItem lines="three">
                  <VRow
                    no-gutters
                    align="center"
                  >
                    <VCol
                      cols="12"
                      md="4"
                    >
                      <VListItemTitle class="mb-1">
                        Status Mode Maintenance
                      </VListItemTitle>
                      <VListItemSubtitle>
                        Aktifkan untuk menampilkan halaman maintenance di seluruh aplikasi, kecuali halaman admin.
                      </VListItemSubtitle>
                    </VCol>
                    <VCol
                      cols="12"
                      md="8"
                      class="d-flex justify-start justify-md-end"
                    >
                      <VSwitch
                        v-model="maintenanceModeActive"
                        :label="maintenanceModeActive ? 'AKTIF' : 'TIDAK AKTIF'"
                        color="error"
                        inset
                      />
                    </VCol>
                  </VRow>
                </VListItem>

                <VListItem lines="three">
                  <VRow
                    no-gutters
                    align="center"
                  >
                    <VCol
                      cols="12"
                      md="4"
                    >
                      <VListItemTitle class="mb-1">
                        Pesan Maintenance
                      </VListItemTitle>
                      <VListItemSubtitle>
                        Teks yang akan ditampilkan di halaman maintenance.
                      </VListItemSubtitle>
                    </VCol>
                    <VCol
                      cols="12"
                      md="8"
                    >
                      <VTextarea
                        v-model="localSettings.MAINTENANCE_MODE_MESSAGE"
                        label="Pesan Maintenance"
                        placeholder="Contoh: Aplikasi sedang dalam perbaikan..."
                        rows="3"
                        :disabled="!maintenanceModeActive"
                        variant="outlined"
                        density="compact"
                      />
                    </VCol>
                  </VRow>
                </VListItem>

                <VDivider class="my-2" />
                <VListSubheader>Informasi Umum</VListSubheader>

                <VListItem>
                  <VRow
                    no-gutters
                    align="center"
                  >
                    <VCol
                      cols="12"
                      md="4"
                    >
                      <VListItemTitle class="mb-1">
                        Nama Aplikasi
                      </VListItemTitle>
                      <VListItemSubtitle>
                        Nama utama aplikasi yang akan ditampilkan.
                      </VListItemSubtitle>
                    </VCol>
                    <VCol
                      cols="12"
                      md="8"
                    >
                      <VTextField
                        v-model="localSettings.APP_NAME"
                        label="Nama Aplikasi"
                        placeholder="Contoh: Portal Hotspot Sobigidul"
                        variant="outlined"
                        density="compact"
                        :error="!!fieldErrors.APP_NAME"
                        :error-messages="fieldErrors.APP_NAME ? [fieldErrors.APP_NAME] : []"
                        name="APP_NAME"
                        data-setting-key="APP_NAME"
                      />
                    </VCol>
                  </VRow>
                </VListItem>

                <VListItem>
                  <VRow
                    no-gutters
                    align="center"
                  >
                    <VCol
                      cols="12"
                      md="4"
                    >
                      <VListItemTitle class="mb-1">
                        Judul di Browser
                      </VListItemTitle>
                      <VListItemSubtitle>
                        Teks yang muncul di tab browser.
                      </VListItemSubtitle>
                    </VCol>
                    <VCol
                      cols="12"
                      md="8"
                    >
                      <VTextField
                        v-model="localSettings.APP_BROWSER_TITLE"
                        label="Judul di Browser"
                        placeholder="Contoh: Hotspot Sobigidul"
                        variant="outlined"
                        density="compact"
                        :error="!!fieldErrors.APP_BROWSER_TITLE"
                        :error-messages="fieldErrors.APP_BROWSER_TITLE ? [fieldErrors.APP_BROWSER_TITLE] : []"
                        name="APP_BROWSER_TITLE"
                        data-setting-key="APP_BROWSER_TITLE"
                      />
                    </VCol>
                  </VRow>
                </VListItem>
              </div>

              <VCardActions class="mt-6 px-0">
                <VSpacer />
                <VBtn
                  type="submit"
                  :loading="isSaving"
                  prepend-icon="tabler:device-floppy"
                  :color="Object.keys(fieldErrors).length ? 'error' : undefined"
                >
                  Simpan Perubahan
                  <VTooltip
                    v-if="Object.keys(fieldErrors).length"
                    activator="parent"
                    location="top"
                    transition="scale-transition"
                  >
                    <div style="max-width:240px">
                      <strong>{{ Object.keys(fieldErrors).length }} error:</strong>
                      <ul class="error-list">
                        <li v-for="(msg, key) in fieldErrors" :key="key">{{ key }}: {{ msg }}</li>
                      </ul>
                    </div>
                  </VTooltip>
                </VBtn>
              </VCardActions>
            </VForm>
          </VWindowItem>

          <VWindowItem value="tampilan">
            <VForm @submit.prevent="handleSaveChanges">
              <div class="d-flex flex-column gap-y-4">
                <VListItem>
                  <VRow
                    no-gutters
                    align="center"
                  >
                    <VCol
                      cols="12"
                      md="4"
                    >
                      <VListItemTitle>Tema</VListItemTitle>
                    </VCol>
                    <VCol
                      cols="12"
                      name="MAINTENANCE_MODE_MESSAGE"
                      data-setting-key="MAINTENANCE_MODE_MESSAGE"
                      md="8"
                    >
                      <VRadioGroup
                        v-model="localSettings.THEME"
                        inline
                        :error="!!fieldErrors.MAINTENANCE_MODE_MESSAGE"
                        :error-messages="fieldErrors.MAINTENANCE_MODE_MESSAGE ? [fieldErrors.MAINTENANCE_MODE_MESSAGE] : []"
                      >
                        <VRadio
                          label="Light"
                          :value="Theme.Light"
                        />
                        <VRadio
                          label="Dark"
                          :value="Theme.Dark"
                        />
                        <VRadio
                          label="Sistem"
                          :value="Theme.System"
                        />
                      </VRadioGroup>
                    </VCol>
                  </VRow>
                </VListItem>

                <VListItem>
                  <VRow
                    no-gutters
                    align="center"
                  >
                    <VCol
                      cols="12"
                      md="4"
                    >
                      <VListItemTitle>Skin</VListItemTitle>
                    </VCol>
                    <VCol
                      cols="12"
                      md="8"
                    >
                      <VRadioGroup
                        v-model="localSettings.SKIN"
                        inline
                      >
                        <VRadio
                          label="Default"
                          :value="Skins.Default"
                        />
                        <VRadio
                          label="Bordered"
                          :value="Skins.Bordered"
                        />
                      </VRadioGroup>
                    </VCol>
                  </VRow>
                </VListItem>

                <VListItem>
                  <VRow
                    no-gutters
                    align="center"
                  >
                    <VCol
                      cols="12"
                      md="4"
                    >
                      <VListItemTitle>Navbar Type</VListItemTitle>
                    </VCol>
                    <VCol
                      cols="12"
                      md="8"
                    >
                      <VRadioGroup
                        v-model="localSettings.NAVBAR_TYPE"
                        inline
                      >
                        <VRadio
                          label="Sticky"
                          :value="NavbarType.Sticky"
                        />
                        <VRadio
                          label="Static"
                          :value="NavbarType.Static"
                        />
                        <VRadio
                          label="Hidden"
                          :value="NavbarType.Hidden"
                        />
                      </VRadioGroup>
                    </VCol>
                  </VRow>
                </VListItem>

                <VListItem>
                  <VRow
                    no-gutters
                    align="center"
                  >
                    <VCol
                      cols="12"
                      md="4"
                    >
                      <VListItemTitle>Tata Letak (Layout)</VListItemTitle>
                    </VCol>
                    <VCol
                      cols="12"
                      md="8"
                    >
                      <VRadioGroup
                        v-model="localSettings.LAYOUT"
                        inline
                      >
                        <VRadio
                          label="Vertical"
                          :value="AppLayout.Vertical"
                        />
                        <VRadio
                          label="Horizontal"
                          :value="AppLayout.Horizontal"
                        />
                      </VRadioGroup>
                    </VCol>
                  </VRow>
                </VListItem>

                <VListItem>
                  <VRow
                    no-gutters
                    align="center"
                  >
                    <VCol
                      cols="12"
                      md="4"
                    >
                      <VListItemTitle>Lebar Konten</VListItemTitle>
                    </VCol>
                    <VCol
                      cols="12"
                      md="8"
                    >
                      <VRadioGroup
                        v-model="localSettings.APP_CONTENT_WIDTH"
                        inline
                      >
                        <VRadio
                          label="Compact"
                          :value="ContentWidth.Boxed"
                        />
                        <VRadio
                          label="Wide"
                          :value="ContentWidth.Fluid"
                        />
                      </VRadioGroup>
                    </VCol>
                  </VRow>
                </VListItem>
              </div>
              <VCardActions class="mt-6 px-0">
                <VSpacer />
                <VBtn
                  type="submit"
                  :loading="isSaving"
                  prepend-icon="tabler:device-floppy"
                >
                  Simpan Perubahan
                </VBtn>
              </VCardActions>
            </VForm>
          </VWindowItem>

          <VWindowItem value="integrasi">
            <VForm @submit.prevent="handleSaveChanges">
              <div class="d-flex flex-column gap-y-4">
                <VListSubheader>WhatsApp (Fonnte)</VListSubheader>
                <VAlert
                  type="info"
                  variant="tonal"
                  class="mb-2"
                  density="comfortable"
                  border="start"
                  color="primary"
                >
                  Nilai kunci sensitif (API Key, Password) disimpan terenkripsi. Kosongkan untuk tidak mengubah nilai tersimpan.
                </VAlert>
                <VListItem lines="three">
                  <VRow
                    no-gutters
                    align="center"
                  >
                    <VCol
                      cols="12"
                      md="4"
                    >
                      <VListItemTitle class="mb-1">
                        Notifikasi WhatsApp
                      </VListItemTitle>
                      <VListItemSubtitle>
                        Saklar utama untuk semua fitur notifikasi via WhatsApp.
                      </VListItemSubtitle>
                    </VCol>
                    <VCol
                      cols="12"
                      md="8"
                      class="d-flex justify-start justify-md-end"
                    >
                      <VSwitch
                        v-model="whatsappEnabled"
                        :label="whatsappEnabled ? 'Aktif' : 'Tidak Aktif'"
                        inset
                      />
                    </VCol>
                  </VRow>
                </VListItem>

                <VListItem>
                  <VRow
                    no-gutters
                    align="center"
                  >
                    <VCol
                      cols="12"
                      md="4"
                    >
                      <VListItemTitle class="mb-1">
                        API Key Fonnte
                      </VListItemTitle>
                      <VListItemSubtitle>Kunci API dari Fonnte.</VListItemSubtitle>
                    </VCol>
                    <VCol
                      cols="12"
                      md="8"
                    >
                      <VTextField
                        v-model="localSettings.WHATSAPP_API_KEY"
                        label="API Key WhatsApp (Fonnte)"
                        type="password"
                        placeholder="Masukkan API Key Fonnte Anda"
                        :disabled="!whatsappEnabled"
                        variant="outlined"
                        density="compact"
                        name="WHATSAPP_API_KEY"
                        data-setting-key="WHATSAPP_API_KEY"
                        :error="!!fieldErrors.WHATSAPP_API_KEY"
                        :error-messages="fieldErr('WHATSAPP_API_KEY')"
                      />
                    </VCol>
                  </VRow>
                </VListItem>
                <VDivider class="my-2" />
                <VListSubheader>Midtrans</VListSubheader>
                <VListItem>
                  <VRow
                    no-gutters
                    align="center"
                  >
                    <VCol
                      cols="12"
                      md="4"
                    >
                      <VListItemTitle class="mb-1">
                        Kunci Midtrans
                      </VListItemTitle>
                      <VListItemSubtitle>Kunci Server & Client untuk integrasi pembayaran.</VListItemSubtitle>
                    </VCol>
                    <VCol
                      cols="12"
                      md="8"
                    >
                      <VRow>
                        <VCol
                          cols="12"
                          sm="6"
                        >
                          <VTextField
                            v-model="localSettings.MIDTRANS_SERVER_KEY"
                            label="Server Key Midtrans"
                            type="password"
                            placeholder="Masukkan Server Key"
                            variant="outlined"
                            density="compact"
                            name="MIDTRANS_SERVER_KEY"
                            data-setting-key="MIDTRANS_SERVER_KEY"
                            :error="!!fieldErrors.MIDTRANS_SERVER_KEY"
                            :error-messages="fieldErr('MIDTRANS_SERVER_KEY')"
                          />
                        </VCol>
                        <VCol
                          cols="12"
                          sm="6"
                        >
                          <VTextField
                            v-model="localSettings.MIDTRANS_CLIENT_KEY"
                            label="Client Key Midtrans"
                            type="password"
                            placeholder="Masukkan Client Key"
                            variant="outlined"
                            density="compact"
                            name="MIDTRANS_CLIENT_KEY"
                            data-setting-key="MIDTRANS_CLIENT_KEY"
                            :error="!!fieldErrors.MIDTRANS_CLIENT_KEY"
                            :error-messages="fieldErr('MIDTRANS_CLIENT_KEY')"
                          />
                        </VCol>
                      </VRow>
                    </VCol>
                  </VRow>
                </VListItem>
                <VDivider class="my-2" />
                <VListSubheader>MikroTik</VListSubheader>
                <VListItem>
                  <VRow
                    no-gutters
                    align="center"
                  >
                    <VCol
                      cols="12"
                      md="4"
                    >
                      <VListItemTitle class="mb-1">
                        Kredensial MikroTik
                      </VListItemTitle>
                      <VListItemSubtitle>Detail koneksi API untuk router MikroTik Anda.</VListItemSubtitle>
                    </VCol>
                    <VCol
                      cols="12"
                      md="8"
                    >
                      <VRow>
                        <VCol
                          cols="12"
                          sm="4"
                        >
                          <VTextField
                            v-model="localSettings.MIKROTIK_HOST"
                            label="Host MikroTik"
                            placeholder="Alamat IP/domain"
                            variant="outlined"
                            density="compact"
                            name="MIKROTIK_HOST"
                            data-setting-key="MIKROTIK_HOST"
                            :error="!!fieldErrors.MIKROTIK_HOST"
                            :error-messages="fieldErr('MIKROTIK_HOST')"
                          />
                        </VCol>
                        <VCol
                          cols="12"
                          sm="4"
                        >
                          <VTextField
                            v-model="localSettings.MIKROTIK_USER"
                            label="User MikroTik"
                            placeholder="Username API"
                            variant="outlined"
                            density="compact"
                            name="MIKROTIK_USER"
                            data-setting-key="MIKROTIK_USER"
                            :error="!!fieldErrors.MIKROTIK_USER"
                            :error-messages="fieldErr('MIKROTIK_USER')"
                          />
                        </VCol>
                        <VCol
                          cols="12"
                          sm="4"
                        >
                          <VTextField
                            v-model="localSettings.MIKROTIK_PASSWORD"
                            label="Password MikroTik"
                            type="password"
                            placeholder="Password API"
                            variant="outlined"
                            density="compact"
                            name="MIKROTIK_PASSWORD"
                            data-setting-key="MIKROTIK_PASSWORD"
                            :error="!!fieldErrors.MIKROTIK_PASSWORD"
                            :error-messages="fieldErr('MIKROTIK_PASSWORD')"
                          />
                        </VCol>
                      </VRow>
                    </VCol>
                  </VRow>
                </VListItem>
              </div>
              <VCardActions class="mt-6 px-0">
                <VSpacer />
                <VBtn
                  type="submit"
                  :loading="isSaving"
                  prepend-icon="tabler:device-floppy"
                >
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
.field-error-highlight {
  animation: flash-border 1.2s ease-in-out 0s 1;
  box-shadow: 0 0 0 2px rgba(244, 67, 54, 0.6);
  border-radius: 6px;
}
@keyframes flash-border {
  0%, 100% { box-shadow: 0 0 0 0 rgba(244,67,54,.0); }
  20% { box-shadow: 0 0 0 3px rgba(244,67,54,.65); }
  60% { box-shadow: 0 0 0 2px rgba(244,67,54,.35); }
}
</style>
