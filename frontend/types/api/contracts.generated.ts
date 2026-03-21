/* eslint-disable */
// AUTO-GENERATED FILE. DO NOT EDIT MANUALLY.
// Source: contracts/openapi/openapi.v1.yaml

export const OPENAPI_SOURCE_SHA256 = '31cc1c933bdf3a88005c38df66f1f42649272e364a2458ecb2be76dd0f4b8b35' as const
export const API_CONTRACT_REVISION = 'openapi-1.0.0' as const

export type MessageResponse = { message: string }
export type ErrorResponse = { code: string; message: string; details?: Array<ValidationErrorDetail>; request_id?: string }
export type ValidationErrorDetail = { loc?: Array<string | number>; msg?: string; type?: string }
export type PaymentAvailabilityResponse = { available: boolean; message: string | null; reason: string | null; circuit_name: string; circuit_state: 'closed' | 'open' | 'half_open' | 'unknown'; retry_after_seconds: number; checked_at: string | null; checked_at_display: string | null; open_until: string | null; open_until_display: string | null }
export type AuthRegisterRequest = { phone_number: string; full_name: string; blok?: string | null; kamar?: string | null; is_tamping?: boolean; tamping_type?: string | null; register_as_komandan?: boolean }
export type AuthRegisterResponse = { message: string; user_id: string; phone_number: string }
export type AuthRequestOtpRequest = { phone_number: string }
export type AuthVerifyOtpRequest = { phone_number: string; otp: string; client_ip?: string | null; client_mac?: string | null; hotspot_login_context?: boolean | null; confirm_device_takeover?: boolean | null }
export type AuthAutoLoginRequest = { client_ip?: string | null; client_mac?: string | null }
export type StatusTokenVerifyRequest = { status: string; token: string }
export type StatusTokenVerifyResponse = { valid: boolean }
export type AuthVerifyOtpResponse = { access_token: string; token_type: string; hotspot_login_required?: boolean | null; hotspot_binding_active?: boolean | null; hotspot_username?: string | null; hotspot_password?: string | null; session_token?: string | null; session_url?: string | null }
export type AuthHotspotSessionStatusResponse = { hotspot_login_required: boolean; hotspot_binding_active?: boolean | null }
export type UserMeResponse = { id: string; phone_number: string; full_name: string; blok?: string | null; kamar?: string | null; is_tamping?: boolean | null; tamping_type?: string | null; role: 'USER' | 'KOMANDAN' | 'ADMIN' | 'SUPER_ADMIN'; approval_status: 'PENDING_APPROVAL' | 'APPROVED' | 'REJECTED'; is_active: boolean; is_unlimited_user?: boolean | null; total_quota_purchased_mb?: number | null; total_quota_used_mb?: number | null; quota_expiry_date?: string | null; created_at?: string | null; updated_at?: string | null; approved_at?: string | null; last_login_at?: string | null }
export type UserProfileUpdateRequest = { full_name?: string; blok?: string | null; kamar?: string | null; is_tamping?: boolean | null; tamping_type?: string | null }
export type UserDevice = { id: string; mac_address: string; ip_address?: string | null; label?: string | null; is_authorized: boolean; created_at?: string | null; updated_at?: string | null; last_seen_at?: string | null }
export type DeviceBindResponse = { success: boolean; message: string; device?: UserDevice }
export type UserQuotaDebtItem = { id: string; debt_date?: string | null; amount_mb: number; paid_mb: number; remaining_mb: number; is_paid: boolean; paid_at?: string | null; note?: string | null; created_at?: string | null }
export type UserQuotaDebtListResponse = { success: boolean; items: Array<UserQuotaDebtItem> }
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
export type SeedImportedUpdateSubmissionsRequest = { test_phone?: string | null; dry_run?: boolean | null }
export type SeedImportedUpdateSubmissionsResponse = { seeded_count: number; skipped_count: number; seeded_phones?: Array<string>; skipped_phones?: Array<string> }
export type PublicDatabaseUpdateSubmissionRequest = { full_name: string; role: 'USER' | 'KOMANDAN' | 'TAMPING'; blok?: string | null; kamar?: string | null; tamping_type?: string | null; phone_number: string }
export type PublicUpdateSubmissionStatusResponse = { success: boolean; status: 'none' | 'reviewing' | 'approved' }
export type SettingItem = { key: string; value: string | number | boolean | null; description?: string | null }
export type AdminSettingsListResponse = { items: Array<SettingItem> }
export type AdminSettingsUpdateRequest = { items: Array<{ key: string; value: string | number | boolean | null }> }
export type AdminQuotaRequestItem = { id: string; user_id: string; request_type: 'QUOTA' | 'UNLIMITED'; requested_mb?: number | null; requested_days?: number | null; status: 'PENDING' | 'APPROVED' | 'REJECTED'; note?: string | null; requested_at: string }
export type AdminQuotaRequestListResponse = { items: Array<AdminQuotaRequestItem> }
export type AdminQuotaRequestProcessRequest = { action: 'approve' | 'reject'; approved_mb?: number | null; approved_days?: number | null; note?: string | null }
export type AdminTransactionListResponse = { items: Array<TransactionDetailResponse>; meta: PaginationMeta }
export type AdminTransactionBillRequest = { user_id: string; package_id: string; payment_method?: 'qris' | 'gopay' | 'va' | 'shopeepay' | null; va_bank?: 'bca' | 'bni' | 'bri' | 'mandiri' | 'permata' | 'cimb' | null }
export type AdminTransactionBillResponse = { message: string; order_id: string; status: string; status_url?: string | null; whatsapp_sent?: boolean | null }
export type AdminTransactionReconcileResponse = { message: string; transaction_status: string; midtrans_status: string; quota_applied: boolean; whatsapp_sent: boolean }
export type AdminQuotaAdjustRequest = { set_purchased_mb?: number | null; set_used_mb?: number | null; reason: string }
export type AdminQuotaAdjustResponse = { message: string; total_quota_purchased_mb: number; total_quota_used_mb: number; remaining_mb: number }
export type AdminUserDebtItem = { id: string; debt_date?: string | null; due_date?: string | null; amount_mb: number; paid_mb: number; remaining_mb: number; is_paid: boolean; paid_at?: string | null; note?: string | null; price_rp?: number | null; estimated_rp: number; created_at: string; updated_at: string; last_paid_source?: string | null }
export type AdminUserDebtSummary = { manual_debt_mb: number; open_items: number; paid_items: number; total_items: number }
export type AdminUserDebtListResponse = { items: Array<AdminUserDebtItem>; summary: AdminUserDebtSummary }
export type AdminDebtSettleItemResponse = { message: string; paid_mb: number; unblocked: boolean; receipt_url?: string | null }
export type AdminDebtSettleAllResponse = { message: string; paid_auto_mb: number; paid_manual_mb: number; debt_auto_before_mb: number; debt_manual_before_mb: number; unblocked: boolean; receipt_url?: string | null }
export type AdminDebtWhatsappQueueResponse = { message: string; queued: boolean }
export type AdminUserMikrotikStatusResponse = { user_id: string; exists_on_mikrotik: boolean; live_available: boolean; message: string; reason?: string | null; details?: { [key: string]: unknown } | null; resolved_profile_name: string; database_profile_name?: string | null; derived_profile_name: string; db_quota_purchased_mb: number; db_quota_used_mb: number; db_quota_remaining_mb: number }
export type AdminUserDetailSummaryMikrotik = { live_available: boolean; exists_on_mikrotik: boolean; message: string; reason?: string | null }
export type AdminUserDetailSummaryDebt = { auto_mb: number; manual_mb: number; total_mb: number; open_items: number }
export type AdminUserDetailSummaryPurchase = { order_id: string; package_name: string; amount?: number; amount_display: string; paid_at?: string | null; paid_at_display: string; payment_method: string }
export type AdminUserDetailSummaryResponse = { mikrotik: AdminUserDetailSummaryMikrotik; profile_display_name: string; profile_source: string; mikrotik_account_label: string; mikrotik_account_hint: string; access_status_label: string; access_status_hint: string; access_status_tone: string; device_count: number; device_count_label: string; last_login_label: string; debt: AdminUserDetailSummaryDebt; recent_purchases: Array<AdminUserDetailSummaryPurchase>; purchase_count_30d: number; purchase_total_amount_30d: number; purchase_total_amount_30d_display: string; admin_whatsapp_default: string }
export type AdminUserDetailReportWhatsappRequest = { recipient_phone?: string | null }
export type AdminMetricsReliabilitySignals = { payment_idempotency_degraded?: boolean; hotspot_sync_lock_degraded?: boolean; policy_parity_degraded?: boolean }
export type AdminMetricsResponse = { metrics?: { [key: string]: number }; reliability_signals?: AdminMetricsReliabilitySignals }
export type AccessParityItem = { user_id: string; phone_number: string; mac: string; ip?: string | null; app_status: string; expected_binding_type: string; actual_binding_type?: string | null; address_list_statuses: Array<string>; mismatches: Array<string> }
export type AccessParitySummary = { users: number; mismatches: number }
export type AdminAccessParityResponse = { items: Array<AccessParityItem>; summary: AccessParitySummary }
export type AdminAccessParityFixRequest = { user_id: string; mac?: string | null; ip?: string | null }
export type AdminAccessParityFixResponse = { message: string; user_id: string; mac?: string | null; resolved_ip?: string | null; expected_binding_type: string; binding_updated: boolean; address_list_synced: boolean }
export type MikrotikRuleCheck = { label: string; found: boolean }
export type MikrotikVerifyRulesResponse = { status: 'ok' | 'error'; all_found: boolean; total_filter_rules: number; total_raw_rules: number; checks: Array<MikrotikRuleCheck> }

