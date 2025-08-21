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
 * Endpoint yang membutuhkan penanganan khusus, seperti:
 * - Cache busting
 * - Penanganan kesalahan khusus
 * - Header kustom
 * - Pengecekan perangkat klien
 */
export const SENSITIVE_ENDPOINTS = [
  '/api/auth/detect-client-info', // Endpoint utama untuk deteksi IP/MAC
  '/api/auth/me',                 // Informasi user saat ini
  '/api/auth/sync-device',        // Sinkronisasi perangkat
  '/api/auth/authorize-device',   // Otorisasi perangkat
  '/api/auth/reject-device',      // Penolakan otorisasi perangkat
  '/api/auth/invalidate-device',  // Pencabutan akses perangkat
  '/api/auth/check-device-status',// Pengecekan status perangkat
  '/api/auth/check-token-device', // Pengecekan token dan perangkat
  '/api/auth/clear-cache',        // Pembersihan cache
  '/api/auth/session-stats',      // Statistik sesi
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
  '/api/auth/admin/login',      // Login admin harus selalu tersedia
  '/api/auth/refresh',          // Refresh token harus selalu tersedia
  '/api/auth/verify-role',      // Verifikasi role harus selalu tersedia
  '/api/auth/detect-client-info', // Deteksi klien harus selalu bisa diakses
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
