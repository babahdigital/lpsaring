export interface PendingHotspotBridgeState {
  returnPath: string
  autoResume: boolean
  at: number
}

const STORAGE_KEY = 'lpsaring:pending-hotspot-bridge'
const MAX_AGE_MS = 2 * 60 * 1000

function isBrowserRuntime(): boolean {
  return typeof window !== 'undefined' && typeof sessionStorage !== 'undefined'
}

export function rememberPendingHotspotBridge(input: { returnPath?: string | null, autoResume?: boolean | null }): void {
  if (!isBrowserRuntime())
    return

  const returnPath = String(input.returnPath ?? '').trim()
  if (!returnPath)
    return

  const payload: PendingHotspotBridgeState = {
    returnPath,
    autoResume: input.autoResume !== false,
    at: Date.now(),
  }

  try {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(payload))
  }
  catch {
    // ignore storage failures
  }
}

export function getPendingHotspotBridge(): PendingHotspotBridgeState | null {
  if (!isBrowserRuntime())
    return null

  try {
    const raw = sessionStorage.getItem(STORAGE_KEY)
    if (!raw)
      return null

    const parsed = JSON.parse(raw) as Partial<PendingHotspotBridgeState>
    const returnPath = String(parsed.returnPath ?? '').trim()
    const at = Number(parsed.at ?? 0)
    if (!returnPath || !Number.isFinite(at) || at <= 0 || (Date.now() - at) > MAX_AGE_MS) {
      sessionStorage.removeItem(STORAGE_KEY)
      return null
    }

    return {
      returnPath,
      autoResume: parsed.autoResume !== false,
      at,
    }
  }
  catch {
    return null
  }
}

export function clearPendingHotspotBridge(): void {
  if (!isBrowserRuntime())
    return

  try {
    sessionStorage.removeItem(STORAGE_KEY)
  }
  catch {
    // ignore storage failures
  }
}