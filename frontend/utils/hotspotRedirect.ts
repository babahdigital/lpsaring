type HotspotRedirectInput = {
  hotspotLoginRequired?: boolean | null
  hotspotBindingActive?: boolean | null
  hotspotSessionActive?: boolean | null
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
  const bindingActive = input.hotspotBindingActive ?? input.hotspotSessionActive
  return input.hotspotLoginRequired === true && bindingActive !== true
}

export function resolvePostHotspotRecheckRoute(status: HotspotAccessStatus): string {
  if (status === 'ok')
    return '/dashboard'

  return STATUS_ROUTE_MAP[status]
}
