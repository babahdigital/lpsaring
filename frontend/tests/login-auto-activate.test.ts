import { describe, expect, it, vi } from 'vitest'
import { attemptAutoActivate } from '../utils/autoActivateHotspot'

describe('attemptAutoActivate', () => {
  it('returns fallback when hotspot login is not required', async () => {
    const apiFetch = vi.fn()
    const result = await attemptAutoActivate({
      apiFetch,
      hotspotLoginRequired: false,
      hasClientIdentity: false,
    })
    expect(result).toBe('fallback')
    expect(apiFetch).not.toHaveBeenCalled()
  })

  it('returns fallback when client identity is already present (skip auto-activate)', async () => {
    const apiFetch = vi.fn()
    const result = await attemptAutoActivate({
      apiFetch,
      hotspotLoginRequired: true,
      hasClientIdentity: true,
    })
    expect(result).toBe('fallback')
    expect(apiFetch).not.toHaveBeenCalled()
  })

  it('returns activated when backend says activated:true', async () => {
    const apiFetch = vi.fn().mockResolvedValue({ activated: true, mac_used: 'AA:BB:CC:DD:EE:FF' })
    const result = await attemptAutoActivate({
      apiFetch,
      hotspotLoginRequired: true,
      hasClientIdentity: false,
    })
    expect(result).toBe('activated')
    expect(apiFetch).toHaveBeenCalledWith('/auth/captive/auto-activate', { method: 'POST' })
  })

  it('returns fallback when backend says activated:false', async () => {
    const apiFetch = vi.fn().mockResolvedValue({ activated: false, reason: 'no_known_device' })
    const result = await attemptAutoActivate({
      apiFetch,
      hotspotLoginRequired: true,
      hasClientIdentity: false,
    })
    expect(result).toBe('fallback')
  })

  it('returns fallback when backend throws (network error)', async () => {
    const apiFetch = vi.fn().mockRejectedValue(new Error('boom'))
    const result = await attemptAutoActivate({
      apiFetch,
      hotspotLoginRequired: true,
      hasClientIdentity: false,
    })
    expect(result).toBe('fallback')
  })

  it('returns fallback when backend returns null/undefined body', async () => {
    const apiFetch = vi.fn().mockResolvedValue(null)
    const result = await attemptAutoActivate({
      apiFetch,
      hotspotLoginRequired: true,
      hasClientIdentity: false,
    })
    expect(result).toBe('fallback')
  })
})
