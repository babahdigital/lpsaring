// Logging for admin routes without modifying route metadata
// Acts as a diagnostic tool to verify admin routes are properly protected

export default defineNuxtPlugin(() => {
  addRouteMiddleware(
    'admin-page-guard',
    (to) => {
      // Only apply to admin routes
      if (to.path.startsWith('/admin')) {
        // Log route detection without modifying metadata
        console.log('[ADMIN-PAGE-GUARD] Admin route detected:', to.path)

        // Log layout and role requirements as diagnostic info
        console.log('[ADMIN-PAGE-GUARD] Route metadata:', {
          layout: to.meta.layout || 'default',
          requiredRole: to.meta.requiredRole || 'none',
        })
      }

      // Always allow navigation to continue - actual protection happens in admin-only middleware
    },
    { global: true },
  )
})
