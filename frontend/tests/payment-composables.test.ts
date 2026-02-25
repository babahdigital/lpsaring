import { computed, ref } from 'vue'
import { describe, expect, it, vi } from 'vitest'

import {
  fetchTransactionByOrderIdWithFallback,
  usePaymentPublicTokenFlow,
} from '../composables/usePaymentPublicTokenFlow'
import { usePaymentInstructions } from '../composables/usePaymentInstructions'
import { usePaymentSnapAction } from '../composables/usePaymentSnapAction'

describe('usePaymentPublicTokenFlow', () => {
  it('reads token and order_id from route query', () => {
    const route = {
      query: {
        t: ' token-123 ',
        order_id: ' order-abc ',
      },
    }

    const { statusTokenFromQuery, orderIdFromQuery } = usePaymentPublicTokenFlow(route)

    expect(statusTokenFromQuery.value).toBe('token-123')
    expect(orderIdFromQuery.value).toBe('order-abc')
  })

  it('supports array query values and empty fallback', () => {
    const route = {
      query: {
        token: [' token-alt '],
        order_id: [''],
      },
    }

    const { statusTokenFromQuery, orderIdFromQuery } = usePaymentPublicTokenFlow(route)

    expect(statusTokenFromQuery.value).toBe('token-alt')
    expect(orderIdFromQuery.value).toBeNull()
  })
})

describe('fetchTransactionByOrderIdWithFallback', () => {
  it('returns authenticated endpoint payload when valid', async () => {
    const apiFetch = vi.fn().mockResolvedValue({ order_id: 'OID-1', status: 'PENDING' })

    const result = await fetchTransactionByOrderIdWithFallback({
      orderId: 'OID-1',
      statusToken: 'tok-1',
      apiFetch,
      validate: (data): data is { order_id: string, status: string } => Boolean((data as any)?.order_id),
    })

    expect(result.order_id).toBe('OID-1')
    expect(apiFetch).toHaveBeenCalledTimes(1)
    expect(apiFetch).toHaveBeenCalledWith('/transactions/by-order-id/OID-1')
  })

  it('falls back to public endpoint on 401 with token', async () => {
    const unauthorizedErr = { response: { status: 401 } }
    const apiFetch = vi
      .fn()
      .mockRejectedValueOnce(unauthorizedErr)
      .mockResolvedValueOnce({ order_id: 'ORDER/1', status: 'PENDING' })

    const result = await fetchTransactionByOrderIdWithFallback({
      orderId: 'ORDER/1',
      statusToken: 'tok+abc',
      apiFetch,
      validate: (data): data is { order_id: string, status: string } => Boolean((data as any)?.order_id),
    })

    expect(result.order_id).toBe('ORDER/1')
    expect(apiFetch).toHaveBeenNthCalledWith(1, '/transactions/by-order-id/ORDER/1')
    expect(apiFetch).toHaveBeenNthCalledWith(
      2,
      '/transactions/public/by-order-id/ORDER%2F1?t=tok%2Babc',
    )
  })

  it('rethrows when unauthorized without token', async () => {
    const unauthorizedErr = { response: { status: 401 } }
    const apiFetch = vi.fn().mockRejectedValue(unauthorizedErr)

    await expect(fetchTransactionByOrderIdWithFallback({
      orderId: 'OID-2',
      statusToken: null,
      apiFetch,
      validate: (_data): _data is { order_id: string } => true,
    })).rejects.toBe(unauthorizedErr)
  })

  it('rethrows public endpoint error when token invalid/expired', async () => {
    const unauthorizedErr = { response: { status: 401 } }
    const invalidTokenErr = { response: { status: 403 }, data: { message: 'invalid token' } }
    const apiFetch = vi
      .fn()
      .mockRejectedValueOnce(unauthorizedErr)
      .mockRejectedValueOnce(invalidTokenErr)

    await expect(fetchTransactionByOrderIdWithFallback({
      orderId: 'OID-3',
      statusToken: 'expired-token',
      apiFetch,
      validate: (_data): _data is { order_id: string } => true,
    })).rejects.toBe(invalidTokenErr)

    expect(apiFetch).toHaveBeenNthCalledWith(1, '/transactions/by-order-id/OID-3')
    expect(apiFetch).toHaveBeenNthCalledWith(
      2,
      '/transactions/public/by-order-id/OID-3?t=expired-token',
    )
  })
})

