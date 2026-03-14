// frontend/types/user.ts

// Basis untuk semua respons API
interface BaseResponse {
  success?: boolean
  message?: string
  error_code?: string
}

export interface UserQuotaResponse extends BaseResponse {
  total_quota_purchased_mb: number
  total_quota_used_mb: number
  remaining_mb: number
  quota_debt_auto_mb?: number
  quota_debt_manual_mb?: number
  quota_debt_total_mb?: number
  quota_debt_total_estimated_rp?: number
  hotspot_username?: string | null
  last_sync_time?: string | null
  is_unlimited_user?: boolean
  quota_expiry_date?: string | null
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
  period?: Period
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

export interface QuotaHistoryDeviceDelta {
  mac_address?: string | null
  ip_address?: string | null
  label?: string | null
  delta_mb?: number | null
  delta_display?: string | null
  host_id?: string | null
  uptime_seconds?: number | null
  source_address?: string | null
  to_address?: string | null
}

export interface QuotaHistoryRebaselineEvent {
  mac_address?: string | null
  ip_address?: string | null
  label?: string | null
  reason?: string | null
  reason_label?: string | null
  host_id?: string | null
  previous_host_id?: string | null
}

export interface QuotaHistoryItem {
  id: string
  source: string
  category: string
  title: string
  description: string
  created_at?: string | null
  created_at_display?: string | null
  actor_name?: string | null
  deltas: {
    purchased_mb?: number | null
    used_mb?: number | null
    debt_total_mb?: number | null
    remaining_before_mb?: number | null
    remaining_after_mb?: number | null
  }
  deltas_display: {
    purchased?: string | null
    used?: string | null
    debt_total?: string | null
    remaining_before?: string | null
    remaining_after?: string | null
  }
  highlights: string[]
  device_deltas?: QuotaHistoryDeviceDelta[]
  rebaseline_events?: QuotaHistoryRebaselineEvent[]
  event_details?: Record<string, any>
}

export interface QuotaHistorySummary {
  page_items: number
  usage_events: number
  purchase_events: number
  debt_events: number
  policy_events: number
  total_net_purchased_mb: number
  total_net_used_mb: number
  first_event_at?: string | null
  last_event_at?: string | null
  first_event_at_display?: string | null
  last_event_at_display?: string | null
}

export interface QuotaHistoryResponse extends BaseResponse {
  items: QuotaHistoryItem[]
  summary: QuotaHistorySummary | null
  totalItems: number
  page: number
  itemsPerPage: number
}
