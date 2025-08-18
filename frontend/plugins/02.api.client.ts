// plugins/02.api.client.ts

import type { ApiResponse } from '~/types/api'

import { CIRCUIT_BREAKER_EXCLUDED, DEFAULT_RETRY_ATTEMPTS, RETRY_BASE_DELAY_MS, SENSITIVE_ENDPOINT_PATTERNS, SENSITIVE_ENDPOINTS, TRANSIENT_ERROR_CODES } from '~/constants/api-endpoints'
import { useApiMetricsStore } from '~/store/apiMetrics'
// Menggunakan native fetch; tidak perlu import ofetch
import { useAuthStore } from '~/store/auth'
import { ApiErrorCode, isApiErrorResponse } from '~/types/api'
import { isProxyIP } from '~/utils/network-config'
import { getClientRealIP, getClientMAC } from '~/utils/client-info'

export default defineNuxtPlugin(() => {
  const config = useRuntimeConfig()
  const baseURL: string = (config.public.apiBaseUrl || '').replace(/\/$/, '')

  const showToast = (type: 'success' | 'error' | 'info', message: string) => {
    try {
      console.log(`[Toast ${type}]`, message)
      if (typeof window !== 'undefined') {
        window.dispatchEvent(new CustomEvent('app:toast', { detail: { type, message } }))
      }
    }
    catch { /* silent */ }
  }

  interface ApiRequestOptions extends RequestInit {
    method?: string
    retryAttempts?: number
    retry?: boolean // set false to disable retry
  }

  function isTransientError(err: any): boolean {
    const code = err?.code || err?.cause?.code
    if (code && TRANSIENT_ERROR_CODES.includes(code))
      return true
    const msg: string = (err?.message || '').toLowerCase()
    if (!msg)
      return false
    return [
      'network error',
      'failed to fetch',
      'timeout',
      'temporarily unavailable',
      'load failed',
    ].some(p => msg.includes(p))
  }

  const sleep = (ms: number) => new Promise(r => setTimeout(r, ms))

  // Circuit breaker config
  const FAILURE_THRESHOLD = 5
  const OPEN_TIME_MS = 30_000

  async function api<T = unknown>(url: string, opts: ApiRequestOptions = {}): Promise<ApiResponse<T>> {
    const authStore = useAuthStore()
    const metrics = useApiMetricsStore()
    const headers = new Headers(opts.headers as any || {})

    // Method normalization
    const method = (opts.method || 'GET').toUpperCase()
    if (['POST', 'PUT', 'PATCH'].includes(method) && !headers.has('Content-Type'))
      headers.set('Content-Type', 'application/json')

    // Auth header
    const activeToken = authStore.token || localStorage.getItem('app_token_backup')
    if (activeToken)
      headers.set('Authorization', `Bearer ${activeToken}`)

    // Detection headers (client side only)
    if (typeof window !== 'undefined') {
      headers.set('X-Frontend-Request', '1')
      let isSensitive = SENSITIVE_ENDPOINTS.some((e: string) => url.includes(e))
      if (!isSensitive)
        isSensitive = SENSITIVE_ENDPOINT_PATTERNS.some((rx: RegExp) => rx.test(url))
      if (isSensitive) {
        headers.set('Cache-Control', 'no-cache, no-store, must-revalidate')
        headers.set('Pragma', 'no-cache')
        headers.set('Expires', '0')
        headers.set('X-Cache-Bust', Date.now().toString())
      }
      // Prefer server-confirmed authStore IP over stale local cache
      const ip = authStore.clientIp || getClientRealIP()
      if (ip && !isProxyIP(ip)) {
        headers.set('X-Frontend-Detected-IP', ip)
        headers.set('X-Frontend-Detection-Method', authStore.clientIp ? 'auth-store' : 'composite')
      }
      const mac = getClientMAC() || authStore.clientMac
      if (mac)
        headers.set('X-Frontend-Detected-MAC', mac)
      headers.set('X-User-Agent', navigator.userAgent)
      headers.set('X-Request-Time', new Date().toISOString())
    }

    // Build full URL
    let fullUrl = url.startsWith('http') ? url : `${baseURL}${url.startsWith('/') ? '' : '/'}${url}`
    // Append cache-busting query for sensitive endpoints (helps defeat stubborn browser caches)
    // Treat OTP and sync endpoints as sensitive to avoid caches
    const otpSensitive = ['/auth/request-otp', '/auth/verify-otp', '/auth/sync-device', '/auth/clear-cache'].some((e: string) => url.startsWith(e))
    const isSensitiveEp = otpSensitive || SENSITIVE_ENDPOINTS.some((e: string) => url.includes(e)) || SENSITIVE_ENDPOINT_PATTERNS.some((rx: RegExp) => rx.test(url))
    if (isSensitiveEp) {
      const bustParam = `_cb=${Date.now()}`
      fullUrl += (fullUrl.includes('?') ? '&' : '?') + bustParam
    }
    const epKey: string = (url.split('?')[0]) || 'unknown'

    // Circuit breaker pre-check (skip excluded endpoints)
    if (!CIRCUIT_BREAKER_EXCLUDED.some((p: string) => epKey.startsWith(p))) {
      if (metrics.isCircuitOpen) {
        if (metrics.state.circuit.openedAt && (Date.now() - metrics.state.circuit.openedAt) > OPEN_TIME_MS) {
          metrics.closeCircuit()
        }
        else {
          throw new Error('CIRCUIT_OPEN: API temporarily disabled due to repeated failures')
        }
      }
    }
    metrics.recordRequest(epKey)

    const maxRetries = opts.retry === false ? 0 : (typeof opts.retryAttempts === 'number' ? opts.retryAttempts : DEFAULT_RETRY_ATTEMPTS)
    let attempt = 0

    while (true) {
      try {
        const nativeOptions: RequestInit = { ...opts, method, headers }
        // Force no-store for sensitive endpoints to bypass HTTP cache and SW caches
        if (isSensitiveEp) {
          (nativeOptions as any).cache = 'no-store'
        }
        // Pastikan body di-serialize bila object
        const rawBody: any = (nativeOptions as any).body
        if (rawBody && typeof rawBody === 'object' && !(rawBody instanceof FormData)) {
          nativeOptions.body = JSON.stringify(rawBody)
          if (!headers.has('Content-Type'))
            headers.set('Content-Type', 'application/json')
        }
        const resp = await fetch(fullUrl, nativeOptions)
        let data: any = null
        try { data = await resp.json() }
        catch { /* ignore parse error */ }
        if (!resp.ok) {
          const err: any = new Error(`HTTP ${resp.status}`)
          err.status = resp.status
          err.response = { status: resp.status, _data: data }
          err.data = data
          // Surface validation detail for 422
          if (resp.status === 422 && data) {
            const validationErrors = data?.data?.errors || data?.errors
            if (validationErrors && typeof validationErrors === 'object') {
              err.name = 'ValidationError'
              err.validationErrors = validationErrors
              if (!err.message || err.message.startsWith('HTTP')) {
                err.message = data?.message || 'Validasi gagal'
              }
            }
          }
          throw err
        }
        // Refresh stored client IP from server response when present
        try {
          const serverIp: string | undefined = (data && typeof data === 'object') ? (data.ip || data?.data?.ip) : undefined
          if (serverIp && typeof serverIp === 'string' && !isProxyIP(serverIp)) {
            // Update local captive_ip and auth store if changed
            const currentStored = (typeof window !== 'undefined') ? localStorage.getItem('captive_ip') : null
            if (typeof window !== 'undefined' && serverIp !== currentStored) {
              localStorage.setItem('captive_ip', serverIp)
            }
            try { (authStore as any)?.setClientInfo?.(serverIp, null) } catch { /* noop */ }
          }
        } catch { /* ignore */ }

        // Refresh stored client IP/MAC from server detection endpoints to prevent staleness
        try {
          const ep = (url && typeof url === 'string') ? (url.split('?')[0] || '') : ''
          if (ep.endsWith('/auth/detect-client-info')) {
            const detectedIp: string | undefined = (data && (data.ip || data?.summary?.detected_ip))
            const detectedMac: string | undefined = (data && (data.mac || data?.summary?.detected_mac))
            if (detectedIp && !isProxyIP(detectedIp)) {
              if (typeof window !== 'undefined') localStorage.setItem('captive_ip', detectedIp)
              try { (authStore as any)?.setClientInfo?.(detectedIp, detectedMac || null) } catch { /* noop */ }
            }
            else if (detectedMac) {
              try { (authStore as any)?.setClientInfo?.(authStore.clientIp || null, detectedMac) } catch { /* noop */ }
            }
          }
        } catch { /* ignore */ }

        // Tambahkan properti success default jika backend tidak mengirim (hanya untuk objek biasa, bukan array)
        if (data && !Array.isArray(data) && typeof data === 'object' && typeof (data as any).success === 'undefined') {
          data = { success: true, ...data }
        }
        if (isApiErrorResponse(data)) {
          switch (data.errorCode) {
            case ApiErrorCode.AUTHENTICATION_ERROR:
              if (authStore.isLoggedIn) {
                console.warn('[API] Auth error, logging out')
                await authStore.logout(true)
                showToast('error', 'Sesi berakhir. Silakan login kembali.')
              }
              break
            case ApiErrorCode.RATE_LIMITED:
              showToast('error', 'Terlalu banyak permintaan. Coba lagi nanti.')
              break
            case ApiErrorCode.CLIENT_DETECTION_ERROR:
              console.warn('[API] Client detection warning:', (data as any).message)
              break
          }
        }
        metrics.recordSuccess(epKey, 200)
        return data
      }
      catch (err: any) {
        const status = err?.status || err?.response?.status
        const shouldRetry = attempt < maxRetries && (status == null || (status >= 500 && status < 600) || isTransientError(err))
        if (status === 401 && authStore.isLoggedIn) {
          const hdrs: Record<string, any> = { ...(opts.headers as any) }
          if (!hdrs['x-skip-refresh'] && typeof (authStore as any).refreshAccessToken === 'function') {
            const refreshed = await (authStore as any).refreshAccessToken()
            if (refreshed) {
              headers.set('Authorization', `Bearer ${authStore.token}`)
              hdrs['x-skip-refresh'] = '1'
              opts.headers = hdrs as any
              continue
            }
          }
          console.warn('[API] 401 final, logout')
          await authStore.logout(true)
          metrics.recordFailure(epKey, 401, err?.message)
          throw err
        }
        if (!shouldRetry) {
          if (status === 422 && err?.validationErrors) {
            // Biarkan caller menangani untuk menampilkan error field-level
            // Hindari toast generik karena UI form akan menampilkan detail
          }
          else if (status >= 500) {
            showToast('error', 'Server bermasalah. Coba lagi.')
          }
          metrics.recordFailure(epKey, status || null, err?.message)
          if (!CIRCUIT_BREAKER_EXCLUDED.some((p: string) => epKey.startsWith(p)) && metrics.state.circuit.consecutiveFailures >= FAILURE_THRESHOLD) {
            metrics.openCircuit()
          }
          throw err
        }
        attempt++
        metrics.recordRetry(epKey)
        const delay = RETRY_BASE_DELAY_MS * 2 ** (attempt - 1)
        console.warn(`[API] Transient error (attempt ${attempt}/${maxRetries}) retry in ${delay}ms`, err?.code || status || err?.message)
        await sleep(delay)
      }
    }
  }

  return { provide: { api } }
})

// Helpers moved to ~/utils/client-info to avoid duplication
