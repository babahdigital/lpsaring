import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  getStoredHotspotIdentity,
  rememberHotspotIdentity,
  resolveHotspotIdentity,
} from '../utils/hotspotIdentity'
import { resolveHotspotTrustConfig } from '../utils/hotspotTrust'

const hotspotTrustConfig = resolveHotspotTrustConfig({
  hotspotAllowedClientCidrs: '172.16.2.0/23',
  trustedLoginUrls: ['http://login.home.arpa/login'],
})

function createStorageMock(initial: Record<string, string> = {}) {
  const storage = new Map<string, string>(Object.entries(initial))
  return {
    getItem: (key: string) => storage.get(key) ?? null,
    setItem: (key: string, value: string) => {
      storage.set(key, value)
    },
    removeItem: (key: string) => {
      storage.delete(key)
    },
    clear: () => {
      storage.clear()
    },
  }
}

describe('hotspotIdentity', () => {
  beforeEach(() => {
    vi.stubGlobal('window', {
      document: {
        referrer: '',
      },
    })
    vi.stubGlobal('localStorage', createStorageMock())
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('uses query identity first and normalizes MAC', () => {
    const identity = resolveHotspotIdentity({
      client_ip: '172.16.2.10',
      client_mac: 'aa-bb-cc-dd-ee-ff',
    }, hotspotTrustConfig)

    expect(identity).toEqual({
      clientIp: '172.16.2.10',
      clientMac: 'AA:BB:CC:DD:EE:FF',
    })
  })

  it('falls back to referrer query when route query is missing', () => {
    vi.stubGlobal('window', {
      document: {
        referrer: 'http://login.home.arpa/captive?client_ip=172.16.2.20&client_mac=aa%3Abb%3Acc%3Add%3Aee%3A11',
      },
    })

    const identity = resolveHotspotIdentity({}, hotspotTrustConfig)
    expect(identity).toEqual({
      clientIp: '172.16.2.20',
      clientMac: 'AA:BB:CC:DD:EE:11',
    })
  })

  it('falls back to stored identity when query and referrer are empty', () => {
    rememberHotspotIdentity({
      clientIp: '172.16.2.30',
      clientMac: 'aa:bb:cc:dd:ee:22',
    }, hotspotTrustConfig)

    const identity = resolveHotspotIdentity({}, hotspotTrustConfig)
    expect(identity).toEqual({
      clientIp: '172.16.2.30',
      clientMac: 'AA:BB:CC:DD:EE:22',
    })
  })

  it('merges partial query with stored identity for bind flows', () => {
    rememberHotspotIdentity({
      clientIp: '172.16.2.31',
      clientMac: 'aa:bb:cc:dd:ee:31',
    }, hotspotTrustConfig)

    const identity = resolveHotspotIdentity({
      client_mac: 'aa-bb-cc-dd-ee-99',
    }, hotspotTrustConfig)

    expect(identity).toEqual({
      clientIp: '172.16.2.31',
      clientMac: 'AA:BB:CC:DD:EE:99',
    })
  })

  it('drops stale stored identity after ttl', () => {
    rememberHotspotIdentity({
      clientIp: '172.16.2.40',
      clientMac: 'aa:bb:cc:dd:ee:33',
    }, hotspotTrustConfig)

    const raw = localStorage.getItem('lpsaring:last-hotspot-identity')
    const parsed = JSON.parse(String(raw ?? '{}')) as { clientIp?: string, clientMac?: string, at?: number }
    parsed.at = Date.now() - (11 * 60 * 1000)
    localStorage.setItem('lpsaring:last-hotspot-identity', JSON.stringify(parsed))

    expect(getStoredHotspotIdentity(hotspotTrustConfig)).toEqual({ clientIp: '', clientMac: '' })
  })

  it('drops identity from foreign hotspot subnet', () => {
    const identity = resolveHotspotIdentity({
      client_ip: '172.16.12.10',
      client_mac: 'aa-bb-cc-dd-ee-44',
    }, hotspotTrustConfig)

    expect(identity).toEqual({ clientIp: '', clientMac: '' })
  })

  it('ignores referrer context from untrusted portal hosts', () => {
    vi.stubGlobal('window', {
      document: {
        referrer: 'https://wartelpas.net/captive?client_ip=172.16.2.21&client_mac=aa%3Abb%3Acc%3Add%3Aee%3A45',
      },
    })

    const identity = resolveHotspotIdentity({}, hotspotTrustConfig)
    expect(identity).toEqual({ clientIp: '', clientMac: '' })
  })
})
