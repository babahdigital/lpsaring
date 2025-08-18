// composables/useAdminAccess.ts
import { useAuthStore } from '~/store/auth'
import { UserRole } from '~/types/enums'

export function useAdminAccess() {
  const authStore = useAuthStore()
  const { $api } = useNuxtApp()
  const router = useRouter()

  /**
   * Check if user has admin access with role verification
   */
  async function verifyAdminAccess(): Promise<boolean> {
    // First check store
    if (authStore.isAdmin) {
      console.log('[ADMIN-ACCESS] Admin status confirmed from store')
      return true
    }

    // Check localStorage as backup
    const isAdminInLocalStorage = localStorage.getItem('is_admin_user') === 'true'
    console.log('[ADMIN-ACCESS] Admin status - store:', authStore.isAdmin, 'localStorage:', isAdminInLocalStorage)

    // If admin flag in localStorage but not in store, verify with backend
    if (isAdminInLocalStorage) {
      console.log('[ADMIN-ACCESS] Potential admin role inconsistency, verifying with backend')

      try {
        const roleVerification = await $api('/auth/verify-role', {
          method: 'GET',
          headers: { 'Content-Type': 'application/json' },
        })

        if (roleVerification?.isAdmin === true || roleVerification?.role === 'ADMIN' || roleVerification?.role === 'SUPER_ADMIN') {
          console.log('[ADMIN-ACCESS] Backend confirmed admin role')

          // Update store if we have user data
          if (authStore.user) {
            // Determine the specific admin role
            const roleToSet = roleVerification?.role === 'SUPER_ADMIN'
              ? UserRole.SUPER_ADMIN
              : UserRole.ADMIN

            authStore.setUser({
              ...authStore.user,
              role: roleToSet,
            })
            return true
          }
        }
        else {
          console.warn('[ADMIN-ACCESS] Backend did not confirm admin role')
          // Clear incorrect localStorage flag
          localStorage.removeItem('is_admin_user')
        }
      }
      catch (error) {
        console.error('[ADMIN-ACCESS] Error verifying role with backend:', error)
      }
    }

    // Final check after potential backend verification
    return authStore.isAdmin
  }

  /**
   * Check if the user has the required roles for a page
   */
  function hasRequiredRoles(requiredRoles: string[] | undefined): boolean {
    if (!requiredRoles || requiredRoles.length === 0)
      return true

    const userRole = authStore.user?.role

    // Super admins can access everything
    if (userRole === 'SUPER_ADMIN')
      return true

    // For other users, check their role against required roles
    return Boolean(userRole && requiredRoles.includes(userRole))
  }

  /**
   * Redirect to appropriate page if access is denied
   */
  function redirectIfNotAdmin() {
    router.replace('/dashboard')
  }

  /**
   * Redirect if user doesn't have required role
   */
  function redirectToAppropriateDashboard() {
    const destination = authStore.isAdmin ? '/admin/dashboard' : '/dashboard'
    router.replace(destination)
  }

  return {
    verifyAdminAccess,
    hasRequiredRoles,
    redirectIfNotAdmin,
    redirectToAppropriateDashboard,
  }
}
