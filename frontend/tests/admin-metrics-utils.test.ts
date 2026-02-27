import { describe, expect, it } from 'vitest'

import { buildReliabilitySummary } from '../utils/adminMetrics'

describe('buildReliabilitySummary', () => {
  it('maps metrics and reliability flags from payload', () => {
    const result = buildReliabilitySummary({
      metrics: {
        'payment.webhook.duplicate': 4,
        'payment.idempotency.redis_unavailable': 2,
        'hotspot.sync.lock.degraded': 1,
        'policy.mismatch.auto_debt_blocked_ip_binding': 3,
        'policy.mismatch.auto_debt_blocked_ip_binding.devices': 5,
      },
      reliability_signals: {
        payment_idempotency_degraded: true,
        hotspot_sync_lock_degraded: false,
        policy_parity_degraded: false,
      },
    })

    expect(result.duplicateWebhookCount).toBe(4)
    expect(result.paymentIdempotencyRedisUnavailableCount).toBe(2)
    expect(result.hotspotSyncLockDegradedCount).toBe(1)
    expect(result.policyParityMismatchCount).toBe(3)
    expect(result.policyParityMismatchDeviceCount).toBe(5)
    expect(result.paymentIdempotencyDegraded).toBe(true)
    expect(result.hotspotSyncLockDegraded).toBe(true)
    expect(result.policyParityDegraded).toBe(true)
  })

  it('returns safe defaults for missing payload', () => {
    const result = buildReliabilitySummary(null)

    expect(result.duplicateWebhookCount).toBe(0)
    expect(result.paymentIdempotencyRedisUnavailableCount).toBe(0)
    expect(result.hotspotSyncLockDegradedCount).toBe(0)
    expect(result.policyParityMismatchCount).toBe(0)
    expect(result.policyParityMismatchDeviceCount).toBe(0)
    expect(result.paymentIdempotencyDegraded).toBe(false)
    expect(result.hotspotSyncLockDegraded).toBe(false)
    expect(result.policyParityDegraded).toBe(false)
  })
})
