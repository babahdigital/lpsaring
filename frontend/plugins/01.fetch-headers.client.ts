// plugins/01.fetch-headers.client.ts
// Inject X-Frontend-Detected-* headers into native fetch for browser-side /api requests

import { defineNuxtPlugin } from '#app'
import { useAuthStore } from '~/store/auth'
import { isProxyIP } from '~/utils/network-config'

function getClientRealIP(): string | null {
    const params = new URLSearchParams(window.location.search)
    const p = params.get('client_ip') || params.get('ip') || params.get('client-ip') || params.get('orig-ip')
    if (p) {
        localStorage.setItem('captive_ip', p)
        return p
    }
    const stored = localStorage.getItem('captive_ip')
    return stored || null
}

function getClientMAC(): string | null {
    const params = new URLSearchParams(window.location.search)
    const m = params.get('client_mac') || params.get('mac') || params.get('client-mac')
    if (m) {
        localStorage.setItem('captive_mac', m)
            ; (window as any).__CLIENT_MAC__ = m
        return m
    }
    return localStorage.getItem('captive_mac')
}

export default defineNuxtPlugin(() => {
    if (typeof window === 'undefined') return
    const originalFetch = window.fetch.bind(window)
    window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
        try {
            const url = typeof input === 'string' ? input : (input as URL).toString()
            // Only modify same-origin API calls
            const isApi = typeof url === 'string' && (url.startsWith('/api/') || url.includes(`${window.location.origin}/api/`))
            if (isApi) {
                const auth = useAuthStore()
                const headers = new Headers(init?.headers as any || {})
                // Set detection headers if not present
                // Prefer authStore (server-confirmed) IP over possibly stale captive_ip cache
                const ip = auth.clientIp || getClientRealIP()
                if (ip && !isProxyIP(ip) && !headers.has('X-Frontend-Detected-IP')) {
                    headers.set('X-Frontend-Detected-IP', ip)
                    headers.set('X-Frontend-Detection-Method', auth.clientIp ? 'auth-store' : 'composite')
                }
                const mac = getClientMAC() || auth.clientMac
                if (mac && !headers.has('X-Frontend-Detected-MAC')) {
                    headers.set('X-Frontend-Detected-MAC', mac)
                }
                // Add no-store/cache-bust for sensitive endpoints to avoid caching
                const sensitive = ['/auth/request-otp', '/auth/verify-otp', '/auth/sync-device', '/auth/clear-cache']
                const needsNoCache = sensitive.some(p => url.includes(p))
                const nextInit: RequestInit = { ...init, headers }
                if (needsNoCache) {
                    ; (nextInit as any).cache = 'no-store'
                    if (typeof input === 'string') {
                        const sep = url.includes('?') ? '&' : '?'
                        input = `${url}${sep}_cb=${Date.now()}`
                    }
                }
                return originalFetch(input, nextInit)
            }
        } catch { /* fall through to original */ }
        return originalFetch(input, init)
    }
})
