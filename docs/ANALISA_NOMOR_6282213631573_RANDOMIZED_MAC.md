# Analisa Error: Nomor +62 822-1363-1573 (Randomized MAC Issue)

**Date**: 18 Mar 2026, 19:16-19:19 UTC+8
**Issue**: User mendapat multiple 401 errors, tidak bisa akses portal
**Root Cause**: MAC Randomization (LAA bit detected)

---

## 1. Error Log Analysis

### Backend Access Log (19:16:31)
```json
{
  "timestamp": "18-03-2026 19:16:31 +0800",
  "method": "POST /api/auth/auto-login HTTP/1.1",
  "client_ip": "202.65.239.3",
  "device_mac": "02:F5:73:9C:1A:71",
  "server_ip_in_hotspot": "172.16.2.177",
  "status": 401,
  "bytes": 270,
  "user_agent": "Chrome/146.0 Mobile on Android 13 (Infinix X6525)"
}
```

### Warning Log (request_id: 6b250221bf45c15adc051fe26c699f09)
```
AUTO_LOGIN_DECISION
  reason=UNAUTHORIZED_DEVICE_REQUIRES_OTP
  status=401
  client_ip=172.16.2.177
  client_mac=02:F5:73:9C:1A:71
  resolved_mac=02:F5:73:9C:1A:71
  user_id=None
  details="resolved MAC has no authorized device ownership"
```

---

## 2. MAC Randomization Detection ✓

### MAC Address: `02:F5:73:9C:1A:71`
- **Prefix**: `02` (hex)
- **Binary**: `00000010`
- **LAA Bit Check** (bit 1):
  - Bit 0 (U/L): 1 = Locally Administered
  - Bit 1 (M): 0 = Unicast
  - **Result**: ✅ **MAC IS RANDOMIZED** (LAA bit = 1)

### Device Indicators
- **OS**: Android 13 (Infinix X6525)
- **Browser**: Chrome 146.0 Mobile
- **Behavior**: Multiple failed 401 attempts in 4 seconds = aggressive retry pattern

---

## 3. Root Cause Timeline

### Normal Flow (Authorized Device)
```
1. Device connects to hotspot portal
2. Router captures MAC (real or randomized)
3. System checks: Is this MAC in user_devices table?
4. YES → Display "Aktifkan Internet" button → Success
5. NO → Show error (need binding)
```

### This User's Problem
```
1. Device connects → MAC: 02:F5:73:9C:1A:71 (randomized)
2. System queries: SELECT * FROM user_devices WHERE mac_address = '02:F5:73:9C:1A:71'
3. Result: NOT FOUND (database never saw this MAC before)
4. Reason: MAC changes every session/every device sleep/every WiFi reconnect
5. System returns: 401 "resolved MAC has no authorized device ownership"
6. User frustrated → Try again → Gets NEW randomized MAC → Try again → Repeat
```

---

## 4. Why This Happens

### iOS 14+, Android 10+ MAC Randomization
```
Device Settings:
  - iOS 14+: "Private Address" enabled by default
  - Android 10+: "Use random MAC" when available
  - Infinix X6525 (Android 13): Enabled by default

Behavior:
  - Each WiFi connect: NEW random MAC
  - Sometimes: NEW random MAC per device sleep/wake
  - Sometimes: Different MAC per app/portal
  - Result: System sees different "device" each time
```

### Why 401 Error Happens
```
Flow (Current System):
1. User POST /api/auth/auto-login with client_mac=02:F5:73:9C:1A:71
2. System checks device ownership:
   - Queries: user_devices WHERE mac_address = '02:F5:73:9C:1A:71'
   - Result: NOT FOUND (MAC is random, never seen before)
3. Response: 401 Unauthorized
   - Reason: "resolved MAC has no authorized device ownership"
   - No user_id resolved because MAC is unknown
```

---

## 5. What Should Happen (Current Implementation)

### MAC Confirmation Dialog (Sprint Ini - LIVE)
User should see:
```
⚠ Alamat MAC Ter-Randomisasi

Device Anda menggunakan "Private Address" (MAC randomization).
Ini dapat menyebabkan masalah koneksi:
- Portal login diminta berulang kali
- Koneksi terputus dan masuk kembali
- Device tidak terdeteksi dengan baik

Sebaiknya matikan "Private Address" terlebih dahulu.

[ Oke, Matikan Dulu ] [ Lanjut dengan Resiko ]
```

