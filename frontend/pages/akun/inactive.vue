<script setup lang="ts">
import { useAuthStore } from '@/store/auth';
import { computed } from 'vue';

definePageMeta({
  layout: 'blank',
});

const authStore = useAuthStore();
const router = useRouter();

// Menyapa pengguna dengan nama jika data tersedia
const userName = computed(() => authStore.currentUser?.full_name || 'Pengguna');

const logout = async () => {
  await authStore.logout();
  await router.push('/login');
};

const goToBeliPaket = () => {
  router.push('/beli');
};
</script>

<template>
  <div class="misc-wrapper">
    <VCard
      class="pa-8 pa-md-12 mx-auto"
      max-width="600"
      elevation="4"
    >
      <VCardText class="text-center">
        <VIcon
          icon="ri-pause-circle-line"
          size="64"
          color="warning"
          class="mb-4"
        />

        <h1 class="text-h4 font-weight-bold mb-2">
          Akses Internet Anda Dijeda
        </h1>

        <p class="text-h6 font-weight-regular text-medium-emphasis">
          Halo, {{ userName }}!
        </p>

        <p class="text-body-1 mt-6">
          Akun Anda saat ini tidak memiliki paket data yang aktif.
          Hal ini dapat terjadi karena Anda adalah pengguna baru, atau masa berlaku paket internet Anda sebelumnya telah berakhir.
        </p>

        <p class="text-body-1 mb-8">
          Untuk dapat terhubung kembali ke internet, silakan aktifkan akun Anda dengan melakukan pembelian paket data.
        </p>

        <div class="d-flex flex-wrap justify-center gap-4">
          <VBtn
            size="large"
            @click="goToBeliPaket"
          >
            <VIcon
              icon="ri-shopping-cart-2-line"
              class="mr-2"
            />
            Lihat & Beli Paket
          </VBtn>

          <VBtn
            size="large"
            variant="tonal"
            @click="logout"
          >
            Keluar
          </VBtn>
        </div>
      </VCardText>
    </VCard>
  </div>
</template>

<style lang="scss">
@use "@core/scss/template/pages/misc.scss";
</style>