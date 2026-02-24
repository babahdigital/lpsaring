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
  payment_method?: string | null
  provider_mode?: 'snap' | 'core_api'
  status_token?: string | null
  status_url?: string | null
}

type PaymentMethod = 'qris' | 'gopay' | 'shopeepay' | 'va'

type PayOptions = {
  manualDebtId?: string
  payment_method?: PaymentMethod
  va_bank?: string
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

  async function pay(arg?: string | PayOptions) {
    if (paying.value)
      return

    paying.value = true
    try {
      const options: PayOptions = typeof arg === 'string'
        ? { manualDebtId: arg }
        : (arg ?? {})

      const requestedMethod = options.payment_method

      const body: Record<string, any> = {}
      if (typeof options.manualDebtId === 'string' && options.manualDebtId.trim() !== '')
        body.manual_debt_id = options.manualDebtId
      if (typeof options.payment_method === 'string' && options.payment_method.trim() !== '')
        body.payment_method = options.payment_method
      if (options.payment_method === 'va' && typeof options.va_bank === 'string' && options.va_bank.trim() !== '')
        body.va_bank = options.va_bank

      const response = await $api<DebtInitiateResponse>('/transactions/debt/initiate', {
        method: 'POST',
        body: Object.keys(body).length > 0 ? body : undefined,
      })

      const orderId = typeof response?.order_id === 'string' && response.order_id.trim() !== ''
        ? response.order_id
        : (typeof response?.midtrans_order_id === 'string' ? response.midtrans_order_id : '')
      const snapToken = typeof response?.snap_token === 'string' && response.snap_token.trim() !== ''
        ? response.snap_token
        : null

      const statusToken = typeof response?.status_token === 'string' && response.status_token.trim() !== ''
        ? response.status_token.trim()
        : null

      const provider = (response?.provider_mode ?? 'snap') === 'core_api' ? 'core_api' : 'snap'
      const redirectUrl = typeof response?.redirect_url === 'string' && response.redirect_url.trim() !== ''
        ? response.redirect_url.trim()
        : null

      const responsePm = typeof response?.payment_method === 'string' && response.payment_method.trim() !== ''
        ? response.payment_method.trim().toLowerCase()
        : null

      if (!orderId) {
        snackbar.add({ type: 'error', title: 'Gagal', text: 'Tidak bisa memulai pembayaran (Order ID tidak tersedia).' })
        return
      }

      if (!snapToken) {
        const wantsDeeplink = requestedMethod === 'gopay' || requestedMethod === 'shopeepay'
        const isDeeplinkPm = responsePm === 'gopay' || responsePm === 'shopeepay'

        // Core API mode: untuk GoPay/ShopeePay redirect langsung jika ada deeplink.
        if (provider === 'core_api' && redirectUrl && (wantsDeeplink || isDeeplinkPm)) {
          window.location.href = redirectUrl
          return
        }

        // Fallback: show instructions + polling.
        void router.push(`/payment/status?order_id=${encodeURIComponent(orderId)}&purpose=debt${statusToken ? `&t=${encodeURIComponent(statusToken)}` : ''}`)
        return
      }

      await ensureMidtransReady()
      if (!window.snap?.pay) {
        snackbar.add({ type: 'error', title: 'Gagal', text: 'Snap.js tidak tersedia di browser. Coba refresh halaman.' })
        return
      }

      window.snap.pay(snapToken, {
        onSuccess: (result: MidtransPayResult) => {
          const oid = encodeURIComponent(result?.order_id || orderId)
          void router.push(`/payment/status?order_id=${oid}&status=SUCCESS&purpose=debt${statusToken ? `&t=${encodeURIComponent(statusToken)}` : ''}`)
        },
        onPending: (result: MidtransPayResult) => {
          const oid = encodeURIComponent(result?.order_id || orderId)
          void router.push(`/payment/status?order_id=${oid}&status=PENDING&purpose=debt${statusToken ? `&t=${encodeURIComponent(statusToken)}` : ''}`)
        },
        onError: (result: MidtransPayResult) => {
          const oid = encodeURIComponent(result?.order_id || orderId)
          void router.push(`/payment/status?order_id=${oid}&status=ERROR&purpose=debt${statusToken ? `&t=${encodeURIComponent(statusToken)}` : ''}`)
        },
        onClose: () => {
          try {
            const oid = (orderId || '').toString()
            if (oid) {
              if (statusToken) {
                void $api(`/transactions/public/${encodeURIComponent(oid)}/cancel?t=${encodeURIComponent(statusToken)}`, { method: 'POST' }).catch(() => {})
              }
              else {
                void $api(`/transactions/${encodeURIComponent(oid)}/cancel`, { method: 'POST' }).catch(() => {})
              }
            }
          }
          catch {
            // ignore
          }
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
