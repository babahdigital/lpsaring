<script lang="ts" setup>
import type { NotificationType } from '@/types/api'
import { useHead, useNuxtApp } from '#app'
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useAuthStore } from '@/store/auth'
import { useSnackbar } from '@/composables/useSnackbar'

// --- Tipe Data ---
interface AdminRecipient {
  id: string
  full_name: string
  phone_number: string
  is_subscribed: boolean
}

interface NotificationTypeItem {
  title: string
  value: NotificationType
  subtitle: string
  icon: string
}

// --- Inisialisasi & State ---
useHead({ title: 'Pengaturan Notifikasi' })

const { $api } = useNuxtApp()
const authStore = useAuthStore()

const recipients = ref<AdminRecipient[]>([])
const loading = ref(true)
const saveLoading = ref(false)
const error = ref<string | null>(null)
const { add: addSnackbar } = useSnackbar()

const hasLoadedOnce = ref(false)
const showInitialSkeleton = computed(() => loading.value === true && hasLoadedOnce.value === false)
const showSilentRefreshing = computed(() => loading.value === true && hasLoadedOnce.value === true)

// --- State Baru untuk Seleksi Tipe Notifikasi ---
const selectedNotificationType = ref<NotificationType>('NEW_USER_REGISTRATION')

const notificationTypes: NotificationTypeItem[] = [
  {
    title: 'Pendaftaran Pengguna Baru',
    value: 'NEW_USER_REGISTRATION',
    subtitle: 'Notifikasi saat pengguna biasa atau komandan baru mendaftar.',
    icon: 'tabler-user-plus',
  },
  {
    title: 'Permintaan Komandan Baru',
    value: 'NEW_KOMANDAN_REQUEST',
    subtitle: 'Notifikasi saat komandan mengajukan permintaan kuota/unlimited.',
    icon: 'tabler-mail-fast',
  },
  {
    title: 'Hutang Kuota Melebihi Batas',
    value: 'QUOTA_DEBT_LIMIT_EXCEEDED',
    subtitle: 'Notifikasi saat user diblokir karena hutang kuota melewati batas pengaman.',
    icon: 'tabler-shield-lock',
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
    // Perbaikan baris 71: Menambahkan pengecekan eksplisit untuk e.data.message dan e.message
    const errorMessage = (e.data?.message !== null && typeof e.data?.message === 'string' && e.data.message !== '')
      ? e.data.message
      : ((typeof e.message === 'string' && e.message !== '') ? e.message : 'Terjadi kesalahan tidak diketahui.')
    error.value = `Gagal memuat data: ${errorMessage}`
    showSnackbar(error.value, 'error')
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

    showSnackbar('Pengaturan notifikasi berhasil disimpan.', 'success')
  }
  catch (e: any) {
    // Perbaikan baris 104: Menambahkan pengecekan eksplisit untuk e.data.message dan e.message
    const errorMessage = (e.data?.message !== null && typeof e.data?.message === 'string' && e.data.message !== '')
      ? e.data.message
      : ((typeof e.message === 'string' && e.message !== '') ? e.message : 'Gagal menyimpan pengaturan.')
    showSnackbar(errorMessage, 'error')
  }
  finally {
    saveLoading.value = false
  }
}

/**
 * Menampilkan notifikasi snackbar.
 */
function showSnackbar(text: string, color: string = 'info') {
  const normalized = String(color || '').toLowerCase()

  const type = (normalized === 'success' || normalized === 'error' || normalized === 'warning')
    ? (normalized as 'success' | 'error' | 'warning')
    : 'info'

  const titleMap: Record<typeof type, string> = {
    success: 'Berhasil',
    error: 'Gagal',
    warning: 'Perhatian',
    info: 'Info',
  }

  addSnackbar({
    type,
    title: titleMap[type],
    text,
  })
}

// --- Lifecycle & Watchers ---
onMounted(() => {
  if (authStore.isSuperAdmin === true) { // Perbaikan: Menambahkan perbandingan eksplisit
    fetchRecipients()
  }
})

// Tonton perubahan pada `selectedNotificationType` dan muat ulang data
watch(selectedNotificationType, () => {
  fetchRecipients()
})

watch(loading, (val) => {
  if (val === false)
    hasLoadedOnce.value = true
}, { immediate: true })
</script>

<template>
  <div>
    <template v-if="authStore.isSuperAdmin === true">
      <VCard class="mb-6">
        <VCardItem>
          <VCardTitle>Pilih Jenis Notifikasi</VCardTitle>
          <VCardSubtitle>Pilih jenis notifikasi yang ingin Anda kelola penerimanya.</VCardSubtitle>
        </VCardItem>
        <VCardText>
          <AppSelect
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
          </AppSelect>
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

        <VProgressLinear
          v-if="showSilentRefreshing"
          indeterminate
          color="primary"
          height="2"
        />

        <div v-if="showInitialSkeleton">
          <VSkeletonLoader
            v-for="i in 4"
            :key="i"
            type="list-item-two-line"
            class="mx-4 my-2"
          />
        </div>

        <div v-else-if="error !== null" class="text-center pa-8">
          <VIcon icon="tabler-alert-triangle" size="48" color="error" class="mb-2" />
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
              <VDivider v-if="Number(index) < recipients.length - 1" />
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
            prepend-icon="tabler-device-floppy"
            :loading="saveLoading"
            :disabled="loading === true || error !== null"
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
          <VIcon icon="tabler-lock-access" size="64" color="error" class="mb-4" />
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
