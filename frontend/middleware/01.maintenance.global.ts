// middleware/01.maintenance.global.ts
import { useMaintenanceStore } from '~/store/maintenance'

export default defineNuxtRouteMiddleware((to) => {
  const maintenanceStore = useMaintenanceStore()

  // — 1. Jika mode maintenance off → lanjut
  if (!maintenanceStore.isActive)
    return

  // — 2. Jalur yang *selalu* kebal —
  //    • Seluruh prefix /admin      (portal internal)
  //    • Halaman /maintenance       (hindari loop)
  //    • Aset devtools Nuxt (saat dev) supaya HMR tetap jalan
  if (
    to.path.startsWith('/admin')
    || to.path === '/maintenance'
    || to.path.startsWith('/__nuxt_')
  ) {
    return // ⇦ langsung lanjut ke halaman tujuan
  }

  // — 3. Semua jalur lain dialihkan ke halaman maintenance
  return navigateTo('/maintenance', { replace: true })
})
