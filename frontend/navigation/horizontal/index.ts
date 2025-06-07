// frontend/navigation/horizontal/index.ts

import { useAuthStore } from '@/store/auth'

// Impor semua set menu modular, termasuk yang baru
import userMenu from './user'
import adminMenu from './admin'
import superAdminMenu from './superadmin'
import commonMenu from './common' // <-- Impor menu bersama

// Definisikan interface di sini sebagai pusat
interface HorizontalNavItem {
  title: string
  to: { name?: string; path?: string }
  icon: { icon: string }
}

export const getHorizontalNavItems = (): HorizontalNavItem[] => {
  const authStore = useAuthStore()
  
  if (!authStore.isLoggedIn) {
    return []
  }

  let roleSpecificMenu: HorizontalNavItem[] = []

  // Langkah 1: Tentukan menu spesifik berdasarkan peran
  if (authStore.isSuperAdmin) {
    roleSpecificMenu = [...adminMenu, ...superAdminMenu]
  }
  else if (authStore.isAdmin) {
    roleSpecificMenu = adminMenu
  }
  else {
    roleSpecificMenu = userMenu
  }
  
  // Langkah 2: Gabungkan menu spesifik peran dengan menu bersama
  return [...roleSpecificMenu, ...commonMenu]
}