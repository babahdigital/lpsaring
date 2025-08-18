// plugins/00.disable-metrics.client.ts
// Menonaktifkan metrics polling (store/metrics) secara global.
// Hapus file ini atau set query ?metrics=on untuk mengaktifkan kembali sementara.

export default defineNuxtPlugin(() => {
  if (typeof window === 'undefined')
    return
  const params = new URLSearchParams(window.location.search)
  if (params.get('metrics') === 'on') {
    console.info('[METRICS] Override aktif via query ?metrics=on -> metrics ENABLED untuk sesi ini')
    ; (window as any).__DISABLE_METRICS__ = false
    return
  }
  ; (window as any).__DISABLE_METRICS__ = true
  console.info('[METRICS] Dinonaktifkan oleh plugin 00.disable-metrics.client')
})

// (Opsional) deklarasi global agar TypeScript tidak warning
declare global { interface Window { __DISABLE_METRICS__?: boolean } }
