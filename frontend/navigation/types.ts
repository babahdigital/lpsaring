// frontend/navigation/types.ts

// Tipe terpusat untuk semua item navigasi
export interface NavItem {
  title: string
  icon: { icon: string }
  to?: { name?: string, path?: string }
  children?: NavItem[]
  action?: string
  subject?: string
  disable?: boolean
  badgeContent?: string
  badgeClass?: string
}
