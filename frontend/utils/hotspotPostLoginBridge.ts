import type { HotspotIdentity } from './hotspotIdentity'

function hasIdentityValue(value: string | null | undefined): boolean {
  return String(value ?? '').trim().length > 0
}

export function shouldAttemptPostLoginHotspotBridge(
  identity: Partial<HotspotIdentity>,
  bridgeTargetUrl: string | null | undefined,
): boolean {
  const hasExplicitIdentity = hasIdentityValue(identity.clientIp) || hasIdentityValue(identity.clientMac)
  if (hasExplicitIdentity)
    return false

  return hasIdentityValue(bridgeTargetUrl)
}

export function sanitizePostLoginHotspotBridgeReturnPath(
  rawPath: string | null | undefined,
  currentOrigin: string,
): string {
  const fallbackPath = '/login'
  const normalizedPath = String(rawPath ?? '').trim()
  if (!normalizedPath)
    return fallbackPath

  try {
    const target = new URL(normalizedPath, currentOrigin)
    if (target.origin !== currentOrigin)
      return fallbackPath

    target.searchParams.delete('bridge_resume')

    return `${target.pathname}${target.search}${target.hash}` || fallbackPath
  }
  catch {
    return fallbackPath
  }
}