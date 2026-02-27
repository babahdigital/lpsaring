import { describe, expect, it } from 'vitest'
import { shouldRedirectToHotspotRequired } from '../utils/hotspotRedirect'

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

  it('returns false when session state is unknown', () => {
    expect(shouldRedirectToHotspotRequired({
      hotspotLoginRequired: true,
      hotspotSessionActive: null,
    })).toBe(false)
  })

  it('returns false when hotspot login is not required', () => {
    expect(shouldRedirectToHotspotRequired({
      hotspotLoginRequired: false,
      hotspotSessionActive: false,
    })).toBe(false)
  })
})
