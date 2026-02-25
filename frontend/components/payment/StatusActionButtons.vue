<script setup lang="ts">
defineProps({
  finalStatus: {
    type: String,
    required: true,
  },
  isPublicView: {
    type: Boolean,
    default: false,
  },
  isRefreshing: {
    type: Boolean,
    default: false,
  },
  showAppDeeplinkButton: {
    type: Boolean,
    default: false,
  },
  showQrCode: {
    type: Boolean,
    default: false,
  },
  deeplinkAppName: {
    type: String,
    default: 'Aplikasi',
  },
  qrDownloadUrl: {
    type: String,
    default: '',
  },
  supportWaUrl: {
    type: String,
    default: '',
  },
})

const emit = defineEmits<{
  (e: 'open-app-deeplink'): void
  (e: 'refresh-status'): void
  (e: 'go-select-package'): void
  (e: 'go-dashboard'): void
  (e: 'go-history'): void
  (e: 'open-support-whatsapp'): void
}>()
</script>

<template>
  <div class="px-sm-8 px-6 pb-10 pt-6 d-flex flex-column" style="gap: 14px;">
    <template v-if="finalStatus === 'PENDING'">
      <v-btn
        v-if="showAppDeeplinkButton"
        block
        size="large"
        rounded="lg"
        color="success"
        variant="flat"
        prepend-icon="tabler-external-link"
        @click="emit('open-app-deeplink')"
      >
        Buka {{ deeplinkAppName }}
      </v-btn>

      <v-btn
        v-else-if="showQrCode"
        block
        size="large"
        rounded="lg"
        color="primary"
        variant="flat"
        prepend-icon="tabler-download"
        :href="qrDownloadUrl"
        target="_blank"
        :disabled="qrDownloadUrl === ''"
      >
        Download QR Code
      </v-btn>

      <v-btn
        v-else
        block
        size="large"
        rounded="lg"
        color="primary"
        variant="flat"
        prepend-icon="tabler-refresh"
        :disabled="isRefreshing"
        @click="emit('refresh-status')"
      >
        Cek Status Pembayaran
      </v-btn>

      <v-btn
        v-if="showAppDeeplinkButton || showQrCode"
        block
        size="large"
        rounded="lg"
        color="secondary"
        variant="text"
        class="text-medium-emphasis"
        prepend-icon="tabler-refresh"
        :disabled="isRefreshing"
        @click="emit('refresh-status')"
      >
        Cek Status Pembayaran
      </v-btn>
      <v-btn
        v-else
        block
        size="large"
        rounded="lg"
        color="secondary"
        variant="text"
        class="text-medium-emphasis"
        prepend-icon="tabler-shopping-cart-plus"
        @click="emit('go-select-package')"
      >
        Buat Pesanan Baru
      </v-btn>
    </template>

    <template v-else-if="finalStatus === 'SUCCESS'">
      <v-btn
        v-if="!isPublicView"
        block
        size="large"
        rounded="lg"
        color="primary"
        variant="flat"
        prepend-icon="tabler-layout-dashboard"
        @click="emit('go-dashboard')"
      >
        Kembali ke Dashboard
      </v-btn>

      <v-btn
        block
        size="large"
        rounded="lg"
        :color="isPublicView ? 'primary' : 'secondary'"
        :variant="isPublicView ? 'flat' : 'text'"
        class="text-medium-emphasis"
        :prepend-icon="isPublicView ? 'tabler-arrow-left' : 'tabler-history'"
        @click="isPublicView ? emit('go-select-package') : emit('go-history')"
      >
        {{ isPublicView ? 'Kembali ke Beranda' : 'Lihat Riwayat Transaksi' }}
      </v-btn>
    </template>

    <template v-else-if="finalStatus === 'CANCELLED'">
      <v-btn
        block
        size="large"
        rounded="lg"
        color="primary"
        variant="flat"
        prepend-icon="tabler-shopping-cart-plus"
        @click="emit('go-select-package')"
      >
        Buat Pesanan Baru
      </v-btn>

      <v-btn
        block
        size="large"
        rounded="lg"
        color="secondary"
        variant="text"
        class="text-medium-emphasis"
        prepend-icon="tabler-arrow-left"
        @click="emit('go-select-package')"
      >
        Kembali ke Beranda
      </v-btn>
    </template>

    <template v-else>
      <v-btn
        block
        size="large"
        rounded="lg"
        color="primary"
        variant="flat"
        prepend-icon="tabler-refresh"
        @click="emit('go-select-package')"
      >
        Ulangi Pembayaran
      </v-btn>

      <v-btn
        v-if="supportWaUrl"
        block
        size="large"
        rounded="lg"
        color="secondary"
        variant="text"
        class="text-medium-emphasis"
        prepend-icon="tabler-brand-whatsapp"
        @click="emit('open-support-whatsapp')"
      >
        Hubungi Bantuan
      </v-btn>
      <v-btn
        v-else
        block
        size="large"
        rounded="lg"
        color="secondary"
        variant="text"
        class="text-medium-emphasis"
        prepend-icon="tabler-arrow-left"
        @click="emit('go-select-package')"
      >
        Kembali
      </v-btn>
    </template>
  </div>
</template>
