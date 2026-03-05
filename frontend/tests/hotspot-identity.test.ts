import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  getStoredHotspotIdentity,
  rememberHotspotIdentity,
  resolveHotspotIdentity,
} from '../utils/hotspotIdentity'

function createSessionStorageMock(initial: Record<string, string> = {}) {
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
    vi.stubGlobal('sessionStorage', createSessionStorageMock())
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('uses query identity first and normalizes MAC', () => {
    const identity = resolveHotspotIdentity({
      client_ip: '172.16.2.10',
      client_mac: 'aa-bb-cc-dd-ee-ff',
    })

    expect(identity).toEqual({
      clientIp: '172.16.2.10',
      clientMac: 'AA:BB:CC:DD:EE:FF',
    })
  })

  it('falls back to referrer query when route query is missing', () => {
    vi.stubGlobal('window', {
      document: {
        referrer: 'https://portal.local/captive?client_ip=172.16.2.20&client_mac=aa%3Abb%3Acc%3Add%3Aee%3A11',
      },
    })

    const identity = resolveHotspotIdentity({})
    expect(identity).toEqual({
      clientIp: '172.16.2.20',
      clientMac: 'AA:BB:CC:DD:EE:11',
    })
  })

  it('falls back to stored identity when query and referrer are empty', () => {
    rememberHotspotIdentity({
      clientIp: '172.16.2.30',
      clientMac: 'aa:bb:cc:dd:ee:22',
    })

    const identity = resolveHotspotIdentity({})
    expect(identity).toEqual({
      clientIp: '172.16.2.30',
      clientMac: 'AA:BB:CC:DD:EE:22',
    })
  })

  it('drops stale stored identity after ttl', () => {
    rememberHotspotIdentity({
      clientIp: '172.16.2.40',
      clientMac: 'aa:bb:cc:dd:ee:33',
    })

    const raw = sessionStorage.getItem('lpsaring:last-hotspot-identity')
    const parsed = JSON.parse(String(raw ?? '{}')) as { clientIp?: string, clientMac?: string, at?: number }
    parsed.at = Date.now() - (11 * 60 * 1000)
    sessionStorage.setItem('lpsaring:last-hotspot-identity', JSON.stringify(parsed))

    expect(getStoredHotspotIdentity()).toEqual({ clientIp: '', clientMac: '' })
  })
})
