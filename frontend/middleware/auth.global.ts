// frontend/middleware/auth.global.ts
import type { RouteLocationNormalized } from 'vue-router'
import { defineNuxtRouteMiddleware, navigateTo, useNuxtApp } from '#app'
import { useAuthStore } from '~/store/auth'

export default defineNuxtRouteMiddleware(async (to: RouteLocationNormalized) => {
  const authStore = useAuthStore()
  const nuxtApp = useNuxtApp()

  // 1. Abaikan path API atau internal Nuxt
  const ignoredPrefixes = ['/api/', '/_nuxt/', '/__nuxt_error', '/.well-known/']
  if (ignoredPrefixes.some(prefix => to.path.startsWith(prefix))) {
    return
  }

  // 2. Pastikan store auth sudah diinisialisasi
  if (!authStore.isInitialized) {
    await authStore.initializeAuth()
  }

  // 3. Definisikan jenis-jenis rute
  const isTargetingAdminRoute = to.path.startsWith('/admin')
  const adminLoginPath = '/admin'
  const isTargetingAdminLoginPage = to.path === adminLoginPath
  const userLoginPath = '/login'
  const publicPaths = [userLoginPath, '/register']
  const isTargetingPublicUserRoute = publicPaths.some(p => to.path.startsWith(p))

  // Opsi navigasi standar
  const navigationOptions = { replace: true, external: false }
  const canNavigate = import.meta.client || !nuxtApp.isHydrating

  // ==========================================================
  // LOGIKA UTAMA MIDDLEWARE
  // ==========================================================

  // --- KASUS 1: PENGGUNA BELUM LOGIN ---
  if (!authStore.isLoggedIn) {
    if (isTargetingAdminRoute && !isTargetingAdminLoginPage) {
      if (canNavigate) return navigateTo(adminLoginPath, navigationOptions)
      return
    }
    if (!isTargetingAdminRoute && !isTargetingPublicUserRoute) {
      if (canNavigate) return navigateTo({ path: userLoginPath, query: { redirect: to.fullPath } }, navigationOptions)
      return
    }
    return
  }

  // --- KASUS 2: PENGGUNA SUDAH LOGIN ---
  if (authStore.isLoggedIn) {
    const isAdmin = authStore.isAdmin
    const userRole = authStore.user?.role
    const isUserApprovedAndActive = authStore.isUserApprovedAndActive
    
    // --- PENAMBAHAN: Logika Pengecekan Role ---
    const requiredRoles = to.meta.requiredRole as string[] | undefined
    if (requiredRoles && requiredRoles.length > 0) {
      // Jika rute memerlukan role, tapi pengguna bukan admin atau rolenya tidak cocok
      if (!isAdmin || !userRole || !requiredRoles.includes(userRole)) {
        // Arahkan ke halaman yang tidak diizinkan atau dashboard
        if (canNavigate) return navigateTo('/dashboard', navigationOptions)
        return
      }
    }
    // --- AKHIR PENAMBAHAN ---

    // A. Jika Pengguna adalah ADMIN
    if (isAdmin) {
      if (isTargetingPublicUserRoute || isTargetingAdminLoginPage) {
        if (canNavigate) return navigateTo('/admin/dashboard', navigationOptions)
        return
      }
      return
    }
    
    // B. Jika Pengguna BUKAN ADMIN (pengguna biasa)
    if (!isAdmin) {
      if (isTargetingAdminRoute) {
        if (canNavigate) return navigateTo('/dashboard', navigationOptions)
        return
      }
      if (isTargetingPublicUserRoute) {
        if (canNavigate) return navigateTo('/dashboard', navigationOptions)
        return
      }
      if (!isUserApprovedAndActive) {
        if (canNavigate) return navigateTo({ path: userLoginPath, query: { message: 'account_pending_or_issue' } }, navigationOptions)
        return
      }
      return
    }
  }
})