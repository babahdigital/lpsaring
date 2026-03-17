# Devlog — Audit & Penyempurnaan Holistik — 2026-03-18

Sesi ini merupakan audit total dan implementasi penyempurnaan berdasarkan `masukan.md`.
Live MikroTik diaudit langsung via Docker flask container → RouterOS API.

---

## 1. cleanup_inactive_command.py — 3 Bug Fixes (masukan.md 8.2)

**File**: `backend/app/commands/cleanup_inactive_command.py`

**Bugs yang diperbaiki**:
- Tidak ada filter role → Admin/Super Admin/Komandan bisa ikut terhapus
- Tidak ada `--dry-run` mode
- Commit DB batch di akhir → jika gagal di tengah, MikroTik sudah terhapus tapi DB belum

**Fix**:
- `_PROTECTED_ROLES = {UserRole.ADMIN, UserRole.SUPER_ADMIN, UserRole.KOMANDAN}` — query + double-check per user
- Tambah `@click.option("--dry-run", ...)` → show candidates tanpa hapus
- Commit per-user (bukan batch) dengan rollback per-user jika gagal
- Threshold dari `INACTIVE_DELETE_DAYS` config (bukan hardcoded 6 bulan)
- MikroTik dihapus DULU (baru DB per-user commit)

---

## 2. verify_otp_handlers.py — Split Blocked Check (masukan.md 5.4 / 6.2)

**File**: `backend/app/infrastructure/http/auth_contexts/verify_otp_handlers.py`

**Bug**: Semua `is_blocked=True` user ditolak 403 di OTP verify, termasuk yang diblokir karena auto-debt-limit. User tidak bisa mengakses halaman pembayaran hutang.

**Fix**:
- Tambah cek `is_auto_debt_limit_reason(blocked_reason)`:
  - Auto-debt-limit block → izinkan login terbatas (`_is_auto_debt_block_login = True`)
  - Manual block / EOM debt → tetap `403 FORBIDDEN`
- Untuk auto-debt-block: skip MikroTik binding + sync
- Session URL redirect ke `/policy/blocked` (bukan `/dashboard`)
- `hotspot_login_required = False`, `hotspot_binding_active = None`
- Tidak kirim hotspot credentials ke frontend

---

## 3. verify_otp_handlers.py — OTP 503 Fix (masukan.md 3.3)

**File**: `backend/app/infrastructure/http/auth_contexts/verify_otp_handlers.py`
**File**: `backend/app/infrastructure/http/auth_routes.py`

**Bug**: OTP dikonsumsi (dihapus dari Redis) SEBELUM router MAC lookup. Jika router tidak tersedia (503), OTP sudah hilang → user harus minta OTP baru → tapi rate limit (429) aktif → loop 503→401→429.

**Fix**:
- Tambah `store_otp_in_redis` ke parameter `verify_otp_impl` + call di `auth_routes.py`
- Pada path `not ok_router_mac` (503): re-store OTP ke Redis (kecuali bypass code)
- User bisa retry dengan OTP yang sama tanpa minta OTP baru

---

## 4. webhook_routes.py — WA Alert MIKROTIK_APPLY_FAILED (masukan.md 9.2)

**File**: `backend/app/infrastructure/http/transactions/webhook_routes.py`

**Bug**: Jika `apply_package_and_sync_to_mikrotik` gagal setelah user bayar, tidak ada notifikasi ke admin.

**Fix**:
- Setelah `MIKROTIK_APPLY_FAILED` event, kirim WA ke semua SUPER_ADMIN aktif
- Alert berisi: `order_id`, phone user, error message (max 200 char)
- Admin langsung bisa gunakan tombol "Perbaiki Transaksi" di panel

---

## 5. hotspot-required.vue — Auto-Bridge Skenario 3 (masukan.md 10.3)

**File**: `frontend/pages/login/hotspot-required.vue`

