// composables/useMidtrans.ts

import { useRuntimeConfig } from '#app'
import { ref } from 'vue'

// Deklarasi tipe global untuk object `snap` dari Midtrans agar TypeScript tidak error.
declare global {
  interface Window {
    snap: {
      pay: (token: string, options?: Record<string, any>) => void
    }
  }
}

// State untuk melacak status pemuatan skrip, diletakkan di luar fungsi
// agar menjadi singleton (hanya ada satu status untuk seluruh aplikasi).
const isScriptLoaded = ref(false)
let loadingPromise: Promise<void> | null = null

export function useMidtrans() {
  const config = useRuntimeConfig()
  const midtransClientKey = config.public.midtransClientKey
  const midtransEnv = config.public.midtransEnv

  const snapUrl = midtransEnv === 'production'
    ? 'https://app.midtrans.com/snap/snap.js'
    : 'https://app.sandbox.midtrans.com/snap/snap.js'

  /**
   * Fungsi untuk memuat skrip Midtrans secara dinamis.
   * Mencegah pemuatan ganda jika sudah ada atau sedang dimuat.
   * @returns Promise<void>
   */
  const loadScript = (): Promise<void> => {
    if (loadingPromise) {
      return loadingPromise
    }
    if (isScriptLoaded.value) {
      return Promise.resolve()
    }

    loadingPromise = new Promise((resolve, reject) => {
      // Pastikan hanya berjalan di browser
      if (typeof window === 'undefined') {
        return resolve()
      }

      const script = document.createElement('script')
      script.src = snapUrl
      script.type = 'text/javascript'
      script.setAttribute('data-client-key', midtransClientKey)
      script.async = true

      script.onload = () => {
        console.info('[useMidtrans] Skrip Midtrans Snap.js berhasil dimuat sesuai permintaan.')
        isScriptLoaded.value = true
        loadingPromise = null
        resolve()
      }
      script.onerror = (error) => {
        console.error('[useMidtrans] Gagal memuat skrip Midtrans.', error)
        loadingPromise = null
        reject(error)
      }

      document.head.appendChild(script)
    })

    return loadingPromise
  }

  /**
   * Fungsi untuk memulai proses pembayaran.
   * Akan memuat skrip terlebih dahulu jika belum ada, lalu memanggil window.snap.pay.
   * @param snapToken Token transaksi dari backend Anda.
   * @param options Callback dari Midtrans (onSuccess, onPending, dll).
   */
  const pay = async (snapToken: string, options: Record<string, any>) => {
    try {
      await loadScript()
      if (window.snap) {
        window.snap.pay(snapToken, options)
      }
      else {
        throw new Error('Objek Midtrans `snap` tidak tersedia.')
      }
    }
    catch (error) {
      console.error('Gagal memulai pembayaran Midtrans:', error)
      // Anda bisa menambahkan notifikasi error di sini jika perlu
    }
  }

  return {
    pay,
  }
}
