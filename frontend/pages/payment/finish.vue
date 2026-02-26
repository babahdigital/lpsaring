<script setup lang="ts">
import type { TransactionStatusContract } from '~/types/api/contracts'
import { useNuxtApp, useRuntimeConfig } from '#app'
import StatusActionButtons from '~/components/payment/StatusActionButtons.vue'
import StatusHeader from '~/components/payment/StatusHeader.vue'
import PendingPaymentInstructions from '~/components/payment/PendingPaymentInstructions.vue'
import PaymentSummaryPanel from '~/components/payment/PaymentSummaryPanel.vue'
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useDisplay } from 'vuetify'
import { useSnackbar } from '~/composables/useSnackbar'
import { usePaymentStatusPolling } from '~/composables/usePaymentStatusPolling'
import { usePaymentInstructions } from '~/composables/usePaymentInstructions'
import { usePaymentSnapAction } from '~/composables/usePaymentSnapAction'
import { usePaymentStatusData } from '~/composables/usePaymentStatusData'
import { usePaymentInvoiceQrDeeplink } from '~/composables/usePaymentInvoiceQrDeeplink'
import {
  formatCurrency,
  formatToLocalPhone,
  usePaymentFinishPresentation,
} from '~/composables/usePaymentFinishPresentation'

const route = useRoute()
const router = useRouter()
const { $api } = useNuxtApp()
const runtimeConfig = useRuntimeConfig()
const { add: addSnackbar } = useSnackbar()
const { smAndDown } = useDisplay()
const { ensureMidtransReady } = useMidtransSnap()
const isHydrated = ref(false)
const isMobile = computed(() => (isHydrated.value ? smAndDown.value : false))
const apiBaseUrl = computed(() => (runtimeConfig.public.apiBaseUrl ?? '/api').replace(/\/$/, ''))

const copySuccess = ref<string | null>(null)

const {
  transactionDetails,
  isLoading,
  isRefreshing,
  fetchError,
  errorMessageFromQuery,
  statusTokenFromQuery,
  isPublicView,
  orderId,
  isDebtSettlement,
  finalStatus,
  refreshStatus,
  cancelTransactionSilently,
} = usePaymentStatusData({
  route,
  apiFetch: (path, options) => $api(path, options),
})

function formatDebtMb(value?: number | null): string | null {
  if (value == null)
    return null
  const n = Math.round(Number(value))
  if (!Number.isFinite(n) || n <= 0)
    return null
  return `${n} MB`
}

onMounted(() => {
  isHydrated.value = true
})

const userPhoneNumberRaw = computed(() => transactionDetails.value?.user?.phone_number ?? null)
const userName = computed(() => transactionDetails.value?.user?.full_name ?? 'Pengguna')
const packageName = computed(() => {
  if (isDebtSettlement.value) {
    const debtType = transactionDetails.value?.debt_type ?? null
    if (debtType === 'auto') {
      const mbText = formatDebtMb(transactionDetails.value?.debt_mb ?? null)
      if (mbText)
        return `Bayar Kuota ${mbText}`
      return 'Pelunasan Tunggakan Kuota'
    }

    if (debtType === 'manual') {
      const note = String(transactionDetails.value?.debt_note ?? '').trim()
      if (note)
        return note
      return 'Pelunasan Hutang Manual'
    }

    return 'Pelunasan Tunggakan Kuota'
  }
  return transactionDetails.value?.package?.name ?? 'Paket Tidak Diketahui'
})

const debtNote = computed(() => (isDebtSettlement.value ? 'Pelunasan Tunggakan Quota' : null))
const paymentMethod = computed(() => transactionDetails.value?.payment_method ?? null)
const displayHotspotUsername = computed(() => formatToLocalPhone(userPhoneNumberRaw.value))

async function copyToClipboard(textToCopy: string | undefined | null, type: string) {
  if (textToCopy == null || navigator.clipboard == null) {
    addSnackbar({ type: 'error', title: 'Gagal Menyalin', text: 'Gagal menyalin: Fitur tidak didukung oleh browser Anda.' })
    return
  }
  try {
    await navigator.clipboard.writeText(textToCopy)
    copySuccess.value = type
    addSnackbar({ type: 'success', title: 'Berhasil', text: `${type} berhasil disalin ke clipboard!` })
    setTimeout(() => {
      copySuccess.value = null
    }, 2500)
  }
  catch {
    addSnackbar({ type: 'error', title: 'Gagal Menyalin', text: `Gagal menyalin ${type}.` })
  }
}

