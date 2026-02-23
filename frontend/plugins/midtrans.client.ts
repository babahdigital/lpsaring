/**
 * Plugin sisi klien untuk menyediakan promise readiness Midtrans Snap.
 *
 * IMPORTANT:
 * - Jangan auto-load Snap.js di sini.
 * - Snap.js hanya boleh di-load saat mode pembayaran `snap` benar-benar dipakai
 *   (lazy-load) melalui composable `useMidtransSnap()`.
 */
export default defineNuxtPlugin((nuxtApp) => {
  // 1. Pastikan plugin ini tidak pernah berjalan di sisi server.
  if (import.meta.server) {
    return
  }

  const globalWindow = window as typeof window & {
    __midtransSnapReady?: Promise<void>
    __midtransSnapResolve?: () => void
    __midtransSnapReject?: (reason?: unknown) => void
    __midtransSnapLastError?: string
  }

  if (!globalWindow.__midtransSnapReady) {
    globalWindow.__midtransSnapReady = new Promise<void>((resolve, reject) => {
      globalWindow.__midtransSnapResolve = resolve
      globalWindow.__midtransSnapReject = reject
    })
  }

  nuxtApp.provide('midtransReady', globalWindow.__midtransSnapReady)
})
