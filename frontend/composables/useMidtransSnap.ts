import { useRuntimeConfig } from '#app'

interface MidtransWindow extends Window {
  __midtransSnapReady?: Promise<void>
  __midtransSnapResolve?: () => void
  __midtransSnapReject?: (reason?: unknown) => void
  __midtransSnapLastError?: string
  snap?: {
    pay: (token: string, options: {
      onSuccess: (result: { order_id: string }) => void
      onPending: (result: { order_id: string }) => void
      onError: (result: { order_id: string }) => void
      onClose: () => void
    }) => void
  }
}

export const useMidtransSnap = () => {
  const runtimeConfig = useRuntimeConfig()
  const midtransClientKey = runtimeConfig.public.midtransClientKey
  const midtransEnv = runtimeConfig.public.midtransEnv
  const midtransSnapUrlProduction = runtimeConfig.public.midtransSnapUrlProduction
  const midtransSnapUrlSandbox = runtimeConfig.public.midtransSnapUrlSandbox
  const snapScriptUrl = midtransEnv === 'production'
    ? midtransSnapUrlProduction
    : midtransSnapUrlSandbox

  const ensureMidtransReady = async () => {
    if (import.meta.server) {
      throw new Error('Midtrans Snap hanya tersedia di browser.')
    }

    const globalWindow = window as MidtransWindow

    if (!globalWindow.__midtransSnapReady) {
      globalWindow.__midtransSnapReady = new Promise<void>((resolve, reject) => {
        globalWindow.__midtransSnapResolve = resolve
        globalWindow.__midtransSnapReject = reject
      })
    }

    if (!midtransClientKey) {
      const error = new Error('Midtrans client key belum diatur.')
      globalWindow.__midtransSnapLastError = error.message
      globalWindow.__midtransSnapReject?.(error)
      throw error
    }

    if (!snapScriptUrl) {
      const error = new Error('URL Snap.js belum diatur.')
      globalWindow.__midtransSnapLastError = error.message
      globalWindow.__midtransSnapReject?.(error)
      throw error
    }

    if (window.snap) {
      globalWindow.__midtransSnapResolve?.()
      await globalWindow.__midtransSnapReady
      return
    }

    const existingScript = document.querySelector(`script[src="${snapScriptUrl}"]`) as HTMLScriptElement | null
    if (existingScript) {
      if (existingScript.getAttribute('data-loaded') === 'true') {
        if (window.snap) {
          globalWindow.__midtransSnapResolve?.()
        }
        else {
          const error = new Error('Snap.js sudah dimuat tetapi objek snap tidak tersedia.')
          globalWindow.__midtransSnapLastError = error.message
          globalWindow.__midtransSnapReject?.(error)
        }
      }
      await globalWindow.__midtransSnapReady
      return
    }

    const script = document.createElement('script')
    script.type = 'text/javascript'
    script.src = snapScriptUrl
    script.setAttribute('data-client-key', midtransClientKey)
    script.setAttribute('data-loaded', 'false')
    script.async = true

    document.head.appendChild(script)

    script.onload = () => {
      script.setAttribute('data-loaded', 'true')
      if (window.snap) {
        globalWindow.__midtransSnapLastError = undefined
        globalWindow.__midtransSnapResolve?.()
      }
      else {
        const error = new Error('Snap.js dimuat, tetapi window.snap tidak tersedia.')
        globalWindow.__midtransSnapLastError = error.message
        globalWindow.__midtransSnapReject?.(error)
      }
    }

    script.onerror = (error) => {
      script.setAttribute('data-loaded', 'true')
      globalWindow.__midtransSnapLastError = 'Gagal memuat skrip Snap.js. Periksa akses ke domain Midtrans.'
      globalWindow.__midtransSnapReject?.(error)
    }

    await globalWindow.__midtransSnapReady
  }

  return { ensureMidtransReady }
}
