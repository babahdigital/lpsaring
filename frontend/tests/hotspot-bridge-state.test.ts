import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  clearPendingHotspotBridge,
  getPendingHotspotBridge,
  rememberPendingHotspotBridge,
} from '../utils/hotspotBridgeState'

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

describe('hotspotBridgeState', () => {
  beforeEach(() => {
    const sessionStorageMock = createStorageMock()
    vi.stubGlobal('window', { sessionStorage: sessionStorageMock })
    vi.stubGlobal('sessionStorage', sessionStorageMock)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('stores a pending bridge return path for the current tab', () => {
    rememberPendingHotspotBridge({
      returnPath: '/login/hotspot-required',
      autoResume: true,
    })

    expect(getPendingHotspotBridge()).toMatchObject({
      returnPath: '/login/hotspot-required',
      autoResume: true,
    })
  })

  it('clears stale pending bridge state after ttl expiry', () => {
    rememberPendingHotspotBridge({
      returnPath: '/login/hotspot-required',
      autoResume: true,
    })

    const raw = sessionStorage.getItem('lpsaring:pending-hotspot-bridge')
    const parsed = JSON.parse(String(raw ?? '{}')) as { returnPath?: string, autoResume?: boolean, at?: number }
    parsed.at = Date.now() - (3 * 60 * 1000)
    sessionStorage.setItem('lpsaring:pending-hotspot-bridge', JSON.stringify(parsed))

    expect(getPendingHotspotBridge()).toBeNull()
  })

  it('removes pending bridge state explicitly', () => {
    rememberPendingHotspotBridge({
      returnPath: '/login/hotspot-required',
      autoResume: true,
    })

    clearPendingHotspotBridge()
    expect(getPendingHotspotBridge()).toBeNull()
  })
})