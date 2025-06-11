<script setup lang="ts">
import { useAuthStore } from '@/store/auth';
import { useSettingsStore } from '@/store/settings';
import { useMaintenanceStore } from '~/store/maintenance' // Tambahkan impor maintenance store
import type { SettingSchema } from '@/types/api/settings';
import { computed, onMounted, ref } from 'vue';
import { useCookie } from '#app';
// Impor semua enum yang Anda gunakan di template atau script
import { Theme, Skins, Layout, ContentWidth } from '@/types/enums';

definePageMeta({
  requiredRole: ['SUPER_ADMIN'],
})

const authStore = useAuthStore();
const settingsStore = useSettingsStore();
const maintenanceStore = useMaintenanceStore(); // Inisialisasi maintenance store
const { $api } = useNuxtApp();
const snackbar = useSnackbar();

const tab = ref('umum');
const isLoading = ref(true);
const isSaving = ref(false);

// Objek lokal untuk menampung data form
const localSettings = ref<Record<string, string>>({});

// Computed properties untuk VSwitch
const maintenanceModeActive = computed({
  get: () => localSettings.value.MAINTENANCE_MODE_ACTIVE === 'True',
  set: (val: boolean) => { localSettings.value.MAINTENANCE_MODE_ACTIVE = val ? 'True' : 'False'; }
});
const whatsappEnabled = computed({
  get: () => localSettings.value.ENABLE_WHATSAPP_NOTIFICATIONS === 'True',
  set: (val: boolean) => { localSettings.value.ENABLE_WHATSAPP_NOTIFICATIONS = val ? 'True' : 'False'; }
});

/**
 * Fungsi untuk menyimpan pengaturan ke cookies browser.
 */
function syncSettingsToCookies(savedSettings: Record<string, string>) {
  useCookie('vuexy-theme').value = savedSettings.THEME || 'system';
  useCookie('vuexy-skin').value = savedSettings.SKIN || 'bordered';
  useCookie('vuexy-layout').value = savedSettings.LAYOUT || 'horizontal';
  useCookie('vuexy-content-width').value = savedSettings.CONTENT_WIDTH || 'boxed';
}

onMounted(async () => {
  if (!authStore.isSuperAdmin) return navigateTo('/admin/dashboard', { replace: true });

  isLoading.value = true;
  try {
    const response = await $api<SettingSchema[]>('/api/admin/settings');
    // Isi form lokal dengan data dari API
    localSettings.value = response.reduce((acc, setting) => {
        // Pastikan nilai default jika setting_value null
        acc[setting.setting_key] = setting.setting_value || '';
        return acc;
    }, {} as Record<string, string>);

    // Setelah localSettings terisi, panggil settingsStore.setSettingsFromObject
    // untuk mengisi data ke Pinia store saat pertama kali dimuat.
    // Ini penting agar state di Pinia store sinkron dengan data yang dimuat dari API.
    settingsStore.setSettingsFromObject(localSettings.value);

  } catch (e) {
    console.error('Error fetching settings:', e);
    snackbar.add({ type: 'error', title: 'Gagal Memuat', text: 'Tidak dapat mengambil data pengaturan.' });
  } finally {
    isLoading.value = false;
  }
});

