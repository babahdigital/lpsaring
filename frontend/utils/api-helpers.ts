// utils/api-helpers.ts
// Utilities for consistent API response handling

import type { User } from '@/types/user'

import { UserRole } from '@/types/enums'

/**
 * Extract a token from various possible API response formats
 * @param response - API response object that might contain token
 * @returns Token string or null if not found
 */
export function extractTokenFromResponse(response: any): string | null {
  if (!response)
    return null

  // Direct token properties
  if (response.token)
    return response.token
  if (response.access_token)
    return response.access_token

  // Nested token in data property (legacy format)
  if (response.data) {
    if (response.data.token)
      return response.data.token
    if (response.data.access_token)
      return response.data.access_token
  }

  return null
}

/**
 * Extract user data from various possible API response formats
 * @param response - API response object that might contain user data
 * @returns User object or null if not found
 */
export function extractUserFromResponse(response: any): User | null {
  if (!response)
    return null

  // Direct user property
  if (response.user)
    return response.user

  // Nested user in data property (legacy format)
  if (response.data && response.data.user)
    return response.data.user

  // If the whole response looks like a user object
  if (response.id && response.phone_number)
    return response as User

  return null
}

/**
 * Handle API errors consistently
 * @param error - Error object from API call
 * @param defaultMessage - Default message to use if no specific message is found
 * @returns Formatted error message
 */
export function handleApiError(error: any, defaultMessage: string): string {
  // Error from API with data property
  if (error.data) {
    if (error.data.message)
      return error.data.message
    if (error.data.error)
      return error.data.error
  }

  // Direct error properties
  if (error.message)
    return error.message
  if (error.error)
    return error.error

  // Status text if available
  if (error.statusText)
    return error.statusText

  return defaultMessage
}

/**
 * Validate if a user object has admin privileges
 * @param user - User object to check
 * @returns Boolean indicating if the user has admin privileges
 */
export function isAdminUser(user: User | null): boolean {
  if (!user)
    return false
  return user.role === UserRole.ADMIN || user.role === UserRole.SUPER_ADMIN
}