**Bug**: Jika user buka hotspot-required.vue tanpa hotspot identity (skenario 3 — buka langsung dari browser), langsung tampil `showFallbackLogin` tanpa auto-bridge ke router dulu.

**Fix**:
- Dalam `onMounted()`, jika tidak ada explicit hotspot identity:
  - Cek apakah `hotspotRequired && (hotspotBridgeTargetUrl || loginHotspotUrl)` tersedia
  - Jika ya → auto-trigger `beginSilentHotspotBridge()` sebelum show fallback
  - Jika bridge navigate berhasil → return (bridge sedang berlangsung)
  - Hanya tampil fallback login jika bridge tidak mungkin

---

## 6. public_routes.py + authAccess.ts + auth.ts — FUP Threshold Runtime (masukan.md 2.3)

**Files**:
- `backend/app/infrastructure/http/public_routes.py`
- `frontend/utils/authAccess.ts`
- `frontend/store/auth.ts`

**Bug**: `QUOTA_FUP_THRESHOLD_MB` hardcoded `3072` di frontend (`authAccess.ts`). Jika admin ubah nilai di `.env.prod`, frontend tidak ikut tanpa rebuild.

**Fix**:
- `public_routes.py`: inject `QUOTA_FUP_THRESHOLD_MB` dari Flask config ke response `/api/settings/public` jika tidak ada di DB
- `authAccess.ts`: ubah signature `resolveAccessStatusFromUser(inputUser, nowMs=Date.now(), fupThresholdMb=3072)` — parameter opsional dengan fallback 3072
- `auth.ts` `getAccessStatusFromUser()`: baca `fupThresholdMb` dari `useSettingsStore().getSettingAsInt('QUOTA_FUP_THRESHOLD_MB', 3072)` → pass ke `resolveAccessStatusFromUser`
- Tests tidak terpengaruh (parameter opsional, default tetap 3072)

---

## 7. tasks.py — expire_stale_transactions Grace Period (masukan.md 8.3)

**File**: `backend/app/tasks.py`

**Bug**: Transaksi WITH `expiry_time` langsung di-expire saat `expiry_time < now_utc`. Tidak ada grace period. Jika webhook Midtrans terlambat (misalnya 2-3 menit setelah expiry_time), transaksi sudah EXPIRED dan webhook tidak bisa inject quota.

**Fix**:
- Tambah `grace_expiry_minutes` (configurable via `TRANSACTION_EXPIRY_GRACE_MINUTES`, default 5)
- Capped: `max(0, min(60))`
- Query sekarang: `expiry_time < now_utc - timedelta(minutes=grace_expiry_minutes)`
- Grace 5 menit = webhook Midtrans yang terlambat masih bisa masuk dalam window tersebut
- Legacy rows (tanpa expiry_time) tetap pakai `grace_minutes=5` seperti sebelumnya

---

## Live MikroTik Audit Results (2026-03-18)

Dilakukan via: `docker exec hotspot_prod_flask_backend python3 -c "import routeros_api..."`

| Item | Hasil |
|------|-------|
| DNS name srv-user | `login.home.arpa` ✅ |
| hotspot-address | `172.16.2.1` |
| wartel addresses-per-mac | `1` (bukan unlimited seperti di .rsc lama) |
| klient_aktif | 85-86 entries |
| klient_fup | 2 entries |
| klient_fup walled-garden | src+dst rules ada → KEEP (safety net) ✅ |
| klient_blocked walled-garden | Bypass_Server + midtrans-prod → ✅ |

**Catatan**: File `.rsc` di `dev-lpsaring/konfigurasi_lengkap_wartelpas.rsc` adalah versi LAMA. Selalu audit dari live MikroTik.

---

## Existing Bugs Already Fixed (Confirmed)

- Inactive/Rejected user MikroTik cleanup: sudah handled di semua path:
  - `process_user_removal` → `run_user_auth_cleanup` → `_cleanup_router_artifacts`
  - Celery auto-deactivation → explicit ip-binding + hotspot user cleanup
  - PENDING_APPROVAL rejection → no MikroTik needed (user belum masuk MikroTik)

