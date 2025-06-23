export interface User {
  id: string
  phone_number?: string
  email?: string
  full_name?: string
  is_active: boolean
  // [PERBAIKAN] Menambahkan peran KOMANDAN
  role: 'USER' | 'KOMANDAN' | 'ADMIN' | 'SUPER_ADMIN'
  approval_status: 'PENDING' | 'APPROVED' | 'REJECTED'

  // [TAMBAHAN] Menambahkan properti lain dari backend untuk kelengkapan
  blok?: string | null
  kamar?: string | null
  is_unlimited_user?: boolean
  mikrotik_server_name?: string | null
  mikrotik_profile_name?: string | null
}

export interface RegistrationPayload {
  phone_number: string
  full_name: string
  email: string
  // tambahkan properti lain
}

export interface VerifyOtpResponse {
  access_token: string
  token_type: string // biasanya 'bearer'
  // tambahkan properti lain jika ada
}

export interface RegisterResponse {
  message: string
  // tambahkan properti lain jika ada
}

// Interface umum untuk error API jika ada struktur standar
export interface ApiErrorResponse {
  error?: string
  message?: string
  detail?: any // Bisa string atau array objek (untuk validation errors)
  statusCode?: number
}
