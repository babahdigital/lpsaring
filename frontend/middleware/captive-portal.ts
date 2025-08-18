// middleware/captive-portal.ts
export default defineNuxtRouteMiddleware(async (to) => {
  // Middleware ini hanya relevan untuk halaman /captive dan turunannya
  if (!to.path.startsWith('/captive')) {
    return
  }

  if (typeof window === 'undefined') {
    return
  }

  const hasCaptiveParams = !!(
    to.query.client_ip
    || to.query.client_mac
    || to.query.username
    || to.query.ip
    || to.query.mac
  )

  // Jika mencoba akses /captive secara langsung tanpa parameter dari MikroTik
  if (!hasCaptiveParams) {
    console.warn('⚠️ Akses langsung ke /captive tanpa parameter. Mengalihkan ke /login...')
    // Di produksi, alihkan ke halaman login
    return navigateTo('/login', { replace: true })
  }

  // Jika parameter ada, tandai sebagai sesi captive
  sessionStorage.setItem('captive_portal_session', 'true')
  localStorage.setItem('captive_portal_mode', 'true')
    ; (window as any).__IS_CAPTIVE_BROWSER__ = true

  // Persist IP/MAC dari parameter agar tersedia sedini mungkin untuk plugin/API
  try {
    const decode = (v: any) => typeof v === 'string' ? decodeURIComponent(v) : v
    const rawIp = (to.query.client_ip as string) || (to.query.ip as string) || (to.query['client-ip'] as string) || (to.query['orig-ip'] as string)
    const rawMac = (to.query.client_mac as string) || (to.query.mac as string) || (to.query['client-mac'] as string)
    const ip = rawIp ? decode(rawIp) : null
    const mac = rawMac ? decode(rawMac).replace(/%3A/gi, ':').replace(/[-.]/g, ':').toUpperCase() : null

    if (ip) {
      localStorage.setItem('captive_ip', ip)
        ; (window as any).__CLIENT_IP__ = ip
    }
    if (mac) {
      localStorage.setItem('captive_mac', mac)
        ; (window as any).__CLIENT_MAC__ = mac
    }

    // Update auth store segera agar header X-Frontend-Detected-* terkirim pada request awal
    try {
      const { useAuthStore } = require('~/store/auth')
      const store = useAuthStore()
      store.setClientInfo(ip, mac)
    }
    catch (_e) { /* no-op */ }
  }
  catch (e) {
    console.warn('[CAPTIVE-MW] Gagal menyimpan parameter captive:', e)
  }

  console.log('✅ Sesi captive portal terdeteksi dan telah dibuat.')

  // Jika sudah login (token aktif), lewati halaman login captive dan langsung sinkronisasi/otorisasi
  try {
    const { useAuthStore } = require('~/store/auth')
    const store = useAuthStore()
    // Jika belum login di konteks captive, coba pulihkan dengan refresh cookie (jika ada)
    if (store && !store.isLoggedIn && typeof (store as any).refreshAccessToken === 'function') {
      try {
        await (store as any).refreshAccessToken()
      } catch { /* ignore */ }
    }

    if (store?.isLoggedIn || (store as any)?.token) {
      const nuxtApp = useNuxtApp()
      const $api = (nuxtApp as any).$api as (<T = any>(u: string, o?: any) => Promise<T>)

      const ip = localStorage.getItem('captive_ip')
      const mac = localStorage.getItem('captive_mac')
      try {
        if ($api && (ip || mac)) {
          await $api('/auth/clear-cache', { method: 'POST', body: { ip, mac, force_refresh: true } })
        }
      } catch { /* ignore */ }

      if ($api) {
        try {
          const res: any = await $api('/auth/sync-device', { method: 'POST', body: { ip, mac } })
          if (res?.status === 'DEVICE_VALID') {
            if (to.path !== '/captive/terhubung')
              return navigateTo('/captive/terhubung', { replace: true })
            return
          }
          if (res?.status === 'DEVICE_UNREGISTERED') {
            if (to.path !== '/captive/otorisasi-perangkat')
              return navigateTo('/captive/otorisasi-perangkat', { replace: true })
            return
          }
        } catch { /* fallback to /captive */ }
      }
    }
  } catch { /* noop */ }
})
