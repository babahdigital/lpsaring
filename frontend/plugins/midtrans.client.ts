/**
 * Plugin sisi klien untuk memuat skrip Midtrans Snap.js secara dinamis dan aman.
 * Skrip ini hanya akan dieksekusi di lingkungan peramban (browser).
 */
export default defineNuxtPlugin(() => {
  // 1. Pastikan plugin ini tidak pernah berjalan di sisi server.
  if (import.meta.server) {
    return
  }

  const runtimeConfig = useRuntimeConfig()
  const midtransClientKey = runtimeConfig.public.midtransClientKey
  const midtransEnv = runtimeConfig.public.midtransEnv

  // 2. Validasi Kunci Konfigurasi: Hentikan eksekusi jika client key tidak ada.
  if (!midtransClientKey) {
    console.error('[Midtrans Plugin] Eksekusi dihentikan: NUXT_PUBLIC_MIDTRANS_CLIENT_KEY tidak diatur di runtime config.')
    return
  }

  // 3. Tentukan URL skrip Midtrans berdasarkan lingkungan (production atau sandbox).
  const snapScriptUrl = midtransEnv === 'production'
    ? 'https://app.midtrans.com/snap/snap.js'
    : 'https://app.sandbox.midtrans.com/snap/snap.js'

  // 4. Mencegah Duplikasi: Cek apakah skrip sudah ada di dalam dokumen.
  //    Ini penting untuk mencegah pemuatan ulang saat navigasi halaman di dalam Nuxt.
  const existingScript = document.querySelector(`script[src="${snapScriptUrl}"]`)
  if (existingScript) {
    console.info('[Midtrans Plugin] Skrip sudah ada, pemuatan baru dilewati.')
    return
  }

  // 5. Buat dan konfigurasikan elemen skrip secara dinamis.
  const script = document.createElement('script')
  script.type = 'text/javascript'
  script.src = snapScriptUrl
  script.setAttribute('data-client-key', midtransClientKey)
  script.async = true

  // 6. Tambahkan skrip ke dalam <head> dokumen untuk memulai proses pemuatan.
  document.head.appendChild(script)

  // 7. Tangani hasil pemuatan skrip.
  script.onload = () => {
    // PENYEMPURNAAN: Gunakan console.info untuk log sukses, karena ini adalah informasi, bukan peringatan.
    console.info('[Midtrans Plugin] Skrip Midtrans Snap.js berhasil dimuat.')
  }
  
  script.onerror = (error) => {
    // Gunakan console.error untuk log kegagalan.
    console.error('[Midtrans Plugin] Gagal memuat skrip Midtrans Snap.js:', error)
  }
})