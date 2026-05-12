import type { ComputedRef } from 'vue'
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type { TransactionStatusContract } from '~/types/api/contracts'

interface UsePaymentStatusPollingOptions {
  finalStatus: ComputedRef<TransactionStatusContract>
  refreshStatus: () => Promise<void>
  intervalMs?: number
}

function isFinalStatus(status: TransactionStatusContract): boolean {
  return status === 'SUCCESS' || status === 'FAILED' || status === 'EXPIRED' || status === 'CANCELLED'
}

export function usePaymentStatusPolling(options: UsePaymentStatusPollingOptions) {
  const { finalStatus, refreshStatus, intervalMs = 8000 } = options
  const isPolling = ref(false)
  const MAX_CONSECUTIVE_ERRORS = 5
  let consecutiveErrors = 0

  let timer: ReturnType<typeof setInterval> | null = null

  const stopPolling = () => {
    if (timer != null) {
      clearInterval(timer)
      timer = null
    }
    isPolling.value = false
  }

  const startPolling = () => {
    if (timer != null)
      return
    if (isFinalStatus(finalStatus.value))
      return

    consecutiveErrors = 0
    timer = setInterval(() => {
      refreshStatus()
        .then(() => {
          consecutiveErrors = 0
        })
        .catch(error => {
          consecutiveErrors += 1
          if (import.meta.dev)
            console.warn(`[paymentPolling] refresh gagal (${consecutiveErrors}/${MAX_CONSECUTIVE_ERRORS})`, error)
          if (consecutiveErrors >= MAX_CONSECUTIVE_ERRORS)
            stopPolling()
        })
    }, intervalMs)
    isPolling.value = true
  }

  watch(finalStatus, status => {
    if (isFinalStatus(status))
      stopPolling()
    else
      startPolling()
  })

  onMounted(() => {
    if (!isFinalStatus(finalStatus.value))
      startPolling()
  })

  onBeforeUnmount(() => {
    stopPolling()
  })

  return {
    isPolling,
    startPolling,
    stopPolling,
  }
}
