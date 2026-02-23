<script setup lang="ts">
import type { SettingSchema } from '@/types/api/settings'
import { useCookie } from '#app'
import { computed, onMounted, ref } from 'vue'
import { useAuthStore } from '@/store/auth'
import { useSettingsStore } from '@/store/settings'
// Impor semua enum yang Anda gunakan di template atau script
import { useMaintenanceStore } from '~/store/maintenance'

definePageMeta({})

const authStore = useAuthStore()
const settingsStore = useSettingsStore()
const maintenanceStore = useMaintenanceStore()
const { $api } = useNuxtApp()
const snackbar = useSnackbar()

const tab = ref('umum')
const isLoading = ref(true)
const isSaving = ref(false)
const testTelegramChatId = ref('')
const testTelegramMessage = ref('Tes Telegram dari panel admin hotspot.')
const isTestingTelegram = ref(false)

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

const telegramEnabled = computed({
  get: () => localSettings.value.ENABLE_TELEGRAM_NOTIFICATIONS === 'True',
  set: (val: boolean) => {
    localSettings.value.ENABLE_TELEGRAM_NOTIFICATIONS = val ? 'True' : 'False'
  },
})

function parseCsvList(value: string | null | undefined): string[] {
  const raw = (value ?? '').toString().trim()
  if (raw === '')
    return []
  const parts = raw.split(',').map(p => p.trim().toLowerCase()).filter(Boolean)
  // keep order, unique
  return Array.from(new Set(parts))
}

function toCsvList(values: string[]): string {
  return values.map(v => v.trim().toLowerCase()).filter(Boolean).join(',')
}

const isCoreApiMode = computed(() => (localSettings.value.PAYMENT_PROVIDER_MODE ?? 'snap') === 'core_api')

const coreApiEnabledPaymentMethods = computed<string[]>({
  get: () => {
    const raw = localSettings.value.CORE_API_ENABLED_PAYMENT_METHODS
    const parsed = parseCsvList(raw)
    return parsed.length > 0 ? parsed : ['qris', 'gopay', 'va']
  },
  set: (val: string[]) => {
    localSettings.value.CORE_API_ENABLED_PAYMENT_METHODS = toCsvList(val)
  },
})

const isCoreApiVaEnabled = computed(() => coreApiEnabledPaymentMethods.value.includes('va'))

const coreApiEnabledVaBanks = computed<string[]>({
  get: () => {
    const raw = localSettings.value.CORE_API_ENABLED_VA_BANKS
    const parsed = parseCsvList(raw)
    return parsed.length > 0 ? parsed : ['bca', 'bni', 'bri', 'mandiri', 'permata', 'cimb']
  },
  set: (val: string[]) => {
    localSettings.value.CORE_API_ENABLED_VA_BANKS = toCsvList(val)
  },
})

const coreApiMethodCheckboxItems = [
  { label: 'QRIS', value: 'qris' },
  { label: 'GoPay', value: 'gopay' },
  { label: 'ShopeePay', value: 'shopeepay' },
  { label: 'Virtual Account (VA)', value: 'va' },
] as const

