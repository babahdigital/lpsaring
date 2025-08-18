// Centralized API endpoint constants & classifications
// Digunakan oleh plugin API untuk header khusus, cache busting, dsb.

export const SENSITIVE_ENDPOINTS = [
  '/auth/detect-client-info',
  '/auth/detect-client',
  '/auth/me',
  '/auth/sync-device',
  '/auth/authorize-device',
  '/auth/clear-cache',
  '/auth/session-stats',
]
// Regex patterns untuk endpoint sensitif (fallback jika tidak match exact)
export const SENSITIVE_ENDPOINT_PATTERNS: RegExp[] = [
  /\/auth\/.*device/i,
]

// Endpoint yang terkait autentikasi (jika nanti ada refresh token, dsb)
export const AUTH_ENDPOINTS = [
  '/auth/admin/login',
  '/auth/logout',
  '/auth/register',
  '/auth/verify-role',
]
// Endpoint yang tidak akan diblokir oleh circuit breaker
export const CIRCUIT_BREAKER_EXCLUDED = [
  '/auth/admin/login',
  '/auth/refresh',
  '/auth/verify-role',
]

// Transient network error codes untuk retry ringan
export const TRANSIENT_ERROR_CODES = [
  'ECONNRESET',
  'ECONNREFUSED',
  'ETIMEDOUT',
  'EAI_AGAIN',
  'UND_ERR_CONNECT_TIMEOUT',
]

export const DEFAULT_RETRY_ATTEMPTS = 2 // total percobaan (tanpa termasuk request awal)
export const RETRY_BASE_DELAY_MS = 250
