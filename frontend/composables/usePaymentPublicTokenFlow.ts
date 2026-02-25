import type { ComputedRef } from 'vue'
import { computed } from 'vue'

export function usePaymentPublicTokenFlow(route: { query: Record<string, unknown> }) {
  const statusTokenFromQuery = computed<string | null>(() => {
    const raw = (route.query.t ?? route.query.token)
    if (Array.isArray(raw))
      return typeof raw[0] === 'string' ? raw[0].trim() || null : null
    return typeof raw === 'string' ? raw.trim() || null : null
  })

  const orderIdFromQuery = computed<string | null>(() => {
    const raw = route.query.order_id
    if (Array.isArray(raw))
      return typeof raw[0] === 'string' ? raw[0].trim() || null : null
    return typeof raw === 'string' ? raw.trim() || null : null
  })

  return {
    statusTokenFromQuery,
    orderIdFromQuery,
  }
}

interface FetchWithFallbackOptions<T> {
  orderId: string
  statusToken: string | null
  apiFetch: (path: string) => Promise<T>
  validate: (data: unknown) => data is T
}

export async function fetchTransactionByOrderIdWithFallback<T>(
  options: FetchWithFallbackOptions<T>,
): Promise<T> {
  const { orderId, statusToken, apiFetch, validate } = options

  try {
    const data = await apiFetch(`/transactions/by-order-id/${orderId}`)
    if (!validate(data))
      throw new Error('Invalid transaction payload from authenticated endpoint.')
    return data
  }
  catch (err: any) {
    const statusCode = err?.response?.status ?? err?.statusCode
    if ((statusCode === 401 || statusCode === 403) && statusToken) {
      const publicPath = `/transactions/public/by-order-id/${encodeURIComponent(orderId)}?t=${encodeURIComponent(statusToken)}`
      const data = await apiFetch(publicPath)
      if (!validate(data))
        throw new Error('Invalid transaction payload from public endpoint.')
      return data
    }

    throw err
  }
}
