// middleware/admin-only.ts
// Simplified admin access middleware using centralized access control

import { useAdminAccess } from '~/composables/useAdminAccess'

export default defineNuxtRouteMiddleware(async (to) => {
  // Skip on server-side
  if (typeof window === 'undefined')
    return

  console.log('[ADMIN-ONLY] Checking admin access...')

  // Use the centralized admin access composable
  const { verifyAdminAccess, hasRequiredRoles, redirectIfNotAdmin: _redirectIfNotAdmin } = useAdminAccess()

  // Verify admin access with backend check if needed
  const isAdmin = await verifyAdminAccess()

  // Deny access if not admin
  if (!isAdmin) {
    console.log('[ADMIN-ONLY] Access denied, redirecting to user dashboard')
    return navigateTo('/dashboard', { replace: true })
  }

  // Check for required roles in page meta
  const requiredRoles = to.meta.requiredRole as string[] | undefined
  if (requiredRoles && requiredRoles.length > 0) {
    if (!hasRequiredRoles(requiredRoles)) {
      console.log('[ADMIN-ONLY] User role does not match required roles for this page')
      return navigateTo('/admin/dashboard', { replace: true })
    }
  }

  console.log('[ADMIN-ONLY] Access granted to admin route')
})
