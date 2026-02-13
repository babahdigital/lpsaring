// frontend/middleware/role-checker.global.ts
import type { RouteLocationNormalized } from 'vue-router'
import { defineNuxtRouteMiddleware, navigateTo } from '#app'
import { useAuthStore } from '~/store/auth'

/**
 * Middleware untuk memvalidasi requiredRole di halaman admin.
 */
export default defineNuxtRouteMiddleware(async (to: RouteLocationNormalized) => {
  const authStore = useAuthStore()

  if (!authStore.initialAuthCheckDone)
    await authStore.initializeAuth()

  const requiredRoles = (to.meta.requiredRole as string[] | undefined) ?? []
  if (requiredRoles.length === 0)
    return

  if (!authStore.isLoggedIn)
    return

  const userRole = authStore.currentUser?.role
  const hasRole = userRole ? requiredRoles.includes(userRole) : false

  if (!hasRole) {
    const destination = authStore.isAdmin ? '/admin/dashboard' : '/dashboard'
    return navigateTo(destination, { replace: true })
  }
})
