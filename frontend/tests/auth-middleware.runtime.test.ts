import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const navigateToMock = vi.fn()
const apiMock = vi.fn()
let authStoreState: any

function createSessionStorageMock(initial: Record<string, string> = {}) {
  const store = new Map<string, string>(Object.entries(initial))
  return {
    getItem: (key: string) => (store.has(key) ? store.get(key)! : null),
    setItem: (key: string, value: string) => {
      store.set(key, String(value))
    },
    removeItem: (key: string) => {
      store.delete(key)
    },
    clear: () => {
      store.clear()
    },
  }
}

function createLocalStorageMock(initial: Record<string, string> = {}) {
  const store = new Map<string, string>(Object.entries(initial))
  return {
    getItem: (key: string) => (store.has(key) ? store.get(key)! : null),
    setItem: (key: string, value: string) => {
      store.set(key, String(value))
    },
    removeItem: (key: string) => {
      store.delete(key)
    },
    clear: () => {
      store.clear()
    },
  }
}

vi.mock('#app', () => ({
  defineNuxtRouteMiddleware: (handler: any) => handler,
  navigateTo: (...args: any[]) => navigateToMock(...args),
  useNuxtApp: () => ({
    $api: (...args: any[]) => apiMock(...args),
  }),
}))

vi.mock('../store/auth', () => ({
  useAuthStore: () => authStoreState,
}))

