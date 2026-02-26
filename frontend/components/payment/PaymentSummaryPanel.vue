<script setup lang="ts">
import type { TransactionStatusContract } from '../../types/api/contracts'

interface StatusInfoBox {
  type: 'success' | 'warning' | 'error' | 'info'
  icon: string
  title: string
  text: string
}

const props = defineProps<{
  isPublicView: boolean
  userName: string
  displayHotspotUsername: string | null
  orderId: string
  midtransTransactionId: string | null
  packageName: string
  debtNote: string | null
  totalAmountText: string
  finalStatus: TransactionStatusContract
  statusInfoBox: StatusInfoBox | null
  canDownloadInvoice: boolean
  isDownloadingInvoice: boolean
  showSnapPaySection: boolean
  isPayingWithSnap: boolean
}>()

const emit = defineEmits<{
  downloadInvoice: []
  openSnapPayment: []
}>()
</script>

<template>
  <div class="px-sm-8 px-6 py-6">
    <div v-if="props.userName && !props.isPublicView" class="d-flex flex-column flex-sm-row justify-space-between align-start align-sm-center mb-3 finish-kv" style="gap: 6px;">
      <span class="text-body-2 text-medium-emphasis">Nama Pengguna</span>
      <span class="font-weight-semibold break-anywhere">{{ props.userName }}</span>
    </div>

    <div v-if="props.displayHotspotUsername && !props.isPublicView" class="d-flex flex-column flex-sm-row justify-space-between align-start align-sm-center mb-3 finish-kv" style="gap: 6px;">
      <span class="text-body-2 text-medium-emphasis">Nomor</span>
      <span class="font-weight-semibold break-anywhere">{{ props.displayHotspotUsername }}</span>
    </div>

    <div class="d-flex flex-column flex-sm-row justify-space-between align-start align-sm-center mb-3 finish-kv" style="gap: 6px;">
      <span class="text-body-2 text-medium-emphasis">Order ID</span>
      <span class="font-weight-bold text-primary break-anywhere">{{ props.orderId }}</span>
    </div>

    <div v-if="props.midtransTransactionId && !props.isPublicView" class="d-flex flex-column flex-sm-row justify-space-between align-start align-sm-center mb-3 finish-kv" style="gap: 6px;">
      <span class="text-body-2 text-medium-emphasis">ID Pembayaran</span>
      <span class="font-weight-bold font-mono break-anywhere">{{ props.midtransTransactionId }}</span>
    </div>

    <div class="d-flex flex-column flex-sm-row justify-space-between align-start align-sm-center mb-3 finish-kv" style="gap: 6px;">
      <span class="text-body-2 text-medium-emphasis">Paket</span>
      <span class="font-weight-semibold break-anywhere">{{ props.packageName }}</span>
    </div>

    <div v-if="props.debtNote && !props.isPublicView" class="d-flex flex-column flex-sm-row justify-space-between align-start align-sm-center mb-3 finish-kv" style="gap: 6px;">
      <span class="text-body-2 text-medium-emphasis">Catatan</span>
      <span class="font-weight-semibold break-anywhere">{{ props.debtNote }}</span>
    </div>

    <div class="d-flex flex-column flex-sm-row justify-space-between align-start align-sm-center" style="gap: 6px;">
      <span class="text-body-2 text-medium-emphasis">Total Tagihan</span>
      <span class="text-h6 font-weight-bold" :class="props.finalStatus === 'SUCCESS' ? 'text-success' : 'text-warning'">
        {{ props.totalAmountText }}
      </span>
    </div>

    <v-alert
      v-if="props.statusInfoBox && !props.isPublicView"
      :type="props.statusInfoBox.type"
      variant="tonal"
      density="comfortable"
      class="mt-6"
      :icon="props.statusInfoBox.icon"
    >
      <div class="font-weight-bold mb-1">{{ props.statusInfoBox.title }}</div>
      <div class="text-body-2">{{ props.statusInfoBox.text }}</div>
    </v-alert>

    <v-alert
      v-if="props.canDownloadInvoice"
      type="info"
      variant="tonal"
      density="compact"
      class="mt-6"
    >
      <div class="d-flex align-center" style="gap: 12px;">
        <div class="flex-grow-1">
          Invoice PDF juga dikirim otomatis melalui WhatsApp setelah pembayaran berhasil.
        </div>
        <v-tooltip location="top" text="Unduh Invoice (PDF)">
          <template #activator="{ props: tooltipProps }">
            <v-btn
              v-bind="tooltipProps"
              icon="tabler-file-download"
              variant="text"
              color="success"
              size="small"
              :loading="props.isDownloadingInvoice"
              :disabled="props.isDownloadingInvoice"
              @click="emit('downloadInvoice')"
            />
          </template>
        </v-tooltip>
      </div>
    </v-alert>

    <v-alert
      v-if="props.showSnapPaySection"
      type="info"
      variant="tonal"
      density="comfortable"
      class="mt-6"
    >
      <div class="d-flex flex-column flex-sm-row align-start align-sm-center" style="gap: 12px;">
        <div class="flex-grow-1">
          Lanjutkan pembayaran dengan membuka halaman pembayaran Midtrans.
        </div>
        <v-btn
          color="primary"
          :loading="props.isPayingWithSnap"
          :disabled="props.isPayingWithSnap"
          @click="emit('openSnapPayment')"
        >
          Bayar
        </v-btn>
      </div>
    </v-alert>
  </div>
</template>

<style scoped>
.font-mono {
  font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, Courier, monospace;
}

.finish-kv {
  min-width: 0;
}

.break-anywhere {
  overflow-wrap: anywhere;
  word-break: break-word;
  min-width: 0;
  max-width: 100%;
}
</style>
