export type AccessStatus = 'ok' | 'blocked' | 'inactive' | 'expired' | 'habis' | 'fup'

interface UserLike {
  role?: string | null
  is_blocked?: boolean | null
  is_active?: boolean | null
  approval_status?: string | null
  is_unlimited_user?: boolean | null
  total_quota_purchased_mb?: number | null
  total_quota_used_mb?: number | null
  quota_expiry_date?: string | null
  mikrotik_profile_name?: string | null
}

export function resolveAccessStatusFromUser(inputUser: UserLike | null, nowMs = Date.now()): AccessStatus {
  if (inputUser == null)
    return 'ok'

  if (inputUser.role === 'ADMIN' || inputUser.role === 'SUPER_ADMIN')
    return 'ok'

  if (inputUser.is_blocked === true)
    return 'blocked'

  if (inputUser.is_active !== true || inputUser.approval_status !== 'APPROVED')
    return 'inactive'

  if (inputUser.is_unlimited_user === true)
    return 'ok'

  const total = inputUser.total_quota_purchased_mb ?? 0
  const used = inputUser.total_quota_used_mb ?? 0
  const remaining = total - used
  const expiryDate = inputUser.quota_expiry_date ? new Date(inputUser.quota_expiry_date) : null
  const isExpired = Boolean(expiryDate && expiryDate.getTime() < nowMs)
  const profileName = (inputUser.mikrotik_profile_name || '').toLowerCase()

  if (isExpired)
    return 'expired'
  if (total <= 0)
    return 'habis'
  if (total > 0 && remaining <= 0)
    return 'habis'
  if (profileName.includes('fup'))
    return 'fup'

  return 'ok'
}
