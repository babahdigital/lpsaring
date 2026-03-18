# Issue: MAC Randomization 401 Errors (Nomor +6282213631573)

## Problem Summary
- **User**: +62 822-1363-1573
- **Error**: 401 Unauthorized on `/api/auth/auto-login`
- **Cause**: Randomized MAC (LAA bit detected: `02:F5:73:9C:1A:71`)
- **Impact**: Device not found in `user_devices` table → return 401 before showing confirmation dialog
- **Date Found**: 18 Mar 2026, 19:16 UTC+8

## Root Cause

### Android 13 Infinix X6525
- MAC Randomization enabled by default
- Changes on every WiFi reconnect or device sleep/wake
- System never saw MAC before → Can't bind automatically

### Current Flow Limitation
```
POST /api/auth/auto-login with client_mac=02:F5:73:9C:1A:71
  ↓
Check: SELECT FROM user_devices WHERE mac_address = '02:F5:73:9C:1A:71'
  ↓
Result: NOT FOUND (first time seeing this MAC)
  ↓
Return: 401 "resolved MAC has no authorized device ownership"
  ↗ (ERROR BEFORE DIALOG SHOWN!)
```

## Current Fixes (Live - Sprint Ini)
✅ MAC Randomization Detection (LAA bit check)
✅ Confirmation Dialog in hotspot-required.vue
✅ Instant DHCP Upsert after binding

## Gap Identified
- Dialog only shown AFTER first successful bind
- Error happens BEFORE dialog on first attempt
- User gets 401, not guided to warning

## Solutions (Priority)

### P0 - Next 30 min
**Move warning to BEFORE first auth attempt**
- Show in `/captive` page before auto-login
- Or: Show in `/login` page pre-login
- Guide user to disable MAC randomization

### P1 - Next Sprint
**Session Storage Binding**
- First auth creates binding
- Store MAC in sessionStorage for 24h
- Subsequent requests in same session → Accept new MAC as same device
- Files: `hotspot-required.vue`, `apply_device_binding_for_login()`

### P2 - Future
**Device Fingerprinting**
- Trust device beyond just MAC
- Fingerprint: User ID + User Agent + IP Range
- Accept same fingerprint for 24h with different MAC

## Testing Needed
- [ ] First connection with randomized MAC
- [ ] Reconnect in same session (new MAC) → Should work
- [ ] New browser/session → Require OTP again
- [ ] Check: No regression in normal (non-randomized) MAC flow
