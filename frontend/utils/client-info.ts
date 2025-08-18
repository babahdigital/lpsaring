// Shared client info utilities to avoid duplication across plugins
import { useAuthStore } from '~/store/auth'

export function getClientRealIP(): string | null {
  const urlParams = new URLSearchParams(window.location.search)
  const captiveIP = urlParams.get('client_ip') || urlParams.get('ip') || urlParams.get('client-ip') || urlParams.get('orig-ip')
  if (captiveIP) {
    try { localStorage.setItem('captive_ip', captiveIP) }
    catch { /* noop */ }
    return captiveIP
  }
  const storedCaptiveIP = localStorage.getItem('captive_ip')
  return storedCaptiveIP || null
}

export function getClientMAC(): string | null {
  const urlParams = new URLSearchParams(window.location.search)
  const captiveMAC = urlParams.get('client_mac') || urlParams.get('mac') || urlParams.get('client-mac')
  if (captiveMAC) {
    try {
      localStorage.setItem('captive_mac', captiveMAC)
      ; (window as any).__CLIENT_MAC__ = captiveMAC
    }
    catch { /* noop */ }
    return captiveMAC
  }
  const storedCaptiveMAC = localStorage.getItem('captive_mac')
  return storedCaptiveMAC || null
}

export function getBestClientInfo() {
  const auth = useAuthStore()
  const params = new URLSearchParams(window.location.search)
  const urlIp = params.get('client_ip') || params.get('ip')
  const urlMac = params.get('client_mac') || params.get('mac')
  if (urlIp) {
    try { localStorage.setItem('captive_ip', urlIp) }
    catch { /* noop */ }
  }
  if (urlMac) {
    try { localStorage.setItem('captive_mac', urlMac) }
    catch { /* noop */ }
  }
  const clientIp = auth.clientIp || localStorage.getItem('captive_ip')
  const clientMac = auth.clientMac || localStorage.getItem('captive_mac')
  return { clientIp, clientMac }
}