async function handleSaveChanges() {
  isSaving.value = true;
  try {
    // Salin semua pengaturan lokal ke objek baru
    const settingsToSave: Record<string, string> = { ...localSettings.value };

    // Hapus kunci yang memiliki nilai kosong dari objek yang akan dikirim
    Object.keys(settingsToSave).forEach(key => {
      if (settingsToSave[key] === null || settingsToSave[key] === '') {
        // Pengecualian: Biarkan pesan maintenance kosong jika maintenance tidak aktif
        if (key === 'MAINTENANCE_MODE_MESSAGE' && settingsToSave['MAINTENANCE_MODE_ACTIVE'] === 'False') {
            return;
        }
        delete settingsToSave[key];
      }
    });

    // 1. Simpan ke database dengan data yang sudah bersih
    // PERBAIKAN ENDPOINT: Hapus /api di depan
    await $api('/admin/settings', {
      method: 'PUT',
      body: { settings: settingsToSave }
    });

    // 2. Simpan ke cookies (gunakan data asli, bukan yang difilter)
    syncSettingsToCookies(localSettings.value);

    // 3. Perbarui state Pinia (gunakan data asli)
    settingsStore.setSettingsFromObject(localSettings.value);

    // 4. PERBARUI MAINTENANCE STORE LANGSUNG
    const active = localSettings.value.MAINTENANCE_MODE_ACTIVE === 'True';
    const message = localSettings.value.MAINTENANCE_MODE_MESSAGE || '';
    maintenanceStore.setMaintenanceStatus(active, message);

    snackbar.add({
      type: 'success',
      title: 'Berhasil',
      text: 'Pengaturan berhasil diperbarui.'
    });

  } catch (e: any) {
    console.error('Error saving settings:', e.data || e);
    const errorDetails = e.data?.errors ? JSON.stringify(e.data.errors) : 'Terjadi kesalahan validasi.';
    snackbar.add({
      type: 'error',
      title: 'Gagal Menyimpan',
      text: errorDetails
    });
  } finally {
    isSaving.value = false;
  }
}
</script>

