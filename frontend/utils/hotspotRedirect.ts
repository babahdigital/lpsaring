type HotspotRedirectInput = {
  hotspotLoginRequired?: boolean | null
  hotspotBindingActive?: boolean | null
}

export type HotspotSuccessPresentation = {
  title: string
  description: string
  ctaLabel: string
}

export type HotspotAccessStatus = 'ok' | 'blocked' | 'inactive' | 'expired' | 'habis' | 'fup'

const STATUS_ROUTE_MAP: Record<Exclude<HotspotAccessStatus, 'ok'>, string> = {
  blocked: '/policy/blocked',
  inactive: '/policy/inactive',
  expired: '/policy/expired',
  habis: '/policy/habis',
  fup: '/policy/fup',
}

const CAPTIVE_SUCCESS_FALLBACK_PATH = '/dashboard'
const CAPTIVE_SUCCESS_BLOCKED_PREFIXES = ['/login', '/register', '/daftar', '/captive']

function matchesPathPrefix(pathname: string, prefix: string): boolean {
  return pathname === prefix || pathname.startsWith(`${prefix}/`)
}

export function shouldRedirectToHotspotRequired(input: HotspotRedirectInput): boolean {
  // `hotspotBindingActive === null` artinya backend tidak dapat menentukan status
  // (mis. identity hint tidak tersedia). Jangan redirect saat status tidak diketahui;
  // ini mencegah false-positive redirect ke /login/hotspot-required yang berujung
  // auto-bridge ke http://login.home.arpa (gagal mixed-content / NXDOMAIN dari luar
  // jaringan internal). Kembalikan true HANYA bila kita yakin binding tidak aktif.
  if (input.hotspotLoginRequired !== true)
    return false
  return input.hotspotBindingActive === false
}

export function resolvePostHotspotRecheckRoute(status: HotspotAccessStatus): string {
  if (status === 'ok')
    return '/dashboard'

  return STATUS_ROUTE_MAP[status]
}

export function resolveHotspotSuccessPresentation(nextRoute: string): HotspotSuccessPresentation {
  if (nextRoute === '/dashboard') {
    return {
      title: 'Anda Terhubung!',
      description: 'Perangkat Anda sudah berhasil terhubung ke internet. Anda akan diarahkan ke dashboard dalam beberapa detik.',
      ctaLabel: 'Buka Dashboard',
    }
  }

  return {
    title: 'Akses Berhasil Diperbarui',
    description: 'Koneksi perangkat sudah diproses. Anda akan diarahkan ke halaman berikutnya secara otomatis.',
    ctaLabel: 'Lanjut Sekarang',
  }
}

export function resolveCaptiveSuccessRedirectTarget(rawTarget: string | null | undefined, currentOrigin: string): string {
  const fallbackTarget = CAPTIVE_SUCCESS_FALLBACK_PATH
  const normalizedTarget = String(rawTarget ?? '').trim()

  try {
    const target = new URL(normalizedTarget || fallbackTarget, currentOrigin)
    if (target.origin !== currentOrigin)
      return target.toString()

    const pathname = target.pathname || '/'
    if (pathname === '/' || CAPTIVE_SUCCESS_BLOCKED_PREFIXES.some(prefix => matchesPathPrefix(pathname, prefix)))
      return fallbackTarget

    return `${pathname}${target.search}${target.hash}`
  }
  catch {
    return fallbackTarget
  }
}
