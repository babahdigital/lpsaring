// Centralized API endpoint constants & classifications
// Digunakan oleh plugin API untuk header khusus, cache busting, dsb.

/**
 * CATATAN PENTING TENTANG ENDPOINT API:
 * 
 * 1. Semua endpoint yang didefinisikan di sini harus memiliki implementasi yang sesuai di backend
 * 2. Setelah menambahkan/mengubah endpoint, jalankan script validasi:
 *    `bash ./scripts/validate-endpoints-final.sh`
 * 3. Update dokumentasi API dengan:
 *    `bash ./scripts/generate-api-docs.sh`
 * 4. Selalu gunakan nama yang sama dengan yang didefinisikan di route Flask backend
 * 
 * Lihat docs/API_ENDPOINT_TOOLS_GUIDE.md untuk informasi lengkap.
 */

/**
 * Endpoint API yang tersedia untuk digunakan
 * Memastikan konsistensi endpoint di seluruh frontend
 */
export const API_ENDPOINTS = {
  // Auth endpoints
  LOGIN: '/auth/admin/login',
  LOGOUT: '/auth/logout',
  REFRESH_TOKEN: '/auth/refresh',
  REGISTER: '/auth/register',
  REQUEST_OTP: '/auth/request-otp',
  VERIFY_OTP: '/auth/verify-otp',
  VERIFY_ROLE: '/auth/verify-role',
  ME: '/auth/me',

  // Device related endpoints
  DEVICE_DETECT: '/auth/detect-client-info',
  DEVICE_AUTHORIZE: '/auth/authorize-device',
  DEVICE_REJECT: '/auth/reject-device',
  DEVICE_INVALIDATE: '/auth/invalidate-device',
  DEVICE_CHECK_STATUS: '/auth/check-device-status',
  DEVICE_CHECK_TOKEN: '/auth/check-token-device',
  DEVICE_SYNC: '/auth/sync-device',
  DEVICE_VALIDATE: '/auth/validate-device',

  // Utilities
  // Prefer this for cache clear + detection refresh
  FORCE_DEVICE_SYNC: '/auth/force-device-sync',
  // Legacy/compat endpoint; keep for older deployments
  CLEAR_CACHE: '/auth/clear-cache',
  SESSION_STATS: '/auth/session-stats',
}

/**
 * Endpoint yang membutuhkan penanganan khusus, seperti:
 * - Cache busting
 * - Penanganan kesalahan khusus
 * - Header kustom
 * - Pengecekan perangkat klien
 */
export const SENSITIVE_ENDPOINTS = [
  API_ENDPOINTS.DEVICE_DETECT,   // Endpoint utama untuk deteksi IP/MAC
  API_ENDPOINTS.ME,              // Informasi user saat ini
  API_ENDPOINTS.DEVICE_SYNC,     // Sinkronisasi perangkat
  API_ENDPOINTS.DEVICE_AUTHORIZE, // Otorisasi perangkat
  API_ENDPOINTS.DEVICE_REJECT,   // Penolakan otorisasi perangkat
  API_ENDPOINTS.DEVICE_INVALIDATE, // Pencabutan akses perangkat
  API_ENDPOINTS.DEVICE_VALIDATE,   // Validasi perangkat oleh MAC untuk user saat ini
  API_ENDPOINTS.DEVICE_CHECK_STATUS, // Pengecekan status perangkat
  API_ENDPOINTS.DEVICE_CHECK_TOKEN, // Pengecekan token dan perangkat
  API_ENDPOINTS.FORCE_DEVICE_SYNC, // Sinkronisasi paksa (membersihkan cache + deteksi ulang)
  API_ENDPOINTS.CLEAR_CACHE,     // Pembersihan cache
  API_ENDPOINTS.SESSION_STATS,   // Statistik sesi
]
// Regex patterns untuk endpoint sensitif (fallback jika tidak match exact)
export const SENSITIVE_ENDPOINT_PATTERNS: RegExp[] = [
  /\/api\/auth\/.*device/i,
  /\/api\/auth\/.*detect/i,
  /\/api\/auth\/.*session/i,
]

/**
 * Endpoint yang terkait autentikasi
 * Digunakan untuk:
 * - Penanganan token
 * - Refresh token otomatis
 * - Penanganan logout
 */
export const AUTH_ENDPOINTS = [
  '/api/auth/admin/login',
  '/api/auth/logout',
  '/api/auth/refresh',          // Endpoint untuk refresh token
  '/api/auth/register',
  '/api/auth/request-otp',
  '/api/auth/verify-otp',
  '/api/auth/verify-role',
]

/**
 * Endpoint yang tidak akan diblokir oleh circuit breaker
 * Digunakan untuk endpoint kritis yang harus selalu tersedia,
 * meski terjadi error pada endpoint lain
 */
export const CIRCUIT_BREAKER_EXCLUDED = [
  API_ENDPOINTS.LOGIN,          // Login admin harus selalu tersedia
  API_ENDPOINTS.REFRESH_TOKEN,  // Refresh token harus selalu tersedia
  API_ENDPOINTS.VERIFY_ROLE,    // Verifikasi role harus selalu tersedia
  API_ENDPOINTS.DEVICE_DETECT,  // Deteksi klien harus selalu bisa diakses
  API_ENDPOINTS.DEVICE_AUTHORIZE, // Device authorization endpoint harus selalu bisa diakses
  API_ENDPOINTS.DEVICE_SYNC,    // Device synchronization endpoint harus selalu bisa diakses
  API_ENDPOINTS.FORCE_DEVICE_SYNC, // Force sync harus selalu bisa diakses
  API_ENDPOINTS.CLEAR_CACHE,    // Cache clearing endpoint harus selalu bisa diakses
  '/auth/detect-client-info',   // Endpoint langsung (explicit path)
  '/auth/authorize-device',     // Endpoint langsung (explicit path)
  '/auth/force-device-sync',    // Endpoint langsung (explicit path)
  '/auth/clear-cache',          // Endpoint langsung (explicit path)
  // Removed legacy placeholder '/auth/device/authorize' (no backend route)
]

/**
 * Kode error jaringan sementara yang memicu retry otomatis
 * Berguna untuk menangani masalah koneksi intermittent
 */
export const TRANSIENT_ERROR_CODES = [
  'ECONNRESET',           // Koneksi di-reset oleh peer
  'ECONNREFUSED',         // Koneksi ditolak
  'ETIMEDOUT',            // Timeout koneksi
  'EAI_AGAIN',            // DNS lookup sementara gagal
  'UND_ERR_CONNECT_TIMEOUT', // Timeout koneksi (Node.js)
  'EHOSTUNREACH',         // Host tidak dapat dijangkau
  'ENETUNREACH',          // Jaringan tidak dapat dijangkau
  'ESOCKETTIMEDOUT',      // Timeout socket
]

/**
 * Status HTTP yang dapat dicoba ulang
 * Status 5xx (server error) biasanya masalah sementara dan dapat dicoba lagi
 */
export const RETRYABLE_STATUS_CODES = [
  500, // Internal Server Error
  502, // Bad Gateway
  503, // Service Unavailable
  504, // Gateway Timeout
  507, // Insufficient Storage
  509, // Bandwidth Limit Exceeded
  521, // Web Server Is Down
  522, // Connection Timed Out
  524, // A Timeout Occurred
]

export const DEFAULT_RETRY_ATTEMPTS = 2 // total percobaan (tanpa termasuk request awal)
export const RETRY_BASE_DELAY_MS = 250
