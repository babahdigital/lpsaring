<script lang="ts" setup>
import { useHead, useNuxtApp } from 'nuxt/app'
import { onMounted, ref, watch } from 'vue'

import { useSnackbar } from '@/composables/useSnackbar'
import { useAuthStore } from '@/store/auth'

// --- Tipe Data ---
interface AdminRecipient {
  id: string
  full_name: string
  phone_number: string
  is_subscribed: boolean
}

interface NotificationTypeItem {
  title: string
  value: string
  subtitle: string
  icon: string
}

type NotificationTypeLocal = 'NEW_USER_REGISTRATION' | 'NEW_PACKAGE_PURCHASE'

// --- Inisialisasi & State ---
useHead({ title: 'Pengaturan Notifikasi' })

const { $api } = useNuxtApp()
const authStore = useAuthStore()
const snackbar = useSnackbar() // Menggunakan composable snackbar terpusat

const recipients = ref<AdminRecipient[]>([])
const loading = ref(true)
const saveLoading = ref(false)
const error = ref<string | null>(null)

// --- State untuk Seleksi Tipe Notifikasi ---
const selectedNotificationType = ref<NotificationTypeLocal>('NEW_USER_REGISTRATION')

const notificationTypes: NotificationTypeItem[] = [
  {
    title: 'Pendaftaran Pengguna Baru',
    value: 'NEW_USER_REGISTRATION' as const,
    subtitle: 'Notifikasi saat pengguna biasa baru mendaftar.',
    icon: 'tabler:user-plus',
  },
  {
    title: 'Pembelian Paket Baru',
    value: 'NEW_PACKAGE_PURCHASE' as const,
    subtitle: 'Notifikasi saat ada pengguna yang membeli paket voucher.',
    icon: 'tabler:receipt-2',
  },
]

// --- Logika Inti ---

/**
 * Mengambil daftar admin dan status langganan notifikasi mereka berdasarkan tipe yang dipilih.
 */
async function fetchRecipients() {
  loading.value = true
  error.value = null
  try {
    // Menambahkan parameter notification_type ke request
    const data = await $api<AdminRecipient[]>('/admin/notification-recipients', {
      method: 'GET',
      params: {
        notification_type: selectedNotificationType.value,
      },
    })
    recipients.value = data
  }
  catch (e: any) {
    const errorMessage = e.data?.message || e.message || 'Terjadi kesalahan tidak diketahui.'
    error.value = `Gagal memuat data: ${errorMessage}`
    snackbar.add({ type: 'error', title: 'Gagal Memuat', text: errorMessage })
  }
  finally {
    loading.value = false
  }
}

/**
 * Menyimpan pengaturan notifikasi yang baru ke API.
 */
async function saveSettings() {
  saveLoading.value = true
  try {
    const subscribed_admin_ids = recipients.value
      .filter(r => r.is_subscribed)
      .map(r => r.id)

    // Payload sekarang dinamis berdasarkan tipe notifikasi yang dipilih
    const payload = {
      notification_type: selectedNotificationType.value,
      subscribed_admin_ids,
    }

    await $api('/admin/notification-recipients', {
      method: 'POST',
      body: payload,
    })

    snackbar.add({ type: 'success', title: 'Berhasil', text: 'Pengaturan notifikasi berhasil disimpan.' })
  }
  catch (e: any) {
    const errorMessage = e.data?.message || e.message || 'Gagal menyimpan pengaturan.'
    snackbar.add({ type: 'error', title: 'Gagal Menyimpan', text: errorMessage })
  }
  finally {
    saveLoading.value = false
  }
}

// --- Lifecycle & Watchers ---
onMounted(() => {
  if (authStore.isSuperAdmin) {
    fetchRecipients()
  }
})

// Tonton perubahan pada `selectedNotificationType` dan muat ulang data
watch(selectedNotificationType, () => {
  fetchRecipients()
})
</script>

<template>
  <div>
    <template v-if="authStore.isSuperAdmin">
      <VCard class="mb-6">
        <VCardItem>
          <VCardTitle>Pilih Jenis Notifikasi</VCardTitle>
          <VCardSubtitle>Pilih jenis notifikasi yang ingin Anda kelola penerimanya.</VCardSubtitle>
        </VCardItem>
        <VCardText>
          <VSelect
            v-model="selectedNotificationType"
            :items="notificationTypes"
            item-title="title"
            item-value="value"
            label="Jenis Notifikasi"
            clearable
            hide-details
          >
            <template #selection="{ item }">
              <div class="d-flex align-center">
                <VIcon :icon="item.raw.icon" class="me-3" />
                <span>{{ item.raw.title }}</span>
              </div>
            </template>
            <template #item="{ props, item }">
              <VListItem v-bind="props" :prepend-icon="item.raw.icon" :title="item.raw.title" :subtitle="item.raw.subtitle" />
            </template>
          </VSelect>
        </VCardText>
      </VCard>

      <VCard>
        <VCardItem>
          <VCardTitle>Manajemen Penerima Notifikasi</VCardTitle>
          <VCardSubtitle>
            Atur admin mana saja yang akan menerima notifikasi WhatsApp untuk jenis yang dipilih.
          </VCardSubtitle>
        </VCardItem>

        <VDivider />

        <div v-if="loading">
          <VSkeletonLoader
            v-for="i in 4"
            :key="i"
            type="list-item-two-line"
            class="mx-4 my-2"
          />
        </div>

        <div v-else-if="error" class="text-center pa-8">
          <VIcon icon="tabler:alert-triangle" size="48" color="error" class="mb-2" />
          <p class="mb-4">
            {{ error }}
          </p>
          <VBtn color="primary" @click="fetchRecipients">
            Coba Lagi
          </VBtn>
        </div>

        <VCardText v-else>
          <VList lines="two">
            <template v-for="(recipient, index) in recipients" :key="recipient.id">
              <VListItem>
                <VListItemTitle class="font-weight-medium">
                  {{ recipient.full_name }}
                </VListItemTitle>
                <VListItemSubtitle>
                  {{ recipient.phone_number }}
                </VListItemSubtitle>

                <template #append>
                  <VSwitch
                    v-model="recipient.is_subscribed"
                    color="primary"
                    inset
                    hide-details
                    aria-label="Aktifkan Notifikasi"
                  />
                </template>
              </VListItem>
              <VDivider v-if="index < recipients.length - 1" />
            </template>
          </VList>
          <p v-if="recipients.length === 0" class="text-center text-medium-emphasis py-6">
            Tidak ada admin yang dapat dikonfigurasi.
          </p>
        </VCardText>

        <VDivider />

        <VCardActions class="pa-4">
          <VSpacer />
          <VBtn
            color="primary"
            variant="elevated"
            prepend-icon="tabler:device-floppy"
            :loading="saveLoading"
            :disabled="loading || error !== null"
            @click="saveSettings"
          >
            Simpan Perubahan
          </VBtn>
        </VCardActions>
      </VCard>
    </template>

    <template v-else>
      <VCard>
        <VCardText class="text-center pa-8">
          <VIcon icon="tabler:lock-access" size="64" color="error" class="mb-4" />
          <h5 class="text-h5 mb-2">
            Akses Ditolak
          </h5>
          <p class="text-medium-emphasis">
            Halaman ini hanya dapat diakses oleh Super Admin.
          </p>
        </VCardText>
      </VCard>
    </template>
  </div>
</template>
