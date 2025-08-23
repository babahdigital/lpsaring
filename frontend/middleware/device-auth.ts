// middleware/device-auth.ts
// Guard halaman otorisasi perangkat: pastikan user login dan memang butuh otorisasi perangkat.
// Hindari loop: biarkan halaman ini tetap jika deviceAuthRequired masih aktif.

import { useAuthStore } from '~/store/auth'

export default defineNuxtRouteMiddleware((to) => {
    const auth = useAuthStore()

    // Jika belum login, arahkan ke login biasa (bukan captive)
    if (!auth.isLoggedIn) {
        return navigateTo('/login', { replace: true })
    }

    // Jika user admin, tidak perlu halaman ini -> langsung ke admin dashboard
    if (auth.isAdmin && to.path.startsWith('/akun/otorisasi-perangkat')) {
        return navigateTo('/admin/dashboard', { replace: true })
    }

    // Jika otorisasi tidak diperlukan lagi, arahkan ke dashboard user
    if (!auth.isDeviceAuthRequired && to.path.startsWith('/akun/otorisasi-perangkat')) {
        return navigateTo('/dashboard', { replace: true })
    }

    // Jika masih butuh otorisasi, tetap di halaman ini (no-op)
    return
})