---

## 8. nginx/conf.d/lpsaring.conf — resolver_timeout (Log Audit)

**File**: `../nginx/conf.d/lpsaring.conf`

**Temuan dari log audit (nginx error.log Mar 17)**:
- 502 bursts: `lpsaring-backend could not be resolved (2: Server failure)` — Docker DNS returns SERVFAIL selama container restart window
- Config sudah correct: `resolver 127.0.0.11 valid=5s;` + `set $backend_upstream lpsaring-backend:5010;` (variable pattern = re-resolve per request)
- Yang kurang: `resolver_timeout` (default nginx 30s) terlalu lama jika Docker DNS hang

**Fix**:
- Tambah `resolver_timeout 2s;` di bawah `resolver` directive
- Sync ke server + nginx reload (test OK)
- Deployed langsung ke production (bukan via docker image)

**Analisis PUT /api/admin/users 500 (Mar 17 02:43-06:02)**:
- 8 failures untuk 3 user ID, lalu sembuh sendiri dari 06:31
- Root cause: MikroTik outage window ~3.5 jam
- Bukan code bug — `_sync_user_to_mikrotik` throw exception saat MikroTik unreachable → propagate → 500
- No fix needed, expected behavior

---

## 9. Parity Dashboard — Auto-Remediation 3-Step & Bulk Fix

**Files**: `backend/app/tasks.py`, `frontend/pages/admin/dashboard.vue`

**Gap**: Auto-remediation hanya sync address-list. Tidak fix `binding_type`, `missing_ip_binding`, `dhcp_lease_missing`, dan hard-cap 20 baris di dashboard.

**Fix tasks.py** — Auto-remediation 3-step:
1. **Step 1**: `upsert_ip_binding` per MAC untuk `binding_type`/`missing_ip_binding`
2. **Step 2**: `sync_address_list_for_single_user(api_connection=api)` (existing)
3. **Step 3**: `upsert_dhcp_static_lease` per MAC untuk `dhcp_lease_missing` (best-effort)

**Fix dashboard.vue**: Hapus `.slice(0,20)` hard-cap. Tambah "Perbaiki Semua (N)" button.

**Root cause persistent mismatch (bypassed users)**: ip-binding type `bypassed` di MikroTik boleh tidak punya field `address` (MAC-only binding). Saat `_collect_candidate_ips_for_user` dipanggil, address kosong → candidate IPs = [] → `_prune_stale_status_entries_for_user(keep_ips=[])` menghapus entri dari klient_aktif.

---

## 10. Parity IP Fallback + Console.log Cleanup (Mar 18 Sesi 2)

**Files**: `backend/app/tasks.py`, `frontend/components/promo/PromoFetcher.vue`,
`frontend/nuxt.config.ts`, `frontend/components/admin/dashboard/AdminSummaryCards.vue`

### tasks.py — Fix persistent address_list mismatch untuk bypassed users

**Root cause lengkap** (dari live audit):
- `ip_binding_map` keyed by MAC ✓ — tapi untuk `bypassed` binding tanpa field `address`:
  `ip_binding_map[mac]["address"]` = "" → `trusted_live_ips` kosong
- `_resolve_policy_parity_auto_remediation_client_ip` returns None → sync dipanggil tanpa `client_ip`
- `sync_address_list_for_single_user(client_ip=None)` → `_collect_candidate_ips_for_user` gagal temukan IP
- `_prune_stale_status_entries_for_user(keep_ips=[])` → hapus entry dari klient_aktif
- Siklus 10 menit → mismatch kembali

