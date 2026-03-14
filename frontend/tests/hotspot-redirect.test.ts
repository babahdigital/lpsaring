import { describe, expect, it } from 'vitest'
import {
  resolveCaptiveSuccessRedirectTarget,
  resolveHotspotSuccessPresentation,
  resolvePostHotspotRecheckRoute,
  shouldRedirectToHotspotRequired,
} from '../utils/hotspotRedirect'

describe('shouldRedirectToHotspotRequired', () => {
  it('returns true when hotspot login required and binding explicitly inactive', () => {
    expect(shouldRedirectToHotspotRequired({
      hotspotLoginRequired: true,
      hotspotBindingActive: false,
    })).toBe(true)
  })

  it('returns false when binding is active', () => {
    expect(shouldRedirectToHotspotRequired({
      hotspotLoginRequired: true,
      hotspotBindingActive: true,
    })).toBe(false)
  })

  it('returns true when binding state is unknown', () => {
    expect(shouldRedirectToHotspotRequired({
      hotspotLoginRequired: true,
      hotspotBindingActive: null,
    })).toBe(true)
  })

  it('returns false when hotspot login is not required', () => {
    expect(shouldRedirectToHotspotRequired({
      hotspotLoginRequired: false,
      hotspotBindingActive: false,
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

  it('returns dashboard-focused success copy for connected users', () => {
    expect(resolveHotspotSuccessPresentation('/dashboard')).toEqual({
      title: 'Anda Terhubung!',
      description: 'Perangkat Anda sudah berhasil terhubung ke internet. Anda akan diarahkan ke dashboard dalam beberapa detik.',
      ctaLabel: 'Buka Dashboard',
    })
  })

  it('returns generic success copy for non-dashboard follow-up routes', () => {
    expect(resolveHotspotSuccessPresentation('/policy/fup')).toEqual({
      title: 'Akses Berhasil Diperbarui',
      description: 'Koneksi perangkat sudah diproses. Anda akan diarahkan ke halaman berikutnya secara otomatis.',
      ctaLabel: 'Lanjut Sekarang',
    })
  })

  it('falls back to dashboard for same-origin root success redirects', () => {
    expect(resolveCaptiveSuccessRedirectTarget('https://lpsaring.babahdigital.net', 'https://lpsaring.babahdigital.net')).toBe('/dashboard')
  })

  it('falls back to dashboard for same-origin hotspot flow routes', () => {
    expect(resolveCaptiveSuccessRedirectTarget('/login/hotspot-required', 'https://lpsaring.babahdigital.net')).toBe('/dashboard')
  })

  it('keeps safe same-origin portal targets relative for client navigation', () => {
    expect(resolveCaptiveSuccessRedirectTarget('/dashboard?from=captive', 'https://lpsaring.babahdigital.net')).toBe('/dashboard?from=captive')
  })

  it('keeps external success targets unchanged', () => {
    expect(resolveCaptiveSuccessRedirectTarget('https://google.com', 'https://lpsaring.babahdigital.net')).toBe('https://google.com/')
  })
})