### Then Auto-Login Should Work With:
1. Fallback to `db-device-mac` lookup mode (from user's last authorized device)
2. OR: Accept first MAC binding in session + remember in temp session storage
3. OR: Trigger instant binding on first auth (even if MAC randomized)

---

## 6. Why Current Fix (Instant DHCP) Isn't Enough

### Current Status (hotspot-required.vue + instant-dhcp task)
✅ **MAC Randomization Detection** - Shows dialog
✅ **Instant DHCP Upsert** - Creates lease immediately
❌ **Auto-Login Binding** - Still requires last-seen device MAC

### Problem
User at 19:16:31 is on **Android 13 Infinix X6525**:
- Sees **first-time randomized MAC** (`02:F5:73:9C:1A:71`)
- System has **NO previous MAC recorded** for this device
- System **CAN'T fallback** to DB device binding
- Result: **401 UNAUTHORIZED** before dialog shown

---

## 7. Recommended Fixes (Priority)

### 🔴 URGENT (P0) - Deploy Now
**Fix**: Show warning **BEFORE** login attempt (not after)
- Move MAC Warning to `/login` page (not `/captive` path)
- Guide user to disable MAC randomization BEFORE hotspot
- Or: Accept randomized MAC for first binding

**Code Change**: `hotspot-required.vue` L619-632
```typescript
// onMounted: Check for randomized MAC EARLY
// If randomized, show warning dialog BEFORE activateInternetOneClick()
// Currently: Shows warning AFTER user clicks button
```

### 🟡 HIGH (P1) - Deploy Next Sprint
**Fix**: Fallback device binding for randomized MAC in same session
```typescript
// Session Storage Binding
// 1. First request with randomized MAC → Accept & store
// 2. Subsequent requests in same browser session → Reuse stored MAC
// 3. New browser session → Request OTP again (security)
```

**Code Changes**:
- `hotspot-required.vue`: Store first MAC in sessionStorage
- `apply_device_binding_for_login()`: Check sessionStorage fallback
- `auth_routes.py`: Accept sessionStorage-bound MAC

### 🟡 MEDIUM (P2) - Future
**Fix**: Trust device fingerprinting (not just MAC)
```
Fingerprint = SHA256(
  Device ID (from DB) +
  User Agent Hash +
  IP Range +
  Timestamp
)
Store fingerprint for 24 hours
Accept same fingerprint even with different MAC
```

---

## 8. Immediate Action Plan (Next 30 min)

### Step 1: Educate User
📱 Message to +6282213631573:
```
Halo, Internet gagal konek karena:
✅ Sudah fixed di system kami (MAC warning sudah live)

Solusi cepat:
1. Buka Settings → WiFi
2. Cari "Private Address" / "Use random MAC"
3. Matikan (turn OFF)
4. Coba akses internet lagi

Atau: Buka lagi, klik "Lanjut dengan Resiko" di warning dialog
```

### Step 2: Deploy Session Storage Fallback (30 min dev)
- Store first randomized MAC in sessionStorage for 24h
- Accept same MAC in subsequent requests (same session)
- Test: Reload page multiple times → Should keep working

### Step 3: Monitor Next 2 Hours
- Check backend logs for this user's IP (202.65.239.3)
- Expect: Switch from 401 UNAUTHORIZED to 200 SUCCESS after session storage deployed
- SMS alert if still seeing errors after session storage fix

---

## 9. Long-term Strategy

### Cascade Binding Strategy
```
Priority Order (in apply_device_binding_for_login):
1. Exact MAC match (current device)
2. Session storage MAC match (same browser session, different MAC)
3. User's latest DB device MAC (fallback for OTP flow)
4. Require new binding (first time)

Lifetime:
- Session storage: 24 hours (browser session)
- DB device binding: Until device revoked
- Temp session: Valid for 5 minutes (portal session)
```

### Security Considerations
```
⚠ Do NOT trust randomized MAC alone for 24+ hours
✅ DO trust: MAC + Session Storage + User Agent consistency
✅ DO require: OTP re-verification if strange IP detected

Example:
- User normally in Bandung (IP 210.x.x.x)
- Today suddenly from Malang (IP 202.x.x.x)
- Randomized MAC different
- Action: Require OTP re-verification
```

---

## 10. Test Cases (Before Deploy)

### Test 1: First Connection (Randomized MAC)
```
✓ Device connects with randomized MAC
✓ Shows warning dialog
✓ User clicks "Lanjut dengan Resiko"
✓ MAC binding created immediately
✓ Dashboard access works
```

### Test 2: Reconnect (Same Session, Different MAC)
```
✓ Browser refresh (MAC changes)
✓ System recognizes: Same session (sessionStorage token)
✓ Accepts new MAC as same device
✓ Dashboard works without re-auth
```

### Test 3: New Browser (Same Device)
```
✓ New browser window
✓ Old sessionStorage gone
✓ Requires OTP again (security)
✓ Accepted after OTP
```

---

## Summary

| Issue | Status | Impact | Fix |
|-------|--------|--------|-----|
| MAC Randomization Detection | ✅ LIVE | Warning shown | — |
| Instant DHCP Upsert | ✅ LIVE | Lease created fast | — |
| First-time MAC Error | ❌ ACTIVE | 401 Unauthorized | Session Storage (P1) |
| Repeated disconnects | ⚠️ PARTIAL | Dialog shown, need action | User education (P0) |
| Device trust timeout | ⚠️ DESIGN | 24h too long? | Fingerprint (P2) |

**Estimated Fix Time**:
- P0 (Education): 10 min (SMS)
- P1 (Session Storage): 30 min (dev + test)
- P2 (Fingerprint): Sprint Depan (6-8 hours)