**Fix**: Tambah fallback setelah `_resolve_policy_parity_auto_remediation_client_ip`:
```python
if not trusted_client_ip:
    for _report_ip in candidate.get("ips") or []:
        _normalized_report_ip = _normalize_policy_parity_ip(_report_ip)
        if _normalized_report_ip:
            trusted_client_ip = _normalized_report_ip
            break
```
Candidate IPs dari report berasal dari live MikroTik scan (parity service LIVE) → trusted.

**Hasil live audit** (setelah 1 siklus guard di 06:11-06:14):
- `172.16.3.93` (user +6281253578275) → **MASUK** ke klient_aktif ✓ (remediated=7)
- `172.16.2.194` (user +6289527796925) → **BELUM** masuk klient_aktif (parity guard IP fallback belum ada)
- Setelah fix ini: kedua user akan di-remediate dengan benar

### Console.log cleanup

**PromoFetcher.vue** (10 console.log → 0): Log debug bocor ke browser console setiap user yang ada promo aktif. Removed. `console.error` untuk error handling dipertahankan.

**nuxt.config.ts** (2 console.log → 0): `Proxy Target` dan `Public API URL` bocor ke server log setiap container start. Removed.

**AdminSummaryCards.vue** (2 console.warn → 0): `_refreshAllData()` is placeholder function; console.warn diganti komentar minimal.

---

## 11. Live MikroTik Audit — 6.5, 7.3, 7.4, 11.3 (Mar 18 Sesi 2)

### 6.5 — klient_inactive Firewall Rules (AUDITED ✅)

**Hasil live audit via RouterOS API**:
```
chain=forward action=accept src-list=klient_inactive dst-list=Bypass_Server
  comment=AUTOFIX-LPSARING-FILTER klient_inactive allow-local-bypass-server
chain=forward action=drop src-list=klient_inactive dst-list=LOCAL_NETWORKS
  comment=AUTOFIX-LPSARING-FILTER klient_inactive drop-local-networks
```

**Analisis**:
- User `klient_inactive` (expired/inactive): BOLEH akses `Bypass_Server`, DIBLOKIR dari `LOCAL_NETWORKS`
- `Bypass_Server` saat audit: 9 entries = portal/server LPSaring + wartelpas (bukan banking sites)
- Skema sudah benar. Yang perlu: populate `Bypass_Server` dengan banking domain/IP (masukan 7.3)
- **Status**: Firewall rules OK, tidak perlu kode fix. Documentation only.

### 7.3 — Akses-Banking Scheduler (ANALYZED, PENDING IMPLEMENTATION)

**Konteks**:
- `klient_inactive` sudah boleh akses `Bypass_Server` via firewall rule
- `Bypass_Server` saat ini: hanya portal LPSaring + wartelpas (9 entries)
- Banking sites (BCA, BRI, Mandiri, dll) TIDAK ada → user inactive tidak bisa akses banking

**Rencana implementasi** (belum dikerjakan, perlu session terpisah):
- Tambah setting `AKSES_BANKING_DOMAINS` di DB (list domain banking seperti `klikbca.com`, `bri.co.id`, dll)
- Celery task `sync_bypass_server_banking_task` (skema: daily + on-change):
  1. Baca domain list dari settings
  2. Resolve DNS → IP addresses
  3. Diff dengan current `Bypass_Server` MikroTik entries
  4. Add missing, remove stale (hanya entry dengan comment `source=banking-sync`)
- Alternatif: manual populate `Bypass_Server` di MikroTik (immediate workaround)

### 7.4 — Wartel vs srv-user Walled-Garden (AUDITED ✅)

**Hasil live audit**:
- Walled garden: **80 entries** (lebih banyak dari .rsc lama)
- `server=srv-user`: rules khusus untuk user portal captive standard
- `server=` (blank): berlaku untuk semua server (wartel + srv-user)
- Rule diferensiasi sudah ada dan lebih lengkap dari .rsc lama
- **Status**: No code fix needed. Walled-garden up-to-date vs .rsc lama.

### 11.3 — MAC Randomization Analysis (DOCUMENTED)

