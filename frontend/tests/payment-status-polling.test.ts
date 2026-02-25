// @vitest-environment jsdom

import { computed, defineComponent, nextTick, ref } from 'vue'
import { mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { usePaymentStatusPolling } from '../composables/usePaymentStatusPolling'
import type { TransactionStatusContract } from '../types/api/contracts'

describe('usePaymentStatusPolling', () => {
  afterEach(() => {
    vi.useRealTimers()
  })

  it('starts polling on mount and stops when status becomes final', async () => {
    vi.useFakeTimers()

    const finalStatus = ref<TransactionStatusContract>('PENDING')
    const refreshStatus = vi.fn().mockResolvedValue(undefined)
    let api!: ReturnType<typeof usePaymentStatusPolling>

    const Host = defineComponent({
      setup() {
        api = usePaymentStatusPolling({
          finalStatus: computed(() => finalStatus.value),
          refreshStatus,
          intervalMs: 100,
        })
        return {}
      },
      template: '<div />',
    })

    const wrapper = mount(Host)

    expect(api.isPolling.value).toBe(true)

    vi.advanceTimersByTime(250)
    expect(refreshStatus).toHaveBeenCalledTimes(2)

    finalStatus.value = 'SUCCESS'
    await nextTick()

    expect(api.isPolling.value).toBe(false)

    vi.advanceTimersByTime(250)
    expect(refreshStatus).toHaveBeenCalledTimes(2)

    wrapper.unmount()
    expect(api.isPolling.value).toBe(false)
  })

  it('does not start polling when initial status is final', () => {
    vi.useFakeTimers()

    const finalStatus = ref<TransactionStatusContract>('FAILED')
    const refreshStatus = vi.fn().mockResolvedValue(undefined)
    let api!: ReturnType<typeof usePaymentStatusPolling>

    const Host = defineComponent({
      setup() {
        api = usePaymentStatusPolling({
          finalStatus: computed(() => finalStatus.value),
          refreshStatus,
          intervalMs: 100,
        })
        return {}
      },
      template: '<div />',
    })

    const wrapper = mount(Host)

    expect(api.isPolling.value).toBe(false)

    vi.advanceTimersByTime(300)
    expect(refreshStatus).not.toHaveBeenCalled()

    wrapper.unmount()
  })
})
