import { describe, expect, it } from 'vitest'

import {
  sanitizePostLoginHotspotBridgeReturnPath,
  shouldAttemptPostLoginHotspotBridge,
} from '../utils/hotspotPostLoginBridge'

describe('hotspotPostLoginBridge', () => {
  it('starts a bridge when post-login flow still has no hotspot identity', () => {
    expect(shouldAttemptPostLoginHotspotBridge({ clientIp: '', clientMac: '' }, 'http://login.home.arpa/login')).toBe(true)
  })

  it('skips the bridge when an explicit hotspot identity already exists', () => {
    expect(shouldAttemptPostLoginHotspotBridge({ clientIp: '172.16.2.10', clientMac: '' }, 'http://login.home.arpa/login')).toBe(false)
    expect(shouldAttemptPostLoginHotspotBridge({ clientIp: '', clientMac: 'AA:BB:CC:DD:EE:FF' }, 'http://login.home.arpa/login')).toBe(false)
  })

  it('skips the bridge when no target URL is available', () => {
    expect(shouldAttemptPostLoginHotspotBridge({ clientIp: '', clientMac: '' }, '')).toBe(false)
  })

  it('sanitizes return path to same-origin login routes and strips bridge resume flag', () => {
    expect(sanitizePostLoginHotspotBridgeReturnPath('/login?redirect=%2Fdashboard&bridge_resume=1', 'https://lpsaring.babahdigital.net')).toBe('/login?redirect=%2Fdashboard')
  })

  it('falls back for external bridge return paths', () => {
    expect(sanitizePostLoginHotspotBridgeReturnPath('https://evil.example/login?redirect=%2Fdashboard', 'https://lpsaring.babahdigital.net')).toBe('/login')
  })
})