function goToSelectPackage() {
  router.push({ path: '/beli' })
}

function goToDashboard() {
  router.push({ path: '/dashboard' })
}

function goToHistory() {
  router.push('/riwayat')
}

const {
  paymentMethodBadgeLabel,
  vaNumberLabel,
  alertType,
  alertTitle,
  alertIcon,
  detailMessage,
  statusInfoBox,
  showSpecificPendingInstructions,
  showEchannel,
} = usePaymentFinishPresentation({
  finalStatus,
  isPublicView,
  transactionDetails,
  errorMessageFromQuery,
  isDebtSettlement,
  packageName,
  displayHotspotUsername,
  userName,
  paymentMethod,
})

const {
  canDownloadInvoice,
  isDownloadingInvoice,
  downloadInvoice,
  qrDownloadUrl,
  qrViewUrl,
  showQrCode,
  qrSize,
  appDeeplinkUrl,
  deeplinkAppName,
  showAppDeeplinkButton,
  showAppInstructions,
  openAppDeeplink,
  supportWaUrl,
  openSupportWhatsApp,
} = usePaymentInvoiceQrDeeplink({
  apiBaseUrl,
  orderId,
  statusToken: statusTokenFromQuery,
  finalStatus,
  isPublicView,
  isMobile,
  transactionDetails: computed(() => transactionDetails.value),
  paymentMethod,
  apiFetch: (path, options) => $api(path, options),
  notify: addSnackbar,
  runtimePublicConfig: runtimeConfig.public as Record<string, unknown>,
})

const snapToken = computed(() => {
  const token = transactionDetails.value?.snap_token
  return (typeof token === 'string' && token.trim() !== '') ? token.trim() : null
})

const showSnapPaySection = computed(() => {
  if (snapToken.value == null)
    return false
  return finalStatus.value === 'UNKNOWN' || finalStatus.value === 'PENDING'
})

const {
  vaInstructionTitle,
  vaInstructions,
  qrisInstructions,
  appDeeplinkInstructions,
} = usePaymentInstructions({
  paymentMethod,
  deeplinkAppName,
})

async function navigateToStatus(orderIdValue: string, token?: string | null) {
  await router.push({
    path: '/payment/status',
    query: {
      order_id: orderIdValue,
      t: token ?? undefined,
    },
  })
}

const { isPayingWithSnap, openSnapPayment } = usePaymentSnapAction({
  snapToken,
  orderId,
  statusToken: statusTokenFromQuery,
  ensureMidtransReady,
  refreshStatus,
  cancelTransactionSilently,
  navigateToStatus,
  notify: addSnackbar,
})

usePaymentStatusPolling({
  finalStatus,
  refreshStatus,
  intervalMs: 8000,
})

definePageMeta({ layout: 'blank' })
useHead({
  title: computed(() => `Status: ${alertTitle.value}`),
  bodyAttrs: {
    style: 'overflow-x: hidden;',
  },
})
</script>

