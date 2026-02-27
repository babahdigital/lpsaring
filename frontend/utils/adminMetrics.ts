export interface AdminMetricsPayload {
  metrics?: Record<string, number | null | undefined>
  reliability_signals?: {
    payment_idempotency_degraded?: boolean
    hotspot_sync_lock_degraded?: boolean
    policy_parity_degraded?: boolean
  }
}

export interface ReliabilitySummary {
  duplicateWebhookCount: number
  paymentIdempotencyRedisUnavailableCount: number
  hotspotSyncLockDegradedCount: number
  policyParityMismatchCount: number
  policyParityMismatchDeviceCount: number
  paymentIdempotencyDegraded: boolean
  hotspotSyncLockDegraded: boolean
  policyParityDegraded: boolean
}

function toSafeInt(value: unknown): number {
  if (typeof value === 'number' && Number.isFinite(value))
    return Math.max(0, Math.trunc(value))

  return 0
}

export function buildReliabilitySummary(payload: AdminMetricsPayload | null | undefined): ReliabilitySummary {
  const metrics = payload?.metrics ?? {}
  const duplicateWebhookCount = toSafeInt(metrics['payment.webhook.duplicate'])
  const paymentIdempotencyRedisUnavailableCount = toSafeInt(metrics['payment.idempotency.redis_unavailable'])
  const hotspotSyncLockDegradedCount = toSafeInt(metrics['hotspot.sync.lock.degraded'])
  const policyParityMismatchCount = toSafeInt(metrics['policy.mismatch.auto_debt_blocked_ip_binding'])
  const policyParityMismatchDeviceCount = toSafeInt(metrics['policy.mismatch.auto_debt_blocked_ip_binding.devices'])

  const paymentIdempotencyDegraded = Boolean(payload?.reliability_signals?.payment_idempotency_degraded)
    || paymentIdempotencyRedisUnavailableCount > 0

  const hotspotSyncLockDegraded = Boolean(payload?.reliability_signals?.hotspot_sync_lock_degraded)
    || hotspotSyncLockDegradedCount > 0

  const policyParityDegraded = Boolean(payload?.reliability_signals?.policy_parity_degraded)
    || policyParityMismatchCount > 0

  return {
    duplicateWebhookCount,
    paymentIdempotencyRedisUnavailableCount,
    hotspotSyncLockDegradedCount,
    policyParityMismatchCount,
    policyParityMismatchDeviceCount,
    paymentIdempotencyDegraded,
    hotspotSyncLockDegraded,
    policyParityDegraded,
  }
}
