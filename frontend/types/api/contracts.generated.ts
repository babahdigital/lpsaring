 
// AUTO-GENERATED FILE. DO NOT EDIT MANUALLY.
// Source: contracts/openapi/openapi.v1.yaml

export const OPENAPI_SOURCE_SHA256 = '3547665c920b980db94f8a92734b20d554e2e68ae7829627b140184af540b54b' as const
export const API_CONTRACT_REVISION = 'openapi-1.0.0' as const

export type MessageResponse = { message: string }
export type ErrorResponse = { code: string; message: string; details?: Array<ValidationErrorDetail>; request_id?: string }
export type ValidationErrorDetail = { loc?: Array<string | number>; msg?: string; type?: string }
export type AuthRegisterRequest = { phone_number: string; full_name: string; blok?: string | null; kamar?: string | null; is_tamping?: boolean; tamping_type?: string | null; register_as_komandan?: boolean }
export type AuthRegisterResponse = { message: string; user_id: string; phone_number: string }
export type AuthRequestOtpRequest = { phone_number: string }
export type AuthVerifyOtpRequest = { phone_number: string; otp: string; client_ip?: string | null; client_mac?: string | null; hotspot_login_context?: boolean | null }
export type AuthVerifyOtpResponse = { access_token: string; token_type: string; hotspot_login_required?: boolean | null; hotspot_username?: string | null; hotspot_password?: string | null; session_token?: string | null; session_url?: string | null }
export type UserMeResponse = { id: string; phone_number: string; full_name: string; blok?: string | null; kamar?: string | null; is_tamping?: boolean | null; tamping_type?: string | null; role: 'USER' | 'KOMANDAN' | 'ADMIN' | 'SUPER_ADMIN'; approval_status: 'PENDING_APPROVAL' | 'APPROVED' | 'REJECTED'; is_active: boolean; is_unlimited_user?: boolean | null; total_quota_purchased_mb?: number | null; total_quota_used_mb?: number | null; quota_expiry_date?: string | null; created_at?: string | null; updated_at?: string | null; approved_at?: string | null; last_login_at?: string | null }
export type UserProfileUpdateRequest = { full_name?: string; blok?: string | null; kamar?: string | null; is_tamping?: boolean | null; tamping_type?: string | null }
export type UserDevice = { id: string; mac_address: string; ip_address?: string | null; label?: string | null; is_authorized: boolean; created_at?: string | null; updated_at?: string | null; last_seen_at?: string | null }
export type DeviceBindResponse = { success: boolean; message: string; device?: UserDevice }
export type TransactionInitiateRequest = { package_id: string; payment_method?: 'qris' | 'gopay' | 'va' | 'shopeepay' | null; va_bank?: 'bca' | 'bni' | 'bri' | 'mandiri' | 'permata' | 'cimb' | null }
export type TransactionDebtInitiateRequest = { payment_method?: 'qris' | 'gopay' | 'va' | 'shopeepay' | null; va_bank?: 'bca' | 'bni' | 'bri' | 'mandiri' | 'permata' | 'cimb' | null; manual_debt_id?: string | null }
export type TransactionInitiateResponse = { order_id: string; snap_token?: string | null; redirect_url?: string | null; provider_mode: 'snap' | 'core_api'; status_token?: string | null; status_url?: string | null }
export type TransactionPackageSummary = { id?: string; name?: string; description?: string | null; price?: number | null; data_quota_gb?: number | null; is_unlimited?: boolean | null } | null
export type TransactionUserSummary = { id?: string | null; phone_number?: string | null; full_name?: string | null; quota_expiry_date?: string | null; is_unlimited_user?: boolean | null } | null
export type TransactionDetailResponse = { id: string; midtrans_order_id: string; midtrans_transaction_id?: string | null; status: 'SUCCESS' | 'PENDING' | 'FAILED' | 'EXPIRED' | 'CANCELLED' | 'ERROR' | 'UNKNOWN'; purpose?: 'purchase' | 'debt' | null; debt_type?: 'auto' | 'manual' | null; debt_mb?: number | null; debt_note?: string | null; amount?: number | null; payment_method?: string | null; snap_token?: string | null; snap_redirect_url?: string | null; deeplink_redirect_url?: string | null; payment_time?: string | null; expiry_time?: string | null; va_number?: string | null; payment_code?: string | null; biller_code?: string | null; qr_code_url?: string | null; hotspot_password?: string | null; package?: TransactionPackageSummary; user?: TransactionUserSummary }
export type TransactionDetailResponsePublic = TransactionDetailResponse & { hotspot_password?: string | null }
export type TransactionCancelResponse = { success: boolean; status: string; message?: string | null }
export type AdminUserListItem = UserMeResponse & { profile_name?: string | null; quota_debt_total_mb?: number | null }
export type PaginationMeta = { page: number; per_page: number; total: number }
export type AdminUserListResponse = { items: Array<AdminUserListItem>; meta: PaginationMeta }
export type AdminUserCreateRequest = { phone_number: string; full_name: string; role?: 'USER' | 'KOMANDAN' | 'ADMIN' | 'SUPER_ADMIN'; blok?: string | null; kamar?: string | null; is_tamping?: boolean | null; tamping_type?: string | null }
export type AdminUserUpdateRequest = { full_name?: string; role?: 'USER' | 'KOMANDAN' | 'ADMIN' | 'SUPER_ADMIN'; is_active?: boolean; approval_status?: 'PENDING_APPROVAL' | 'APPROVED' | 'REJECTED'; is_blocked?: boolean | null; blocked_reason?: string | null; blok?: string | null; kamar?: string | null }
export type AdminUserMutationResponse = { message: string; user: UserMeResponse }
export type SettingItem = { key: string; value: string | number | boolean | null; description?: string | null }
export type AdminSettingsListResponse = { items: Array<SettingItem> }
export type AdminSettingsUpdateRequest = { items: Array<{ key: string; value: string | number | boolean | null }> }
export type AdminQuotaRequestItem = { id: string; user_id: string; request_type: 'QUOTA' | 'UNLIMITED'; requested_mb?: number | null; requested_days?: number | null; status: 'PENDING' | 'APPROVED' | 'REJECTED'; note?: string | null; requested_at: string }
export type AdminQuotaRequestListResponse = { items: Array<AdminQuotaRequestItem> }
export type AdminQuotaRequestProcessRequest = { action: 'approve' | 'reject'; approved_mb?: number | null; approved_days?: number | null; note?: string | null }
export type AdminTransactionListResponse = { items: Array<TransactionDetailResponse>; meta: PaginationMeta }

