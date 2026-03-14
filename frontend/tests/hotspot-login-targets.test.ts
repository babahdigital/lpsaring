import { describe, expect, it } from 'vitest'

import { normalizeHotspotLoginUrl, resolveHotspotBridgeTarget } from '../utils/hotspotLoginTargets'

describe('hotspot login targets', () => {
  it('prefers the router login URL over the generic probe target', () => {
    expect(resolveHotspotBridgeTarget('http://login.home.arpa/login', 'http://neverssl.com/')).toBe('http://login.home.arpa/login')
  })

  it('falls back to the configured probe target and then to neverssl', () => {
    expect(resolveHotspotBridgeTarget('', 'http://example.test/probe')).toBe('http://example.test/probe')
    expect(resolveHotspotBridgeTarget('', '')).toBe('http://neverssl.com/')
  })

  it('forces local hotspot targets back to http when given as https', () => {
    expect(normalizeHotspotLoginUrl('https://login.home.arpa/login')).toBe('http://login.home.arpa/login')
    expect(normalizeHotspotLoginUrl('https://192.168.88.1/login')).toBe('http://192.168.88.1/login')
  })
})