**Konteks**:
- iOS 14+ dan Android 10+: random MAC per-SSID (Locally Administered Address, bit 1 byte pertama = 1)
- Dampak: user dengan MAC randomization → ip-binding by MAC tidak match → portal kembali muncul setiap koneksi baru
- Deteksi: MAC `UV:WX:YZ:AB:CD:EF` dimana U & 2 = 0b10 → locally administered (randomized)

**Mitigasi yang tersedia** (belum diimplementasi):
1. **User-facing**: Tampilkan peringatan di halaman login jika MAC terdeteksi randomized → minta user matikan di WiFi settings
2. **Sistem**: Gunakan username-based binding (sudah ada) sebagai fallback
3. **Admin**: Dashboard flag user dengan randomized MAC untuk proaktif bantuan

**Status**: Documentation only. Implementasi deteksi MAC rand memerlukan frontend change + backend MAc OUI check.

---

## Final masukan.md Checklist (Mar 18 Audit — Updated)

| Item | Status | Notes |
|------|--------|-------|
| 2.3 FUP threshold hardcode | ✅ DONE | public_routes.py + authAccess.ts + auth.ts |
| 2.4 User quota 0 awal | ✅ by design | status habis → /beli |
| 2.5 Dua tipe unlimited | ✅ already correct | expired check sebelum is_unlimited (BE+FE sinkron) |
| 3.2 Auto-bridge skenario 3 | ✅ DONE | hotspot-required.vue onMounted auto-bridge |
| 3.3 OTP 503 loop | ✅ DONE | verify_otp_handlers re-store OTP on 503 |
| 3.4 MAC mismatch VPN edge | docs only | no code fix, acceptable |
| 3.5 + 5.4 Auto-debt block OTP | ✅ DONE | verify_otp_handlers split blocked check |
| 4.3 FUP window after login | ✅ SYNC_ON_LOGIN=True | already active in .env.prod |
| 4.4 klient_fup walled-garden | ✅ by design | bypass portal, irrelevant |
| 5.3 EOM debt block | ✅ by user | walled-garden rules ditambah manual di MikroTik |
| 6.2 Inactive/rejected user sync | ✅ already handled | process_user_removal → _cleanup_router_artifacts |
| 6.3 Parity guard inactive | ✅ DONE | tasks.py auto-remediation 3-step + dashboard bulk-fix + IP fallback fix |
| 6.5 klient_inactive firewall | ✅ AUDITED | 2 rules: allow Bypass_Server, drop LOCAL_NETWORKS. OK. |
| 7.2 klient_blocked WA walled-garden | ✅ by user | rules ditambah manual di MikroTik |
| 7.3 Akses-Banking scheduler | ⏳ ANALYZED | Bypass_Server infra ada, perlu task populate banking domains |
| 7.4 wartel vs srv-user walled-garden | ✅ AUDITED | 80 entries, sudah terdifferensiasi server=srv-user |
| 8.2 cleanup_inactive_command.py | ✅ DONE | role filter + dry-run + per-user commit |
| 8.3 expire_stale grace period | ✅ DONE | tasks.py TRANSACTION_EXPIRY_GRACE_MINUTES |
| 9.2 Webhook MIKROTIK_APPLY_FAILED | ✅ DONE | webhook_routes.py WA alert ke SUPER_ADMIN |
| 10.3 hotspot-required auto-bridge | ✅ DONE | onMounted auto-trigger bridge |
| 11.2 Admin debug route | docs only | @admin_required sudah ada |
| 11.3 MAC randomization / cross-user | ✅ ANALYZED | Documented. Frontend detection planned (separate session) |
| 12.3 Celery worker memory | ✅ monitored | 608MB OK, dalam limit 500MB/child (auto-restart saat melebihi) |
| nginx 502 DNS | ✅ DONE | resolver_timeout 2s + deployed |
| Parity DHCP fallback bypassed user | ✅ DONE `10aa05f0` | dhcp_ips_by_mac fallback ke-4 di hotspot_sync + parity service |

