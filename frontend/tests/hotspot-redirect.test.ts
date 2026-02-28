import { describe, expect, it } from 'vitest'
import { resolvePostHotspotRecheckRoute, shouldRedirectToHotspotRequired } from '../utils/hotspotRedirect'

describe('shouldRedirectToHotspotRequired', () => {
  it('returns true when hotspot login required and binding explicitly inactive', () => {
    expect(shouldRedirectToHotspotRequired({
      hotspotLoginRequired: true,
      hotspotBindingActive: false,
    })).toBe(true)
  })

  it('returns false when binding is active', () => {
    expect(shouldRedirectToHotspotRequired({
      hotspotLoginRequired: true,
      hotspotBindingActive: true,
    })).toBe(false)
  })

  it('returns true when binding state is unknown', () => {
    expect(shouldRedirectToHotspotRequired({
      hotspotLoginRequired: true,
      hotspotBindingActive: null,
    })).toBe(true)
  })

  it('returns false when hotspot login is not required', () => {
    expect(shouldRedirectToHotspotRequired({
      hotspotLoginRequired: false,
      hotspotBindingActive: false,
    })).toBe(false)
  })

  it('routes blocked status to blocked policy page after realtime refresh', () => {
    expect(resolvePostHotspotRecheckRoute('blocked')).toBe('/policy/blocked')
  })

  it('routes fup status to fup policy page after realtime refresh', () => {
    expect(resolvePostHotspotRecheckRoute('fup')).toBe('/policy/fup')
  })

  it('routes ok status to dashboard after realtime refresh', () => {
    expect(resolvePostHotspotRecheckRoute('ok')).toBe('/dashboard')
  })
})
