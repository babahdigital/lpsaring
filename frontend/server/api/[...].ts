import { proxyRequest } from 'h3'

export default defineEventHandler(async (event) => {
  const config = useRuntimeConfig(event)
  const internalApiBaseUrl = config.internalApiBaseUrl

  if (!internalApiBaseUrl) {
    console.error('[PROXY DEBUG] FATAL: NUXT_INTERNAL_API_BASE_URL tidak diatur di file .env!')
    throw createError({
      statusCode: 500,
      statusMessage: 'Server Error: Backend API URL is not configured.',
    })
  }

  const path = event.context.params?._ ?? ''
  const targetUrl = `${internalApiBaseUrl}/${path}`

  console.log(`[PROXY DEBUG] Menerima permintaan untuk: /api/${path}`)
  console.log(`[PROXY DEBUG] Meneruskan ke target URL: ${targetUrl}`)

  // Enhanced: Forward query parameters (including captive portal parameters)
  const url = getQuery(event)
  const queryString = new URLSearchParams()

  // Add all query parameters to the target URL
  Object.entries(url).forEach(([key, value]) => {
    if (value !== undefined && value !== null) {
      queryString.append(key, String(value))
    }
  })

  // Build final target URL with query parameters
  const finalTargetUrl = queryString.toString()
    ? `${targetUrl}?${queryString.toString()}`
    : targetUrl

  console.log(`[PROXY DEBUG] Final target URL with params: ${finalTargetUrl}`)

  // Forward all headers (including IP detection headers from client plugin)
  const forwardedHeaders = new Headers(event.headers)
  forwardedHeaders.delete('host')

  // Log important headers for debugging
  console.log('[PROXY DEBUG] Headers being forwarded:')
  console.log('  X-Frontend-Detected-IP:', forwardedHeaders.get('X-Frontend-Detected-IP'))
  console.log('  X-Frontend-Detected-MAC:', forwardedHeaders.get('X-Frontend-Detected-MAC'))
  console.log('  X-Frontend-Request:', forwardedHeaders.get('X-Frontend-Request'))

  try {
    console.log('[PROXY DEBUG] Mencoba melakukan proxy request...')
    const response = await proxyRequest(event, finalTargetUrl, {
      fetchOptions: {
        headers: forwardedHeaders,
      },
    })
    console.log(`[PROXY DEBUG] Berhasil melakukan proxy untuk /api/${path}`)
    return response
  }
  catch (error: any) {
    console.error(`[PROXY DEBUG] GAGAL melakukan proxy ke ${targetUrl}. Error:`, error.cause ?? error)

    throw createError({
      statusCode: 502, // Bad Gateway
      statusMessage: 'Bad Gateway: Gagal terhubung ke server backend.',
    })
  }
})
