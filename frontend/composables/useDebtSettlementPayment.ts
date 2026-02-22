import { useNuxtApp } from '#app'
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useMidtransSnap } from '~/composables/useMidtransSnap'
import { useSnackbar } from '~/composables/useSnackbar'

type DebtInitiateResponse = {
  order_id?: string | null
  midtrans_order_id?: string | null
  snap_token?: string | null
  redirect_url?: string | null
}

interface MidtransPayResult {
  order_id: string
}

export function useDebtSettlementPayment() {
  const { $api } = useNuxtApp()
  const router = useRouter()
  const snackbar = useSnackbar()
  const { ensureMidtransReady } = useMidtransSnap()

  const paying = ref(false)

  async function pay(manualDebtId?: string) {
    if (paying.value)
      return

    paying.value = true
    try {
      const response = await $api<DebtInitiateResponse>('/transactions/debt/initiate', {
        method: 'POST',
        body: manualDebtId ? { manual_debt_id: manualDebtId } : undefined,
      })

      const orderId = typeof response?.order_id === 'string' && response.order_id.trim() !== ''
        ? response.order_id
        : (typeof response?.midtrans_order_id === 'string' ? response.midtrans_order_id : '')
      const snapToken = typeof response?.snap_token === 'string' && response.snap_token.trim() !== ''
        ? response.snap_token
        : null

      if (!orderId || !snapToken) {
        snackbar.add({
          type: 'error',
          title: 'Gagal',
          text: !orderId
            ? 'Tidak bisa memulai pembayaran (Order ID tidak tersedia).'
            : 'Tidak bisa memulai pembayaran (Snap token tidak tersedia).',
        })
        return
      }

      await ensureMidtransReady()

      if (!window.snap?.pay) {
        snackbar.add({
          type: 'error',
          title: 'Gagal',
          text: 'Snap.js tidak tersedia di browser. Coba refresh halaman.',
        })
        return
      }

      window.snap.pay(snapToken, {
        onSuccess: (result: MidtransPayResult) => {
          const oid = encodeURIComponent(result?.order_id || orderId)
          void router.push(`/payment/finish?order_id=${oid}&status=SUCCESS&purpose=debt`)
        },
        onPending: (result: MidtransPayResult) => {
          const oid = encodeURIComponent(result?.order_id || orderId)
          void router.push(`/payment/finish?order_id=${oid}&status=PENDING&purpose=debt`)
        },
        onError: (result: MidtransPayResult) => {
          const oid = encodeURIComponent(result?.order_id || orderId)
          void router.push(`/payment/finish?order_id=${oid}&status=ERROR&purpose=debt`)
        },
        onClose: () => {
          snackbar.add({
            type: 'info',
            title: 'Ditutup',
            text: 'Pembayaran ditutup. Anda bisa coba lagi kapan saja.',
          })
        },
      })
    }
    catch (err: any) {
      const msg = typeof err?.data?.message === 'string'
        ? err.data.message
        : (typeof err?.message === 'string' ? err.message : 'Gagal memulai pembayaran.')

      snackbar.add({ type: 'error', title: 'Gagal', text: msg })
    }
    finally {
      paying.value = false
    }
  }

  return { paying, pay }
}
