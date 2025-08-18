// plugins/sse-fallback.client.ts
// Simple SSE fallback when websocket degraded. Listens to /api/sse/client-updates (adjust path if backend differs).
import { defineNuxtPlugin } from '#app'

import { useClientGlobalState } from '~/composables/useClientGlobalState'
import { useAuthStore } from '~/store/auth'

export default defineNuxtPlugin(() => {
  if (typeof window === 'undefined')
    return
  const globalState = useClientGlobalState()
  const auth = useAuthStore()
  let es: EventSource | null = null

  function start() {
    // Only start if websocket degraded (plugin websocket exposes window.__WS_DEGRADED flag optionally)
    if (!(window as any).__WS_DEGRADED)
      return
    if (es)
      return
    const token = auth.token ? `?token=${encodeURIComponent(auth.token)}` : ''
    // Sesuaikan path SSE baru yang berada di bawah prefix /api/ws
    es = new EventSource(`/api/ws/sse/client-updates${token}`)

    es.onmessage = (ev) => {
      try {
        const data = JSON.parse(ev.data)
        if (data.type === 'mac_detected') {
          globalState.setClientInfo({
            mac: data.mac,
            ip: data.ip || globalState.clientInfo.value.ip,
            detectionMethod: 'sse',
          })
        }
      }
      catch (e) { /* ignore */ }
    }

    es.onerror = () => {
      // Retry after short delay
      if (es) {
        es.close(); es = null
        setTimeout(start, 5000)
      }
    }
  }

  // Poll degraded flag
  setInterval(start, 4000)
})
