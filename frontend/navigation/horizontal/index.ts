// frontend/navigation/horizontal/index.ts

import { useAuthStore } from '@/store/auth'

// Impor semua set menu modular
import userMenu from './user'
import komandanMenu from './komandan'
import adminMenu from './admin'
import superAdminMenu from './superadmin'
import commonMenu from './common'

interface HorizontalNavItem {
  title: string
  icon: { icon: string }
  to?: { name?: string; path?: string }
  children?: HorizontalNavItem[]
}

export const getHorizontalNavItems = (): HorizontalNavItem[] => {
  const authStore = useAuthStore()

  if (!authStore.isLoggedIn)
    return []

  let roleSpecificMenu: HorizontalNavItem[] = []

  // Langkah 1: Tentukan menu spesifik berdasarkan peran
  if (authStore.isSuperAdmin) {
    roleSpecificMenu = [...adminMenu, ...superAdminMenu]
  }
  else if (authStore.isAdmin) {
    roleSpecificMenu = adminMenu
  }
  // [PENYEMPURNAAN] Tambahkan kondisi untuk Komandan
  else if (authStore.isKomandan) {
    roleSpecificMenu = komandanMenu
  }
  else {
    // Pengguna biasa akan mendapatkan menu default
    roleSpecificMenu = userMenu
  }

  // Langkah 2: Gabungkan menu spesifik peran dengan menu bersama
  return [...roleSpecificMenu, ...commonMenu]
}