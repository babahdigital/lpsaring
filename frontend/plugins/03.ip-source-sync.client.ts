// plugins/03.ip-source-sync.client.ts
// Keep auth store IP in sync with server-detected IP and clear MAC when IP changes

import { defineNuxtPlugin } from '#app'
import { useAuthStore } from '~/store/auth'
import { isProxyIP } from '~/utils/network-config'

export default defineNuxtPlugin((nuxtApp) => {
    if (typeof window === 'undefined') return

    const auth = useAuthStore()

    let lastIp: string | null = null
    let lastCheckTs = 0
    let intervalMs = 15000 // start moderately fast
    let rateLimitedUntil: number | null = null

    function scheduleNextTick(adjust?: 'faster' | 'slower' | 'default') {
        if (adjust === 'faster') intervalMs = Math.max(5000, Math.floor(intervalMs * 0.75))
        else if (adjust === 'slower') intervalMs = Math.min(60000, Math.floor(intervalMs * 1.5))
        return intervalMs
    }

    function getClientRealIP(): string | null {
        const params = new URLSearchParams(window.location.search)
        const p = params.get('client_ip') || params.get('ip') || params.get('client-ip') || params.get('orig-ip')
        if (p) { try { localStorage.setItem('captive_ip', p) } catch { /* noop */ } return p }
        return localStorage.getItem('captive_ip')
    }

    function getClientMAC(): string | null {
        const params = new URLSearchParams(window.location.search)
        const m = params.get('client_mac') || params.get('mac') || params.get('client-mac')
        if (m) { try { localStorage.setItem('captive_mac', m) } catch { /* noop */ }; (window as any).__CLIENT_MAC__ = m; return m }
        return localStorage.getItem('captive_mac')
    }

    async function checkIpOnce(reason: string) {
        try {
            const now = Date.now()
            // Avoid hammering if called too frequently by multiple triggers
            if (now - lastCheckTs < 2000) return
            lastCheckTs = now

            // Respect backoff if previously rate limited
            if (rateLimitedUntil && now < rateLimitedUntil) {
                return
            }

            // Inject minimal detection headers so backend has an early candidate even jika proxy header belum ada
            const headers = new Headers()
            headers.set('X-Frontend-Request', '1')
            const feIp = auth.clientIp || getClientRealIP()
            if (feIp && !isProxyIP(feIp)) {
                headers.set('X-Frontend-Detected-IP', feIp)
                headers.set('X-Frontend-Detection-Method', auth.clientIp ? 'auth-store' : 'composite')
            }
            const feMac = getClientMAC() || auth.clientMac
            if (feMac) headers.set('X-Frontend-Detected-MAC', feMac)

            const resp = await fetch('/api/debug/ip-source?_cb=' + now, { cache: 'no-store', headers })
            if (resp.status === 429) {
                // Exponential backoff up to 60s
                intervalMs = Math.min(Math.floor(intervalMs * 2), 60000)
                rateLimitedUntil = Date.now() + Math.max(intervalMs, 5000)
                // schedule slower next
                scheduleNextTick('slower')
                return
            }
            if (!resp.ok) return
            const data = await resp.json().catch(() => ({}))
            const serverIp: string | null = (data && typeof data.ip === 'string') ? data.ip : null
            if (!serverIp) return
            const current = auth.clientIp
            if (serverIp && serverIp !== current) {
                console.log(`[IP-SYNC] Updating client IP from ${current || 'null'} → ${serverIp} (reason=${reason})`)
                try { localStorage.setItem('captive_ip', serverIp) } catch { /* noop */ }
                // Clear MAC to force re-detection for the new IP
                try {
                    localStorage.removeItem('captive_mac')
                    localStorage.removeItem('auth_client_mac')
                } catch { /* noop */ }
                auth.setClientInfo(serverIp, null)
                // Trigger a background sync to update bypass/lease with new IP
                try { await auth.syncDevice() } catch { /* ignore */ }
                // After IP change, keep faster cadence briefly
                scheduleNextTick('faster')
                rateLimitedUntil = null
            } else if (serverIp !== lastIp) {
                // IP stable but updated value observed, slow down a bit
                scheduleNextTick('slower')
                rateLimitedUntil = null
            }
            lastIp = serverIp
        } catch { /* silent */ }
    }

    // Run on page finish and then periodically (adaptive interval)
    nuxtApp.hook('page:finish', () => { checkIpOnce('page:finish:immediate'); setTimeout(() => checkIpOnce('page:finish:followup'), 1200) })

    let timer: number | null = null
    function tickLoop() {
        if (timer) window.clearTimeout(timer)
        timer = window.setTimeout(async () => {
            await checkIpOnce('loop')
            // Reschedule with adjusted interval
            tickLoop()
        }, intervalMs)
    }
    tickLoop()

    // Extra triggers
    window.addEventListener('online', () => checkIpOnce('online'))
    document.addEventListener('visibilitychange', () => { if (!document.hidden) checkIpOnce('visible') })
    // Coordinate with network-change plugin via a custom event if present
    window.addEventListener('app:network-changed', () => checkIpOnce('network-change'))

    // Cleanup
    window.addEventListener('beforeunload', () => { if (timer) window.clearTimeout(timer) })
})
