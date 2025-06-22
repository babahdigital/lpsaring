// frontend/types/user.ts

// Basis untuk semua respons API
interface BaseResponse {
  success: boolean
  message?: string
  error_code?: string
}

export interface UserQuotaResponse extends BaseResponse {
  total_quota_purchased_mb: number
  total_quota_used_mb: number
  remaining_mb: number
  hotspot_username?: string | null
  last_sync_time?: string | null
}

export interface UserProfile {
  id: string // Diubah menjadi string untuk kompatibilitas frontend
  username: string
  email: string | null
  phone_number: string
  full_name: string | null
  is_admin: boolean
  picture_url: string | null
}

export interface Period {
  start_date: string // Format ISO 8601
  end_date: string // Format ISO 8601
}

export interface WeeklyUsageResponse extends BaseResponse {
  period: Period
  weekly_data: number[]
}

export interface MonthlyUsageData {
  month_year: string
  usage_mb: number
}

export interface MonthlyUsageResponse extends BaseResponse {
  monthly_data: MonthlyUsageData[]
}

export interface UserProfileResponse extends BaseResponse {
  phone_number: string
  full_name: string | null
  created_at: string
}
