// plugins/websocket.client.ts
import { defineNuxtPlugin } from '#app'
import { watch } from 'vue'

import { useClientGlobalState } from '~/composables/useClientGlobalState'
import { useAuthStore } from '~/store/auth'

export default defineNuxtPlugin((nuxtApp) => {
  // Only run on client
  if (typeof window === 'undefined')
    return

  // Access global state
  const globalState = useClientGlobalState()
  const authStore = useAuthStore()

  let socket: WebSocket | null = null
  let reconnectAttempts = 0
  const baseDelay = 3000 // ms
  const hardMaxDelay = 60000 // 60s cap
  let manuallyClosed = false
  let degraded = false
  let visibilityPending = false
  let sse: EventSource | null = null
  let sseActive = false
  const sseBackoffBase = 5000
  let sseAttempts = 0
  let lastCloseCode: number | null = null
  let lastCloseReason: string | null = null
  let heartbeatTimer: number | null = null

  function startSSEFallback(reason: string) {
    if (sseActive)
      return
    sseActive = true
    sseAttempts++
    const url = `${window.location.protocol}//${window.location.host}/api/ws/sse/client-updates`
    console.warn('🌐 [SSE] Starting fallback stream:', { url, reason, attempts: sseAttempts })
    try {
      sse = new EventSource(url, { withCredentials: false })
    }
    catch (e) {
      console.error('❌ [SSE] Failed to construct EventSource:', e)
      scheduleRetrySSE()
      return
    }

    sse.onopen = () => {
      console.log('✅ [SSE] Fallback connected')
      // Mirror an auth/register handshake (lightweight) if we have data; SSE is server push only
    }

    sse.onmessage = (ev) => {
      try {
        const data = JSON.parse(ev.data)
        switch (data.type) {
          case 'mac_detected':
            if (data.mac && (!globalState.clientInfo.value.mac || data.force_update)) {
              globalState.setClientInfo({
                mac: data.mac,
                ip: data.ip || globalState.clientInfo.value.ip,
                detectionMethod: 'sse',
              })
              authStore.setClientInfo(
                data.ip || globalState.clientInfo.value.ip,
                data.mac,
              )
            }
            break
          case 'cache_cleared':
            console.log('🧹 [SSE] Cache cleared notification (fallback)')
            break
          case 'ping':
          case 'welcome':
            break
        }
      }
      catch (e) {
        // ignore parse errors
      }
    }

    sse.onerror = (err) => {
      console.warn('⚠️ [SSE] Error event:', err)
      stopSSE()
      scheduleRetrySSE()
    }
  }

  function stopSSE() {
    if (sse) {
      try { sse.close() }
      catch { /* ignore */ }
      sse = null
    }
    sseActive = false
  }

  function scheduleRetrySSE() {
    const delay = Math.min(sseBackoffBase * 1.5 ** Math.min(sseAttempts, 6), 60000)
    setTimeout(() => {
      if (degraded && !socket)
        startSSEFallback('retry')
    }, delay)
  }

  function calcDelay() {
    const exp = Math.min(reconnectAttempts, 8)
    const raw = baseDelay * 1.8 ** exp
    const jitter = Math.random() * 400
    return Math.min(raw + jitter, hardMaxDelay)
  }

  let connectInProgress = false

  // Kandidat path (canonical lalu legacy)
  const wsCandidatePaths = ['/api/ws/client-updates', '/client-updates']
  let pathIndex = 0

  const connectWebSocket = () => {
    if (manuallyClosed || degraded || connectInProgress)
      return
    connectInProgress = true
    if (document.hidden) {
      // Tunda sampai tab aktif untuk menghemat resource
      visibilityPending = true
      connectInProgress = false
      return
    }
    try {
      // Get the current host but switch protocol to ws/wss
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
      const host = window.location.host
      const path = wsCandidatePaths[pathIndex] || wsCandidatePaths[0] || '/api/ws/client-updates'
      const currentIp = authStore.clientIp || (typeof window !== 'undefined' ? localStorage.getItem('captive_ip') : '') || ''
      const qp = currentIp ? ((path && path.includes('?')) ? `&ip=${encodeURIComponent(currentIp)}` : `?ip=${encodeURIComponent(currentIp)}`) : ''
      const wsUrl = `${protocol}//${host}${path}${qp}`
      console.debug('[WS] Attempt connect', { wsUrl, attempt: reconnectAttempts, pathIndex })

      // Close existing socket if any
      if (socket)
        socket.close()

      // Try with query param first; some servers may prefer header/subprotocol. If later we get policy fail, we can retry with subprotocol.
      // Hapus penggunaan subprotocol custom karena server (flask-sock/simple-websocket) bisa menolak jika tidak menyatakan protokol.
      socket = new WebSocket(wsUrl)

      socket.onopen = () => {
        console.log('🔌 [WEBSOCKET] Connected to real-time updates')
        reconnectAttempts = 0
        degraded = false
        connectInProgress = false

        // Start a lightweight client → server heartbeat to keep intermediaries happy
        if (heartbeatTimer)
          window.clearInterval(heartbeatTimer)
        heartbeatTimer = window.setInterval(() => {
          try {
            if (socket && socket.readyState === WebSocket.OPEN) {
              socket.send(JSON.stringify({ type: 'ping', t: Date.now() }))
            }
          }
          catch { }
        }, 25000)

        // Send authentication if available
        if (authStore.token) {
          socket?.send(JSON.stringify({
            type: 'auth',
            token: authStore.token,
          }))
        }

        // Send client info to register for updates
        if (globalState.clientInfo.value.ip) {
          console.log(`[WS] Registering client with IP: ${globalState.clientInfo.value.ip} and MAC: ${globalState.clientInfo.value.mac || 'N/A'}`)
          socket?.send(JSON.stringify({
            type: 'register_client',
            payload: {
              ip: globalState.clientInfo.value.ip,
              mac: globalState.clientInfo.value.mac,
            },
          }))
        }
      }

      socket.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data)

          // Handle different message types
          switch (data.type) {
            case 'mac_detected':
              console.log(`🔄 [WEBSOCKET] MAC detected: ${data.mac}`)
              if (data.mac && (!globalState.clientInfo.value.mac || data.force_update)) {
                // Update global state
                globalState.setClientInfo({
                  mac: data.mac,
                  ip: data.ip || globalState.clientInfo.value.ip,
                  detectionMethod: 'websocket',
                })

                // Update auth store
                authStore.setClientInfo(
                  data.ip || globalState.clientInfo.value.ip,
                  data.mac,
                )

                // Notify user if enabled
                if (data.notify) {
                  // Could show a toast notification here
                  console.log('✅ MAC address detected successfully!')
                }
              }
              break

            case 'cache_cleared':
              console.log('🧹 [WEBSOCKET] Cache cleared notification')
              // Could trigger a redetection here
              break

            case 'ping':
              // Keep-alive, respond with pong
              socket?.send(JSON.stringify({ type: 'pong' }))
              break
          }
        }
        catch (err) {
          console.error('Error processing WebSocket message:', err)
        }
      }

      socket.onclose = (event) => {
        console.log(`🔌 [WEBSOCKET] Connection closed (${event.code})`)
        lastCloseCode = event.code
        lastCloseReason = event.reason || null
        if (heartbeatTimer) { window.clearInterval(heartbeatTimer); heartbeatTimer = null }
        if (manuallyClosed)
          return
        socket = null
        connectInProgress = false
        // Abandon large close codes for auth / 403 style (1008 policy, 400x custom) after a few tries
        if ([1008].includes(event.code) || reconnectAttempts > 25) {
          degraded = true
            ; (window as any).__WS_DEGRADED = true
          console.warn('🛑 [WEBSOCKET] Degraded mode: stop reconnect attempts.')
          // Start SSE fallback if not already
          if (!sseActive)
            startSSEFallback('ws-degraded')
          return
        }
        reconnectAttempts++
        // Jika beberapa kali gagal awal (misal 2x) di path canonical, coba legacy path sekali sebelum lanjut backoff.
        if (reconnectAttempts === 2 && pathIndex === 0 && wsCandidatePaths.length > 1) {
          console.warn('[WS] Switching to legacy path fallback after 2 failed attempts')
          pathIndex = 1
        }
        const delay = calcDelay()
        console.log(`🔄 [WEBSOCKET] Reconnecting in ${(delay / 1000).toFixed(1)}s (attempt ${reconnectAttempts})...`)
        setTimeout(connectWebSocket, delay)
        // If many attempts failing early, opportunistically start SSE
        if (reconnectAttempts === 5 && !degraded && !sseActive) {
          console.warn('🌐 [SSE] Opportunistic fallback start (retries threshold)')
          startSSEFallback('ws-retries')
        }
      }

      socket.onerror = (error) => {
        // Throttle noise: only log first 1 & at powers of two
        const shouldLog = reconnectAttempts === 0 || [1, 2, 4, 8, 16].includes(reconnectAttempts)
        if (shouldLog)
          console.error(`WebSocket error (attempt ${reconnectAttempts}):`, error)
      }
    }
    catch (err) {
      console.error('Failed to connect WebSocket:', err)
      reconnectAttempts++
      connectInProgress = false
      setTimeout(connectWebSocket, calcDelay())
    }
  }

  // Connect when a user is authenticated
  nuxtApp.hook('page:finish', () => {
    if (authStore.token && !socket && !degraded)
      connectWebSocket()
  })

  // Reconnect / connect when token changes (login/logout)
  watch(() => authStore.token, (newTok: string | null | undefined, _oldTok: string | null | undefined) => {
    if (manuallyClosed)
      return
    if (newTok && !socket) {
      reconnectAttempts = 0
      connectWebSocket()
    }
    else if (!newTok && socket) {
      manuallyClosed = true
      socket.close()
      socket = null
      manuallyClosed = false
    }
  })

  // Visibility handling: saat tab kembali fokus, coba konek jika pending / disconnected
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden && (visibilityPending || (!socket && !degraded && authStore.token))) {
      visibilityPending = false
      connectWebSocket()
    }
  })

  // Cleanup on app unmount
  nuxtApp.hook('page:transition:finish', () => {
    // Check if we're navigating away from the app
    if (socket && window.location.pathname === '/logout') {
      manuallyClosed = true
      socket.close()
      socket = null
      manuallyClosed = false
    }
  })

  // Also handle browser unload event
  if (typeof window !== 'undefined') {
    window.addEventListener('beforeunload', () => {
      if (socket) {
        manuallyClosed = true
        socket.close()
        socket = null
        manuallyClosed = false
      }
      if (heartbeatTimer) { window.clearInterval(heartbeatTimer); heartbeatTimer = null }
    })
  }

  // If client IP changes while socket is open, re-register mapping on the server
  watch(() => authStore.clientIp, (newIp: string | null | undefined, oldIp: string | null | undefined) => {
    if (!newIp || newIp === oldIp)
      return
    if (socket && socket.readyState === WebSocket.OPEN) {
      try {
        socket.send(JSON.stringify({ type: 'register', ip: newIp, mac: globalState.clientInfo.value.mac }))
        console.debug('[WS] Re-registered with new IP', { newIp, oldIp })
      }
      catch { }
    }
  })

  // Expose WebSocket functionality
  return {
    provide: {
      websocket: {
        reconnect: () => { degraded = false; reconnectAttempts = 0; connectWebSocket() },
        send: (message: any) => {
          if (socket && socket.readyState === WebSocket.OPEN) {
            socket.send(JSON.stringify(message))
            return true
          }
          return false
        },
        status: () => ({
          connected: !!socket && socket.readyState === WebSocket.OPEN,
          attempts: reconnectAttempts,
          degraded,
          nextBackoffMs: calcDelay(),
          sseActive,
          lastCloseCode,
          lastCloseReason,
        }),
      },
    },
  }
})