<template>
  <div>
    <VCard title="Pengaturan Aplikasi">
        <VTabs v-model="tab">
          <VTab value="umum">Umum & Maintenance</VTab>
          <VTab value="tampilan">Tampilan & Layout</VTab>
          <VTab value="integrasi">Integrasi</VTab>
        </VTabs>

        <VCardText>
          <VProgressLinear v-if="isLoading" indeterminate />
          <VWindow v-else v-model="tab" class="disable-tab-transition mt-4">
            <VWindowItem value="umum">
              <VForm @submit.prevent="handleSaveChanges">
                  <h6 class="text-h6 mb-4">Mode Maintenance</h6>
                  <VRow>
                    <VCol cols="12">
                      <VSwitch v-model="maintenanceModeActive" :label="maintenanceModeActive ? 'Mode Maintenance AKTIF' : 'Mode Maintenance TIDAK AKTIF'" color="error"/>
                      <p class="text-caption">Jika diaktifkan, seluruh aplikasi kecuali halaman admin akan menampilkan halaman maintenance.</p>
                    </VCol>
                    <VCol cols="12">
                      <VTextarea v-model="localSettings.MAINTENANCE_MODE_MESSAGE" label="Pesan Maintenance" placeholder="Contoh: Aplikasi sedang dalam perbaikan..." rows="3" :disabled="!maintenanceModeActive"/>
                    </VCol>
                  </VRow>
                  <VDivider class="my-6" />

                  <h6 class="text-h6 mb-4">Informasi Umum</h6>
                  <VRow>
                    <VCol cols="12" md="6"><VTextField v-model="localSettings.APP_NAME" label="Nama Aplikasi" persistent-placeholder placeholder="Contoh: Portal Hotspot Sobigidul" /></VCol>
                    <VCol cols="12" md="6"><VTextField v-model="localSettings.APP_BROWSER_TITLE" label="Judul di Browser" persistent-placeholder placeholder="Contoh: Hotspot Sobigidul" /></VCol>
                  </VRow>
                  <VCardActions class="mt-4 px-0">
                    <VSpacer />
                    <VBtn type="submit" :loading="isSaving">Simpan Perubahan</VBtn>
                  </VCardActions>
              </VForm>
            </VWindowItem>

            <VWindowItem value="tampilan">
                <VForm @submit.prevent="handleSaveChanges">
                  <VRow>
                    <VCol cols="12" md="6">
                      <p class="text-subtitle-1 mb-2">Tema</p>
                      <VRadioGroup v-model="localSettings.THEME" inline><VRadio label="Light" value="light" /><VRadio label="Dark" value="dark" /><VRadio label="Sistem" value="system" /></VRadioGroup>
                    </VCol>
                    <VCol cols="12" md="6">
                      <p class="text-subtitle-1 mb-2">Skin</p>
                      <VRadioGroup v-model="localSettings.SKIN" inline><VRadio label="Default" value="default" /><VRadio label="Bordered" value="bordered" /></VRadioGroup>
                    </VCol>
                    <VCol cols="12" md="6">
                      <p class="text-subtitle-1 mb-2">Tata Letak (Layout)</p>
                      <VRadioGroup v-model="localSettings.LAYOUT" inline><VRadio label="Vertical" value="vertical" /><VRadio label="Horizontal" value="horizontal" /></VRadioGroup>
                    </VCol>
                    <VCol cols="12" md="6">
                      <p class="text-subtitle-1 mb-2">Lebar Konten</p>
                      <VRadioGroup v-model="localSettings.CONTENT_WIDTH" inline><VRadio label="Compact (Boxed)" value="boxed" /><VRadio label="Wide (Full-width)" value="fluid" /></VRadioGroup>
                    </VCol>
                  </VRow>
                   <VCardActions class="mt-4 px-0">
                    <VSpacer />
                    <VBtn type="submit" :loading="isSaving">Simpan Perubahan</VBtn>
                   </VCardActions>
                </VForm>
            </VWindowItem>

            <VWindowItem value="integrasi">
                <VForm @submit.prevent="handleSaveChanges">
                  <h6 class="text-h6 mb-4">WhatsApp (Fonnte)</h6>
                  <VRow>
                    <VCol cols="12"><VSwitch v-model="whatsappEnabled" :label="whatsappEnabled ? 'Notifikasi WhatsApp Aktif' : 'Notifikasi WhatsApp Tidak Aktif'"/></VCol>
                    <VCol cols="12"><VTextField v-model="localSettings.WHATSAPP_API_KEY" label="API Key WhatsApp (Fonnte)" type="password" persistent-placeholder placeholder="Masukkan API Key Fonnte Anda" :disabled="!whatsappEnabled"/></VCol>
                  </VRow>
                  <VDivider class="my-6" />
                  <h6 class="text-h6 mb-4">Midtrans</h6>
                  <VRow>
                    <VCol cols="12" md="6"><VTextField v-model="localSettings.MIDTRANS_SERVER_KEY" label="Server Key Midtrans" type="password" persistent-placeholder placeholder="Masukkan Server Key Midtrans"/></VCol>
                    <VCol cols="12" md="6"><VTextField v-model="localSettings.MIDTRANS_CLIENT_KEY" label="Client Key Midtrans" type="password" persistent-placeholder placeholder="Masukkan Client Key Midtrans"/></VCol>
                  </VRow>
                  <VDivider class="my-6" />
                  <h6 class="text-h6 mb-4">MikroTik</h6>
                    <VRow>
                      <VCol cols="12" md="4"><VTextField v-model="localSettings.MIKROTIK_HOST" label="Host MikroTik" persistent-placeholder placeholder="Alamat IP atau domain router"/></VCol>
                      <VCol cols="12" md="4"><VTextField v-model="localSettings.MIKROTIK_USER" label="User MikroTik" persistent-placeholder placeholder="Username API MikroTik"/></VCol>
                      <VCol cols="12" md="4"><VTextField v-model="localSettings.MIKROTIK_PASSWORD" label="Password MikroTik" type="password" persistent-placeholder placeholder="Password API MikroTik"/></VCol>
                    </VRow>
                   <VCardActions class="mt-4 px-0">
                    <VSpacer />
                    <VBtn type="submit" :loading="isSaving">Simpan Perubahan</VBtn>
                   </VCardActions>
                </VForm>
            </VWindowItem>
          </VWindow>
        </VCardText>
    </VCard>
  </div>
</template>