describe('usePaymentInstructions', () => {
  it('maps VA title by bank name', () => {
    const paymentMethod = ref<string | null>('bank_bca_va')
    const deeplinkAppName = ref<string | null>(null)

    const { vaInstructionTitle } = usePaymentInstructions({
      paymentMethod: computed(() => paymentMethod.value),
      deeplinkAppName: computed(() => deeplinkAppName.value),
    })

    expect(vaInstructionTitle.value).toBe('Cara bayar VA BCA')

    paymentMethod.value = 'unknown_va'
    expect(vaInstructionTitle.value).toBe('Cara bayar Virtual Account')
  })

  it('returns deeplink instructions for supported app', () => {
    const paymentMethod = ref<string | null>(null)
    const deeplinkAppName = ref<string | null>('GoPay')

    const { appDeeplinkInstructions } = usePaymentInstructions({
      paymentMethod: computed(() => paymentMethod.value),
      deeplinkAppName: computed(() => deeplinkAppName.value),
    })

    expect(appDeeplinkInstructions.value.length).toBeGreaterThan(0)
    expect(appDeeplinkInstructions.value[0]).toContain('GoPay')
  })
})

describe('usePaymentSnapAction', () => {
  it('notifies warning when snap token missing', async () => {
    const notify = vi.fn()

    const { openSnapPayment, isPayingWithSnap } = usePaymentSnapAction({
      snapToken: computed(() => null),
      orderId: computed(() => 'ORDER-1'),
      statusToken: computed(() => 'TOK-1'),
      ensureMidtransReady: vi.fn().mockResolvedValue(undefined),
      refreshStatus: vi.fn().mockResolvedValue(undefined),
      cancelTransactionSilently: vi.fn().mockResolvedValue(undefined),
      navigateToStatus: vi.fn().mockResolvedValue(undefined),
      notify,
    })

    await openSnapPayment()

    expect(isPayingWithSnap.value).toBe(false)
    expect(notify).toHaveBeenCalledWith(
      expect.objectContaining({ type: 'warning', title: 'Tidak Tersedia' }),
    )
  })

  it('handles onClose by cancelling transaction and refreshing', async () => {
    const notify = vi.fn()
    const cancelTransactionSilently = vi.fn().mockResolvedValue(undefined)
    const refreshStatus = vi.fn().mockResolvedValue(undefined)
    const ensureMidtransReady = vi.fn().mockResolvedValue(undefined)

    ;(globalThis as any).window = {
      snap: {
        pay: (_token: string, options: { onClose: () => void }) => {
          void options.onClose()
        },
      },
    }

    const { openSnapPayment, isPayingWithSnap } = usePaymentSnapAction({
      snapToken: computed(() => 'SNAP-TOKEN-1'),
      orderId: computed(() => 'ORDER-CLOSE-1'),
      statusToken: computed(() => 'TOK-CLOSE-1'),
      ensureMidtransReady,
      refreshStatus,
      cancelTransactionSilently,
      navigateToStatus: vi.fn().mockResolvedValue(undefined),
      notify,
    })

    await openSnapPayment()
    await Promise.resolve()

    expect(ensureMidtransReady).toHaveBeenCalledTimes(1)
    expect(cancelTransactionSilently).toHaveBeenCalledWith('ORDER-CLOSE-1')
    expect(refreshStatus).toHaveBeenCalledTimes(1)
    expect(notify).toHaveBeenCalledWith(expect.objectContaining({ type: 'info', title: 'Dibatalkan' }))
    expect(isPayingWithSnap.value).toBe(false)
  })

  it('handles onSuccess by navigating to status and refreshing', async () => {
    const notify = vi.fn()
    const refreshStatus = vi.fn().mockResolvedValue(undefined)
    const ensureMidtransReady = vi.fn().mockResolvedValue(undefined)
    const navigateToStatus = vi.fn().mockResolvedValue(undefined)

    ;(globalThis as any).window = {
      snap: {
        pay: (_token: string, options: { onSuccess: (result: { order_id: string }) => void }) => {
          void options.onSuccess({ order_id: 'ORDER-SUCCESS-1' })
        },
      },
    }

    const { openSnapPayment, isPayingWithSnap } = usePaymentSnapAction({
      snapToken: computed(() => 'SNAP-TOKEN-OK'),
      orderId: computed(() => 'ORDER-SUCCESS-1'),
      statusToken: computed(() => 'TOK-SUCCESS-1'),
      ensureMidtransReady,
      refreshStatus,
      cancelTransactionSilently: vi.fn().mockResolvedValue(undefined),
      navigateToStatus,
      notify,
    })

    await openSnapPayment()
    await Promise.resolve()

    expect(ensureMidtransReady).toHaveBeenCalledTimes(1)
    expect(navigateToStatus).toHaveBeenCalledWith('ORDER-SUCCESS-1', 'TOK-SUCCESS-1')
    expect(refreshStatus).toHaveBeenCalledTimes(1)
    expect(isPayingWithSnap.value).toBe(false)
  })
})
