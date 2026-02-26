import type { Ref } from 'vue'
import { computed, onMounted, ref } from 'vue'
import type { TransactionDetailResponseContract, TransactionStatusContract } from '~/types/api/contracts'
import { fetchTransactionByOrderIdWithFallback, usePaymentPublicTokenFlow } from '~/composables/usePaymentPublicTokenFlow'

interface RouteLike {
  query: Record<string, unknown>
}

interface UsePaymentStatusDataOptions {
  route: RouteLike
  apiFetch: <T>(path: string, options?: Record<string, unknown>) => Promise<T>
}

export function usePaymentStatusData(options: UsePaymentStatusDataOptions) {
  const { route, apiFetch } = options

  const transactionDetails = ref<TransactionDetailResponseContract | null>(null)
  const isLoading = ref(true)
  const isRefreshing = ref(false)
  const fetchError = ref<string | null>(null)
  const errorMessageFromQuery = ref<string | null>(
    typeof route.query.msg === 'string' ? decodeURIComponent(route.query.msg) : null,
  )

  const { statusTokenFromQuery, orderIdFromQuery } = usePaymentPublicTokenFlow(route)

  const isPublicView = computed(() => {
    if (statusTokenFromQuery.value != null)
      return true
    return transactionDetails.value?.user?.id === ''
  })

  const orderId = computed(() => {
    if (transactionDetails.value?.midtrans_order_id)
      return transactionDetails.value.midtrans_order_id
    return orderIdFromQuery.value
  })

  const isDebtSettlement = computed(() => {
    const oid = orderId.value ?? ''
    if (transactionDetails.value?.purpose === 'debt')
      return true
    if (oid.startsWith('DEBT-'))
      return true
    return route.query.purpose === 'debt'
  })

  function isValidTransactionDetails(data: unknown): data is TransactionDetailResponseContract {
    if (data == null || typeof data !== 'object')
      return false

    const obj = data as Record<string, unknown>
    return typeof obj.midtrans_order_id === 'string' && typeof obj.status === 'string'
  }

  async function fetchTransactionDetails(orderIdValue: string, options?: { showLoading?: boolean; silent?: boolean }) {
    const showLoading = options?.showLoading !== false
    const silent = options?.silent === true

    if (showLoading)
      isLoading.value = true
    else
      isRefreshing.value = true

    if (!silent)
      fetchError.value = null

    try {
      const response = await fetchTransactionByOrderIdWithFallback<TransactionDetailResponseContract>({
        orderId: orderIdValue,
        statusToken: statusTokenFromQuery.value,
        apiFetch: path => apiFetch<TransactionDetailResponseContract>(path),
        validate: isValidTransactionDetails,
      })
      transactionDetails.value = response
    }
    catch (err: any) {
      if (silent)
        return
      const status = err.response?.status ?? err.statusCode ?? 'N/A'
      const description = err.data?.message ?? 'Terjadi kesalahan.'
      if (status === 404)
        fetchError.value = `Transaksi dengan Order ID '${orderIdValue}' tidak ditemukan.`
      else
        fetchError.value = `Gagal memuat detail transaksi (Kode: ${status}). ${description}`
      transactionDetails.value = null
    }
    finally {
      isLoading.value = false
      isRefreshing.value = false
    }
  }

  onMounted(() => {
    const raw = route.query.order_id
    const orderIdFromQueryValue = Array.isArray(raw) ? raw[0] : raw
    const statusFromQuery = typeof route.query.status === 'string' ? route.query.status.toUpperCase() : undefined

    if (typeof orderIdFromQueryValue === 'string' && orderIdFromQueryValue.trim() !== '') {
      const cleaned = orderIdFromQueryValue.trim()
      void fetchTransactionDetails(cleaned)
    }
    else if (statusFromQuery === 'ERROR' && errorMessageFromQuery.value != null) {
      fetchError.value = `Pembayaran Gagal: ${errorMessageFromQuery.value}`
      isLoading.value = false
    }
    else {
      fetchError.value = 'Order ID tidak valid atau tidak ditemukan.'
      isLoading.value = false
    }
  })

  const finalStatus = computed((): TransactionStatusContract => {
    const statusFromQuery = typeof route.query.status === 'string' ? route.query.status.toUpperCase() as TransactionStatusContract : undefined
    if (transactionDetails.value?.status != null && transactionDetails.value.status !== 'UNKNOWN')
      return transactionDetails.value.status
    if (statusFromQuery != null && ['SUCCESS', 'PENDING', 'FAILED', 'EXPIRED', 'CANCELLED', 'ERROR'].includes(statusFromQuery))
      return statusFromQuery
    return transactionDetails.value?.status ?? 'UNKNOWN'
  })

  async function refreshStatus() {
    if (orderId.value)
      await fetchTransactionDetails(orderId.value, { showLoading: false })
  }

  async function cancelTransactionSilently(orderIdToCancel: string) {
    try {
      if (statusTokenFromQuery.value) {
        const url = `/transactions/public/${encodeURIComponent(orderIdToCancel)}/cancel?t=${encodeURIComponent(statusTokenFromQuery.value)}`
        await apiFetch(url, { method: 'POST' })
      }
      else {
        await apiFetch(`/transactions/${encodeURIComponent(orderIdToCancel)}/cancel`, { method: 'POST' })
      }
    }
    catch {
    }
  }

  return {
    transactionDetails,
    isLoading,
    isRefreshing,
    fetchError,
    errorMessageFromQuery,
    statusTokenFromQuery,
    orderIdFromQuery,
    isPublicView,
    orderId,
    isDebtSettlement,
    finalStatus,
    fetchTransactionDetails,
    refreshStatus,
    cancelTransactionSilently,
  }
}
