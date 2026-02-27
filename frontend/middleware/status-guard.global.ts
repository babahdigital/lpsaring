import type { RouteLocationNormalized } from 'vue-router'
import { defineNuxtRouteMiddleware, navigateTo, useNuxtApp, useRuntimeConfig } from '#app'
import { useAuthStore } from '~/store/auth'
import { isLegalPublicPath } from '~/utils/authRoutePolicy'

const STATUS_PATHS: Record<string, 'blocked' | 'inactive' | 'expired' | 'habis' | 'fup'> = {
  '/policy/blocked': 'blocked',
  '/policy/inactive': 'inactive',
  '/policy/expired': 'expired',
  '/policy/habis': 'habis',
  '/policy/fup': 'fup',
  '/login/blocked': 'blocked',
  '/login/inactive': 'inactive',
  '/login/expired': 'expired',
  '/login/habis': 'habis',
  '/login/fup': 'fup',
  '/captive/blokir': 'blocked',
  '/captive/inactive': 'inactive',
  '/captive/expired': 'expired',
  '/captive/habis': 'habis',
  '/captive/fup': 'fup',
}

export default defineNuxtRouteMiddleware(async (to: RouteLocationNormalized) => {
  if (isLegalPublicPath(to.path))
    return

  const expectedStatus = STATUS_PATHS[to.path]
  if (!expectedStatus)
    return

  const config = useRuntimeConfig()
  const guardEnabled = String(config.public.statusPageGuardEnabled ?? 'false') === 'true'
  if (!guardEnabled)
    return

  const authStore = useAuthStore()
  if (!authStore.initialAuthCheckDone)
    await authStore.initializeAuth({ path: to.path, query: to.query as any })

  const user = authStore.currentUser ?? authStore.lastKnownUser
  const actualStatus = authStore.getAccessStatusFromUser(user)

  if (actualStatus === expectedStatus)
    return

  const statusParam = typeof to.query.status === 'string' ? to.query.status : null
  const sigParam = typeof to.query.sig === 'string' ? to.query.sig : null
  if (statusParam === expectedStatus && sigParam) {
    try {
      const { $api } = useNuxtApp()
      const result = await $api<{ valid: boolean }>('/auth/status-token/verify', {
        method: 'POST',
        body: {
          status: statusParam,
          token: sigParam,
        },
      })
      if (result?.valid === true)
        return
    }
    catch {
      // Ignore verify errors and fallback to redirect
    }
  }

  const fallbackPath = to.path.startsWith('/captive') ? '/captive' : '/login'
  return navigateTo(fallbackPath, { replace: true })
})
