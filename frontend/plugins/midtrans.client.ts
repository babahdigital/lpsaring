/**
 * Plugin sisi klien untuk memuat skrip Midtrans Snap.js secara dinamis dan aman.
 * Skrip ini hanya akan dieksekusi di lingkungan peramban (browser).
 */
export default defineNuxtPlugin((nuxtApp) => {
  // 1. Pastikan plugin ini tidak pernah berjalan di sisi server.
  if (import.meta.server) {
    return
  }

  const route = useRoute()
  const runtimeConfig = useRuntimeConfig()
  const midtransClientKey = runtimeConfig.public.midtransClientKey
  const midtransEnv = runtimeConfig.public.midtransEnv
  const midtransSnapUrlProduction = runtimeConfig.public.midtransSnapUrlProduction
  const midtransSnapUrlSandbox = runtimeConfig.public.midtransSnapUrlSandbox

  // 2. Validasi Kunci Konfigurasi: Hentikan eksekusi jika client key tidak ada.
  if (!midtransClientKey) {
    console.error('[Midtrans Plugin] Eksekusi dihentikan: NUXT_PUBLIC_MIDTRANS_CLIENT_KEY tidak diatur di runtime config.')
    return
  }

  // 3. Tentukan URL skrip Midtrans berdasarkan lingkungan (production atau sandbox).
  const snapScriptUrl = midtransEnv === 'production'
    ? midtransSnapUrlProduction
    : midtransSnapUrlSandbox

  if (!snapScriptUrl) {
    console.error('[Midtrans Plugin] Eksekusi dihentikan: URL Snap.js belum diatur di runtime config.')
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

  const shouldLoadSnapForPath = (path: string) => {
    return path === '/beli'
      || path === '/captive/beli'
  }

  const ensureSnapLoaded = () => {
    if (!shouldLoadSnapForPath(route.path))
      return

    if (window.snap) {
      globalWindow.__midtransSnapResolve?.()
      return
    }

    // 4. Mencegah Duplikasi: Cek apakah skrip sudah ada di dalam dokumen.
    //    Ini penting untuk mencegah pemuatan ulang saat navigasi halaman di dalam Nuxt.
    const existingScript = document.querySelector(`script[src="${snapScriptUrl}"]`) as HTMLScriptElement | null
    if (existingScript) {
      if (existingScript.getAttribute('data-loaded') === 'true') {
        if (window.snap)
          globalWindow.__midtransSnapResolve?.()
        else
          globalWindow.__midtransSnapReject?.(new Error('Snap.js sudah dimuat tetapi objek snap tidak tersedia.'))
      }
      return
    }

    // 5. Buat dan konfigurasikan elemen skrip secara dinamis.
    const script = document.createElement('script')
    script.type = 'text/javascript'
    script.src = snapScriptUrl
    script.setAttribute('data-client-key', midtransClientKey)
    script.setAttribute('data-loaded', 'false')
    script.async = true

    // 6. Tambahkan skrip ke dalam <head> dokumen untuk memulai proses pemuatan.
    document.head.appendChild(script)

    // 7. Tangani hasil pemuatan skrip.
    script.onload = () => {
      // PENYEMPURNAAN: Gunakan console.info untuk log sukses, karena ini adalah informasi, bukan peringatan.
      console.info('[Midtrans Plugin] Skrip Midtrans Snap.js berhasil dimuat.')
      script.setAttribute('data-loaded', 'true')
      if (window.snap) {
        globalWindow.__midtransSnapLastError = undefined
        globalWindow.__midtransSnapResolve?.()
      }
      else {
        const missingSnapError = new Error('Snap.js dimuat, tetapi window.snap tidak tersedia.')
        globalWindow.__midtransSnapLastError = missingSnapError.message
        globalWindow.__midtransSnapReject?.(missingSnapError)
      }
    }

    script.onerror = (error) => {
      // Gunakan console.error untuk log kegagalan.
      console.error('[Midtrans Plugin] Gagal memuat skrip Midtrans Snap.js:', error)
      script.setAttribute('data-loaded', 'true')
      globalWindow.__midtransSnapLastError = 'Gagal memuat skrip Snap.js. Periksa akses ke domain Midtrans.'
      globalWindow.__midtransSnapReject?.(error)
    }
  }

  watch(
    () => route.path,
    () => ensureSnapLoaded(),
    { immediate: true },
  )
})
