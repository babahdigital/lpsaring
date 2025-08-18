// Auto-generated lightweight interfaces aligning with backend models.
// If backend models change, regenerate accordingly.

export interface UserDevice {
  id: number
  user_id: number
  mac_address: string
  ip_address?: string | null
  last_seen_at?: string | null // ISO timestamp
}

export interface User {
  id: number
  username: string
  full_name?: string | null
  is_active: boolean
  created_at: string
  updated_at?: string | null
  devices?: UserDevice[]
}

export interface AddressListAudit {
  id: number
  created_at: string
  action: string
  mac_address?: string | null
  ip_address?: string | null
  notes?: string | null
}

export interface QuotaRequest {
  id: number
  user_id: number
  requested_at: string
  amount: number
  status: 'pending' | 'approved' | 'rejected'
}

export interface PromoEvent {
  id: number
  name: string
  starts_at: string
  ends_at?: string | null
  metadata?: Record<string, any>
}

export interface MetricsBrief {
  mac_lookup_total: number
  failure_ratio: number
  grace_cache_size: number
  duration_ms_sum: number
  supports_seconds_histogram: boolean
}

export interface ApiVersionInfo {
  version: string
  features: Record<string, boolean>
}

export interface UserDevicesSummary {
  user_id: number
  devices: Array<Pick<UserDevice, 'mac_address' | 'ip_address' | 'last_seen_at'>>
  last_seen_at?: string | null
}
