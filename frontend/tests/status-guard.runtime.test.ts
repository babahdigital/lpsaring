import { beforeEach, describe, expect, it, vi } from 'vitest'

const navigateToMock = vi.fn()
let authStoreState: any
let verifyMock: any

vi.mock('#app', () => ({
  defineNuxtRouteMiddleware: (handler: any) => handler,
  navigateTo: (...args: any[]) => navigateToMock(...args),
  useRuntimeConfig: () => ({
    public: {
      statusPageGuardEnabled: 'true',
    },
  }),
  useNuxtApp: () => ({
    $api: verifyMock,
  }),
}))

vi.mock('~/store/auth', () => ({
  useAuthStore: () => authStoreState,
}))

vi.mock('~/utils/authRoutePolicy', () => ({
  isLegalPublicPath: (path: string) => path.startsWith('/merchant-center/privacy') || path.startsWith('/merchant-center/terms') || path.startsWith('/privacy') || path.startsWith('/terms'),
}))

describe('status-guard.global runtime', () => {
  beforeEach(() => {
    navigateToMock.mockReset()
    verifyMock = vi.fn().mockResolvedValue({ valid: false })
    authStoreState = {
      initialAuthCheckDone: true,
      initializeAuth: vi.fn().mockResolvedValue(undefined),
      currentUser: { id: 'u-1' },
      lastKnownUser: null,
      getAccessStatusFromUser: vi.fn().mockReturnValue('blocked'),
    }
  })

  it('never redirects legal terms/privacy paths', async () => {
    const middleware = (await import('../middleware/status-guard.global')).default

    await middleware({
      path: '/merchant-center/terms',
      fullPath: '/merchant-center/terms?from=beli',
      query: { from: 'beli' },
      meta: {},
    } as any)

    expect(navigateToMock).not.toHaveBeenCalled()
    expect(authStoreState.initializeAuth).not.toHaveBeenCalled()
    expect(verifyMock).not.toHaveBeenCalled()
  })

  it('redirects non-matching login status page to /login', async () => {
    const middleware = (await import('../middleware/status-guard.global')).default
    authStoreState.getAccessStatusFromUser = vi.fn().mockReturnValue('ok')

    await middleware({
      path: '/login/blocked',
      fullPath: '/login/blocked',
      query: {},
      meta: {},
    } as any)

    expect(navigateToMock).toHaveBeenCalledWith('/login', { replace: true })
  })
})