---

## 12. DHCP Fallback IP untuk Bypassed User (Sesi 3, commit `10aa05f0`)

**Files**:
- `backend/app/services/hotspot_sync_service.py`
- `backend/app/services/access_parity_service.py`
- `backend/app/services/device_management_service.py`

**Root cause 2 mismatch persistent (+6281253578275, +6289527796925)**:
- User `unlimited` → ip-binding type=`bypassed` di MikroTik.
- `bypassed` ip-binding **tidak masuk** ke `/ip/hotspot/host` (bypass portal, sehingga tidak ada hotspot session).
- Field `address` pada ip-binding type=bypassed **kosong/NULL** (MikroTik tidak mengisi `address` untuk bypass tanpa IP eksplisit).
- `_collect_candidate_ips_for_user`: (1) host_map→kosong, (2) ip_binding_map["address"]→kosong, (3) ip_binding_rows_by_mac→rows ada tapi address NULL → `candidate_ips=[]`.
- Siklus sync: `sync_address_list` dipanggil tanpa client_ip → prune `keep_ips=[]` → klient_aktif dibersihkan → mismatch kembali setiap 10 menit.
- `collect_access_parity_report` juga tidak bisa resolve IP → salah tampilkan status.

**Fix**:
1. `_collect_candidate_ips_for_user`: tambah param `dhcp_ips_by_mac: Optional[Dict[str, set[str]]] = None` sebagai fallback ke-4. Jika semua lookup lain gagal dan DHCP lease user ada → ambil IP pertama sebagai candidate.
2. `sync_hotspot_usage_and_profiles`: inisialisasi + pass `dhcp_ips_by_mac` ke `_collect_candidate_ips_for_user`.
3. `sync_address_list_for_single_user`: inisialisasi `dhcp_ips_by_mac: Optional[...] = None` + query DHCP jika `enable_policy_self_heal` + pass ke fungsi.
4. `collect_access_parity_report`: tambah DHCP fallback ke chain IP resolution untuk tampilan report yang akurat.
5. `device_management_service.py` (L834): `cast(AbstractContextManager[Any], begin_nested())` — pure Pylance strict-mode fix.

**Verifikasi**: ruff ✅, ESLint ✅, TypeCheck ✅, CI ci.yml ✅, docker-publish.yml ✅, deploy ✅.

---

## Verifikasi Post-Deploy (Mar 18 2026, ~07:49 WIB)

**Parity report setelah deploy `10aa05f0`**:
```
Users: 91
Mismatches (parity): 0      ← WAS 2, NOW CLEAN ✅
Mismatches total: 31
Non-parity: 31
no_authorized_device: 25    ← expected, belum login perangkat
auto_fixable: 6             ← semua dhcp_lease_missing
mismatch_types:
  binding_type: 0 ✅
  missing_ip_binding: 0 ✅
  address_list: 0 ✅
  no_resolvable_ip: 0 ✅
  no_authorized_device: 25
  dhcp_lease_missing: 6     ← auto-fixable, DHCP_ENABLED=True, SERVER=Klien
```

- +6281253578275: **tidak muncul di mismatch** → FULLY RESOLVED ✅
- +6289527796925: hanya `dhcp_lease_missing` (bukan `address_list`) → IP sudah resolved, klient_aktif sudah benar, hanya DHCP static lease pending (auto-fix oleh parity guard).

**Nginx log post-deploy**: **BERSIH** — tidak ada 502 atau 500 seit deploy 07:42.

**Backend WARNING/ERROR log** post-deploy: **BERSIH** — tidak ada exception apapun.

**Celery warning**: 1x stale quota sync lock reclaim (expected behavior fresh restart, tidak berulang).

**Settings produksi**:
- `MIKROTIK_DHCP_STATIC_LEASE_ENABLED: True`
- `MIKROTIK_DHCP_LEASE_SERVER_NAME: Klien`
- `QUOTA_FUP_THRESHOLD_MB: 3072`

