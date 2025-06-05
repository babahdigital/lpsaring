// frontend/middleware/auth.global.ts
import type { RouteLocationNormalized, RouteRecordName } from 'vue-router'
import { defineNuxtRouteMiddleware, navigateTo, useNuxtApp } from '#app'
import { useAuthStore } from '~/store/auth'

export default defineNuxtRouteMiddleware(async (to: RouteLocationNormalized, _from: RouteLocationNormalized) => {
  const authStore = useAuthStore()
  const nuxtApp = useNuxtApp() // Untuk cek nuxtApp.isHydrating

  // 1. Abaikan path API, path internal Nuxt, atau path well-known
  const ignoredPrefixes = ['/api/', '/_nuxt/', '/__nuxt_error', '/.well-known/']
  if (ignoredPrefixes.some(prefix => to.path.startsWith(prefix))) {
    return
  }

  // 2. Pastikan store auth sudah diinisialisasi.
  // Ini penting agar state isLoggedIn dan user sudah termuat.
  if (!authStore.isInitialized) {
    await authStore.initializeAuth()
  }

  // 3. Definisikan rute publik
  // Hanya halaman login dan register yang publik.
  // Halaman lain (termasuk /beli dan /payment/finish) memerlukan autentikasi.
  const publicRouteNames: ReadonlyArray<RouteRecordName | null | undefined> = [
    'login',
    'register', // Nama rute untuk halaman register (jika ada dan bernama demikian)
    // Halaman 'beli' dan 'payment-finish' tidak lagi di sini
  ]
  const publicPaths: ReadonlyArray<string> = [
    '/login',
    '/register', // Path untuk halaman register
    // Path '/beli' dan '/payment/finish' tidak lagi di sini
  ]

  const targetRouteName = to.name
  const targetPath = to.path

  // Cek apakah target adalah rute publik berdasarkan nama atau path prefix
  const isTargetPublic = publicRouteNames.includes(targetRouteName) || publicPaths.some(p => targetPath.startsWith(p))

  const commonNavigationOptions = { replace: true, external: false }
  const canNavigate = import.meta.client || !nuxtApp.isHydrating // Kondisi navigasi yang aman

  // --- Logika untuk Pengguna BELUM Login ---
  if (!authStore.isLoggedIn) {
    // Jika mencoba mengakses root path ('/') dan belum login, arahkan ke login.
    if (targetPath === '/' && canNavigate) {
      return navigateTo({ path: '/login', query: { redirect: '/' }, ...commonNavigationOptions })
    }
    // Jika mencoba mengakses rute non-publik dan belum login, arahkan ke login
    // dengan menyimpan path tujuan awal untuk redirect setelah login.
    if (!isTargetPublic && canNavigate) {
      return navigateTo({ path: '/login', query: { redirect: to.fullPath }, ...commonNavigationOptions })
    }
    // Jika sudah di rute publik (login/register), biarkan.
  }
  // --- Logika untuk Pengguna SUDAH Login ---
  else { // authStore.isLoggedIn is true
    const userIsApprovedAndActive = authStore.isUserApprovedAndActive

    // Jika pengguna sudah login dan mencoba mengakses halaman login atau register:
    if (isTargetPublic && (targetRouteName === 'login' || targetRouteName === 'register') && canNavigate) {
      if (userIsApprovedAndActive) {
        // Jika akun aktif, arahkan ke dashboard.
        return navigateTo({ path: '/dashboard', ...commonNavigationOptions })
      }
      else {
        // Jika akun belum aktif, biarkan pengguna di halaman login/register.
        // Halaman login/register mungkin perlu menampilkan pesan status akun.
        // Tidak ada redirect eksplisit di sini agar pesan dari query param (jika ada) bisa ditampilkan.
      }
    }

    // Jika pengguna sudah login dan mencoba mengakses root path ('/'):
    if (targetPath === '/' && canNavigate) {
      if (userIsApprovedAndActive) {
        return navigateTo({ path: '/dashboard', ...commonNavigationOptions })
      }
      else {
        // Jika akun belum aktif, arahkan kembali ke login dengan pesan.
        // Ini akan menangani kasus jika pengguna belum aktif mencoba akses root.
        return navigateTo({ path: '/login', query: { redirect: '/', message: 'account_pending_or_issue' }, ...commonNavigationOptions })
      }
    }

    // Jika pengguna sudah login TAPI akunnya BELUM disetujui/aktif
    // DAN mencoba mengakses rute non-publik (sekarang termasuk /beli dan /payment/finish):
    if (!userIsApprovedAndActive && !isTargetPublic && canNavigate) {
      // Arahkan kembali ke login dengan pesan dan simpan tujuan awal.
      return navigateTo({ path: '/login', query: { redirect: to.fullPath, message: 'account_pending_or_issue' }, ...commonNavigationOptions })
    }

    // Jika pengguna sudah login, akunnya aktif, dan mengakses rute non-publik (seperti /beli atau /payment/finish),
    // maka tidak ada kondisi di atas yang terpenuhi, sehingga navigasi diizinkan.
  }

  // Jika tidak ada kondisi pengalihan yang terpenuhi, biarkan navigasi berlanjut.
})
