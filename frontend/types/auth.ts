// frontend/types/auth.ts

// ✅ PERBAIKAN: Mengimpor tipe 'User' dari file 'user.ts'.
// Ini akan menyelesaikan error 'Cannot find name User'.
import type { User } from './user'

/**
 * Payload (data yang dikirim) untuk endpoint registrasi pengguna.
 */
export interface RegistrationPayload {
  phone_number: string
  full_name: string
  blok?: string | null
  kamar?: string | null
  register_as_komandan?: boolean
}

/**
 * Payload untuk endpoint verifikasi OTP.
 */
export interface VerifyOtpPayload {
  phone_number: string
  otp: string
  client_ip: string | null
  client_mac: string | null
}

/**
 * Respons yang diterima setelah verifikasi OTP berhasil.
 */
export interface VerifyOtpResponse {
  access_token: string
  token_type: string // biasanya 'bearer'
  token: string
  user: User // Sekarang tipe 'User' sudah dikenali
}

/**
 * Respons yang diterima setelah registrasi berhasil.
 */
export interface RegisterResponse {
  message: string
  user_id: string
  phone_number: string
}

/**
 * Tipe untuk respons dari endpoint /pre-login-status.
 */
export interface PreLoginStatus {
  status: 'unauthenticated' | 'blocked'
}

/**
 * Interface umum untuk error API jika ada struktur standar.
 */
export interface ApiErrorResponse {
  error?: string
  message?: string
  detail?: any
  statusCode?: number
}
