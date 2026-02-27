import type { AccessStatus } from '~/types/accessStatus'

interface UserLike {
  role?: string | null
  is_blocked?: boolean | null
  is_active?: boolean | null
  approval_status?: string | null
  is_unlimited_user?: boolean | null
  total_quota_purchased_mb?: number | null
  total_quota_used_mb?: number | null
  quota_expiry_date?: string | null
}

const QUOTA_FUP_THRESHOLD_MB = 3072

export function resolveAccessStatusFromUser(inputUser: UserLike | null, nowMs = Date.now()): AccessStatus {
  if (inputUser == null)
    return 'inactive'

  if (inputUser.role === 'ADMIN' || inputUser.role === 'SUPER_ADMIN')
    return 'ok'

  if (inputUser.is_blocked === true)
    return 'blocked'

  if (inputUser.is_active !== true || inputUser.approval_status !== 'APPROVED')
    return 'inactive'

  const total = inputUser.total_quota_purchased_mb ?? 0
  const used = inputUser.total_quota_used_mb ?? 0
  const remaining = total - used
  const expiryDate = inputUser.quota_expiry_date ? new Date(inputUser.quota_expiry_date) : null
  const isExpired = Boolean(expiryDate && expiryDate.getTime() < nowMs)

  if (isExpired)
    return 'expired'
  if (inputUser.is_unlimited_user === true)
    return 'ok'
  if (total <= 0)
    return 'habis'
  if (total > 0 && remaining <= 0)
    return 'habis'
  if (total > QUOTA_FUP_THRESHOLD_MB && remaining <= QUOTA_FUP_THRESHOLD_MB)
    return 'fup'

  return 'ok'
}
