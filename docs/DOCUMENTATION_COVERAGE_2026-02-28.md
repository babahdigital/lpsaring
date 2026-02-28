# Documentation Coverage 2026-02-28

Dokumen ini merangkum sinkronisasi dokumentasi terhadap implementasi terbaru pada area auth/hotspot, policy parity, ledger audit, dan Cloudflare Tunnel.

## Ruang Lingkup yang Disinkronkan

- Hardening `POST /api/auth/auto-login`:
  - trusted source gate via router MAC authority,
  - hard reject untuk IP di luar `HOTSPOT_CLIENT_IP_CIDRS`,
  - reject mismatch `client_mac` request vs MAC router.
- Precision `POST /api/auth/verify-otp`:
  - pre-check `hotspot_session_active` berbasis ip-binding ownership user,
  - tetap tidak memakai active-session by-IP sebagai identity authority.
- Endpoint baru re-check captive/hotspot:
  - `GET /api/auth/hotspot-session-status`.
- Frontend flow hotspot-required:
  - re-check endpoint realtime sebelum melanjutkan ke dashboard.
- Policy parity guard periodik:
  - service parity report + action plan,
  - task `policy_parity_guard_task` + beat schedule,
  - env gate `ENABLE_POLICY_PARITY_GUARD` dan `POLICY_PARITY_GUARD_INTERVAL_SECONDS`.
- Audit ledger policy transition:
  - event append-only `policy.block_transition:*` pada flow admin action, debt settlement, dan sinkronisasi policy.
- Cloudflare Tunnel trust chain:
  - `TRUST_CF_CONNECTING_IP`, `TRUSTED_PROXY_CIDRS`,
  - `HOTSPOT_CLIENT_IP_CIDRS`,
  - `CSRF_NO_ORIGIN_ALLOWED_IPS` yang ketat.

## Dokumen yang Diupdate

- `docs/API_DETAIL.md`
- `docs/API_DETAIL_OPS_ADDENDUM.md`
- `docs/OPERATIONAL_API_MATRIX.md`
- `docs/OPERATIONS_POLICY_PARITY_RESPONSE.md`
- `docs/RULES_QUOTA_DEBT_ACCESS_FLOW.md`
- `docs/CLOUDFLARE_TUNNEL_CHECKLIST.md`
- `docs/POLICY_CODE_TRACE_MAP.md`
- `docs/REFERENCE_PENGEMBANGAN.md`
- `docs/DEVLOG_2026-02-28.md`

## Catatan Verifikasi

- Endpoint `GET /api/auth/hotspot-session-status` sudah terdokumentasi konsisten pada API ringkas, matriks operasional, dan referensi pengembangan.
- Narasi legacy yang menyatakan fallback identity dari active-session by-IP telah dihapus/dikoreksi.
- Runbook parity kini mencakup guard periodik otomatis dan variabel env operasional.
- Checklist Cloudflare mencerminkan baseline produksi terbaru untuk captive flow dan CSRF no-origin whitelist.
