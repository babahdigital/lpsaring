// types/api.ts
/**
 * Standardized API response types
 * Matches the backend response structure from api_response.py
 */

export interface NotificationType {
  id: string
  name: string
  description?: string
  enabled: boolean
  created_at: string
  updated_at: string
}

// These values must match the backend ApiErrorCode class
export enum ApiErrorCode {
  AUTHENTICATION_ERROR = 'AUTH_ERROR',
  AUTHORIZATION_ERROR = 'ACCESS_DENIED',
  VALIDATION_ERROR = 'VALIDATION_ERROR',
  RESOURCE_NOT_FOUND = 'NOT_FOUND',
  RESOURCE_ALREADY_EXISTS = 'ALREADY_EXISTS',
  RATE_LIMITED = 'RATE_LIMITED',
  SERVER_ERROR = 'SERVER_ERROR',
  CLIENT_DETECTION_ERROR = 'CLIENT_DETECTION_ERROR',
  MIKROTIK_ERROR = 'MIKROTIK_ERROR',
  DEVICE_ERROR = 'DEVICE_ERROR',
  OTP_ERROR = 'OTP_ERROR',
}

export interface ApiSuccessResponse<T> {
  success: true
  data: T
  message?: string
  meta?: Record<string, any>
}

export interface ApiErrorResponse {
  success: false
  message: string
  errorCode: ApiErrorCode
  data?: Record<string, any>
  meta?: Record<string, any>
}

export type ApiResponse<T = any> = ApiSuccessResponse<T> | ApiErrorResponse

export interface PaginatedData<T = any> {
  items: T[]
  pagination: {
    page: number
    per_page: number
    total_pages: number
    total_items: number
    has_prev: boolean
    has_next: boolean
    prev_num: number | null
    next_num: number | null
  }
}

export type PaginatedResponse<T = any> = ApiSuccessResponse<PaginatedData<T>>

// Type guard to check if a response is an error response
export function isApiErrorResponse(response: any): response is ApiErrorResponse {
  return response
    && typeof response === 'object'
    && response.success === false
    && typeof response.message === 'string'
}

// Type guard to check if a response is a success response
export function isApiSuccessResponse<T>(response: any): response is ApiSuccessResponse<T> {
  return response
    && typeof response === 'object'
    && response.success === true
    && 'data' in response
}

export interface WeeklyUsageResponse {
  success: boolean
  data: Array<{
    date: string
    usage_mb: number
  }>
}

export interface MonthlyUsageResponse {
  success: boolean
  data: Array<{
    month: string
    usage_mb: number
  }>
}
