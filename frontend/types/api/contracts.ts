export type ApiRole = 'USER' | 'KOMANDAN' | 'ADMIN' | 'SUPER_ADMIN'
export type ApiApprovalStatus = 'PENDING' | 'PENDING_APPROVAL' | 'APPROVED' | 'REJECTED'
export const API_CONTRACT_REVISION = '2026-02-26-internal-refactor-no-signature-change' as const

export interface ApiErrorDetail {
  loc?: Array<string | number>
  msg?: string
  type?: string
}

export interface ApiErrorEnvelope {
  code: string
  message: string
  details?: ApiErrorDetail[]
  request_id?: string
}

export interface ApiMessageResponse {
  message: string
}

export interface AuthRegisterRequestContract {
  phone_number: string
  full_name: string
  blok?: string | null
  kamar?: string | null
  is_tamping?: boolean
  tamping_type?: string | null
  register_as_komandan?: boolean
}

export interface AuthRegisterResponseContract {
  message: string
  user_id: string
  phone_number: string
}

export interface AuthRequestOtpRequestContract {
  phone_number: string
}

export interface AuthVerifyOtpRequestContract {
  phone_number: string
  otp: string
  client_ip?: string | null
  client_mac?: string | null
  hotspot_login_context?: boolean | null
}

export interface AuthVerifyOtpResponseContract {
  access_token: string
  token_type: string
  hotspot_login_required?: boolean | null
  hotspot_username?: string | null
  hotspot_password?: string | null
  session_token?: string | null
  session_url?: string | null
}

export interface UserMeResponseContract {
  id: string
  phone_number: string
  full_name: string
  blok?: string | null
  kamar?: string | null
  is_tamping?: boolean | null
  tamping_type?: string | null
  role: ApiRole
  approval_status: ApiApprovalStatus
  is_active: boolean
  is_demo_user?: boolean | null
  is_blocked?: boolean | null
  blocked_reason?: string | null
  mikrotik_profile_name?: string | null
  is_unlimited_user?: boolean | null
  total_quota_purchased_mb?: number | null
  total_quota_used_mb?: number | null
  quota_expiry_date?: string | null
  created_at?: string | null
  updated_at?: string | null
  approved_at?: string | null
  last_login_at?: string | null
}

export interface UserProfileUpdateRequestContract {
  full_name?: string
  blok?: string | null
  kamar?: string | null
  is_tamping?: boolean | null
  tamping_type?: string | null
}

export interface UserDeviceContract {
  id: string
  mac_address: string
  ip_address?: string | null
  label?: string | null
  is_authorized: boolean
  created_at?: string | null
  updated_at?: string | null
  last_seen_at?: string | null
}

export interface DeviceListResponseContract {
  devices: UserDeviceContract[]
}

export interface DeviceBindResponseContract {
  success: boolean
  message: string
  device?: UserDeviceContract
}

export type PaymentMethodContract = 'qris' | 'gopay' | 'va' | 'shopeepay'
export type VaBankContract = 'bca' | 'bni' | 'bri' | 'mandiri' | 'permata' | 'cimb'

export interface TransactionInitiateRequestContract {
  package_id: string
  payment_method?: PaymentMethodContract | null
  va_bank?: VaBankContract | null
}

export interface TransactionDebtInitiateRequestContract {
  payment_method?: PaymentMethodContract | null
  va_bank?: VaBankContract | null
  manual_debt_id?: string | null
}

export interface TransactionInitiateResponseContract {
  order_id: string
  snap_token?: string | null
  redirect_url?: string | null
  provider_mode: 'snap' | 'core_api'
  status_token?: string | null
  status_url?: string | null
}

export type TransactionStatusContract =
  | 'SUCCESS'
  | 'PENDING'
  | 'FAILED'
  | 'EXPIRED'
  | 'CANCELLED'
  | 'ERROR'
  | 'UNKNOWN'