export interface GeneratedApiContractMap {
  'GET /admin/quota-requests': {
    request: never
    response: AdminQuotaRequestListResponse
    error: ErrorResponse
  }
  'POST /admin/quota-requests/{request_id}/process': {
    request: AdminQuotaRequestProcessRequest
    response: MessageResponse
    error: ErrorResponse
  }
  'GET /admin/settings': {
    request: never
    response: AdminSettingsListResponse
    error: ErrorResponse
  }
  'PUT /admin/settings': {
    request: AdminSettingsUpdateRequest
    response: MessageResponse
    error: ErrorResponse
  }
  'GET /admin/transactions': {
    request: never
    response: AdminTransactionListResponse
    error: ErrorResponse
  }
  'GET /admin/transactions/{order_id}/detail': {
    request: never
    response: TransactionDetailResponse
    error: ErrorResponse
  }
  'GET /admin/users': {
    request: never
    response: AdminUserListResponse
    error: ErrorResponse
  }
  'POST /admin/users': {
    request: AdminUserCreateRequest
    response: AdminUserMutationResponse
    error: ErrorResponse
  }
  'PUT /admin/users/{user_id}': {
    request: AdminUserUpdateRequest
    response: AdminUserMutationResponse
    error: ErrorResponse
  }
  'GET /auth/me': {
    request: never
    response: UserMeResponse
    error: ErrorResponse
  }
  'PUT /auth/me/profile': {
    request: UserProfileUpdateRequest
    response: UserMeResponse
    error: ErrorResponse
  }
  'POST /auth/register': {
    request: AuthRegisterRequest
    response: AuthRegisterResponse
    error: ErrorResponse
  }
  'POST /auth/request-otp': {
    request: AuthRequestOtpRequest
    response: MessageResponse
    error: ErrorResponse
  }
  'POST /auth/session/consume': {
    request: { token: string }
    response: AuthVerifyOtpResponse
    error: ErrorResponse
  }
  'POST /auth/verify-otp': {
    request: AuthVerifyOtpRequest
    response: AuthVerifyOtpResponse
    error: ErrorResponse
  }
  'GET /transactions/by-order-id/{order_id}': {
    request: never
    response: TransactionDetailResponse
    error: ErrorResponse
  }
  'POST /transactions/debt/initiate': {
    request: TransactionDebtInitiateRequest
    response: TransactionInitiateResponse
    error: ErrorResponse
  }
  'POST /transactions/initiate': {
    request: TransactionInitiateRequest
    response: TransactionInitiateResponse
    error: ErrorResponse
  }
  'GET /transactions/public/by-order-id/{order_id}': {
    request: never
    response: TransactionDetailResponsePublic
    error: ErrorResponse
  }
  'POST /transactions/public/{order_id}/cancel': {
    request: never
    response: TransactionCancelResponse
    error: ErrorResponse
  }
  'GET /transactions/public/{order_id}/qr': {
    request: never
    response: string
    error: ErrorResponse
  }
  'POST /transactions/{order_id}/cancel': {
    request: never
    response: TransactionCancelResponse
    error: ErrorResponse
  }
  'GET /transactions/{order_id}/qr': {
    request: never
    response: string
    error: ErrorResponse
  }
  'GET /users/me/devices': {
    request: never
    response: { devices: Array<UserDevice> }
    error: ErrorResponse
  }
  'POST /users/me/devices/bind-current': {
    request: { client_ip?: string; client_mac?: string }
    response: DeviceBindResponse
    error: ErrorResponse
  }
  'DELETE /users/me/devices/{device_id}': {
    request: never
    response: MessageResponse
    error: ErrorResponse
  }
  'PUT /users/me/devices/{device_id}/label': {
    request: { label: string }
    response: MessageResponse
    error: ErrorResponse
  }
  'GET /users/me/profile': {
    request: never
    response: UserMeResponse
    error: ErrorResponse
  }
  'PUT /users/me/profile': {
    request: UserProfileUpdateRequest
    response: UserMeResponse
    error: ErrorResponse
  }
}
