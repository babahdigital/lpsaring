import { describe, expect, it } from 'vitest'
import { normalizeRedirectTarget, shouldBypassAuthGuard } from '../utils/authGuards'

describe('auth guard helpers', () => {
  it('normalizes invalid redirect values to fallback', () => {
    expect(normalizeRedirectTarget(undefined, '/dashboard')).toBe('/dashboard')
    expect(normalizeRedirectTarget('', '/dashboard')).toBe('/dashboard')
    expect(normalizeRedirectTarget('https://evil.example', '/dashboard')).toBe('/dashboard')
    expect(normalizeRedirectTarget('//evil.example', '/dashboard')).toBe('/dashboard')
  })

  it('keeps valid app-relative redirect value', () => {
    expect(normalizeRedirectTarget('/admin/settings')).toBe('/admin/settings')
  })

  it('detects auth bypass path segments', () => {
    expect(shouldBypassAuthGuard('/admin/dashboard')).toBe(true)
    expect(shouldBypassAuthGuard('/payment/finish')).toBe(true)
    expect(shouldBypassAuthGuard('/dashboard')).toBe(false)
  })
})
