// types/user.ts

import type { ApprovalStatus, UserRole } from './enums'

/* -------------------------------------------------------------------------- */
/* MODEL INTI                                                                 */
/* -------------------------------------------------------------------------- */
export interface User {
  id: string
  phone_number: string
  full_name: string | null
  // Mark role as potentially undefined to handle backend responses that might not include it
  role: UserRole | undefined
  approval_status: ApprovalStatus
  is_active: boolean
  is_blocked: boolean
  blok: string | null
  kamar: string | null
  total_quota_purchased_mb: number | null
  total_quota_used_mb: number | null
  is_unlimited_user: boolean
  quota_expiry_date: string | null
  is_quota_finished?: boolean
  hotspot_username?: string | null
  mikrotik_server_name?: string | null
  mikrotik_profile_name?: string | null
  device_brand: string | null
  device_model: string | null
  client_ip: string | null
  client_mac: string | null
  last_login_mac: string | null
  blocking_reason: string | null
  created_at: string
  updated_at: string
  approved_at: string | null
  last_login_at: string | null
  last_sync_time?: string | null

  // Device verification status properties
  device_mismatch?: boolean
  requires_device_auth?: boolean

  // Backend response properties that might be included
  status?: string
  message?: string
  token?: string
  access_token?: string
}

/* -------------------------------------------------------------------------- */
/* UTILITAS PENGGUNA                                                          */
/* -------------------------------------------------------------------------- */
export interface LoginHistory {
  login_time: string
  ip_address: string | null
  mac_address: string | null
  user_agent_string: string | null
}

export interface ChangePasswordRequest {
  current_password: string
  new_password: string
}

/* -------------------------------------------------------------------------- */
/* GENERIC API RESPONSE                                                       */
/* -------------------------------------------------------------------------- */
export interface ApiResponse<T> {
  success: boolean
  message?: string
  data: T
}

/* -------------------------------------------------------------------------- */
/* DATA PENGGUNAAN (QUOTA)                                                    */
/* -------------------------------------------------------------------------- */
export type WeeklyUsageData = number[]

export interface MonthlyUsageItem {
  month_year: string // 'YYYY-MM'
  usage_mb: number
}
export type MonthlyUsageData = MonthlyUsageItem

/* -------------------------------------------------------------------------- */
/* RESPONSE SPESIFIK                                                          */
/* -------------------------------------------------------------------------- */
export type WeeklyUsageResponse = ApiResponse<WeeklyUsageData>

export interface MonthlyUsageResponse extends ApiResponse<MonthlyUsageData[]> {
  monthly_data?: MonthlyUsageData[]
}
