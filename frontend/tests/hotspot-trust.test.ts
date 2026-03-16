import { describe, expect, it } from 'vitest'

import {
  extractTrustedHotspotLoginHintFromQuery,
  isTrustedHotspotClientIp,
  resolveHotspotTrustConfig,
  sanitizeHotspotLoginHint,
} from '../utils/hotspotTrust'

const hotspotTrustConfig = resolveHotspotTrustConfig({
  hotspotAllowedClientCidrs: '172.16.2.0/23',
  trustedLoginUrls: ['http://login.home.arpa/login'],
})

describe('hotspotTrust', () => {
  it('accepts hotspot identities only from trusted client CIDRs', () => {
    expect(isTrustedHotspotClientIp('172.16.2.20', hotspotTrustConfig)).toBe(true)
    expect(isTrustedHotspotClientIp('172.16.3.200', hotspotTrustConfig)).toBe(true)
    expect(isTrustedHotspotClientIp('172.16.12.20', hotspotTrustConfig)).toBe(false)
  })

  it('accepts login hints only from trusted hotspot hosts', () => {
    expect(sanitizeHotspotLoginHint('http://login.home.arpa/login', hotspotTrustConfig)).toBe('http://login.home.arpa/login')
    expect(sanitizeHotspotLoginHint('http://wartelpas.net/login', hotspotTrustConfig)).toBe('')
    expect(sanitizeHotspotLoginHint('http://172.16.12.1/login', hotspotTrustConfig)).toBe('')
  })

  it('drops nested redirect login hints from foreign portal hosts', () => {
    expect(extractTrustedHotspotLoginHintFromQuery({
      redirect: '/captive?link_login_only=http%3A%2F%2Fwartelpas.net%2Flogin',
    }, hotspotTrustConfig)).toBe('')
  })
})