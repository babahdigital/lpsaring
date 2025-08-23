<script setup lang="ts">
import { useAuthStore } from '@/store/auth'

definePageMeta({
  layout: 'blank',
})

const authStore = useAuthStore()
const router = useRouter()

const logout = async () => {
  await authStore.logout()
  router.push('/login')
}

const goToBeliPaket = () => {
  router.push('/beli')
}
</script>

<template>
  <div class="misc-wrapper">
    <ErrorHeader
      status-code="INACTIVE"
      title="Akun Anda Tidak Aktif ⌛"
      description="Akun Anda terdaftar dan disetujui, namun belum memiliki paket aktif. Silakan beli paket untuk mulai menggunakan internet."
    />

    <div class="mt-6 d-flex gap-4 align-center justify-center">
      <VBtn color="primary" @click="goToBeliPaket">Beli Paket Data</VBtn>
      <VBtn variant="tonal" color="secondary" @click="logout">
        <VIcon icon="ri-logout-box-line" class="mr-2" />
        Keluar
      </VBtn>
    </div>

    <div class="misc-avatar w-100 text-center mt-8">
      <VImg
        src="/assets/images/pages/misc-under-maintenance.png"
        alt="Inactive"
        :max-width="800"
        class="mx-auto"
      />
    </div>
  </div>
</template>

<style lang="scss">
@use "@core/scss/template/pages/misc.scss";
</style>
