// frontend/navigation/horizontal/index.ts

import { useAuthStore } from '@/store/auth'

// Impor semua set menu modular
import userMenu from './user'
import adminMenu from './admin'
import superAdminMenu from './superadmin'
import commonMenu from './common'

// PENYEMPURNAAN: Memperbarui interface untuk mendukung child menu
// Ini adalah pusat dari perbaikan.
interface HorizontalNavItem {
  title: string
  icon: { icon: string }
  to?: { name?: string; path?: string } // Menjadi opsional dengan tanda '?'
  children?: HorizontalNavItem[] // Properti baru yang opsional, berisi array dari item itu sendiri
}

export const getHorizontalNavItems = (): HorizontalNavItem[] => {
  const authStore = useAuthStore()
  
  if (!authStore.isLoggedIn) {
    return []
  }

  let roleSpecificMenu: HorizontalNavItem[] = []

  // Langkah 1: Tentukan menu spesifik berdasarkan peran
  if (authStore.isSuperAdmin) {
    // Gabungkan menu admin dan super admin untuk Super Admin
    roleSpecificMenu = [...adminMenu, ...superAdminMenu]
  }
  else if (authStore.isAdmin) {
    roleSpecificMenu = adminMenu
  }
  else {
    roleSpecificMenu = userMenu
  }
  
  // Langkah 2: Gabungkan menu spesifik peran dengan menu bersama
  // TypeScript tidak akan error lagi karena `roleSpecificMenu` sekarang menerima objek dengan `children`.
  return [...roleSpecificMenu, ...commonMenu]
}