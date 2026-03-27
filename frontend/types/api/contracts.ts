export {
  type GeneratedApiContractMap as ApiContractMap,
  type ErrorResponse as ApiErrorEnvelope,
  type ValidationErrorDetail as ApiErrorDetail,
  type MessageResponse as ApiMessageResponse,
  type AuthRegisterRequest as AuthRegisterRequestContract,
  type AuthRegisterResponse as AuthRegisterResponseContract,
  type AuthRequestOtpRequest as AuthRequestOtpRequestContract,
  type AuthVerifyOtpRequest as AuthVerifyOtpRequestContract,
  type AuthVerifyOtpResponse as AuthVerifyOtpResponseContract,
  type AuthHotspotSessionStatusResponse as AuthHotspotSessionStatusResponseContract,
  type UserProfileUpdateRequest as UserProfileUpdateRequestContract,
  type UserDevice as UserDeviceContract,
  type DeviceBindResponse as DeviceBindResponseContract,
  type TransactionInitiateRequest as TransactionInitiateRequestContract,
  type TransactionDebtInitiateRequest as TransactionDebtInitiateRequestContract,
  type TransactionInitiateResponse as TransactionInitiateResponseContract,
  type TransactionDetailResponse as TransactionDetailResponseContract,
  type TransactionCancelResponse as TransactionCancelResponseContract,
  type TransactionPackageSummary as TransactionPackageSummaryContract,
  type TransactionUserSummary as TransactionUserSummaryContract,
  type AdminUserListItem,
  type AdminUserListResponse,
  type AdminUserCreateRequest,
  type AdminUserUpdateRequest,
  type AdminUserMutationResponse,
  type SeedImportedUpdateSubmissionsRequest,
  type SeedImportedUpdateSubmissionsResponse,
  type AdminSettingsListResponse,
  type AdminSettingsUpdateRequest,
  type AdminQuotaRequestListResponse,
  type AdminQuotaRequestProcessRequest,
  type AdminTransactionListResponse,
  type AdminTransactionReconcileResponse,
  type AdminMetricsResponse,
  type AdminAccessParityResponse,
  type AccessParityItem,
  type AdminAccessParityFixRequest,
  type AdminAccessParityFixResponse,
  type AdminQuotaAdjustRequest,
  type AdminQuotaAdjustResponse,
  type AdminUserDebtItem,
  type AdminUserDebtSummary,
  type AdminUserDebtListResponse,
  type AdminDebtSettleItemResponse,
  type AdminDebtSettleAllResponse,
  type AdminDebtWhatsappQueueResponse,
  type AdminResetPasswordResponse,
  type AdminUserMikrotikStatusResponse,
  type AdminUserDetailSummaryMikrotik,
  type AdminUserDetailSummaryDebt,
  type AdminUserDetailSummaryPurchase,
  type AdminUserDetailSummaryResponse,
  type AdminUserDetailReportWhatsappRequest,
  type AdminUserDetailReportWhatsappRecipient,
  type AdminUserDetailReportWhatsappResponse,
  // quota-history/send-wa uses inline response type in GeneratedApiContractMap
  type PublicDatabaseUpdateSubmissionRequest,
  type PublicUpdateSubmissionStatusResponse,
  type PaymentAvailabilityResponse,
} from './contracts.generated'

import type {
  UserMeResponse,
  TransactionDetailResponse,
  TransactionInitiateRequest,
  TransactionDebtInitiateRequest,
} from './contracts.generated'

export type ApiRole = UserMeResponse['role']
export type ApiApprovalStatus = UserMeResponseContract['approval_status']
export type PaymentMethodContract = NonNullable<TransactionInitiateRequest['payment_method']>
export type VaBankContract = NonNullable<TransactionInitiateRequest['va_bank']>
export type TransactionStatusContract = TransactionDetailResponse['status']

export type UserMeApprovalStatusLegacy = UserMeResponse['approval_status'] | 'PENDING'
export type UserMeResponseContract = Omit<UserMeResponse, 'approval_status'> & {
  approval_status: UserMeApprovalStatusLegacy
  is_demo_user?: boolean | null
  is_blocked?: boolean | null
  blocked_reason?: string | null
}

export interface DeviceListResponseContract {
  devices: import('./contracts.generated').UserDevice[]
}

export type TransactionDetailResponsePublicContract = import('./contracts.generated').TransactionDetailResponsePublic

export type TransactionDebtInitiateRequestLegacyContract = TransactionDebtInitiateRequest

export type MikrotikVerifyRulesResponseContract = import('./contracts.generated').MikrotikVerifyRulesResponse
export type PaymentAvailabilityResponseContract = PaymentAvailabilityResponse
