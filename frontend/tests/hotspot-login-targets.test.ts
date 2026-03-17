import { describe, expect, it } from 'vitest'

import { normalizeHotspotBridgeUrl, normalizeHotspotLoginUrl, resolveHotspotBridgeTarget } from '../utils/hotspotLoginTargets'

describe('hotspot login targets', () => {
  it('prefers the configured probe for bridge flows when the router hint is a local captive host', () => {
    expect(resolveHotspotBridgeTarget('http://login.home.arpa/login', 'http://neverssl.com/')).toBe('http://neverssl.com/')
    expect(resolveHotspotBridgeTarget('http://login.home.arpa', 'http://neverssl.com/')).toBe('http://neverssl.com/')
    expect(resolveHotspotBridgeTarget('http://192.168.88.1/login', 'http://neverssl.com/')).toBe('http://neverssl.com/')
  })

  it('falls back to the router portal root when no configured probe exists', () => {
    expect(resolveHotspotBridgeTarget('http://login.home.arpa/login', '')).toBe('http://login.home.arpa/')
  })

  it('falls back to the configured probe target and then to neverssl', () => {
    expect(resolveHotspotBridgeTarget('', 'http://example.test/probe')).toBe('http://example.test/probe')
    expect(resolveHotspotBridgeTarget('', '')).toBe('http://neverssl.com/')
  })

  it('keeps public bridge targets on the trusted login target when it is not a local captive host', () => {
    expect(resolveHotspotBridgeTarget('https://portal.example/login', 'http://neverssl.com/')).toBe('https://portal.example/login')
  })

  it('forces local hotspot targets back to http when given as https', () => {
    expect(normalizeHotspotLoginUrl('https://login.home.arpa/login')).toBe('http://login.home.arpa/login')
    expect(normalizeHotspotLoginUrl('https://192.168.88.1/login')).toBe('http://192.168.88.1/login')
  })

  it('normalizes bare local router hosts to the login path', () => {
    expect(normalizeHotspotLoginUrl('http://login.home.arpa')).toBe('http://login.home.arpa/login')
    expect(normalizeHotspotLoginUrl('login.home.arpa')).toBe('http://login.home.arpa/login')
    expect(normalizeHotspotLoginUrl('http://192.168.88.1')).toBe('http://192.168.88.1/login')
  })

  it('keeps bridge flows on the router portal root', () => {
    expect(normalizeHotspotBridgeUrl('http://login.home.arpa/login')).toBe('http://login.home.arpa/')
    expect(normalizeHotspotBridgeUrl('https://192.168.88.1/login')).toBe('http://192.168.88.1/')
    expect(normalizeHotspotBridgeUrl('http://example.test/probe')).toBe('http://example.test/probe')
  })
})
