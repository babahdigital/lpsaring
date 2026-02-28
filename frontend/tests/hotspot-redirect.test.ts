import { describe, expect, it } from 'vitest'
import { resolvePostHotspotRecheckRoute, shouldRedirectToHotspotRequired } from '../utils/hotspotRedirect'

describe('shouldRedirectToHotspotRequired', () => {
  it('returns true when hotspot login required and session explicitly inactive', () => {
    expect(shouldRedirectToHotspotRequired({
      hotspotLoginRequired: true,
      hotspotSessionActive: false,
    })).toBe(true)
  })

  it('returns false when session is active', () => {
    expect(shouldRedirectToHotspotRequired({
      hotspotLoginRequired: true,
      hotspotSessionActive: true,
    })).toBe(false)
  })

  it('returns true when session state is unknown', () => {
    expect(shouldRedirectToHotspotRequired({
      hotspotLoginRequired: true,
      hotspotSessionActive: null,
    })).toBe(true)
  })

  it('returns false when hotspot login is not required', () => {
    expect(shouldRedirectToHotspotRequired({
      hotspotLoginRequired: false,
      hotspotSessionActive: false,
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
