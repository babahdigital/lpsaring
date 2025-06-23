<script lang="ts" setup>
import { useNuxtApp } from '#app'
import { ref } from 'vue'
import { useSnackbar } from '@/composables/useSnackbar'

// Menerima properti dari komponen induk
const props = defineProps<{
  modelValue: boolean // Untuk mengontrol visibilitas dialog (v-model)
  errorMessage: string // Pesan error dari server untuk ditampilkan
}>()

// Mendefinisikan event yang akan dikirim kembali ke induk
const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void
  (e: 'profiles-created'): void // Sinyal bahwa profil berhasil dibuat
}>()

// State internal komponen
const { $api } = useNuxtApp()
const snackbar = useSnackbar()
const loading = ref(false)

/**
 * Fungsi cerdas untuk membuat profil sistem yang hilang.
 * Ia akan mengecek dulu profil apa yang sudah ada, lalu hanya membuat yang belum ada.
 */
async function setupMissingProfiles() {
  loading.value = true

  // Ini adalah profil wajib yang harus ada di sistem
  const requiredProfiles = ['user', 'unlimited']

  try {
    // 1. Ambil semua profil yang sudah ada dari server
    const existingProfiles: { profile_name: string }[] = await $api('/admin/profiles')
    const existingProfileNames = new Set(existingProfiles.map(p => p.profile_name))

    // 2. Tentukan profil mana yang belum ada
    const profilesToCreate = requiredProfiles.filter(pName => !existingProfileNames.has(pName))

    // Jika semua sudah ada, beri info dan tutup
    if (profilesToCreate.length === 0) {
      snackbar.add({ type: 'info', title: 'Sudah Lengkap', text: 'Semua profil sistem yang dibutuhkan sudah ada.' })
      emit('profiles-created') // Kirim sinyal sukses agar induk bisa mencoba lagi
      closeDialog()
      return
    }

    // 3. Buat profil yang hilang satu per satu
    for (const profileName of profilesToCreate) {
      await $api('/admin/profiles', {
        method: 'POST',
        body: {
          profile_name: profileName,
          description: `Profil sistem otomatis untuk paket ${profileName === 'unlimited' ? 'tanpa batas kuota' : 'berkuota'}.`,
        },
      })
    }

    snackbar.add({ type: 'success', title: 'Konfigurasi Selesai', text: `Profil sistem (${profilesToCreate.join(', ')}) berhasil dibuat.` })
    emit('profiles-created') // Kirim sinyal sukses ke induk
    closeDialog()
  }
  catch (error: any) {
    snackbar.add({
      type: 'error',
      title: 'Gagal Membuat Profil',
      text: error.data?.message || 'Terjadi kesalahan saat menghubungi server.',
    })
  }
  finally {
    loading.value = false
  }
}

// Fungsi untuk menutup dialog
function closeDialog() {
  emit('update:modelValue', false)
}
</script>

<template>
  <VDialog
    :model-value="props.modelValue"
    max-width="500px"
    persistent
  >
    <VCard>
      <VCardItem class="text-center pa-6">
        <VIcon
          icon="tabler-settings-cog"
          size="56"
          color="warning"
          class="mb-4"
        />
        <VCardTitle class="text-h5 mb-2">
          Konfigurasi Diperlukan
        </VCardTitle> <p
          class="text-body-1 text-medium-emphasis mx-auto"
          style="max-width: 350px;"
          v-html="props.errorMessage"
        />
      </VCardItem>
      <VCardText class="text-center pb-6">
        <p class="text-caption text-disabled">
          Sistem dapat membuat profil ini untuk Anda secara otomatis.
        </p>
        <div class="d-flex justify-center gap-4 mt-4">
          <VBtn
            variant="tonal"
            color="secondary"
            @click="closeDialog"
          >
            Batal
          </VBtn>
          <VBtn
            color="warning"
            :loading="loading"
            @click="setupMissingProfiles"
          >
            <VIcon
              start
              icon="tabler-bolt"
            />
            Perbaiki Otomatis
          </VBtn>
        </div>
      </VCardText>
    </VCard>
  </VDialog>
</template>