describe('auth.global runtime', () => {
  beforeEach(() => {
    navigateToMock.mockReset()
    apiMock.mockReset()
    apiMock.mockResolvedValue({
      hotspot_login_required: false,
      hotspot_binding_active: null,
    })
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

  afterEach(() => {
    vi.unstubAllGlobals()
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

  it('allows guest to open public payment status route without redirect', async () => {
    const middleware = (await import('../middleware/auth.global')).default

    await middleware({
      path: '/payment/status',
      fullPath: '/payment/status?order_id=ORDER-1&t=token-1',
      query: {
        order_id: 'ORDER-1',
        t: 'token-1',
      },
      meta: {
        auth: false,
        public: true,
      },
    } as any)

    expect(navigateToMock).not.toHaveBeenCalled()
  })

  it('redirects guest hotspot context to captive while preserving login hint', async () => {
    const middleware = (await import('../middleware/auth.global')).default

    await middleware({
      path: '/login',
      fullPath: '/login?client_ip=172.16.2.10&client_mac=AA:BB:CC:DD:EE:FF&link_login_only=http%3A%2F%2Flogin.home.arpa%2Flogin',
      query: {
        client_ip: '172.16.2.10',
        client_mac: 'AA:BB:CC:DD:EE:FF',
        link_login_only: 'http://login.home.arpa/login',
      },
      meta: {},
    } as any)

    expect(navigateToMock).toHaveBeenCalledWith('/captive?client_ip=172.16.2.10&client_mac=AA%3ABB%3ACC%3ADD%3AEE%3AFF&link_login_only=http%3A%2F%2Flogin.home.arpa%2Flogin', { replace: true })
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

  it('blocks dashboard path when captive context is active', async () => {
    const middleware = (await import('../middleware/auth.global')).default
    authStoreState.isLoggedIn = true
    authStoreState.currentUser = { id: 'u-1', role: 'USER' }
    authStoreState.getAccessStatusFromUser = vi.fn().mockReturnValue('ok')

    vi.stubGlobal('window', {
      sessionStorage: createSessionStorageMock({
        captive_context_active: '1',
      }),
    } as any)

    await middleware({
      path: '/dashboard',
      fullPath: '/dashboard',
      query: {},
      meta: {},
    } as any)

    expect(navigateToMock).toHaveBeenCalledWith('/captive/terhubung', { replace: true })
  })

  it('allows dashboard path for fup user even when captive context is active', async () => {
    const middleware = (await import('../middleware/auth.global')).default
    authStoreState.isLoggedIn = true
    authStoreState.currentUser = { id: 'u-1', role: 'USER' }
    authStoreState.getAccessStatusFromUser = vi.fn().mockReturnValue('fup')

    vi.stubGlobal('window', {
      sessionStorage: createSessionStorageMock({
        captive_context_active: '1',
      }),
    } as any)

    await middleware({
      path: '/dashboard',
      fullPath: '/dashboard',
      query: {},
      meta: {},
    } as any)

    expect(navigateToMock).not.toHaveBeenCalled()
  })

  it('allows quota purchase path for fup user even when captive context is active', async () => {
    const middleware = (await import('../middleware/auth.global')).default
    authStoreState.isLoggedIn = true
    authStoreState.currentUser = { id: 'u-1', role: 'USER' }
    authStoreState.getAccessStatusFromUser = vi.fn().mockReturnValue('fup')

    vi.stubGlobal('window', {
      sessionStorage: createSessionStorageMock({
        captive_context_active: '1',
      }),
    } as any)

    await middleware({
      path: '/beli',
      fullPath: '/beli',
      query: {},
      meta: {},
    } as any)

    expect(navigateToMock).not.toHaveBeenCalled()
  })

  it('allows quota purchase path for expired/habis user even when captive context is active', async () => {
    const middleware = (await import('../middleware/auth.global')).default
    authStoreState.isLoggedIn = true
    authStoreState.currentUser = { id: 'u-1', role: 'USER' }

    vi.stubGlobal('window', {
      sessionStorage: createSessionStorageMock({
        captive_context_active: '1',
      }),
    } as any)

    for (const status of ['expired', 'habis']) {
      navigateToMock.mockReset()
      authStoreState.getAccessStatusFromUser = vi.fn().mockReturnValue(status)

      await middleware({
        path: '/beli',
        fullPath: '/beli',
        query: {},
        meta: {},
      } as any)

      expect(navigateToMock).not.toHaveBeenCalled()
    }
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

  it('redirects logged-in user on login route to hotspot-required when hotspot session is still required', async () => {
    const middleware = (await import('../middleware/auth.global')).default
    authStoreState.isLoggedIn = true
    apiMock.mockResolvedValue({
      hotspot_login_required: true,
      hotspot_binding_active: false,
    })

    await middleware({
      path: '/login',
      fullPath: '/login?client_ip=172.16.2.10&client_mac=AA:BB:CC:DD:EE:FF&link_login_only=http%3A%2F%2Flogin.home.arpa%2Flogin',
      query: {
        client_ip: '172.16.2.10',
        client_mac: 'AA:BB:CC:DD:EE:FF',
        link_login_only: 'http://login.home.arpa/login',
      },
      meta: {},
    } as any)

    expect(apiMock).toHaveBeenCalledWith('/auth/hotspot-session-status', {
      method: 'GET',
      query: {
        client_ip: '172.16.2.10',
        client_mac: 'AA:BB:CC:DD:EE:FF',
      },
    })
    expect(navigateToMock).toHaveBeenCalledWith('/login/hotspot-required?client_ip=172.16.2.10&client_mac=AA%3ABB%3ACC%3ADD%3AEE%3AFF&link_login_only=http%3A%2F%2Flogin.home.arpa%2Flogin&auto_start=1', { replace: true })
  })

  it('routes logged-in login visits with only remembered mikrotik hint into auto-start hotspot recovery', async () => {
    const middleware = (await import('../middleware/auth.global')).default
    authStoreState.isLoggedIn = true

    const localStorageMock = createLocalStorageMock({
      'lpsaring:last-mikrotik-login-link': 'http://login.home.arpa/login',
    })

    vi.stubGlobal('window', {
      document: {
        referrer: '',
      },
      localStorage: localStorageMock,
      sessionStorage: createSessionStorageMock(),
    } as any)
    vi.stubGlobal('localStorage', localStorageMock)

    await middleware({
      path: '/login',
      fullPath: '/login',
      query: {},
      meta: {},
    } as any)

    expect(apiMock).not.toHaveBeenCalled()
    expect(navigateToMock).toHaveBeenCalledWith('/login/hotspot-required?link_login_only=http%3A%2F%2Flogin.home.arpa%2Flogin&auto_start=1', { replace: true })
  })

  it('does not redirect to hotspot-required when hotspot session already active', async () => {
    const middleware = (await import('../middleware/auth.global')).default
    authStoreState.isLoggedIn = true
    apiMock.mockResolvedValue({
      hotspot_login_required: true,
      hotspot_binding_active: true,
    })

    await middleware({
      path: '/login',
      fullPath: '/login?client_ip=172.16.2.10&client_mac=AA:BB:CC:DD:EE:FF',
      query: {
        client_ip: '172.16.2.10',
        client_mac: 'AA:BB:CC:DD:EE:FF',
      },
      meta: {},
    } as any)

    expect(apiMock).toHaveBeenCalledTimes(1)
    expect(navigateToMock).toHaveBeenCalledWith('/dashboard', { replace: true })
  })

  it('falls back to normal guard redirect when hotspot status check fails', async () => {
    const middleware = (await import('../middleware/auth.global')).default
    authStoreState.isLoggedIn = true
    apiMock.mockRejectedValue(new Error('network down'))

    await middleware({
      path: '/login',
      fullPath: '/login?client_ip=172.16.2.11&client_mac=AA:BB:CC:DD:EE:11',
      query: {
        client_ip: '172.16.2.11',
        client_mac: 'AA:BB:CC:DD:EE:11',
      },
      meta: {},
    } as any)

    expect(apiMock).toHaveBeenCalledTimes(1)
    expect(navigateToMock).toHaveBeenCalledWith('/dashboard', { replace: true })
  })

  it('skips hotspot precheck on direct portal login without hotspot hints', async () => {
    const middleware = (await import('../middleware/auth.global')).default
    authStoreState.isLoggedIn = true

    await middleware({
      path: '/login',
      fullPath: '/login',
      query: {},
      meta: {},
    } as any)

    expect(apiMock).not.toHaveBeenCalled()
    expect(navigateToMock).toHaveBeenCalledWith('/dashboard', { replace: true })
  })

  it('prechecks hotspot on dashboard route even without query hints', async () => {
    const middleware = (await import('../middleware/auth.global')).default
    authStoreState.isLoggedIn = true
    apiMock.mockResolvedValue({
      hotspot_login_required: true,
      hotspot_binding_active: false,
    })

    await middleware({
      path: '/dashboard',
      fullPath: '/dashboard',
      query: {},
      meta: {},
    } as any)

    expect(apiMock).toHaveBeenCalledWith('/auth/hotspot-session-status', {
      method: 'GET',
      query: {},
    })
    expect(navigateToMock).toHaveBeenCalledWith('/login/hotspot-required?auto_start=1', { replace: true })
  })

  it('uses stored hotspot identity for dashboard precheck after hotspot-required succeeds', async () => {
    const middleware = (await import('../middleware/auth.global')).default
    authStoreState.isLoggedIn = true
    apiMock.mockResolvedValue({
      hotspot_login_required: true,
      hotspot_binding_active: true,
    })

    const localStorageMock = createLocalStorageMock({
      'lpsaring:last-hotspot-identity': JSON.stringify({
        clientIp: '172.16.3.131',
        clientMac: '08:FA:79:B6:29:F5',
        at: Date.now(),
      }),
    })

    vi.stubGlobal('window', {
      document: {
        referrer: '',
      },
      localStorage: localStorageMock,
      sessionStorage: createSessionStorageMock(),
    } as any)
    vi.stubGlobal('localStorage', localStorageMock)

    await middleware({
      path: '/dashboard',
      fullPath: '/dashboard',
      query: {},
      meta: {},
    } as any)

    expect(apiMock).toHaveBeenCalledWith('/auth/hotspot-session-status', {
      method: 'GET',
      query: {
        client_ip: '172.16.3.131',
        client_mac: '08:FA:79:B6:29:F5',
      },
    })
    expect(navigateToMock).not.toHaveBeenCalled()
  })

  it('preserves stored hotspot identity when dashboard still must redirect back to hotspot-required', async () => {
    const middleware = (await import('../middleware/auth.global')).default
    authStoreState.isLoggedIn = true
    apiMock.mockResolvedValue({
      hotspot_login_required: true,
      hotspot_binding_active: false,
    })

    const localStorageMock = createLocalStorageMock({
      'lpsaring:last-hotspot-identity': JSON.stringify({
        clientIp: '172.16.3.131',
        clientMac: '08:FA:79:B6:29:F5',
        at: Date.now(),
      }),
    })

    vi.stubGlobal('window', {
      document: {
        referrer: '',
      },
      localStorage: localStorageMock,
      sessionStorage: createSessionStorageMock(),
    } as any)
    vi.stubGlobal('localStorage', localStorageMock)

    await middleware({
      path: '/dashboard',
      fullPath: '/dashboard',
      query: {},
      meta: {},
    } as any)

    expect(navigateToMock).toHaveBeenCalledWith('/login/hotspot-required?client_ip=172.16.3.131&client_mac=08%3AFA%3A79%3AB6%3A29%3AF5&auto_start=1', { replace: true })
  })

  it('prioritizes demo-user redirect to beli over hotspot precheck', async () => {
    const middleware = (await import('../middleware/auth.global')).default
    authStoreState.isLoggedIn = true
    authStoreState.currentUser = { id: 'u-demo', role: 'USER', is_demo_user: true }

    await middleware({
      path: '/login',
      fullPath: '/login?client_ip=172.16.2.50&client_mac=AA:BB:CC:DD:EE:50',
      query: {
        client_ip: '172.16.2.50',
        client_mac: 'AA:BB:CC:DD:EE:50',
      },
      meta: {},
    } as any)

    expect(apiMock).not.toHaveBeenCalled()
    expect(navigateToMock).toHaveBeenCalledWith('/beli', { replace: true })
  })

  it('skips hotspot precheck for admin user', async () => {
    const middleware = (await import('../middleware/auth.global')).default
    authStoreState.isLoggedIn = true
    authStoreState.isAdmin = true

    await middleware({
      path: '/login',
      fullPath: '/login',
      query: {},
      meta: {},
    } as any)

    expect(apiMock).not.toHaveBeenCalled()
    expect(navigateToMock).toHaveBeenCalledWith('/admin/dashboard', { replace: true })
  })
})