const coreApiVaBankCheckboxItems = [
  { label: 'BCA', value: 'bca' },
  { label: 'BNI', value: 'bni' },
  { label: 'BRI', value: 'bri' },
  { label: 'Mandiri', value: 'mandiri' },
  { label: 'Permata', value: 'permata' },
  { label: 'CIMB Niaga', value: 'cimb' },
] as const

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
  isLoading.value = true
  try {
    const response = await $api<SettingSchema[]>('/admin/settings')

    // Inisialisasi semua kemungkinan nilai agar tidak 'undefined'
    const initialSettings: Record<string, string> = {
      MAINTENANCE_MODE_ACTIVE: 'False',
      ENABLE_WHATSAPP_NOTIFICATIONS: 'False',
      ENABLE_WHATSAPP_LOGIN_NOTIFICATION: 'False', // PENAMBAHAN: Inisialisasi nilai default
      ENABLE_TELEGRAM_NOTIFICATIONS: 'False',
      APP_NAME: '',
      APP_BROWSER_TITLE: '',
      THEME: 'system',
      SKIN: 'bordered',
      LAYOUT: 'horizontal',
      CONTENT_WIDTH: 'boxed',
      WHATSAPP_API_KEY: '',
      TELEGRAM_BOT_USERNAME: '',
      TELEGRAM_BOT_TOKEN: '',
      TELEGRAM_ADMIN_CHAT_IDS: '',
      TELEGRAM_WEBHOOK_SECRET: '',
      MIDTRANS_SERVER_KEY: '',
      MIDTRANS_CLIENT_KEY: '',
      PAYMENT_PROVIDER_MODE: 'snap',
      CORE_API_ENABLED_PAYMENT_METHODS: 'qris,gopay,va',
      CORE_API_ENABLED_VA_BANKS: 'bca,bni,bri,mandiri,permata,cimb',
      MIKROTIK_HOST: '',
      MIKROTIK_USER: '',
      MIKROTIK_PASSWORD: '',
      MAINTENANCE_MODE_MESSAGE: '',
      // Tambahkan kunci lain jika perlu
    }

    const fetchedSettings = response.reduce((acc, setting) => {
      // Perbaikan: Memastikan nilai selalu string secara eksplisit
      acc[setting.setting_key] = setting.setting_value != null ? setting.setting_value : ''
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
      // Perbaikan: Hapus pengecekan `null` yang tidak perlu karena nilai sudah dijamin string.
      // Saring nilai yang kosong, kecuali 'MAINTENANCE_MODE_MESSAGE' jika mode maintenance tidak aktif
      if (settingsToSave[key] === '') {
        if (key === 'MAINTENANCE_MODE_MESSAGE' && settingsToSave.MAINTENANCE_MODE_ACTIVE === 'False') {
          return // Jangan hapus jika mode maintenance tidak aktif
        }
        delete settingsToSave[key]
      }
    })

    await $api('/admin/settings', {
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
    console.error('Gagal menyimpan pengaturan. Detail error:', e.data ?? e)

    let errorDetails = 'Terjadi kesalahan pada server.'

    // Perbaikan: Lakukan pengecekan `e.data` sebagai objek terlebih dahulu
    // kemudian akses propertinya dengan casting ke Record<string, unknown>
    if (typeof e.data === 'object' && e.data !== null) {
      const dataAsObject = e.data as Record<string, unknown>

      // Perbaikan: Pengecekan error dibuat lebih eksplisit untuk memenuhi aturan `strict-boolean-expressions`.
      if ('errors' in dataAsObject && Array.isArray(dataAsObject.errors)) {
        errorDetails = (dataAsObject.errors as any[]).map((err: any) => {
          if (typeof err === 'object' && err !== null && 'message' in err) {
            return String(err.message)
          }
          return String(err)
        }).join(' ')
      }
      else if ('message' in dataAsObject && typeof dataAsObject.message === 'string') {
        errorDetails = dataAsObject.message as string
      }
    }

    snackbar.add({
      type: 'error',
      title: `Gagal Menyimpan (Error ${e.statusCode ?? '422'})`,
      text: errorDetails,
    })
  }
  finally {
    isSaving.value = false
  }
}

async function handleTestTelegramSend() {
  if (isTestingTelegram.value)
    return
  isTestingTelegram.value = true
  try {
    const chatId = testTelegramChatId.value.trim()
    const message = testTelegramMessage.value.trim() || 'Tes Telegram dari panel admin hotspot.'
    if (!chatId) {
      snackbar.add({ type: 'warning', title: 'Validasi', text: 'chat_id Telegram wajib diisi.' })
      return
    }
    await $api('/admin/telegram/test-send', {
      method: 'POST',
      body: { chat_id: chatId, message },
    })
    snackbar.add({ type: 'success', title: 'Berhasil', text: `Pesan Telegram terkirim ke chat_id ${chatId}.` })
  }
  catch (e: any) {
    const msg = (e?.data?.message as string | undefined) || 'Gagal mengirim Telegram uji coba.'
    snackbar.add({ type: 'error', title: 'Gagal', text: msg })
  }
  finally {
    isTestingTelegram.value = false
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

      <VCardText>
        <VProgressLinear v-if="isLoading" indeterminate class="mb-4" />

        <VRow v-else class="settings-layout" align="start">
          <VCol cols="12" md="4" class="settings-layout__nav">
            <ClientOnly>
              <div class="text-caption text-medium-emphasis mb-2">
                Kategori Pengaturan
              </div>
              <VTabs
                v-model="tab"
                direction="vertical"
                class="v-tabs-pill settings-tabs"
                density="compact"
              >
                <VTab value="umum" class="settings-tab">
                  <VIcon start icon="mdi-cog-outline" />
                  Umum & Maintenance
                </VTab>
                <VTab value="tampilan" class="settings-tab">
                  <VIcon start icon="mdi-view-dashboard-outline" />
                  Tampilan & Layout
                </VTab>
                <VTab value="integrasi" class="settings-tab">
                  <VIcon start icon="mdi-link-variant" />
                  Integrasi
                </VTab>
              </VTabs>

              <template #fallback>
                <div class="py-2">
                  <VSkeletonLoader type="text@2" />
                </div>
              </template>
            </ClientOnly>
          </VCol>

          <VCol cols="12" md="8" class="settings-layout__content">
            <VWindow v-model="tab" class="disable-tab-transition settings-window" :touch="false">
              <VWindowItem value="umum">
                <div>
                  <div class="d-flex flex-column gap-y-4">
                <VListSubheader>Mode Maintenance</VListSubheader>
                <VListItem lines="three" class="overflow-visible">
                  <VRow no-gutters align="center">
                    <VCol cols="12" md="4" class="text-start text-md-right">
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
                    <VCol cols="12" md="8" class="overflow-visible">
                      <VTextarea v-model="localSettings.MAINTENANCE_MODE_MESSAGE" placeholder="Contoh: Aplikasi sedang dalam perbaikan..." persistent-placeholder rows="3" :disabled="!maintenanceModeActive" variant="outlined" density="comfortable" />
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
                      <VTextField v-model="localSettings.APP_NAME" label="Nama Aplikasi" persistent-placeholder placeholder="Contoh: Portal Hotspot Sobigidul" variant="outlined" density="comfortable" />
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
                      <VTextField v-model="localSettings.APP_BROWSER_TITLE" label="Judul di Browser" persistent-placeholder placeholder="Contoh: Hotspot Sobigidul" variant="outlined" density="comfortable" />
                    </VCol>
                  </VRow>
                </VListItem>
              </div>

              <VCardActions class="mt-6 px-0">
                <VSpacer />
                <VBtn :loading="isSaving" prepend-icon="mdi-content-save-outline" @click="handleSaveChanges">
                  Simpan Perubahan
                </VBtn>
              </VCardActions>
                </div>
              </VWindowItem>

              <VWindowItem value="tampilan">
                <div>
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
                <VBtn :loading="isSaving" prepend-icon="mdi-content-save-outline" @click="handleSaveChanges">
                  Simpan Perubahan
                </VBtn>
              </VCardActions>
                </div>
              </VWindowItem>

              <VWindowItem value="integrasi">
                <div>
                  <div class="d-flex flex-column gap-y-4">
                <VListSubheader>WhatsApp (Fonnte)</VListSubheader>

                <VListItem lines="three">
                  <VRow no-gutters align="center">
                    <VCol cols="12" md="4" class="text-start text-md-right">
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
                    <VCol cols="12" md="4" class="text-start text-md-right">
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
                      <VTextField v-model="localSettings.WHATSAPP_API_KEY" label="API Key WhatsApp (Fonnte)" type="password" persistent-placeholder placeholder="Masukkan API Key Fonnte Anda" :disabled="!whatsappEnabled" variant="outlined" density="comfortable" />
                    </VCol>
                  </VRow>
                </VListItem>

                <VDivider class="my-2" />

                <VListSubheader>Telegram</VListSubheader>

                <VListItem lines="three">
                  <VRow no-gutters align="center">
                    <VCol cols="12" md="4" class="text-start text-md-right">
                      <VListItemTitle class="mb-1">
                        Notifikasi Telegram
                      </VListItemTitle>
                      <VListItemSubtitle>
                        Saklar utama untuk pengiriman notifikasi via Telegram Bot.
                      </VListItemSubtitle>
                    </VCol>
                    <VCol cols="12" md="8" class="d-flex justify-start justify-md-end">
                      <VSwitch v-model="telegramEnabled" :label="telegramEnabled ? 'Aktif' : 'Tidak Aktif'" inset />
                    </VCol>
                  </VRow>
                </VListItem>

                <VListItem>
                  <VRow no-gutters align="center">
                    <VCol cols="12" md="4">
                      <VListItemTitle class="mb-1">
                        Bot Username
                      </VListItemTitle>
                      <VListItemSubtitle>Digunakan untuk deep link (opsional).</VListItemSubtitle>
                    </VCol>
                    <VCol cols="12" md="8">
                      <VTextField v-model="localSettings.TELEGRAM_BOT_USERNAME" label="Telegram Bot Username" persistent-placeholder placeholder="Contoh: lpsaring_bot" :disabled="!telegramEnabled" variant="outlined" density="comfortable" />
                    </VCol>
                  </VRow>
                </VListItem>

                <VListItem>
                  <VRow no-gutters align="center">
                    <VCol cols="12" md="4">
                      <VListItemTitle class="mb-1">
                        Bot Token
                      </VListItemTitle>
                      <VListItemSubtitle>Token dari BotFather (server-side secret).</VListItemSubtitle>
                    </VCol>
                    <VCol cols="12" md="8">
                      <VTextField v-model="localSettings.TELEGRAM_BOT_TOKEN" label="Telegram Bot Token" type="password" persistent-placeholder placeholder="123456:ABC..." :disabled="!telegramEnabled" variant="outlined" density="comfortable" />
                    </VCol>
                  </VRow>
                </VListItem>

                <VListItem>
                  <VRow no-gutters align="center">
                    <VCol cols="12" md="4">
                      <VListItemTitle class="mb-1">
                        Webhook Secret
                      </VListItemTitle>
                      <VListItemSubtitle>
                        Secret untuk memvalidasi request webhook dari Telegram.
                      </VListItemSubtitle>
                    </VCol>
                    <VCol cols="12" md="8">
                      <VTextField
                        v-model="localSettings.TELEGRAM_WEBHOOK_SECRET"
                        label="Telegram Webhook Secret"
                        type="password"
                        persistent-placeholder
                        placeholder="isi random string panjang"
                        :disabled="!telegramEnabled"
                        variant="outlined"
                        density="comfortable"
                      />
                    </VCol>
                  </VRow>
                </VListItem>

                <VListItem>
                  <VRow no-gutters align="center">
                    <VCol cols="12" md="4">
                      <VListItemTitle class="mb-1">
                        Admin Chat IDs
                      </VListItemTitle>
                      <VListItemSubtitle>
                        Daftar chat_id admin untuk fase awal (pisahkan dengan koma).
                      </VListItemSubtitle>
                    </VCol>
                    <VCol cols="12" md="8">
                      <VTextField v-model="localSettings.TELEGRAM_ADMIN_CHAT_IDS" label="Telegram Admin Chat IDs" persistent-placeholder placeholder="Contoh: 123456789,987654321" :disabled="!telegramEnabled" variant="outlined" density="comfortable" />
                    </VCol>
                  </VRow>
                </VListItem>

                <VListItem>
                  <VRow no-gutters align="center">
                    <VCol cols="12" md="4" class="text-start text-md-right">
                      <VListItemTitle class="mb-1">
                        Test Kirim Telegram
                      </VListItemTitle>
                      <VListItemSubtitle>
                        Uji koneksi bot token + chat_id (tidak menyimpan apa pun).
                      </VListItemSubtitle>
                    </VCol>
                    <VCol cols="12" md="8">
                      <VRow>
                        <VCol cols="12" sm="6" md="5">
                          <VTextField
                            v-model="testTelegramChatId"
                            label="chat_id"
                            placeholder="123456789"
                            :disabled="!telegramEnabled || isTestingTelegram"
                            variant="outlined"
                            density="comfortable"
                            hide-details
                          />
                        </VCol>
                        <VCol cols="12" sm="6" md="7">
                          <VTextField
                            v-model="testTelegramMessage"
                            label="Pesan"
                            placeholder="Tes Telegram..."
                            :disabled="!telegramEnabled || isTestingTelegram"
                            variant="outlined"
                            density="comfortable"
                            hide-details
                          />
                        </VCol>
                      </VRow>
                      <div class="d-flex justify-end mt-2">
                        <VBtn
                          color="primary"
                          variant="tonal"
                          :loading="isTestingTelegram"
                          :disabled="!telegramEnabled || isTestingTelegram"
                          prepend-icon="tabler-send"
                          @click="handleTestTelegramSend"
                        >
                          Kirim Test
                        </VBtn>
                      </div>
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
                          <VTextField v-model="localSettings.MIDTRANS_SERVER_KEY" label="Server Key Midtrans" type="password" persistent-placeholder placeholder="Masukkan Server Key" variant="outlined" density="comfortable" />
                        </VCol>
                        <VCol cols="12" sm="6">
                          <VTextField v-model="localSettings.MIDTRANS_CLIENT_KEY" label="Client Key Midtrans" type="password" persistent-placeholder placeholder="Masukkan Client Key" variant="outlined" density="comfortable" />
                        </VCol>
                      </VRow>
                    </VCol>
                  </VRow>
                </VListItem>

                <VListItem lines="three">
                  <VRow no-gutters align="center">
                    <VCol cols="12" md="4">
                      <VListItemTitle class="mb-1">
                        Mode Pembayaran
                      </VListItemTitle>
                      <VListItemSubtitle>
                        Snap memakai halaman pembayaran Midtrans. Core API menampilkan metode secara langsung (QRIS/GoPay/VA).
                      </VListItemSubtitle>
                    </VCol>
                    <VCol cols="12" md="8">
                      <AppSelect
                        v-model="localSettings.PAYMENT_PROVIDER_MODE"
                        label="Mode Pembayaran"
                        :items="[
                          { title: 'Snap (default)', value: 'snap' },
                          { title: 'Core API (tanpa Snap)', value: 'core_api' },
                        ]"
                        item-title="title"
                        item-value="value"
                        density="comfortable"
                      />
                    </VCol>
                  </VRow>
                </VListItem>

                <VListItem v-if="isCoreApiMode">
                  <VRow no-gutters align="start">
                    <VCol cols="12" md="4" class="pb-2 pb-md-0">
                      <VListItemTitle class="mb-1">
                        Metode Pembayaran
                      </VListItemTitle>
                      <VListItemSubtitle class="core-api-subtitle">
                        Pilih metode yang ditampilkan saat Core API aktif.
                      </VListItemSubtitle>
                    </VCol>
                    <VCol cols="12" md="8">
                      <div class="core-api-grid">
                        <div v-for="item in coreApiMethodCheckboxItems" :key="item.value" class="core-api-grid__item">
                          <VCheckbox
                            v-model="coreApiEnabledPaymentMethods"
                            :value="item.value"
                            :label="item.label"
                            class="core-api-checkbox"
                            density="comfortable"
                            hide-details
                          />
                        </div>
                      </div>
                    </VCol>
                  </VRow>
                </VListItem>

                <VListItem v-if="isCoreApiMode && isCoreApiVaEnabled">
                  <VRow no-gutters align="start">
                    <VCol cols="12" md="4" class="pb-2 pb-md-0">
                      <VListItemTitle class="mb-1">
                        Bank Virtual Account
                      </VListItemTitle>
                      <VListItemSubtitle class="core-api-subtitle">
                        Pilih bank yang tersedia saat pengguna memilih pembayaran VA.
                      </VListItemSubtitle>
                    </VCol>
                    <VCol cols="12" md="8">
                      <div class="core-api-grid">
                        <div v-for="item in coreApiVaBankCheckboxItems" :key="item.value" class="core-api-grid__item">
                          <VCheckbox
                            v-model="coreApiEnabledVaBanks"
                            :value="item.value"
                            :label="item.label"
                            class="core-api-checkbox"
                            density="comfortable"
                            hide-details
                          />
                        </div>
                      </div>
                    </VCol>
                  </VRow>
                </VListItem>

                <VDivider class="my-2" />
                <VListSubheader>MikroTik</VListSubheader>
                <VListItem>
                  <VRow no-gutters align="center">
                    <VCol cols="12" md="4" class="text-start text-md-right">
                      <VListItemTitle class="mb-1">
                        Kredensial MikroTik
                      </VListItemTitle>
                      <VListItemSubtitle>Detail koneksi API untuk router MikroTik Anda.</VListItemSubtitle>
                    </VCol>
                    <VCol cols="12" md="8">
                      <VRow>
                        <VCol cols="12" sm="6" md="4">
                          <VTextField v-model="localSettings.MIKROTIK_HOST" label="Host MikroTik" persistent-placeholder placeholder="Alamat IP/domain" variant="outlined" density="comfortable" />
                        </VCol>
                        <VCol cols="12" sm="6" md="4">
                          <VTextField v-model="localSettings.MIKROTIK_USER" label="User MikroTik" persistent-placeholder placeholder="Username API" variant="outlined" density="comfortable" />
                        </VCol>
                        <VCol cols="12" sm="12" md="4">
                          <VTextField v-model="localSettings.MIKROTIK_PASSWORD" label="Password MikroTik" type="password" persistent-placeholder placeholder="Password API" variant="outlined" density="comfortable" />
                        </VCol>
                      </VRow>
                    </VCol>
                  </VRow>
                </VListItem>
              </div>
              <VCardActions class="mt-6 px-0">
                <VSpacer />
                <VBtn :loading="isSaving" prepend-icon="mdi-content-save-outline" @click="handleSaveChanges">
                  Simpan Perubahan
                </VBtn>
              </VCardActions>
                </div>
              </VWindowItem>
            </VWindow>
          </VCol>
        </VRow>
      </VCardText>
    </VCard>
  </div>
</template>

<style scoped>
.gap-y-4 {
  gap: 1rem 0;
}

.settings-layout__nav {
  padding-top: 0;
}

.settings-layout__content {
  padding-top: 0;
}

.settings-window {
  min-height: 0;
}

.settings-tabs {
  width: 100%;
}

.settings-tabs :deep(.v-tab) {
  max-width: none;
}

.settings-tab {
  justify-content: flex-start;
  white-space: normal;
  text-align: start;
}

.core-api-subtitle {
  white-space: normal;
}

.core-api-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 0.5rem 1rem;
}

@media (min-width: 600px) {
  .core-api-grid {
    grid-template-columns: 1fr 1fr;
  }
}

.core-api-grid__item {
  min-height: 44px;
  display: flex;
  align-items: flex-start;
}

.core-api-checkbox :deep(.v-label) {
  white-space: normal;
}

.core-api-checkbox :deep(.v-selection-control__wrapper) {
  align-self: flex-start;
}
</style>
