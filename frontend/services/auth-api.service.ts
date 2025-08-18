// services/auth-api.service.ts
// Centralized service for all auth-related API calls

import type { AuthResponse, DeviceSyncResponse, RoleVerificationResponse, UserInfoResponse } from '@/types/api-responses'
import type { RegistrationPayload, VerifyOtpPayload } from '@/types/auth'
import type { User } from '@/types/user'

import { extractUserFromResponse } from '@/utils/api-helpers'

// Type for the $api function from NuxtApp
type ApiFunction = <T = any>(
  url: string,
  options?: {
    method?: string
    body?: any
    headers?: Record<string, string>
    onResponseError?: (context: { response: any }) => void
  }
) => Promise<T>

export class AuthApiService {
  constructor(private $api: ApiFunction) { }

  /**
   * Get current user information
   * @returns User object or null if not authenticated
   */
  async getCurrentUser(): Promise<User | null> {
    try {
      const response = await this.$api<UserInfoResponse>('auth/me')
      return extractUserFromResponse(response)
    }
    catch (error) {
      console.error('[AUTH-API] Error fetching user data:', error)
      return null
    }
  }

  /**
   * Verify user role with backend
   * @returns Role verification response
   */
  async verifyRole(): Promise<RoleVerificationResponse> {
    try {
      return await this.$api<RoleVerificationResponse>('/auth/verify-role', {
        method: 'GET',
        headers: { 'Content-Type': 'application/json' },
      })
    }
    catch (error) {
      console.error('[AUTH-API] Error verifying role:', error)
      return {
        status: 'ERROR',
        isAdmin: false,
        message: 'Failed to verify role',
      }
    }
  }

  /**
   * Admin login
   * @param username Admin username
   * @param password Admin password
   * @returns Auth response with token and user data
   */
  async adminLogin(username: string, password: string): Promise<AuthResponse> {
    return await this.$api<AuthResponse>('/auth/admin/login', {
      method: 'POST',
      body: { username, password },
    })
  }

  /**
   * Register a new user
   * @param payload Registration payload
   * @returns Success status
   */
  async registerUser(payload: RegistrationPayload): Promise<boolean> {
    await this.$api('/auth/register', { method: 'POST', body: payload })
    return true
  }

  /**
   * Verify OTP code
   * @param payload OTP verification payload
   * @returns Auth response with token and user data
   */
  async verifyOtp(payload: VerifyOtpPayload): Promise<AuthResponse> {
    return await this.$api<AuthResponse>('/auth/verify-otp', {
      method: 'POST',
      body: payload,
    })
  }

  /**
   * Request a new OTP code
   * @param phoneNumber User's phone number
   * @returns Success status
   */
  async requestOtp(phoneNumber: string): Promise<boolean> {
    await this.$api('/auth/request-otp', {
      method: 'POST',
      body: { phone_number: phoneNumber },
    })
    return true
  }

  /**
   * Authorize a new device
   * @param clientIp Client IP address
   * @param clientMac Client MAC address
   * @returns Success status
   */
  async authorizeDevice(clientIp: string, clientMac: string): Promise<boolean> {
    await this.$api('/auth/authorize-device', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: { client_ip: clientIp, client_mac: clientMac },
    })
    return true
  }

  /**
   * Sync device with backend
   * @param ip Client IP address
   * @param mac Client MAC address
   * @returns Device sync response
   */
  async syncDevice(ip: string | null, mac: string | null): Promise<DeviceSyncResponse> {
    return await this.$api<DeviceSyncResponse>('/auth/sync-device', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: { ip, mac },
    })
  }
}
