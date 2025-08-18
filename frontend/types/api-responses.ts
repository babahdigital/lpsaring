// types/api-responses.ts
// Standardized API response types to match backend response structures

import type { User } from './user'

/**
 * Base API Response interface that all API responses extend
 */
export interface BaseApiResponse {
  status: 'SUCCESS' | 'ERROR' | string
  message?: string
}

/**
 * Generic success response with data
 */
export interface SuccessResponse<T = any> extends BaseApiResponse {
  status: 'SUCCESS'
  data?: T
}

/**
 * Error response structure
 */
export interface ErrorResponse extends BaseApiResponse {
  status: 'ERROR'
  error_code?: string
  error?: string | any
}

/**
 * Authentication responses
 */
export interface AuthResponse extends BaseApiResponse {
  token?: string
  access_token?: string
  user?: User
  // Support for legacy response format with data property
  data?: {
    token?: string
    access_token?: string
    user?: User
  }
}

/**
 * Role verification response
 */
export interface RoleVerificationResponse extends BaseApiResponse {
  isAdmin: boolean
  role?: string
}

/**
 * User data response from /auth/me
 */
export interface UserInfoResponse extends BaseApiResponse {
  user: User
}

/**
 * Device sync response
 */
export interface DeviceSyncResponse extends BaseApiResponse {
  status: 'DEVICE_VALID' | 'DEVICE_UNREGISTERED' | 'DEVICE_NOT_FOUND' | 'THROTTLED' | 'RATE_LIMITED' | 'ERROR'
  retry_after?: number
  message?: string
  error?: any
  ip?: string
}
