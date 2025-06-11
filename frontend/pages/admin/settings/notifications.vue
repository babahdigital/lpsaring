<script lang="ts" setup>
import { ref, reactive, onMounted } from 'vue'
import { useNuxtApp, useHead } from '#app'
import { useAuthStore } from '@/store/auth'

// --- Tipe Data ---
interface AdminRecipient {
  id: string
  full_name: string
  phone_number: string
  is_subscribed: boolean
}

// --- Inisialisasi & Store ---
useHead({ title: 'Pengaturan Notifikasi' })

const { $api } = useNuxtApp()
const authStore = useAuthStore()

// --- State Reaktif ---
const recipients = ref<AdminRecipient[]>([])
const loading = ref(true)
const saveLoading = ref(false)
const error = ref<string | null>(null)
const snackbar = reactive({ show: false, text: '', color: 'info' })

// --- Logika Inti ---

/**
 * Mengambil daftar admin dan status langganan notifikasi mereka dari API.
 */
async function fetchRecipients() {
  loading.value = true
  error.value = null
  try {
    const data = await $api<AdminRecipient[]>('/admin/notification-recipients', {
      method: 'GET',
    })
    recipients.value = data
  }
  catch (e: any) {
    const errorMessage = e.data?.message || e.message || 'Terjadi kesalahan tidak diketahui.'
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

    const payload = { subscribed_admin_ids }

    await $api('/admin/notification-recipients', {
      method: 'POST',
      body: payload,
    })

    showSnackbar('Pengaturan notifikasi berhasil disimpan.', 'success')
  }
  catch (e: any) {
    const errorMessage = e.data?.message || e.message || 'Gagal menyimpan pengaturan.'
    showSnackbar(errorMessage, 'error')
  }
  finally {
    saveLoading.value = false
  }
}

/**
 * Menampilkan notifikasi snackbar.
 * @param text Pesan yang akan ditampilkan.
 * @param color Warna snackbar.
 */
function showSnackbar(text: string, color: string = 'info') {
  snackbar.text = text
  snackbar.color = color
  snackbar.show = true
}

// --- Lifecycle Hook ---
onMounted(() => {
  // Hanya fetch data jika pengguna adalah Super Admin
  if (authStore.isSuperAdmin) {
    fetchRecipients()
  }
})
useHead({ title: 'Notifikasi WhatsApp' })
</script>

<template>
  <div>
    <template v-if="authStore.isSuperAdmin">
      <VCard>
        <VCardItem>
          <VCardTitle>Pengaturan Notifikasi</VCardTitle>
          <VCardSubtitle>
            Atur admin mana saja yang akan menerima notifikasi WhatsApp saat ada pendaftaran pengguna baru.
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
              <VDivider v-if="index < recipients.length - 1" />
            </template>
          </VList>
        </VCardText>

        <VDivider />

        <VCardActions class="pa-4">
          <VSpacer />
          <VBtn
            color="primary"
            variant="elevated"
            prepend-icon="tabler-device-floppy"
            :loading="saveLoading"
            :disabled="loading || !!error"
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

    <VSnackbar
      v-model="snackbar.show"
      :color="snackbar.color"
      :timeout="4000"
      location="top end"
    >
      {{ snackbar.text }}
      <template #actions>
        <VBtn
          icon="tabler-x"
          variant="text"
          color="white"
          @click="snackbar.show = false"
        />
      </template>
    </VSnackbar>
  </div>
</template>