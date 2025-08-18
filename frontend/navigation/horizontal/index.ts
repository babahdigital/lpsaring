// frontend/navigation/horizontal/index.ts

import type { ComputedRef } from 'vue'

import { computed } from 'vue'

// [PERBAIKAN] Mengimpor "cetak biru" atau tipe data NavItem dari file types.ts
// Ini menyelesaikan error "Cannot find name 'NavItem'".
import type { NavItem } from '@/navigation/types'

import { useAuthStore } from '~/store/auth'
import { UserRole } from '~/types/enums'

// [PERBAIKAN] Mengimpor semua modul "penyedia data" menu.
// Ini menyelesaikan error "Cannot find name 'commonMenu'" dan potensi error serupa lainnya.
import adminMenu from './admin'
import commonMenu from './common'
import komandanMenu from './komandan'
import superAdminMenu from './superadmin'
import userMenu from './user'

export function useHorizontalNav() {
  const authStore = useAuthStore()

  // Tipe ComputedRef<NavItem[]> sekarang valid karena NavItem sudah diimpor.
  const navItems: ComputedRef<NavItem[]> = computed(() => {
    // Debug info untuk membantu memahami kondisi menu
    console.log('Menu navigation check:', {
      isAuthCheckDone: authStore.isAuthCheckDone,
      isLoggedIn: authStore.isLoggedIn,
      hasCurrentUser: !!authStore.currentUser,
      userRole: authStore.currentUser?.role,
    })

    // 1. Tunggu hingga pengecekan otentikasi awal selesai.
    if (!authStore.isAuthCheckDone) {
      console.log('Menu not shown: Auth check not done yet')
      return []
    }

    // 2. Setelah pengecekan selesai, periksa apakah user sudah login.
    if (!authStore.isLoggedIn || !authStore.currentUser) {
      console.log('Menu not shown: User not logged in or no user data')
      return []
    }

    // 3. Bangun menu berdasarkan peran (role) pengguna.
    let roleSpecificMenu: NavItem[] = []
    const userRole = authStore.currentUser.role

    console.log(`Building menu for user role: ${userRole}`)
    console.log('Available menus:', {
      admin: adminMenu.length,
      superAdmin: superAdminMenu.length,
      komandan: komandanMenu.length,
      user: userMenu.length,
      common: commonMenu.length,
    })

    if (userRole === UserRole.SUPER_ADMIN) {
      console.log('Using SUPER_ADMIN menu')
      roleSpecificMenu = [...adminMenu, ...superAdminMenu]
    }
    else if (userRole === UserRole.ADMIN) {
      console.log('Using ADMIN menu')
      roleSpecificMenu = adminMenu
    }
    else if (userRole === UserRole.KOMANDAN) {
      console.log('Using KOMANDAN menu')
      roleSpecificMenu = komandanMenu
    }
    else {
      console.log('Using USER menu')
      roleSpecificMenu = userMenu
    }

    // 4. Gabungkan menu spesifik peran dengan menu umum.
    const finalMenu = [...roleSpecificMenu, ...commonMenu]

    // Temporary debug - akan dihapus nanti
    console.log('🎯 Final navigation menu:', {
      roleSpecificCount: roleSpecificMenu.length,
      commonCount: commonMenu.length,
      totalCount: finalMenu.length,
      items: finalMenu.map(item => ({ title: item.title, to: item.to })),
    })

    return finalMenu
  })

  return {
    navItems,
  }
}
