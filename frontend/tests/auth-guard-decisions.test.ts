import { describe, expect, it } from 'vitest'

import {
  getSafeRedirectTarget,
  resolveExpiredOrHabisRedirect,
  resolveGuestProtectedRedirect,
  resolveLoggedInRoleRedirect,
} from '../utils/authGuardDecisions'

describe('auth guard decisions', () => {
  describe('getSafeRedirectTarget', () => {
    it('blocks invalid and disallowed redirect targets', () => {
      expect(getSafeRedirectTarget(undefined, false)).toBeNull()
      expect(getSafeRedirectTarget('https://evil.test', false)).toBeNull()
      expect(getSafeRedirectTarget('/login', false)).toBeNull()
      expect(getSafeRedirectTarget('/admin/login', true)).toBeNull()
      expect(getSafeRedirectTarget('/admin/settings', false)).toBeNull()
    })

    it('keeps allowed internal redirect targets', () => {
      expect(getSafeRedirectTarget('/dashboard', false)).toBe('/dashboard')
      expect(getSafeRedirectTarget('/admin/settings', true)).toBe('/admin/settings')
    })
  })

  describe('resolveGuestProtectedRedirect', () => {
    it('redirects guest to admin login for admin protected path', () => {
      expect(resolveGuestProtectedRedirect('/admin/dashboard', '/admin/dashboard')).toBe('/admin')
    })

    it('redirects guest to login with original fullPath for user protected path', () => {
      expect(resolveGuestProtectedRedirect('/dashboard', '/dashboard?tab=usage')).toBe('/login?redirect=%2Fdashboard%3Ftab%3Dusage')
    })

    it('does not redirect guest routes', () => {
      expect(resolveGuestProtectedRedirect('/login', '/login')).toBeNull()
      expect(resolveGuestProtectedRedirect('/admin', '/admin')).toBeNull()
    })
  })

  describe('resolveLoggedInRoleRedirect', () => {
    it('redirects non-admin away from admin paths', () => {
      expect(resolveLoggedInRoleRedirect('/admin/dashboard', false, false)).toBe('/dashboard')
    })

    it('redirects admin away from non-admin paths except shared profile', () => {
      expect(resolveLoggedInRoleRedirect('/dashboard', true, false)).toBe('/admin/dashboard')
      expect(resolveLoggedInRoleRedirect('/akun', true, false)).toBeNull()
    })

    it('applies komandan specific route rules', () => {
      expect(resolveLoggedInRoleRedirect('/beli', false, true)).toBe('/requests')
      expect(resolveLoggedInRoleRedirect('/requests', false, false)).toBe('/dashboard')
    })
  })

  describe('resolveExpiredOrHabisRedirect', () => {
    it('allows payment status and finish paths for expired/habis users', () => {
      expect(resolveExpiredOrHabisRedirect('/payment/status', 'expired', false)).toBeNull()
      expect(resolveExpiredOrHabisRedirect('/payment/finish', 'habis', false)).toBeNull()
    })

    it('redirects expired/habis users to destination when path not allowed', () => {
      expect(resolveExpiredOrHabisRedirect('/dashboard', 'expired', false)).toBe('/beli')
      expect(resolveExpiredOrHabisRedirect('/dashboard', 'habis', true)).toBe('/requests')
    })

    it('does nothing for non expired/habis status', () => {
      expect(resolveExpiredOrHabisRedirect('/dashboard', 'ok', false)).toBeNull()
      expect(resolveExpiredOrHabisRedirect('/dashboard', 'blocked', false)).toBeNull()
    })
  })
})