<template>
  <v-container fluid class="fill-height bg-background pa-0 ma-0 finish-no-x finish-shell">
    <v-row justify="center" align="center" class="fill-height py-md-10 py-6 px-4 finish-shell-row">
      <v-col cols="12" class="mx-auto finish-max">
        <div v-if="isLoading && !transactionDetails" class="text-center pa-10">
          <v-progress-circular indeterminate color="primary" size="64" width="6" />
          <p class="text-h6 mt-8 text-medium-emphasis font-weight-regular">
            Memeriksa Status Transaksi Anda...
          </p>
        </div>

        <v-card v-else-if="fetchError" variant="tonal" color="error" class="mx-auto rounded-xl pa-2">
          <v-card-text class="text-center pa-6">
            <v-icon size="56" class="mb-4" color="error" icon="tabler-alert-octagon" />
            <h2 class="text-h5 font-weight-bold mb-3">
              Gagal Memuat Transaksi
            </h2>
            <p class="text-body-1 mb-6 text-medium-emphasis">
              {{ fetchError }}
            </p>
            <v-btn color="primary" variant="flat" size="large" @click="goToSelectPackage">
              <v-icon start icon="tabler-arrow-left" />Kembali ke Pilihan Paket
            </v-btn>
          </v-card-text>
        </v-card>

        <v-card v-else-if="transactionDetails" variant="flat" border class="mx-auto finish-card overflow-hidden bg-surface elevation-12">
          <StatusHeader
            :alert-type="alertType"
            :alert-icon="alertIcon"
            :alert-title="alertTitle"
            :detail-message="detailMessage"
            :final-status="finalStatus"
            :is-public-view="isPublicView"
            :payment-method-badge-label="paymentMethodBadgeLabel ?? undefined"
          />

          <v-divider />

          <v-card-text class="pa-0">
            <PaymentSummaryPanel
              :is-public-view="isPublicView"
              :user-name="userName"
              :display-hotspot-username="displayHotspotUsername"
              :order-id="transactionDetails.midtrans_order_id"
              :midtrans-transaction-id="transactionDetails.midtrans_transaction_id ?? null"
              :package-name="packageName"
              :debt-note="debtNote"
              :total-amount-text="formatCurrency(transactionDetails.amount)"
              :final-status="finalStatus"
              :status-info-box="statusInfoBox"
              :can-download-invoice="canDownloadInvoice"
              :is-downloading-invoice="isDownloadingInvoice"
              :show-snap-pay-section="showSnapPaySection"
              :is-paying-with-snap="isPayingWithSnap"
              @download-invoice="downloadInvoice"
              @open-snap-payment="openSnapPayment"
            />
          </v-card-text>

          <PendingPaymentInstructions
            :final-status="finalStatus"
            :show-specific-pending-instructions="showSpecificPendingInstructions"
            :transaction-details="transactionDetails"
            :va-number-label="vaNumberLabel"
            :copy-success="copySuccess"
            :va-instruction-title="vaInstructionTitle"
            :va-instructions="vaInstructions"
            :show-echannel="showEchannel"
            :show-app-instructions="showAppInstructions"
            :app-deeplink-instructions="appDeeplinkInstructions"
            :deeplink-app-name="deeplinkAppName"
            :show-qr-code="showQrCode"
            :qr-view-url="qrViewUrl"
            :qr-download-url="qrDownloadUrl"
            :qr-size="qrSize"
            :qris-instructions="qrisInstructions"
            :show-app-deeplink-button="showAppDeeplinkButton"
            @copy="({ value, label }) => copyToClipboard(value, label)"
          />

          <v-divider />
          <StatusActionButtons
            :final-status="finalStatus"
            :is-public-view="isPublicView"
            :is-refreshing="isRefreshing"
            :show-app-deeplink-button="showAppDeeplinkButton"
            :show-qr-code="showQrCode"
            :deeplink-app-name="deeplinkAppName ?? 'Aplikasi'"
            :qr-download-url="qrDownloadUrl"
            :support-wa-url="supportWaUrl ?? ''"
            @open-app-deeplink="openAppDeeplink"
            @refresh-status="refreshStatus"
            @go-select-package="goToSelectPackage"
            @go-dashboard="goToDashboard"
            @go-history="goToHistory"
            @open-support-whatsapp="openSupportWhatsApp"
          />
        </v-card>
      </v-col>
    </v-row>
  </v-container>
</template>

<style scoped>
.font-mono { font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, Courier, monospace; }

.finish-no-x {
  overflow-x: hidden;
}

.finish-shell {
  min-height: 100vh;
  min-height: 100dvh;
}

.finish-shell-row {
  min-height: inherit;
}

.finish-kv {
  min-width: 0;
}

.finish-header-title,
.finish-header-desc {
  overflow-wrap: anywhere;
  word-break: break-word;
}

.break-anywhere {
  overflow-wrap: anywhere;
  word-break: break-word;
  min-width: 0;
  max-width: 100%;
}

.finish-big-input :deep(.v-field--variant-outlined .v-field__input) {
  font-size: 1.1rem !important;
  line-height: 1.4 !important;
}

.finish-max {
  max-width: 520px;
}

.finish-card {
  border-radius: 16px;
}

@media (max-width: 600px) {
  .finish-max {
    max-width: 100%;
  }

  .finish-big-input :deep(.v-field--variant-outlined .v-field__input) {
    font-size: 1.02rem !important;
  }
}
</style>
