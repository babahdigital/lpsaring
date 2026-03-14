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

export function shouldRedirectToHotspotRequired(input: HotspotRedirectInput): boolean {
  return input.hotspotLoginRequired === true && input.hotspotBindingActive !== true
}

export function resolvePostHotspotRecheckRoute(status: HotspotAccessStatus): string {
  if (status === 'ok')
    return '/dashboard'

  return STATUS_ROUTE_MAP[status]
}

export function resolveHotspotSuccessPresentation(nextRoute: string): HotspotSuccessPresentation {
  if (nextRoute === '/dashboard') {
    return {
      title: 'Internet Sudah Aktif',
      description: 'Perangkat Anda sudah berhasil dikenali. Anda akan diarahkan ke dashboard dalam beberapa detik.',
      ctaLabel: 'Buka Dashboard',
    }
  }

  return {
    title: 'Akses Berhasil Diperbarui',
    description: 'Koneksi perangkat sudah diproses. Anda akan diarahkan ke halaman berikutnya secara otomatis.',
    ctaLabel: 'Lanjut Sekarang',
  }
}