export interface GeneratedApiContractMap {
  'GET /admin/metrics/access-parity': {
    request: never
    response: AdminAccessParityResponse
    error: ErrorResponse
  }
  'POST /admin/metrics/access-parity/fix': {
    request: AdminAccessParityFixRequest
    response: AdminAccessParityFixResponse
    error: ErrorResponse
  }
  'GET /admin/mikrotik/verify-rules': {
    request: never
    response: MikrotikVerifyRulesResponse
    error: ErrorResponse
  }
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
  'POST /admin/transactions/bill': {
    request: AdminTransactionBillRequest
    response: AdminTransactionBillResponse
    error: ErrorResponse
  }
  'GET /admin/transactions/{order_id}/detail': {
    request: never
    response: TransactionDetailResponse
    error: ErrorResponse
  }
  'GET /admin/transactions/{order_id}/reconcile': {
    request: never
    response: AdminMetricsResponse
    error: ErrorResponse
  }
  'POST /admin/transactions/{order_id}/reconcile': {
    request: never
    response: AdminTransactionReconcileResponse
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
  'GET /admin/users/debt-settlements/temp/{token}.pdf': {
    request: never
    response: unknown
    error: ErrorResponse
  }
  'GET /admin/users/debts/temp/{token}.pdf': {
    request: never
    response: unknown
    error: ErrorResponse
  }
  'GET /admin/users/detail-report/temp/{token}.pdf': {
    request: never
    response: unknown
    error: ErrorResponse
  }
  'POST /admin/users/seed-imported-update-submissions': {
    request: SeedImportedUpdateSubmissionsRequest
    response: SeedImportedUpdateSubmissionsResponse
    error: ErrorResponse
  }
  'PUT /admin/users/{user_id}': {
    request: AdminUserUpdateRequest
    response: AdminUserMutationResponse
    error: ErrorResponse
  }
  'GET /admin/users/{user_id}/debts': {
    request: never
    response: AdminUserDebtListResponse
    error: ErrorResponse
  }
  'POST /admin/users/{user_id}/debts/send-whatsapp': {
    request: never
    response: AdminDebtWhatsappQueueResponse
    error: ErrorResponse
  }
  'POST /admin/users/{user_id}/debts/settle-all': {
    request: never
    response: AdminDebtSettleAllResponse
    error: ErrorResponse
  }
  'POST /admin/users/{user_id}/debts/{debt_id}/settle': {
    request: never
    response: AdminDebtSettleItemResponse
    error: ErrorResponse
  }
  'GET /admin/users/{user_id}/detail-report/export': {
    request: never
    response: unknown
    error: ErrorResponse
  }
  'POST /admin/users/{user_id}/detail-report/send-whatsapp': {
    request: AdminUserDetailReportWhatsappRequest
    response: AdminDebtWhatsappQueueResponse
    error: ErrorResponse
  }
  'GET /admin/users/{user_id}/detail-summary': {
    request: never
    response: AdminUserDetailSummaryResponse
    error: ErrorResponse
  }
  'GET /admin/users/{user_id}/mikrotik-status': {
    request: never
    response: AdminUserMikrotikStatusResponse
    error: ErrorResponse
  }
  'POST /admin/users/{user_id}/quota-adjust': {
    request: AdminQuotaAdjustRequest
    response: AdminQuotaAdjustResponse
    error: ErrorResponse
  }
  'POST /auth/admin/login': {
    request: { username: string; password: string }
    response: AuthVerifyOtpResponse
    error: ErrorResponse
  }
  'POST /auth/auto-login': {
    request: AuthAutoLoginRequest
    response: AuthVerifyOtpResponse
    error: ErrorResponse
  }
  'GET /auth/hotspot-session-status': {
    request: never
    response: AuthHotspotSessionStatusResponse
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
  'POST /auth/status-token/verify': {
    request: StatusTokenVerifyRequest
    response: StatusTokenVerifyResponse
    error: ErrorResponse
  }
  'POST /auth/verify-otp': {
    request: AuthVerifyOtpRequest
    response: AuthVerifyOtpResponse
    error: ErrorResponse
  }
  'GET /settings/payment-availability': {
    request: never
    response: PaymentAvailabilityResponse
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
  'POST /users/database-update-submissions': {
    request: PublicDatabaseUpdateSubmissionRequest
    response: MessageResponse
    error: ErrorResponse
  }
  'GET /users/database-update-submissions/status': {
    request: never
    response: PublicUpdateSubmissionStatusResponse
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
  'GET /users/me/quota-debts': {
    request: never
    response: UserQuotaDebtListResponse
    error: ErrorResponse
  }
}
