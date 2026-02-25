import type { ComputedRef } from 'vue'
import { ref } from 'vue'

interface SnapPayResult {
  order_id: string
}

interface SnapInstance {
  pay: (token: string, options: {
    onSuccess: (result: SnapPayResult) => void
    onPending: (result: SnapPayResult) => void
    onError: (result: SnapPayResult) => void
    onClose: () => void
  }) => void
}

declare global {
  interface Window {
    snap?: SnapInstance
  }
}

interface UsePaymentSnapActionOptions {
  snapToken: ComputedRef<string | null>
  orderId: ComputedRef<string | null>
  statusToken: ComputedRef<string | null>
  ensureMidtransReady: () => Promise<void>
  refreshStatus: () => Promise<void>
  cancelTransactionSilently: (orderId: string) => Promise<void>
  navigateToStatus: (orderId: string, statusToken?: string | null) => Promise<void>
  notify: (payload: { type: 'error' | 'warning' | 'info' | 'success'; title: string; text: string }) => void
}

export function usePaymentSnapAction(options: UsePaymentSnapActionOptions) {
  const {
    snapToken,
    orderId,
    statusToken,
    ensureMidtransReady,
    refreshStatus,
    cancelTransactionSilently,
    navigateToStatus,
    notify,
  } = options

  const isPayingWithSnap = ref(false)

  async function openSnapPayment() {
    if (isPayingWithSnap.value)
      return

    const token = snapToken.value
    if (!token) {
      notify({ type: 'warning', title: 'Tidak Tersedia', text: 'Token pembayaran Snap tidak tersedia.' })
      return
    }

    isPayingWithSnap.value = true
    try {
      await ensureMidtransReady()
      if (!window.snap)
        throw new Error('Snap.js siap, tetapi window.snap tidak tersedia.')

      window.snap.pay(token, {
        onSuccess: async (result) => {
          try {
            const oid = (result?.order_id || orderId.value || '').toString()
            if (oid)
              await navigateToStatus(oid, statusToken.value)
            await refreshStatus()
          }
          finally {
            isPayingWithSnap.value = false
          }
        },
        onPending: async (result) => {
          try {
            const oid = (result?.order_id || orderId.value || '').toString()
            if (oid)
              await navigateToStatus(oid, statusToken.value)
            await refreshStatus()
          }
          finally {
            isPayingWithSnap.value = false
          }
        },
        onError: async (result) => {
          try {
            const oid = (result?.order_id || orderId.value || '').toString()
            notify({ type: 'error', title: 'Gagal', text: 'Pembayaran gagal diproses. Silakan coba lagi.' })
            if (oid)
              await navigateToStatus(oid, statusToken.value)
            await refreshStatus()
          }
          finally {
            isPayingWithSnap.value = false
          }
        },
        onClose: async () => {
          try {
            notify({ type: 'info', title: 'Dibatalkan', text: 'Jendela pembayaran ditutup.' })
            const oid = (orderId.value || '').toString()
            if (oid)
              await cancelTransactionSilently(oid)
            await refreshStatus()
          }
          finally {
            isPayingWithSnap.value = false
          }
        },
      })
    }
    catch (err: any) {
      const msg = err?.message || 'Gagal membuka pembayaran Snap.'
      notify({ type: 'error', title: 'Gagal', text: msg })
      isPayingWithSnap.value = false
    }
  }

  return {
    isPayingWithSnap,
    openSnapPayment,
  }
}
