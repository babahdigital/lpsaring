// middleware/00.1-nginx-realip-debug.global.ts

/**
 * Debug middleware untuk troubleshooting Real IP detection dari Nginx
 * Hanya aktif di development mode
 */
export default defineNuxtRouteMiddleware((to, _from) => {
  // Hanya jalankan di client-side dan development mode
  if (!import.meta.client || !import.meta.dev) {
    return
  }

  // Skip untuk asset requests
  const path = to.path
  if (path.startsWith('/_nuxt/') || path.includes('.')) {
    return
  }

  // Log semua headers yang berkaitan dengan IP detection
  console.group('🔍 [NGINX-REALIP-DEBUG] Real IP Detection Info')

  try {
    // Ambil info dari window object jika ada
    const windowInfo = {
      userAgent: navigator.userAgent,
      location: window.location.href,
      referrer: document.referrer || 'none',
    }

    // Check captive browser markers
    const captiveMarkers = {
      isCaptiveBrowser: !!(window as any).__IS_CAPTIVE_BROWSER__,
      hasConnectivityCheck: navigator.userAgent.includes('CaptiveNetworkSupport'),
      hasWispr: navigator.userAgent.includes('wispr'),
      isAndroidCaptive: navigator.userAgent.includes('CaptivePortalLogin'),
      isiOSCaptive: navigator.userAgent.includes('Apple') && navigator.userAgent.includes('captive'),
    }

    // Extract URL parameters
    const url = new URL(window.location.href)
    const rawClientMac = url.searchParams.get('client_mac') || url.searchParams.get('mac')
    const urlParams = {
      client_ip: url.searchParams.get('client_ip') || url.searchParams.get('ip'),
      client_mac_raw: rawClientMac,
      client_mac_decoded: rawClientMac ? decodeURIComponent(decodeURIComponent(rawClientMac || '')) : null,
      redirect: url.searchParams.get('redirect'),
      allParams: Object.fromEntries(url.searchParams.entries()),
    }

    // Validate decoded MAC
    if (urlParams.client_mac_decoded) {
      const cleanMac = urlParams.client_mac_decoded.replace(/%3A/gi, ':').replace(/[-.]/g, ':').toUpperCase()
      urlParams.client_mac_decoded = cleanMac
    }

    // Network info (jika tersedia)
    const networkInfo = {
      effectiveType: (navigator as any).connection?.effectiveType || 'unknown',
      downlink: (navigator as any).connection?.downlink || 'unknown',
      rtt: (navigator as any).connection?.rtt || 'unknown',
    }

    console.log('📱 Window Info:', windowInfo)
    console.log('🌐 Captive Browser Detection:', captiveMarkers)
    console.log('🔗 URL Parameters:', urlParams)
    console.log('📡 Network Info:', networkInfo)

    // Highlight issues
    const issues = []
    if (!urlParams.client_ip && captiveMarkers.isCaptiveBrowser) {
      issues.push('❗ Captive browser detected but no client_ip in URL')
    }
    if (!urlParams.client_mac_decoded && captiveMarkers.isCaptiveBrowser) {
      issues.push('❗ Captive browser detected but no valid client_mac in URL')
    }
    if (urlParams.client_ip && !urlParams.client_ip.match(/^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$/)) {
      issues.push('❗ Invalid client_ip format detected')
    }
    if (urlParams.client_mac_raw && !urlParams.client_mac_decoded) {
      issues.push('❗ MAC parameter exists but failed to decode properly')
    }
    if (urlParams.client_mac_decoded && !urlParams.client_mac_decoded.match(/^([0-9A-F]{2}:){5}[0-9A-F]{2}$/)) {
      issues.push('❗ Invalid MAC format after decoding')
    }

    if (issues.length > 0) {
      console.warn('⚠️ Potential Issues:', issues)
    }
    else {
      console.log('✅ No obvious issues detected')
    }
  }
  catch (error) {
    console.error('💥 Error in debug middleware:', error)
  }

  console.groupEnd()
})
