// middleware/03-role-checker.global.ts
// Simplified role checking middleware using centralized admin access logic

import { useAdminAccess } from '~/composables/useAdminAccess'
import { useAuthStore } from '~/store/auth'

export default defineNuxtRouteMiddleware(async (to) => {
  // Skip on server-side to avoid hydration issues
  if (typeof window === 'undefined')
    return

  // Get required roles from page meta
  const requiredRoles = to.meta.requiredRole as string[] | undefined

  // Only proceed if page has role requirements
  if (requiredRoles?.length) {
    const authStore = useAuthStore()
    const { hasRequiredRoles, verifyAdminAccess, redirectToAppropriateDashboard: _redirectToAppropriateDashboard } = useAdminAccess()

    console.log('[ROLE-MIDDLEWARE] Page requires roles:', requiredRoles)
    console.log('[ROLE-MIDDLEWARE] Current user:', authStore.user?.role, 'isAdmin:', authStore.isAdmin)

    // If path is admin but user may not have proper role, verify with backend
    if (to.path.startsWith('/admin') && !authStore.isAdmin) {
      await verifyAdminAccess()
    }

    // Check if user has required roles using the composable
    if (authStore.isLoggedIn && !hasRequiredRoles(requiredRoles)) {
      console.log('[ROLE-MIDDLEWARE] User lacks required role, redirecting')

      // Don't redirect if already on the fallback destination
      const destination = authStore.isAdmin ? '/admin/dashboard' : '/dashboard'
      if (to.path !== destination) {
        return navigateTo(destination, { replace: true })
      }
    }
  }
})
