// frontend/types/api/settings.ts

export interface SettingSchema {
  setting_key: string
  setting_value: string | null
  description: string | null
  is_encrypted: boolean
}
