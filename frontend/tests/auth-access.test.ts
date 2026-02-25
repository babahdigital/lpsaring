import { describe, expect, it } from 'vitest'
import { resolveAccessStatusFromUser } from '../utils/authAccess'

describe('resolveAccessStatusFromUser', () => {
  it('returns blocked for blocked user', () => {
    expect(resolveAccessStatusFromUser({ is_blocked: true })).toBe('blocked')
  })

  it('returns inactive when user not active or not approved', () => {
    expect(resolveAccessStatusFromUser({ is_active: false, approval_status: 'APPROVED' })).toBe('inactive')
    expect(resolveAccessStatusFromUser({ is_active: true, approval_status: 'PENDING' })).toBe('inactive')
  })

  it('returns expired when quota expiry already passed', () => {
    const now = Date.parse('2026-01-01T00:00:00.000Z')
    expect(resolveAccessStatusFromUser({
      is_active: true,
      approval_status: 'APPROVED',
      total_quota_purchased_mb: 100,
      total_quota_used_mb: 10,
      quota_expiry_date: '2025-12-31T00:00:00.000Z',
    }, now)).toBe('expired')
  })

  it('returns habis when purchased quota is empty or depleted', () => {
    expect(resolveAccessStatusFromUser({
      is_active: true,
      approval_status: 'APPROVED',
      total_quota_purchased_mb: 0,
      total_quota_used_mb: 0,
    })).toBe('habis')

    expect(resolveAccessStatusFromUser({
      is_active: true,
      approval_status: 'APPROVED',
      total_quota_purchased_mb: 100,
      total_quota_used_mb: 100,
    })).toBe('habis')
  })

  it('returns fup when profile indicates fup and quota still available', () => {
    expect(resolveAccessStatusFromUser({
      is_active: true,
      approval_status: 'APPROVED',
      total_quota_purchased_mb: 100,
      total_quota_used_mb: 20,
      mikrotik_profile_name: 'paket_fup_malam',
    })).toBe('fup')
  })

  it('returns ok for admin role', () => {
    expect(resolveAccessStatusFromUser({ role: 'ADMIN', is_blocked: true })).toBe('ok')
  })
})
