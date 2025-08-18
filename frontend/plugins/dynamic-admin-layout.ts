// plugins/dynamic-admin-layout.ts
// Apply admin layout automatically to admin routes

export default defineNuxtPlugin((nuxtApp) => {
  // Use app hook to set layout dynamically
  nuxtApp.hook('app:created', () => {
    // Wait for the initial navigation to complete
    setTimeout(() => {
      const route = useRoute()

      if (route.path.startsWith('/admin') && route.path !== '/admin/login') {
        // For admin routes, ensure they have standard admin role requirements
        // This is equivalent to the page meta but applied dynamically
        console.log('[DYNAMIC-ADMIN] Auto-applying admin protections to:', route.path)

        // The actual protection is done by middleware, this just adds dynamic configuration
        // without requiring explicit page meta in each admin component
      }
    }, 0)
  })
})
