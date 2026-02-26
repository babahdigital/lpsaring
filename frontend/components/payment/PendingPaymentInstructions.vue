<script setup lang="ts">
import type { TransactionDetailResponseContract, TransactionStatusContract } from '~/types/api/contracts'

interface CopyPayload {
  value: string | null | undefined
  label: string
}

const props = defineProps<{
  finalStatus: TransactionStatusContract
  showSpecificPendingInstructions: boolean
  transactionDetails: TransactionDetailResponseContract | null
  vaNumberLabel: string
  copySuccess: string | null
  vaInstructionTitle: string
  vaInstructions: string[]
  showEchannel: boolean
  showAppInstructions: boolean
  appDeeplinkInstructions: string[]
  deeplinkAppName: string | null
  showQrCode: boolean
  qrViewUrl: string
  qrDownloadUrl: string
  qrSize: number
  qrisInstructions: string[]
  showAppDeeplinkButton: boolean
}>()

const emit = defineEmits<{
  copy: [payload: CopyPayload]
}>()

function emitCopy(value: string | null | undefined, label: string) {
  emit('copy', { value, label })
}
</script>

<template>
  <div v-if="props.finalStatus === 'PENDING' && props.showSpecificPendingInstructions" class="px-sm-6 px-4 pb-6 pt-3">
    <v-divider class="mb-6" />
    <h3 class="text-h6 font-weight-bold mb-5 text-center text-high-emphasis">
      Instruksi Pembayaran
    </h3>

    <div v-if="props.transactionDetails?.va_number" class="mb-4">
      <v-text-field
        :model-value="props.transactionDetails.va_number"
        :label="props.vaNumberLabel"
        readonly
        variant="outlined"
        density="comfortable"
        hide-details
        class="finish-big-input font-weight-bold"
      >
        <template #append-inner>
          <v-tooltip location="top" :text="props.copySuccess === 'Nomor VA' ? 'Berhasil Disalin!' : 'Salin Nomor VA'">
            <template #activator="{ props: tooltipProps }">
              <v-btn
                v-bind="tooltipProps"
                :color="props.copySuccess === 'Nomor VA' ? 'success' : ''"
                :icon="props.copySuccess === 'Nomor VA' ? 'tabler-checks' : 'tabler-copy'"
                variant="text"
                @click="emitCopy(props.transactionDetails?.va_number, 'Nomor VA')"
              />
            </template>
          </v-tooltip>
        </template>
      </v-text-field>

      <v-alert type="info" variant="tonal" density="compact" class="mt-4 text-start">
        <div class="font-weight-medium mb-2">{{ props.vaInstructionTitle }}</div>
        <ol class="text-body-2 ps-4 mb-0">
          <li v-for="(step, idx) in props.vaInstructions" :key="`va-step-${idx}`">{{ step }}</li>
        </ol>
      </v-alert>
    </div>

    <div v-else-if="props.showEchannel" class="mb-4">
      <p class="text-body-1 font-weight-medium mb-2 text-medium-emphasis">
        Mandiri Bill Payment
      </p>

      <v-row>
        <v-col cols="12" sm="6">
          <v-text-field
            :model-value="props.transactionDetails?.payment_code"
            label="Bill Key"
            readonly
            variant="outlined"
            density="comfortable"
            hide-details
            class="finish-big-input font-weight-bold"
          >
            <template #append-inner>
              <v-tooltip location="top" :text="props.copySuccess === 'Bill Key' ? 'Berhasil Disalin!' : 'Salin Bill Key'">
                <template #activator="{ props: tooltipProps }">
                  <v-btn
                    v-bind="tooltipProps"
                    :color="props.copySuccess === 'Bill Key' ? 'success' : ''"
                    :icon="props.copySuccess === 'Bill Key' ? 'tabler-checks' : 'tabler-copy'"
                    variant="text"
                    @click="emitCopy(props.transactionDetails?.payment_code, 'Bill Key')"
                  />
                </template>
              </v-tooltip>
            </template>
          </v-text-field>
        </v-col>

        <v-col cols="12" sm="6">
          <v-text-field
            :model-value="props.transactionDetails?.biller_code"
            label="Biller Code"
            readonly
            variant="outlined"
            density="comfortable"
            hide-details
            class="finish-big-input font-weight-bold"
          >
            <template #append-inner>
              <v-tooltip location="top" :text="props.copySuccess === 'Biller Code' ? 'Berhasil Disalin!' : 'Salin Biller Code'">
                <template #activator="{ props: tooltipProps }">
                  <v-btn
                    v-bind="tooltipProps"
                    :color="props.copySuccess === 'Biller Code' ? 'success' : ''"
                    :icon="props.copySuccess === 'Biller Code' ? 'tabler-checks' : 'tabler-copy'"
                    variant="text"
                    @click="emitCopy(props.transactionDetails?.biller_code, 'Biller Code')"
                  />
                </template>
              </v-tooltip>
            </template>
          </v-text-field>
        </v-col>
      </v-row>

      <v-alert type="info" variant="tonal" density="comfortable" class="mt-4 text-start">
        <div class="font-weight-bold mb-1">Cara bayar Mandiri Bill Payment</div>
        <ol class="text-body-2 ps-4 mb-0">
          <li>Buka aplikasi Livin’/Mandiri.</li>
          <li>Pilih Bayar → Multi Payment/Provider.</li>
          <li>Masukkan Bill Key &amp; Biller Code di atas, lalu konfirmasi.</li>
          <li>Kembali ke halaman ini dan klik “Cek Status Pembayaran”.</li>
        </ol>
      </v-alert>
    </div>

    <div v-else-if="props.showAppInstructions" class="mb-4">
      <v-alert type="info" variant="tonal" density="comfortable" class="text-start">
        <div class="font-weight-bold mb-1">Instruksi {{ props.deeplinkAppName }}</div>
        <ol class="text-body-2 ps-4 mb-0">
          <li v-for="(step, idx) in props.appDeeplinkInstructions" :key="`deeplink-step-${idx}`">{{ step }}</li>
        </ol>
      </v-alert>
    </div>

    <div v-else-if="props.showQrCode" class="mb-4 text-center">
      <p class="text-body-1 font-weight-medium mb-3 text-medium-emphasis">
        Scan QR Code Menggunakan Aplikasi Pembayaran Anda
      </p>
      <v-sheet border rounded="lg" class="d-inline-block pa-3 mx-auto bg-white">
        <v-img
          :src="props.qrViewUrl"
          :width="props.qrSize"
          :height="props.qrSize"
          contain
        >
          <template #placeholder>
            <v-skeleton-loader type="image" :width="props.qrSize" :height="props.qrSize" />
          </template>
        </v-img>
      </v-sheet>

      <div class="d-flex justify-center mt-4">
        <v-btn
          color="primary"
          variant="tonal"
          prepend-icon="tabler-file-download"
          :href="props.qrDownloadUrl"
          target="_blank"
          :disabled="props.qrDownloadUrl === ''"
        >
          Download QR
        </v-btn>
      </div>

      <v-alert type="info" variant="tonal" density="comfortable" class="mt-6 text-start">
        <div class="font-weight-bold mb-1">Cara Pembayaran (QRIS)</div>
        <ol class="text-body-2 ps-4 mb-0">
          <li v-for="(step, idx) in props.qrisInstructions" :key="`qris-step-${idx}`">{{ step }}</li>
        </ol>
      </v-alert>

      <p v-if="props.showAppDeeplinkButton" class="text-caption text-medium-emphasis mt-4 mb-0">
        Jika QR tidak terbaca, Anda juga bisa mencoba tombol “Buka {{ props.deeplinkAppName }}” di bawah.
      </p>
    </div>
  </div>
</template>
