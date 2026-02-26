import { beforeEach, describe, expect, it, vi } from 'vitest'

const navigateToMock = vi.fn()
let authStoreState: any

vi.mock('#app', () => ({
  defineNuxtRouteMiddleware: (handler: any) => handler,
  navigateTo: (...args: any[]) => navigateToMock(...args),
}))

vi.mock('../store/auth', () => ({
  useAuthStore: () => authStoreState,
}))

describe('auth.global runtime', () => {
  beforeEach(() => {
    navigateToMock.mockReset()
    authStoreState = {
      initialAuthCheckDone: true,
      initializeAuth: vi.fn().mockResolvedValue(undefined),
      isLoggedIn: false,
      isAdmin: false,
      isKomandan: false,
      currentUser: null,
      lastKnownUser: null,
      getAccessStatusFromUser: vi.fn().mockReturnValue('ok'),
    }
  })

  it('redirects guest protected user path to login with encoded redirect', async () => {
    const middleware = (await import('../middleware/auth.global')).default

    await middleware({
      path: '/dashboard',
      fullPath: '/dashboard?tab=usage',
      query: {},
      meta: {},
    } as any)

    expect(navigateToMock).toHaveBeenCalledWith('/login?redirect=%2Fdashboard%3Ftab%3Dusage', { replace: true })
  })

  it('allows expired user to open payment finish without redirect', async () => {
    const middleware = (await import('../middleware/auth.global')).default
    authStoreState.isLoggedIn = true
    authStoreState.getAccessStatusFromUser = vi.fn().mockReturnValue('expired')

    await middleware({
      path: '/payment/finish',
      fullPath: '/payment/finish?order_id=ORDER-1',
      query: { order_id: 'ORDER-1' },
      meta: {},
    } as any)

    expect(navigateToMock).not.toHaveBeenCalled()
  })

  it('redirects logged-in non-admin away from admin area', async () => {
    const middleware = (await import('../middleware/auth.global')).default
    authStoreState.isLoggedIn = true

    await middleware({
      path: '/admin/dashboard',
      fullPath: '/admin/dashboard',
      query: {},
      meta: {},
    } as any)

    expect(navigateToMock).toHaveBeenCalledWith('/dashboard', { replace: true })
  })

  it('resolves safe redirect query when logged in and visiting guest route', async () => {
    const middleware = (await import('../middleware/auth.global')).default
    authStoreState.isLoggedIn = true

    await middleware({
      path: '/',
      fullPath: '/?redirect=%2Friwayat',
      query: { redirect: '/riwayat' },
      meta: {},
    } as any)

    expect(navigateToMock).toHaveBeenCalledWith('/riwayat', { replace: true })
  })

  it('runs initializeAuth when initial check not done', async () => {
    const middleware = (await import('../middleware/auth.global')).default
    authStoreState.initialAuthCheckDone = false

    await middleware({
      path: '/login',
      fullPath: '/login',
      query: {},
      meta: {},
    } as any)

    expect(authStoreState.initializeAuth).toHaveBeenCalledWith({ path: '/login', query: {} })
  })

  it('never redirects legal privacy path regardless of user status', async () => {
    const middleware = (await import('../middleware/auth.global')).default
    authStoreState.isLoggedIn = true
    authStoreState.getAccessStatusFromUser = vi.fn().mockReturnValue('blocked')

    await middleware({
      path: '/merchant-center/privacy',
      fullPath: '/merchant-center/privacy?from=beli',
      query: { from: 'beli' },
      meta: {},
    } as any)

    expect(navigateToMock).not.toHaveBeenCalled()
  })

  it('keeps legal terms path open with from=beli for non-ok user without auth init', async () => {
    const middleware = (await import('../middleware/auth.global')).default
    authStoreState.initialAuthCheckDone = false
    authStoreState.isLoggedIn = true
    authStoreState.getAccessStatusFromUser = vi.fn().mockReturnValue('expired')

    await middleware({
      path: '/merchant-center/terms',
      fullPath: '/merchant-center/terms?from=beli',
      query: { from: 'beli' },
      meta: {},
    } as any)

    expect(navigateToMock).not.toHaveBeenCalled()
    expect(authStoreState.initializeAuth).not.toHaveBeenCalled()
  })
})