export interface TransactionPackageSummaryContract {
  id?: string
  name?: string
  description?: string | null
  price?: number | null
  data_quota_gb?: number | null
  is_unlimited?: boolean | null
}

export interface TransactionUserSummaryContract {
  id?: string | null
  phone_number?: string | null
  full_name?: string | null
  quota_expiry_date?: string | null
  is_unlimited_user?: boolean | null
}

export interface TransactionDetailResponseContract {
  id: string
  midtrans_order_id: string
  midtrans_transaction_id?: string | null
  status: TransactionStatusContract
  purpose?: 'purchase' | 'debt' | null
  debt_type?: 'auto' | 'manual' | null
  debt_mb?: number | null
  debt_note?: string | null
  amount?: number | null
  payment_method?: string | null
  snap_token?: string | null
  snap_redirect_url?: string | null
  deeplink_redirect_url?: string | null
  payment_time?: string | null
  expiry_time?: string | null
  va_number?: string | null
  payment_code?: string | null
  biller_code?: string | null
  qr_code_url?: string | null
  hotspot_password?: string | null
  package?: TransactionPackageSummaryContract | null
  user?: TransactionUserSummaryContract | null
}

export interface TransactionCancelResponseContract {
  success: boolean
  status: string
  message?: string | null
}

export interface ApiContractMap {
  'POST /auth/register': {
    request: AuthRegisterRequestContract
    response: AuthRegisterResponseContract
    error: ApiErrorEnvelope
  }
  'POST /auth/request-otp': {
    request: AuthRequestOtpRequestContract
    response: ApiMessageResponse
    error: ApiErrorEnvelope
  }
  'POST /auth/verify-otp': {
    request: AuthVerifyOtpRequestContract
    response: AuthVerifyOtpResponseContract
    error: ApiErrorEnvelope
  }
  'POST /auth/session/consume': {
    request: { token: string }
    response: AuthVerifyOtpResponseContract
    error: ApiErrorEnvelope
  }
  'GET /auth/me': {
    request: never
    response: UserMeResponseContract
    error: ApiErrorEnvelope
  }
  'PUT /auth/me/profile': {
    request: UserProfileUpdateRequestContract
    response: UserMeResponseContract
    error: ApiErrorEnvelope
  }
  'GET /users/me/profile': {
    request: never
    response: UserMeResponseContract
    error: ApiErrorEnvelope
  }
  'PUT /users/me/profile': {
    request: UserProfileUpdateRequestContract
    response: UserMeResponseContract
    error: ApiErrorEnvelope
  }
  'GET /users/me/devices': {
    request: never
    response: DeviceListResponseContract
    error: ApiErrorEnvelope
  }
  'POST /users/me/devices/bind-current': {
    request: { client_ip?: string | null; client_mac?: string | null }
    response: DeviceBindResponseContract
    error: ApiErrorEnvelope
  }
  'POST /transactions/initiate': {
    request: TransactionInitiateRequestContract
    response: TransactionInitiateResponseContract
    error: ApiErrorEnvelope
  }
  'POST /transactions/debt/initiate': {
    request: TransactionDebtInitiateRequestContract
    response: TransactionInitiateResponseContract
    error: ApiErrorEnvelope
  }
  'GET /transactions/by-order-id/{order_id}': {
    request: { order_id: string }
    response: TransactionDetailResponseContract
    error: ApiErrorEnvelope
  }
  'GET /transactions/public/by-order-id/{order_id}': {
    request: { order_id: string; t: string }
    response: TransactionDetailResponseContract
    error: ApiErrorEnvelope
  }
  'POST /transactions/{order_id}/cancel': {
    request: { order_id: string }
    response: TransactionCancelResponseContract
    error: ApiErrorEnvelope
  }
  'POST /transactions/public/{order_id}/cancel': {
    request: { order_id: string; t: string }
    response: TransactionCancelResponseContract
    error: ApiErrorEnvelope
  }
}
