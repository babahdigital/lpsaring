// Helper untuk smoothing flow OTP → captive aktif tanpa redirect ganda.
// Dipanggil oleh frontend/pages/login/index.vue setelah verify-otp sukses
// dan SEBELUM redirect ke /login/hotspot-required.
//
// Kontrak backend lihat: contracts/openapi/openapi.v1.yaml — POST /auth/captive/auto-activate.

export type AutoActivateReason
  = | 'no_known_device'
    | 'mikrotik_unavailable'
    | 'binding_failed'
    | 'disabled'
    | 'user_not_found'

export interface AutoActivateResponse {
  activated: boolean
  reason?: AutoActivateReason | string
  mac_used?: string
  binding_active?: boolean
  detail?: string
}

export type AutoActivateOutcome
  = | 'activated'
    | 'fallback'

export interface AttemptAutoActivateOptions {
  apiFetch: (url: string, init?: { method?: string }) => Promise<unknown>
  hotspotLoginRequired: boolean | null | undefined
  hasClientIdentity: boolean
}

/**
 * Decide whether to attempt auto-activate based on verify-otp response, then
 * call the backend best-effort. Returns 'activated' if frontend should skip
 * /login/hotspot-required and go straight to /captive/terhubung. Returns
 * 'fallback' for the existing flow.
 */
export async function attemptAutoActivate(opts: AttemptAutoActivateOptions): Promise<AutoActivateOutcome> {
  if (!opts.hotspotLoginRequired)
    return 'fallback'
  // Hanya untuk skenario dimana frontend tidak punya client_ip/client_mac
  // (mis. user buka portal via HTTPS dan Cloudflare proxy).
  if (opts.hasClientIdentity)
    return 'fallback'

  try {
    const data = await opts.apiFetch('/auth/captive/auto-activate', { method: 'POST' }) as AutoActivateResponse | null
    if (data && data.activated === true)
      return 'activated'
    return 'fallback'
  }
  catch {
    return 'fallback'
  }
}