→ 6 `dhcp_lease_missing` akan auto-fix dalam siklus parity guard berikutnya (≤10 menit).

**Resource usage** (post-deploy):
- nuxt frontend: 59.55 MB (0.75%)
- flask backend: 982.8 MB (12.38%)
- celery worker: 550.8 MB (6.94%)
- celery beat: 84.13 MB (1.06%)
- redis: 4.01 MB (0.05%)
- postgres: 57.9 MB (0.73%)
- Total lpsaring stack: ~1.74 GB / 7.755 GB (22.4%) ←  HEALTHY

---

## Analisa Arsitektur Auth Flow vs simulasi-auth-otp.html (Mar 18 Sesi 3)

### Skenario 1 (Popup Captive + Session Aktif) ✅
- Router membuka login.home.arpa → redirect ke `/captive` dengan `client_ip`, `client_mac`, `link_login_only`
- Frontend `auth/me 200` → skip OTP → check hotspot-session-status → direct ke portal
- **Status**: Implemented correctly. Login.html di MikroTik redirect ke `/captive`.

### Skenario 2 (/login Manual + Identity Stored) ✅
- User buka /login, cookie masih valid, `resolveHotspotIdentity` temukan identity di query/localStorage
- `fetchHotspotStatus()` → jika aktif → `continueToPortal` tanpa OTP
- **Status**: Implemented correctly. `rememberHotspotIdentity` menyimpan ke localStorage.

### Skenario 3 (/login Manual + Identity Kosong) ✅ (fix commit `c39dcd0b` + sesi ini)
- User buka `/login/hotspot-required` tanpa `client_ip`/`client_mac`
- `fetchHotspotStatus()` → `hotspotRequired=true`, `hotspotHintApplied=false`
- `hasExplicitHotspotIdentity()=false` → auto-trigger `beginSilentHotspotBridge()` ke `hotspotBridgeTargetUrl`
- Router mengembalikan identity, redirect kembali dengan `bridge_resume=1`
- `onMounted()` deteksi `bridge_resume=1` → `activateInternetOneClick()` dengan identity baru
- **Status**: Implemented. Auto-bridge di `onMounted()` baris 658-669.

### Skenario 4 (Background-Only Tidak Cukup) ✅
- `fetch(no-cors)` / `img beacon` ke login.home.arpa: best-effort ping, bukan authoritative source
- Sistem sudah benar: `triggerHotspotProbe()` hanya dipakai sebagai warmup, bukan decision source
- Decision dibuat dari `fetchHotspotStatus()` (backend API) yang authoritative
- **Status**: Design correct. Simulasi sudah terdokumentasi batas background bridge.

### Gap yang Masih Relevan dari Simulasi:
- **bridge target fallback**: `hotspotBridgeTargetUrl` = `resolveHotspotBridgeTarget(mikrotikLoginUrl, probeUrl)`. Jika `NUXT_PUBLIC_HOTSPOT_CONTEXT_PROBE_URL` tidak diset, bridge target = mikrotikLoginUrl biasa. Ini sudah benar untuk sistem dengan login.home.arpa.
- **Skenario 4 — manual fallback**: Tombol "Buka Login Hotspot" tampil saat `showFallbackLogin=true && loginHotspotUrl` tersedia. User masih bisa manual buka router login. OK.

---

## Pending (Perlu Session Terpisah)

- **7.3 Akses-Banking scheduler**: Celery task populate `Bypass_Server` dengan banking domain IPs (DNS resolve periodik)
- **11.3 MAC randomization**: Frontend detection bit LAA + tampilkan warning + panduan user nonaktifkan random MAC
- **6 dhcp_lease_missing**: Auto-fix oleh parity guard dalam ≤10 menit dari deploy (DHCP_ENABLED=True, SERVER=Klien)
