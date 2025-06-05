export default defineNuxtPlugin(() => {
  if (import.meta.server)
    return

  const runtimeConfig = useRuntimeConfig()
  const midtransClientKey = runtimeConfig.public.midtransClientKey
  const midtransEnv = runtimeConfig.public.midtransEnv

  if (!midtransClientKey) {
    console.error('[Plugin Midtrans] Error: Client key not set!')
    return
  }

  const snapScriptUrl = midtransEnv === 'production'
    ? 'https://app.midtrans.com/snap/snap.js'
    : 'https://app.sandbox.midtrans.com/snap/snap.js'

  const existingScript = document.querySelector(`script[src="${snapScriptUrl}"]`)
  if (existingScript)
    return

  const script = document.createElement('script')
  script.type = 'text/javascript'
  script.src = snapScriptUrl
  script.setAttribute('data-client-key', midtransClientKey)
  script.async = true

  document.head.appendChild(script)

  script.onload = () => {
    console.warn('[Plugin Midtrans] Script loaded successfully') // Diubah dari log ke warn
  }
  script.onerror = (error) => {
    console.error('[Plugin Midtrans] Script load failed:', error)
    if (typeof document !== 'undefined') {
      // Hapus alert dan ganti dengan mekanisme yang lebih baik
      console.error('Gagal memuat komponen pembayaran. Silakan refresh halaman.')
    }
  }
})
