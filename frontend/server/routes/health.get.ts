// Endpoint kesehatan ringan untuk Docker healthcheck.
// Tidak memicu SSR rendering halaman sehingga tidak ada API call ke backend.
export default defineEventHandler(() => {
  return { status: 'ok' }
})
