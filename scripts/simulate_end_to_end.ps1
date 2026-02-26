Param(
  [string]$BaseUrl = "http://localhost",
  [string]$AdminPhone = "0817701083",
  [string]$AdminName = "Super Admin",
  [string]$AdminPassword = "alhabsyi",
  [string]$AdminBlok = "A",
  [string]$AdminKamar = "Kamar_1",
  [string]$UserPhone = "0811580040",
  [string]$UserName = "User Demo",
  [string]$UserBlok = "A",
  [string]$UserKamar = "1",
  [string]$KomandanPhone = "081234000003",
  [string]$KomandanName = "Komandan Demo",
  [string]$KomandanBlok = "A",
  [string]$KomandanKamar = "2",
  [int]$KomandanRequestMb = 1024,
  [int]$KomandanRequestDays = 7,
  [string]$SimulatedClientIp = "172.16.15.254",
  [string]$SimulatedClientMac = "4E:C3:55:C6:21:67",
  [string]$SimulatedKomandanIp = "172.16.15.253",
  [string]$SimulatedPublicIp = "202.65.238.59",
  # NOTE: Saat dipanggil via `powershell -File`, argumen sering masuk sebagai string.
  # Karena itu flag boolean di sini diterima sebagai object dan akan dinormalisasi (true/false/1/0).
  [object]$FreshStart = $true,
  [object]$CleanupAddressList = $true,
  [object]$RunKomandanFlow = $true,
  # Deprecated: sebelumnya dipakai untuk memilih backend/.env.<profile>.
  # Sekarang dev stack memakai root .env (DB_*) + root .env.public (public URL + NUXT_PUBLIC_*).
  [string]$AppEnv = "local",
  [object]$Build = $false,
  [string]$BindingTypeAllowed = "regular",
  [object]$EnableMikrotikOps = $true,
  [object]$ApplyMikrotikOnQuotaSimulation = $true,
  [object]$UseOtpBypassOnly = $true,
  [string]$OtpBypassCode = $null,

  # Isolasi Docker Compose agar E2E tidak mengganggu stack dev.
  [object]$UseIsolatedCompose = $true,
  [string]$ComposeProjectName = "hotspot-portal-e2e",
  [int]$IsolatedNginxPort = 8089
)

$ErrorActionPreference = "Stop"

function Normalize-Bool([object]$Value, [bool]$Default) {
  if ($null -eq $Value) { return $Default }
  if ($Value -is [bool]) { return [bool]$Value }
  $s = ("$Value").Trim().ToLowerInvariant()
  if ($s -in @('1','true','t','yes','y','on')) { return $true }
  if ($s -in @('0','false','f','no','n','off')) { return $false }
  return $Default
}

function Normalize-PhoneToE164([string]$Phone) {
  if (-not $Phone) { return $Phone }
  $raw = ("$Phone").Trim()
  if (-not $raw) { return $raw }

  # Jika sudah +E.164, bersihkan ke +digits.
  if ($raw.StartsWith('+')) {
    $digits = ($raw -replace '[^0-9]', '')
    return ('+' + $digits)
  }

  $digits = ($raw -replace '[^0-9]', '')
  if (-not $digits) { return $raw }

  # 00<cc><number> => +<cc><number>
  if ($digits.StartsWith('00') -and $digits.Length -gt 2) {
    return ('+' + $digits.Substring(2))
  }

  # Indonesia legacy handling
  if ($digits.StartsWith('0')) {
    return ('+62' + $digits.Substring(1))
  }
  if ($digits.StartsWith('8')) {
    return ('+62' + $digits)
  }
  if ($digits.StartsWith('62')) {
    return ('+' + $digits)
  }

  # Asumsi internasional tanpa '+' (mis. 675...)
  return ('+' + $digits)
}

$FreshStart = Normalize-Bool $FreshStart $true
$CleanupAddressList = Normalize-Bool $CleanupAddressList $true
$RunKomandanFlow = Normalize-Bool $RunKomandanFlow $true
$Build = Normalize-Bool $Build $false
$EnableMikrotikOps = Normalize-Bool $EnableMikrotikOps $true
$ApplyMikrotikOnQuotaSimulation = Normalize-Bool $ApplyMikrotikOnQuotaSimulation $true
$UseOtpBypassOnly = Normalize-Bool $UseOtpBypassOnly $true
$UseIsolatedCompose = Normalize-Bool $UseIsolatedCompose $true

if (-not $OtpBypassCode) {
  if ($env:OTP_BYPASS_CODE) {
    $OtpBypassCode = $env:OTP_BYPASS_CODE
  } else {
    $OtpBypassCode = "000000"
  }
}

if (-not $UseOtpBypassOnly) {
  throw "Mode non-bypass dinonaktifkan. Jalankan dengan -UseOtpBypassOnly true agar tidak mengirim OTP real."
}

function Get-DotEnvValue([string]$Path, [string]$Key) {
  if (-not (Test-Path $Path)) { return $null }
  $lines = Get-Content -Path $Path -ErrorAction SilentlyContinue
  foreach ($line in $lines) {
    $t = ("$line").Trim()
    if (-not $t -or $t.StartsWith('#')) { continue }
    $idx = $t.IndexOf('=')
    if ($idx -lt 1) { continue }
    $k = $t.Substring(0, $idx).Trim()
    if ($k -ne $Key) { continue }
    $v = $t.Substring($idx + 1).Trim()
    if ($v.StartsWith('"') -and $v.EndsWith('"')) { $v = $v.Substring(1, $v.Length - 2) }
    return $v
  }
  return $null
}

function Get-HostFromUrl([string]$Url) {
  try {
    if (-not $Url) { return $null }
    $u = [Uri]$Url
    return $u.Host
  } catch {
    return $null
  }
}

if ($env:E2E_BASE_URL) { $BaseUrl = $env:E2E_BASE_URL }
if ($env:E2E_ADMIN_PHONE) { $AdminPhone = $env:E2E_ADMIN_PHONE }
if ($env:E2E_ADMIN_NAME) { $AdminName = $env:E2E_ADMIN_NAME }
if ($env:E2E_ADMIN_PASSWORD) { $AdminPassword = $env:E2E_ADMIN_PASSWORD }
if ($env:E2E_USER_PHONE) { $UserPhone = $env:E2E_USER_PHONE }
if ($env:E2E_USER_NAME) { $UserName = $env:E2E_USER_NAME }
if ($env:E2E_USER_BLOK) { $UserBlok = $env:E2E_USER_BLOK }
if ($env:E2E_USER_KAMAR) { $UserKamar = $env:E2E_USER_KAMAR }
if ($env:E2E_CLIENT_IP) { $SimulatedClientIp = $env:E2E_CLIENT_IP }
if ($env:E2E_CLIENT_MAC) { $SimulatedClientMac = $env:E2E_CLIENT_MAC }

# Normalisasi nomor agar konsisten dengan backend (OTP Redis key menggunakan nomor yang sudah dinormalisasi).
$AdminPhoneE164 = Normalize-PhoneToE164 $AdminPhone
$UserPhoneE164 = Normalize-PhoneToE164 $UserPhone
$KomandanPhoneE164 = Normalize-PhoneToE164 $KomandanPhone

[string]$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
[string]$ProjectRoot = Split-Path -Parent $ScriptDir
[string]$ComposeFile = Join-Path $ProjectRoot "docker-compose.yml"
[string]$ComposeE2EStandaloneFile = Join-Path $ProjectRoot "docker-compose.e2e.yml"
[string]$RootDotEnvPath = Join-Path $ProjectRoot ".env"
[string]$RootPublicEnvPath = Join-Path $ProjectRoot ".env.public"
$TranscriptPath = Join-Path $ScriptDir ("simulate_end_to_end_{0}.log" -f (Get-Date -Format "yyyyMMdd_HHmmss"))
Start-Transcript -Path $TranscriptPath | Out-Null

if ($UseIsolatedCompose) {
  $ComposeFile = $ComposeE2EStandaloneFile
}

if (-not (Test-Path $ComposeFile)) {
  throw "Compose file tidak ditemukan: $ComposeFile"
}

if ($UseIsolatedCompose) {
  # Jika user tidak mengisi BaseUrl, arahkan default ke port Nginx isolated.
  if (-not $PSBoundParameters.ContainsKey('BaseUrl')) {
    $BaseUrl = "http://localhost:$IsolatedNginxPort"
  }
}

if ($PSBoundParameters.ContainsKey('AppEnv')) {
  Write-Host "[INFO] Parameter -AppEnv sudah deprecated dan diabaikan (compose dev tidak lagi memilih env berdasarkan APP_ENV)." -ForegroundColor Yellow
}

# Preflight: dev compose butuh .env (DB_*) dan .env.public (public URL + NUXT_PUBLIC_*).
# E2E standalone butuh backend/.env.<profile> dan frontend/.env.<profile>.
if (-not $UseIsolatedCompose) {
  if (-not (Test-Path $RootDotEnvPath)) {
    throw "File .env tidak ditemukan: $RootDotEnvPath`nSalin dari .env.example -> .env (isi DB_NAME/DB_USER/DB_PASSWORD)."
  }
  if (-not (Test-Path $RootPublicEnvPath)) {
    throw "File .env.public tidak ditemukan: $RootPublicEnvPath`nSalin dari .env.public.example -> .env.public (isi NUXT_PUBLIC_* dan URL dev)."
  }
} else {
  $effectiveAppEnv = $env:APP_ENV
  if (-not $effectiveAppEnv) { $effectiveAppEnv = "local" }
  $backendEnv = Join-Path $ProjectRoot ("backend/.env.{0}" -f $effectiveAppEnv)
  $frontendEnv = Join-Path $ProjectRoot ("frontend/.env.{0}" -f $effectiveAppEnv)
  if (-not (Test-Path $backendEnv)) {
    throw "File backend env tidak ditemukan: $backendEnv`nBuat dari backend/.env.local.example -> backend/.env.local (atau set APP_ENV sesuai file yang ada)."
  }
  if (-not (Test-Path $frontendEnv)) {
    throw "File frontend env tidak ditemukan: $frontendEnv`nBuat dari frontend/.env.local.example -> frontend/.env.local (atau set APP_ENV sesuai file yang ada)."
  }
}

# Deprecated: APP_ENV tidak lagi dipakai untuk memilih env_file di compose.
# Tetap dipertahankan sebagai parameter agar kompatibel dengan pemanggilan lama.

function Invoke-Compose([string[]]$ComposeArgs) {
  $cmd = @("compose", "-f", $ComposeFile)
  if ($UseIsolatedCompose) {
    # Project name dipakai agar `down -v` hanya menyentuh stack E2E.
    $cmd += @("-p", $ComposeProjectName)
  }
  $cmd += @("--project-directory", $ProjectRoot) + $ComposeArgs
  & docker @cmd
  if ($LASTEXITCODE -ne 0) {
    throw "docker compose gagal (exit=$LASTEXITCODE): docker $($cmd -join ' ')"
  }
}

function Test-BindingDebug($baseUrl, $adminToken, $label, $userId, $clientIp, $clientMac) {
  $body = @{
    user_id = $userId
    client_ip = $clientIp
    client_mac = $clientMac
  } | ConvertTo-Json
  try {
    $result = Invoke-RestMethod -Method Post -Uri "$baseUrl/api/auth/debug/binding" -Headers @{ Authorization = "Bearer $adminToken" } -ContentType "application/json" -Body $body
    $binding = $result.binding
    Write-Host "Binding debug ($label): input_ip=$($binding.input_ip) input_mac=$($binding.input_mac) resolved_ip=$($binding.resolved_ip) ip_source=$($binding.ip_source) ip_msg=$($binding.ip_message) resolved_mac=$($binding.resolved_mac) mac_source=$($binding.mac_source) mac_msg=$($binding.mac_message)"
  } catch {
    Write-Host "Binding debug ($label) gagal: $($_.Exception.Message)"
  }
}

function Force-UserActiveDirect([string]$phoneNumber) {
  if (-not $phoneNumber) { return }
  $envArgs = @(
    "-e", "TARGET_PHONE=$phoneNumber"
  )

  $py = @'
import os
from app import create_app
from app.extensions import db
from app.infrastructure.db.models import User, ApprovalStatus, UserRole
from app.utils.formatters import get_phone_number_variations
from app.services import settings_service

app = create_app()
with app.app_context():
    phone = os.environ.get("TARGET_PHONE") or ""
    variations = get_phone_number_variations(phone)
    user = db.session.query(User).filter(User.phone_number.in_(variations)).first()
    if not user:
        print(f"Force-activate skipped: user not found for {phone}")
        raise SystemExit(0)

    user.is_blocked = False
    user.blocked_reason = None
    user.is_active = True
    user.approval_status = ApprovalStatus.APPROVED

    # Pastikan field MikroTik minimal terisi agar endpoint admin update tidak gagal
    # saat ENABLE_MIKROTIK_OPERATIONS=True.
    try:
      if not user.mikrotik_server_name:
        if getattr(user, 'role', None) == UserRole.KOMANDAN:
          user.mikrotik_server_name = settings_service.get_setting('MIKROTIK_DEFAULT_SERVER_KOMANDAN', 'testing')
        else:
          user.mikrotik_server_name = settings_service.get_setting('MIKROTIK_DEFAULT_SERVER_USER', 'testing')
    except Exception:
      pass

    try:
      if not user.mikrotik_profile_name:
        user.mikrotik_profile_name = settings_service.get_setting('MIKROTIK_ACTIVE_PROFILE', 'profile-aktif')
    except Exception:
      pass

    db.session.commit()
    print(f"Force-activate OK: user_id={user.id} phone={user.phone_number}")
'@

  $pyB64 = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($py))
  $cmdArgs = @("exec", "-T") + $envArgs + @(
    "backend",
    "python",
    "-c",
    "import base64,sys; exec(base64.b64decode('$pyB64').decode('utf-8'))"
  )
  try {
    Invoke-Compose $cmdArgs | Out-Null
  } catch {
    Write-Host "[WARN] Force-activate gagal untuk phone=${phoneNumber}: $($_.Exception.Message)" -ForegroundColor Yellow
  }
}

function Invoke-AutoDebtThresholdSimulation([string]$phoneNumber, [string]$clientIp, [string]$clientMac) {
  if (-not $phoneNumber) { return }
  $envArgs = @(
    "-e", "TARGET_PHONE=$phoneNumber",
    "-e", "TARGET_IP=$clientIp",
    "-e", "TARGET_MAC=$clientMac"
  )

  $py = @'
import os
from app import create_app
from app.extensions import db
from app.infrastructure.db.models import User, ApprovalStatus
from app.services.hotspot_sync_service import resolve_target_profile_for_user, sync_address_list_for_single_user
from app.services import settings_service
from app.utils.formatters import get_phone_number_variations

app = create_app()
with app.app_context():
    phone = os.environ.get("TARGET_PHONE") or ""
    client_ip = os.environ.get("TARGET_IP") or None
    variations = get_phone_number_variations(phone)
    user = db.session.query(User).filter(User.phone_number.in_(variations)).first()
    if not user:
        raise SystemExit(f"User not found for {phone}")

    user.is_active = True
    user.approval_status = ApprovalStatus.APPROVED
    user.is_unlimited_user = False

    # Simulasi auto debt melewati limit.
    user.total_quota_purchased_mb = 1000
    user.total_quota_used_mb = 1700
    user.auto_debt_offset_mb = 0

    # Pastikan tidak terkunci oleh reason lain agar policy auto-debt bisa dievaluasi jelas.
    user.is_blocked = False
    user.blocked_reason = None
    user.blocked_at = None
    user.blocked_by_id = None

    if not user.mikrotik_profile_name:
        user.mikrotik_profile_name = settings_service.get_setting("MIKROTIK_ACTIVE_PROFILE", "profile-aktif")

    target_profile = resolve_target_profile_for_user(user)
    db.session.commit()

    # Sinkronisasi address-list single-user agar blocked list langsung terbentuk.
    try:
        sync_address_list_for_single_user(user, client_ip=client_ip)
        db.session.commit()
    except Exception as e:
        print(f"WARN sync_address_list_for_single_user failed: {e}")

    print(
        f"Auto-debt threshold simulation: user_id={user.id} is_blocked={user.is_blocked} "
        f"blocked_reason={user.blocked_reason} target_profile={target_profile}"
    )
'@

  $pyB64 = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($py))
  $cmdArgs = @("exec", "-T") + $envArgs + @(
    "backend",
    "python",
    "-c",
    "import base64,sys; exec(base64.b64decode('$pyB64').decode('utf-8'))"
  )
  try {
    Invoke-Compose $cmdArgs
  } catch {
    Write-Host "[WARN] Simulasi auto debt threshold gagal: $($_.Exception.Message)" -ForegroundColor Yellow
  }
}

function Assert-AutoDebtBindingRegular([string]$phoneNumber, [string]$clientMac) {
  if (-not $phoneNumber) { return }
  $envArgs = @(
    "-e", "TARGET_PHONE=$phoneNumber",
    "-e", "TARGET_MAC=$clientMac"
  )

  $py = @'
import os
from app import create_app
from app.extensions import db
from app.infrastructure.db.models import User
from app.infrastructure.gateways.mikrotik_client import get_mikrotik_connection
from app.utils.formatters import get_phone_number_variations, format_to_local_phone

app = create_app()
with app.app_context():
    phone = os.environ.get("TARGET_PHONE") or ""
    target_mac = (os.environ.get("TARGET_MAC") or "").upper()
    variations = get_phone_number_variations(phone)
    user = db.session.query(User).filter(User.phone_number.in_(variations)).first()
    if not user:
        raise SystemExit(f"User not found for {phone}")

    username_08 = format_to_local_phone(user.phone_number) or ""

    with get_mikrotik_connection() as api:
        if not api:
            print("SKIP: MikroTik connection not available for binding assertion")
            raise SystemExit(0)

        entries = api.get_resource("/ip/hotspot/ip-binding").get()
        matched = []
        for entry in entries:
            mac = str(entry.get("mac-address") or "").upper()
            comment = str(entry.get("comment") or "")
            if target_mac and mac == target_mac:
                matched.append(entry)
                continue
            if username_08 and (f"user={username_08}" in comment or f"uid={user.id}" in comment):
                matched.append(entry)

        blocked_entries = [e for e in matched if str(e.get("type") or "").lower() == "blocked"]
        if blocked_entries:
            raise SystemExit(f"Found blocked ip-binding entries for auto-debt user: {blocked_entries}")

        print(f"IP-binding OK for auto-debt flow: matched_entries={len(matched)} type!=blocked")
'@

  $pyB64 = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($py))
  $cmdArgs = @("exec", "-T") + $envArgs + @(
    "backend",
    "python",
    "-c",
    "import base64,sys; exec(base64.b64decode('$pyB64').decode('utf-8'))"
  )
  try {
    Invoke-Compose $cmdArgs
  } catch {
    Write-Host "[WARN] Skip assert ip-binding regular untuk auto debt: $($_.Exception.Message)" -ForegroundColor Yellow
  }
}

function Clear-AddressListForIp($ipAddress) {
  if (-not $ipAddress) { return }
  $envArgs = @(
    "-e", "TARGET_IP=$ipAddress"
  )

  $py = @'
import os
from app import create_app
from app.services import settings_service
from app.infrastructure.gateways.mikrotik_client import get_mikrotik_connection, remove_address_list_entry

app = create_app()
with app.app_context():
    target_ip = os.environ.get("TARGET_IP")
    if not target_ip:
        raise SystemExit("TARGET_IP empty")

    list_names = [
        settings_service.get_setting("MIKROTIK_ADDRESS_LIST_ACTIVE", "active"),
        settings_service.get_setting("MIKROTIK_ADDRESS_LIST_FUP", "fup"),
        settings_service.get_setting("MIKROTIK_ADDRESS_LIST_INACTIVE", "inactive"),
        settings_service.get_setting("MIKROTIK_ADDRESS_LIST_EXPIRED", "expired"),
        settings_service.get_setting("MIKROTIK_ADDRESS_LIST_HABIS", "habis"),
        settings_service.get_setting("MIKROTIK_ADDRESS_LIST_BLOCKED", "blocked"),
    ]

    removed = 0
    with get_mikrotik_connection() as api:
        if not api:
            raise SystemExit("MikroTik connection failed")
        for list_name in list_names:
            if not list_name:
                continue
            ok, _msg = remove_address_list_entry(api, target_ip, list_name)
            if ok:
                removed += 1
    print(f"Cleanup address-list: ip={target_ip} removed={removed}")
'@

  $pyB64 = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($py))
  $cmdArgs = @("exec", "-T") + $envArgs + @(
    "backend",
    "python",
    "-c",
    "import base64,sys; exec(base64.b64decode('$pyB64').decode('utf-8'))"
  )
  try {
    Invoke-Compose $cmdArgs
  } catch {
    Write-Host "[WARN] Skip MikroTik cleanup address-list (ip=$ipAddress): $($_.Exception.Message)"
  }
}

function Assert-AddressListStatus($ipAddress, $expectedStatus, $phoneNumber, $clientMac) {
  if (-not $ipAddress -or -not $expectedStatus) { return }
  $envArgs = @(
    "-e", "TARGET_IP=$ipAddress",
    "-e", "EXPECTED_STATUS=$expectedStatus",
    "-e", "TARGET_PHONE=$phoneNumber",
    "-e", "TARGET_MAC=$clientMac"
  )

  $py = @'
import os
from app import create_app
from app.extensions import db
from app.infrastructure.db.models import User
from app.infrastructure.gateways.mikrotik_client import get_mikrotik_connection
from app.services import settings_service
from app.utils.formatters import get_phone_number_variations, format_to_local_phone

STATUS_KEYS = {
  "active": "MIKROTIK_ADDRESS_LIST_ACTIVE",
  "fup": "MIKROTIK_ADDRESS_LIST_FUP",
  "habis": "MIKROTIK_ADDRESS_LIST_HABIS",
  "expired": "MIKROTIK_ADDRESS_LIST_EXPIRED",
  "inactive": "MIKROTIK_ADDRESS_LIST_INACTIVE",
  "blocked": "MIKROTIK_ADDRESS_LIST_BLOCKED",
}

def _matches_comment(comment, user_id, username_08):
  if not comment:
    return False
  text = str(comment)
  return f"user_id={user_id}" in text or f"phone={username_08}" in text or f"user={user_id}" in text

app = create_app()
with app.app_context():
  target_ip = os.environ.get("TARGET_IP")
  expected_status = (os.environ.get("EXPECTED_STATUS") or "").lower()
  phone = os.environ.get("TARGET_PHONE") or ""
  target_mac = (os.environ.get("TARGET_MAC") or "").upper()
  if not target_ip:
    raise SystemExit("TARGET_IP empty")
  if expected_status not in STATUS_KEYS:
    raise SystemExit(f"Unknown EXPECTED_STATUS: {expected_status}")

  variations = get_phone_number_variations(phone)
  user = db.session.query(User).filter(User.phone_number.in_(variations)).first()
  if not user:
    raise SystemExit("User not found for address-list validation")
  username_08 = format_to_local_phone(user.phone_number) or ""

  list_names = {
    key: (settings_service.get_setting(cfg, key) or key)
    for key, cfg in STATUS_KEYS.items()
  }
  expected_list = list_names[expected_status]

  with get_mikrotik_connection() as api:
    if not api:
      raise SystemExit("MikroTik connection failed")

    candidate_ips = []
    if target_ip:
      candidate_ips.append(target_ip)

    bindings = api.get_resource("/ip/hotspot/ip-binding").get()
    for entry in bindings:
      mac = str(entry.get("mac-address") or "").upper()
      address = str(entry.get("address") or "")
      comment = entry.get("comment")
      if target_mac and mac == target_mac and address:
        candidate_ips.append(address)
        continue
      if _matches_comment(comment, user.id, username_08) and address:
        candidate_ips.append(address)

    seen = set()
    candidate_ips = [ip for ip in candidate_ips if ip and not (ip in seen or seen.add(ip))]

    success = False
    for ip in candidate_ips:
      entries = api.get_resource("/ip/firewall/address-list").get(address=ip)
      if not entries:
        continue

      matching_expected = [
        e for e in entries
        if e.get("list") == expected_list and _matches_comment(e.get("comment"), user.id, username_08)
      ]
      if not matching_expected:
        matching_expected = [
          e for e in entries
          if e.get("list") == expected_list
        ]
      if not matching_expected:
        continue

      other_status_lists = {v for k, v in list_names.items() if v and v != expected_list}
      conflicts = [e for e in entries if e.get("list") in other_status_lists]
      if conflicts:
        lists = ",".join(sorted({str(e.get("list")) for e in conflicts}))
        raise SystemExit(f"Conflicting lists for ip={ip}: {lists}")

      print(f"Address-list OK: ip={ip} status={expected_status} list={expected_list}")
      success = True
      break

    if not success:
      raise SystemExit(f"Expected list '{expected_list}' not found for ip(s)={candidate_ips}")
'@

  $pyB64 = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($py))
  $cmdArgs = @("exec", "-T") + $envArgs + @(
    "backend",
    "python",
    "-c",
    "import base64,sys; exec(base64.b64decode('$pyB64').decode('utf-8'))"
  )
  $maxAttempts = 4
  for ($attempt = 1; $attempt -le $maxAttempts; $attempt++) {
    try {
      Invoke-Compose $cmdArgs
      return
    } catch {
      if ($attempt -lt $maxAttempts) {
        Write-Host "[WARN] MikroTik assert address-list belum konsisten (attempt=$attempt/$maxAttempts, ip=$ipAddress status=$expectedStatus). Retry 2 detik..." -ForegroundColor Yellow
        Start-Sleep -Seconds 2
        continue
      }
      Write-Host "[WARN] Skip MikroTik assert address-list (ip=$ipAddress status=$expectedStatus): $($_.Exception.Message)"
    }
  }
}

Write-Host "[1/14] Start containers"
if ($FreshStart) {
  Write-Host "[0/14] Fresh start (down + remove volumes)"
  Invoke-Compose @("down", "-v", "--remove-orphans")
}
if ($Build) {
  Invoke-Compose @("up", "-d", "--build", "db", "redis", "backend", "migrate", "celery_worker", "celery_beat", "frontend", "nginx")
} else {
  Invoke-Compose @("up", "-d", "db", "redis", "backend", "migrate", "celery_worker", "celery_beat", "frontend", "nginx")
}

Write-Host "[1.5/14] Wait for backend readiness"
$maxAttempts = 90
$candidateApiBases = @($BaseUrl)
if ($UseIsolatedCompose) {
  $candidateApiBases = @(
    $BaseUrl,
    "http://localhost:$IsolatedNginxPort",
    "http://127.0.0.1:$IsolatedNginxPort",
    "http://localhost:5011",
    "http://127.0.0.1:5011"
  )
} else {
  $candidateApiBases += @(
    "http://localhost:5010",
    "http://127.0.0.1:5010",
    "http://localhost"
  )
}

$candidateFrontendBases = @($BaseUrl)
if ($UseIsolatedCompose) {
  $candidateFrontendBases = @(
    "http://localhost:$IsolatedNginxPort",
    "http://127.0.0.1:$IsolatedNginxPort",
    "http://localhost:3011",
    "http://127.0.0.1:3011",
    $BaseUrl
  )
} else {
  $candidateFrontendBases = @(
    "http://localhost",
    $BaseUrl
  )
}
$resolvedApiBaseUrl = $null
for ($i = 0; $i -lt $maxAttempts; $i++) {
  $ready = $false
  foreach ($base in $candidateApiBases) {
    $url = "$base/api/ping"
    try {
      Invoke-RestMethod -Method Get -Uri $url | Out-Null
      $ready = $true
      $resolvedApiBaseUrl = $base
      break
    } catch {
      continue
    }
  }
  if ($ready) { break }
  Start-Sleep -Seconds 2
  if ($i -eq ($maxAttempts - 1)) {
    Write-Host "Backend tidak siap setelah menunggu. Dump logs backend + nginx..."
    Invoke-Compose @("logs", "--tail=200", "backend", "nginx")
    throw "Backend tidak siap setelah menunggu."
  }
}
if (-not $resolvedApiBaseUrl) {
  throw "Backend tidak siap setelah menunggu."
}
$ApiBaseUrl = $resolvedApiBaseUrl.TrimEnd("/")
$FrontendBaseUrl = $null

# Frontend biasanya diakses via Nginx (BaseUrl/http://localhost). Jika backend sudah siap
# tapi Nginx/frontend belum, jangan fallback ke ApiBaseUrl karena itu akan bikin pengecekan
# halaman Nuxt (/login/*) salah (404 dari backend).
$frontendWaitSeconds = 60
for ($sec = 0; $sec -lt $frontendWaitSeconds -and -not $FrontendBaseUrl; $sec++) {
  foreach ($base in $candidateFrontendBases) {
    try {
      $headers = curl.exe -s -o NUL -D - "$base/"
      $statusLine = ($headers | Select-String -Pattern "^HTTP/").Line
      if ($statusLine -and ($statusLine -notmatch "\s502\s") -and ($statusLine -notmatch "\s504\s")) {
        $FrontendBaseUrl = $base.TrimEnd("/")
        break
      }
    } catch {
      continue
    }
  }
  if (-not $FrontendBaseUrl) {
    Start-Sleep -Seconds 1
  }
}

if (-not $FrontendBaseUrl) {
  Write-Host "[WARN] Frontend/Nginx belum siap; fallback FrontendBaseUrl -> ApiBaseUrl (status pages mungkin tidak valid)." -ForegroundColor Yellow
  $FrontendBaseUrl = $ApiBaseUrl
}
Write-Host "Backend ready via $ApiBaseUrl"
Write-Host "Frontend base via $FrontendBaseUrl"

if ($CleanupAddressList) {
  Write-Host "[1.6/14] Cleanup address-list (client + komandan + public ip)"
  Clear-AddressListForIp $SimulatedClientIp
  if ($RunKomandanFlow) {
    Clear-AddressListForIp $SimulatedKomandanIp
  }
  Clear-AddressListForIp $SimulatedPublicIp
}

Write-Host "[2/14] Run migrations"
Invoke-Compose @("exec", "-T", "backend", "flask", "db", "upgrade")

Write-Host "[3/14] Seed database"
Invoke-Compose @("exec", "-T", "backend", "flask", "seed-db")

Write-Host "[4/14] Create super admin (skip if already exists)"
try {
  Invoke-Compose @("exec", "-T", "backend", "flask", "user", "create-admin", "--phone", $AdminPhone, "--name", $AdminName, "--role", "1", "--portal-password", $AdminPassword, "--blok", $AdminBlok, "--kamar", $AdminKamar)
} catch {
  Write-Host "Admin mungkin sudah ada, lanjutkan..."
}

Write-Host "[5/14] Admin login"
$adminLoginBody = @{ username = $AdminPhone; password = $AdminPassword } | ConvertTo-Json
$adminLogin = Invoke-RestMethod -Method Post -Uri "$ApiBaseUrl/api/auth/admin/login" -ContentType "application/json" -Body $adminLoginBody
$adminToken = $adminLogin.access_token

Write-Host "[5.5/14] Set settings for simulation (fail-open IP binding + walled-garden)"
$publicBase = $null
$frontendUrl = $null
if (Test-Path $RootPublicEnvPath) {
  $publicBase = Get-DotEnvValue -Path $RootPublicEnvPath -Key "APP_PUBLIC_BASE_URL"
  $frontendUrl = Get-DotEnvValue -Path $RootPublicEnvPath -Key "FRONTEND_URL"
}
$envHost = (Get-HostFromUrl $publicBase)
if (-not $envHost) { $envHost = (Get-HostFromUrl $frontendUrl) }
if (-not $envHost) { $envHost = (Get-HostFromUrl $BaseUrl) }

$allowedHostsList = @("localhost")
if ($envHost -and ($allowedHostsList -notcontains $envHost)) { $allowedHostsList += $envHost }
$allowedHostsStr = "['{0}']" -f ($allowedHostsList -join "','")

$settingsBody = @{ settings = @{ 
  IP_BINDING_FAIL_OPEN = "True"
  IP_BINDING_TYPE_ALLOWED = $BindingTypeAllowed
  IP_BINDING_TYPE_BLOCKED = "blocked"
  REQUIRE_EXPLICIT_DEVICE_AUTH = "False"
  LOG_BINDING_DEBUG = "True"
  ENABLE_WHATSAPP_NOTIFICATIONS = "False"
  ENABLE_MIKROTIK_OPERATIONS = ($(if ($EnableMikrotikOps) { "True" } else { "False" }))
  QUOTA_DEBT_LIMIT_MB = "500"
  WALLED_GARDEN_ENABLED = "True"
  WALLED_GARDEN_ALLOWED_HOSTS = $allowedHostsStr
  WALLED_GARDEN_ALLOWED_IPS = "['$SimulatedClientIp']"
  MIKROTIK_EXPIRED_PROFILE = "profile-expired"
  MIKROTIK_BLOCKED_PROFILE = "profile-blokir"
  MIKROTIK_ADDRESS_LIST_BLOCKED = "klient_blocked"
  MIKROTIK_DEFAULT_SERVER_USER = "testing"
  MIKROTIK_DEFAULT_SERVER_KOMANDAN = "testing"
} } | ConvertTo-Json
Invoke-RestMethod -Method Put -Uri "$ApiBaseUrl/api/admin/settings" -Headers @{ Authorization = "Bearer $adminToken" } -ContentType "application/json" -Body $settingsBody

Write-Host "[6/14] Register user"
$registerBody = @{
  phone_number = $UserPhone
  full_name = $UserName
  blok = $UserBlok
  kamar = $UserKamar
  is_tamping = $false
  register_as_komandan = $false
} | ConvertTo-Json
try {
  $reg = Invoke-RestMethod -Method Post -Uri "$ApiBaseUrl/api/auth/register" -ContentType "application/json" -Body $registerBody
  $userId = $reg.user_id
} catch {
  Write-Host "User sudah terdaftar, ambil ID via admin search..."
  $users = Invoke-RestMethod -Method Get -Uri "$ApiBaseUrl/api/admin/users?search=$UserPhone" -Headers @{ Authorization = "Bearer $adminToken" }
  $userId = $users.items[0].id
}

Write-Host "[7/14] Approve user"
try {
  Invoke-RestMethod -Method Patch -Uri "$ApiBaseUrl/api/admin/users/$userId/approve" -Headers @{ Authorization = "Bearer $adminToken" }
} catch {
  Write-Host "User mungkin sudah approved, lanjutkan..."
}

Write-Host "[7.5/14] Ensure user not blocked"
try {
  $unblockBody = @{ is_blocked = $false; blocked_reason = $null } | ConvertTo-Json
  Invoke-RestMethod -Method Put -Uri "$ApiBaseUrl/api/admin/users/$userId" -Headers @{ Authorization = "Bearer $adminToken" } -ContentType "application/json" -Body $unblockBody
} catch {
  Write-Host "Gagal memastikan unblock (mungkin sudah unblocked), lanjutkan..."
}

Write-Host "[7.6/14] Force user aktif (DB direct; tanpa MikroTik)"
Force-UserActiveDirect $UserPhoneE164

Write-Host "[8/14] OTP bypass (tanpa request-otp)"
$otp = $OtpBypassCode
Write-Host "[9/14] (skip) Bypass OTP via Redis"

Write-Host "[10/14] Verify OTP (OTP-only, tanpa konteks hotspot/mikrotik)"
$verifyBody = @{
  phone_number = $UserPhoneE164
  otp = $otp
  hotspot_login_context = $false
  client_ip = $SimulatedClientIp
  client_mac = $SimulatedClientMac
} | ConvertTo-Json

# Pakai WebSession supaya cookie auth/refresh tersimpan (HttpOnly cookie tidak bisa diambil dari JS;
# di PowerShell kita harus simpan dari Set-Cookie agar bisa uji refresh-token dengan realistis).
$userSession = $null
$verifyResp = Invoke-WebRequest -UseBasicParsing -Method Post -Uri "$ApiBaseUrl/api/auth/verify-otp" -ContentType "application/json" -Body $verifyBody -SessionVariable userSession
$verify = $verifyResp.Content | ConvertFrom-Json
$userToken = $verify.access_token

try {
  $setCookieHeader = $verifyResp.Headers['Set-Cookie']
  if ($setCookieHeader) {
    Write-Host "[DEBUG] Set-Cookie from /verify-otp:" -ForegroundColor DarkGray
    if ($setCookieHeader -is [System.Array]) {
      foreach ($h in $setCookieHeader) { Write-Host ("  " + $h) -ForegroundColor DarkGray }
    } else {
      Write-Host ("  " + $setCookieHeader) -ForegroundColor DarkGray
    }
  } else {
    Write-Host "[DEBUG] No Set-Cookie header from /verify-otp" -ForegroundColor DarkGray
  }
} catch {
  # ignore
}

Write-Host "[10.1/14] Refresh-token check: new session with refresh_token only (simulate browser closed)"
try {
  $cookieUri = [Uri]($ApiBaseUrl + "/")
  $allCookies = $userSession.Cookies.GetCookies($cookieUri)

  $refreshCookieName = "refresh_token"
  $refreshCookie = $null
  foreach ($c in $allCookies) { if ($c.Name -eq $refreshCookieName) { $refreshCookie = $c; break } }
  if (-not $refreshCookie) {
    Write-Host "[WARN] refresh_token cookie tidak ditemukan. Endpoint refresh-token mungkin belum aktif di environment ini." -ForegroundColor Yellow
  } else {
    $refreshOnlySession = New-Object Microsoft.PowerShell.Commands.WebRequestSession
    $cookieObj = New-Object System.Net.Cookie
    $cookieObj.Name = $refreshCookie.Name
    $cookieObj.Value = $refreshCookie.Value
    $cookieObj.Path = "/"
    $cookieObj.Domain = $cookieUri.Host
    $refreshOnlySession.Cookies.Add($cookieUri, $cookieObj)

    $meViaRefresh = Invoke-RestMethod -Method Get -Uri "$ApiBaseUrl/api/auth/me" -WebSession $refreshOnlySession
    if (-not $meViaRefresh -or -not $meViaRefresh.user) {
      throw "Response /api/auth/me invalid via refresh-only session"
    }
    Write-Host ("OK: /api/auth/me via refresh-only session => user_id={0}" -f $meViaRefresh.user.id)
  }
} catch {
  Write-Host "[WARN] Refresh-token check gagal: $($_.Exception.Message)" -ForegroundColor Yellow
}

if ($verify.hotspot_login_required -eq $true) {
  if (-not $verify.hotspot_username -or -not $verify.hotspot_password) {
    Write-Host "[WARN] hotspot_login_required=true tapi kredensial hotspot tidak tersedia (kemungkinan MikroTik tidak aktif/terkonfigurasi di env ini). Lanjutkan simulasi tanpa login hotspot." -ForegroundColor Yellow
  }
}

Write-Host "[10.6/14] Debug binding resolution (ip+mac, public ip, dan MAC-only)"
Test-BindingDebug $ApiBaseUrl $adminToken "local-ip" $userId $SimulatedClientIp $SimulatedClientMac
Test-BindingDebug $ApiBaseUrl $adminToken "public-ip" $userId $SimulatedPublicIp $SimulatedClientMac
if ($EnableMikrotikOps) {
  # MAC-only: client_ip null agar backend mencoba resolve IP via MikroTik berdasarkan MAC device yang sudah tersimpan.
  Test-BindingDebug $ApiBaseUrl $adminToken "mac-only" $userId $null $SimulatedClientMac
}

Write-Host "[11/14] Device endpoints"
Invoke-RestMethod -Method Get -Uri "$ApiBaseUrl/api/users/me/devices" -WebSession $userSession

$cookieOriginHeaders = @{
  Origin  = $FrontendBaseUrl
  Referer = ("{0}/" -f $FrontendBaseUrl)
}
Invoke-RestMethod -Method Post -Uri "$ApiBaseUrl/api/users/me/devices/bind-current" -WebSession $userSession -Headers $cookieOriginHeaders

function Get-AccessStatusFromUser($user) {
  if ($user.is_blocked -eq $true) { return "blocked" }
  if ($user.is_active -ne $true -or $user.approval_status -ne "APPROVED") { return "inactive" }
  if ($user.is_unlimited_user -eq $true) { return "ok" }

  $totalRaw = $user.total_quota_purchased_mb
  if ($null -eq $totalRaw) { $totalRaw = 0 }
  $total = [double]$totalRaw

  $usedRaw = $user.total_quota_used_mb
  if ($null -eq $usedRaw) { $usedRaw = 0 }
  $used = [double]$usedRaw
  $remaining = $total - $used
  $expiryDate = $null
  if ($user.quota_expiry_date) { $expiryDate = [datetime]::Parse($user.quota_expiry_date) }
  $isExpired = $false
  if ($expiryDate -ne $null) { $isExpired = $expiryDate.ToUniversalTime() -lt (Get-Date).ToUniversalTime() }
  $profileNameRaw = $user.mikrotik_profile_name
  if ($null -eq $profileNameRaw) { $profileNameRaw = "" }
  $profileName = $profileNameRaw.ToString().ToLower()

  if ($isExpired) { return "expired" }
  if ($total -le 0) { return "habis" }
  if ($total -gt 0 -and $remaining -le 0) { return "habis" }
  if ($profileName.Contains("fup")) { return "fup" }
  return "ok"
}

function Show-ExpectedRedirect($status, $context) {
  $base = if ($context -eq "captive") { "/captive" } else { "/login" }
  $map = @{
    ok = ""
    blocked = if ($context -eq "captive") { "blokir" } else { "blocked" }
    inactive = "inactive"
    expired = "expired"
    habis = "habis"
    fup = "fup"
  }
  $slug = $map[$status]
  if (-not $slug) { return $base }
  return "$base/$slug"
}

function Parse-ErrorJson($err) {
  $message = $err.ErrorDetails.Message
  if (-not $message) { return $null }
  try {
    return $message | ConvertFrom-Json
  } catch {
    return $null
  }
}

function Set-UserStatus($status, $totalMb, $usedMb, $expiryDays, $profileName) {
  $envArgs = @(
    "-e", "TARGET_PHONE=$UserPhone",
    "-e", "TARGET_STATUS=$status",
    "-e", "TOTAL_MB=$totalMb",
    "-e", "USED_MB=$usedMb",
    "-e", "EXPIRY_DAYS=$expiryDays",
    "-e", "PROFILE_NAME=$profileName"
  )

  $py = @'
import os
from datetime import datetime, timezone, timedelta
from app import create_app
from app.extensions import db
from app.infrastructure.db.models import User, ApprovalStatus
from app.utils.formatters import get_phone_number_variations

app = create_app()
with app.app_context():
    phone = os.environ.get("TARGET_PHONE")
    status = os.environ.get("TARGET_STATUS")
    total_mb = float(os.environ.get("TOTAL_MB", "0"))
    used_mb = float(os.environ.get("USED_MB", "0"))
    expiry_days = int(os.environ.get("EXPIRY_DAYS", "0"))
    profile = os.environ.get("PROFILE_NAME") or None

    variations = get_phone_number_variations(phone)
    user = db.session.query(User).filter(User.phone_number.in_(variations)).first()
    if not user:
      raise SystemExit("User not found for status update")

    if status == "blocked":
        user.is_blocked = True
        user.blocked_reason = "Simulated"
        user.is_active = True
        user.approval_status = ApprovalStatus.APPROVED
    elif status == "inactive":
        user.is_blocked = False
        user.is_active = False
        user.approval_status = ApprovalStatus.APPROVED
    else:
        user.is_blocked = False
        user.is_active = True
        user.approval_status = ApprovalStatus.APPROVED

    user.total_quota_purchased_mb = total_mb
    user.total_quota_used_mb = used_mb
    if expiry_days != 0:
        user.quota_expiry_date = datetime.now(timezone.utc) + timedelta(days=expiry_days)
    else:
        user.quota_expiry_date = None

    if profile:
        user.mikrotik_profile_name = profile

    db.session.commit()
    print(f"User status updated: {status}")
'@

  $pyB64 = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($py))
  $cmdArgs = @("exec", "-T") + $envArgs + @(
    "backend",
    "python",
    "-c",
    "import base64,sys; exec(base64.b64decode('$pyB64').decode('utf-8'))"
  )
  Invoke-Compose $cmdArgs
}

function Test-RedirectWithCookie($baseUrl, $cookieValue, $label) {
  $paths = @(
    "/dashboard",
    "/beli",
    "/payment/finish",
    "/login/expired",
    "/login/habis",
    "/login/fup"
  )
  Write-Host "--- Redirect check ($label) ---"
  foreach ($path in $paths) {
    $headers = curl.exe -s -o NUL -D - -H "Cookie: $cookieValue" "$baseUrl$path"
    $statusLine = ($headers | Select-String -Pattern "^HTTP/").Line
    $location = ($headers | Select-String -Pattern "^Location:" -CaseSensitive:$false | Select-Object -First 1).Line
    if (-not $location) { $location = "" }
    Write-Host "Page $path => $statusLine $location"
  }
}


function Test-SignedStatusPage($baseUrl, $status, $sig) {
  if (-not $status -or -not $sig) { return }
  $path = if ($status -eq "blocked") { "/login/blocked" } elseif ($status -eq "inactive") { "/login/inactive" } else { "/login/$status" }
  $url = "$baseUrl$path?status=$status&sig=$sig"
  $headers = curl.exe -s -o NUL -D - $url
  $statusLine = ($headers | Select-String -Pattern "^HTTP/").Line
  $location = ($headers | Select-String -Pattern "^Location:" -CaseSensitive:$false | Select-Object -First 1).Line
  if (-not $location) { $location = "" }
  Write-Host "Signed page $path => $statusLine $location"
}

function Test-StatusPages($baseUrl, [bool]$failOnNotFound = $true) {
  $paths = @(
    "/login/blocked",
    "/login/inactive",
    "/login/expired",
    "/login/habis",
    "/login/fup",
    "/captive/blokir",
    "/captive/inactive",
    "/captive/expired",
    "/captive/habis",
    "/captive/fup"
  )
  foreach ($path in $paths) {
    $headers = curl.exe -s -o NUL -D - "$baseUrl$path"
    $statusLine = ($headers | Select-String -Pattern "^HTTP/").Line
    $location = ($headers | Select-String -Pattern "^Location:" -CaseSensitive:$false | Select-Object -First 1).Line
    if (-not $location) { $location = "" }
    Write-Host "Page $path => $statusLine $location"
    if ($failOnNotFound -and $statusLine -match "\s404\s") {
      throw "Status page tidak ditemukan: $path"
    }
  }
}

Write-Host "[11.5/14] Uji halaman status (frontend)"
Test-StatusPages $FrontendBaseUrl

Write-Host "[11.6/14] Uji redirect user (expired/habis/fup)"
$authCookie = "auth_token=$userToken"

Set-UserStatus "expired" 1024 0 -1 "user"
Test-RedirectWithCookie $FrontendBaseUrl $authCookie "expired"

Set-UserStatus "habis" 100 100 7 "user"
Test-RedirectWithCookie $FrontendBaseUrl $authCookie "habis"

Set-UserStatus "fup" 1024 200 7 "profile-fup"
Test-RedirectWithCookie $FrontendBaseUrl $authCookie "fup"

Write-Host "[11.7/14] Uji status signed (blocked/inactive)"
Set-UserStatus "blocked" 1024 0 7 "user"

$blockedOtpRequested = $false
$blockedOtpRequested = $true
$blockedOtp = $OtpBypassCode
$blockedVerifyBody = @{ phone_number = $UserPhoneE164; otp = $blockedOtp; hotspot_login_context = $false } | ConvertTo-Json
try {
  Invoke-RestMethod -Method Post -Uri "$ApiBaseUrl/api/auth/verify-otp" -ContentType "application/json" -Body $blockedVerifyBody | Out-Null
} catch {
  $payload = Parse-ErrorJson $_
  if ($payload) {
    Test-SignedStatusPage $FrontendBaseUrl $payload.status $payload.status_token
  }
}

Set-UserStatus "inactive" 1024 0 0 "user"
$inactiveOtpRequested = $false
if ($UseOtpBypassOnly) {
  $inactiveOtpRequested = $true
  $inactiveOtp = $OtpBypassCode
} else {
  $inactiveOtpBody = @{ phone_number = $UserPhoneE164 } | ConvertTo-Json
  for ($attempt = 1; $attempt -le 2 -and -not $inactiveOtpRequested; $attempt++) {
    try {
      Invoke-RestMethod -Method Post -Uri "$ApiBaseUrl/api/auth/request-otp" -ContentType "application/json" -Body $inactiveOtpBody | Out-Null
      $inactiveOtpRequested = $true
    } catch {
      $errorMessage = $_.ErrorDetails.Message
      if ($_.Exception.Message -match "closed" -or $_.Exception.Message -match "timed out") {
        Write-Host "Koneksi terputus saat request OTP (inactive), tunggu 5 detik lalu coba lagi..."
        Start-Sleep -Seconds 5
        continue
      }
      if ($errorMessage -and $errorMessage -match "Terlalu sering meminta OTP") {
        Write-Host "OTP cooldown aktif (inactive), tunggu 65 detik lalu coba lagi..."
        Start-Sleep -Seconds 65
        continue
      }
      $payload = Parse-ErrorJson $_
      if ($payload) {
        Test-SignedStatusPage $FrontendBaseUrl $payload.status $payload.status_token
        $inactiveOtpRequested = $true
        break
      }
      throw
    }
  }
  if (-not $inactiveOtpRequested) { throw "Gagal request OTP inactive setelah retry." }
  $inactiveOtp = $OtpBypassCode
}

Write-Host "[11.8/14] Reset user ke aktif (agar flow Komandan tidak terblokir)"
Set-UserStatus "active" 1024 0 7 "user"

if ($RunKomandanFlow) {
  Write-Host "[12/14] Simulasi permintaan Komandan (QUOTA)"
  $komandanRequestCreated = $false
  $komandanAttemptPhone = $KomandanPhone
  for ($attempt = 1; $attempt -le 2 -and -not $komandanRequestCreated; $attempt++) {
    if ($attempt -gt 1) {
      $randomSuffix = Get-Random -Minimum 1000 -Maximum 9999
      $komandanAttemptPhone = "0812349$randomSuffix"
      Write-Host "Retry Komandan dengan nomor baru: $komandanAttemptPhone"
    }

    $komandanAttemptPhoneE164 = Normalize-PhoneToE164 $komandanAttemptPhone

    $komandanRegisterBody = @{
      phone_number = $komandanAttemptPhone
      full_name = $KomandanName
      blok = $KomandanBlok
      kamar = $KomandanKamar
      is_tamping = $false
      register_as_komandan = $true
    } | ConvertTo-Json

    try {
      $komandanReg = Invoke-RestMethod -Method Post -Uri "$ApiBaseUrl/api/auth/register" -ContentType "application/json" -Body $komandanRegisterBody
      $komandanId = $komandanReg.user_id
    } catch {
      Write-Host "Komandan sudah terdaftar, ambil ID via admin search..."
      $komandanUsers = Invoke-RestMethod -Method Get -Uri "$ApiBaseUrl/api/admin/users?search=$komandanAttemptPhone" -Headers @{ Authorization = "Bearer $adminToken" }
      $komandanId = $komandanUsers.items[0].id
    }

    try {
      Invoke-RestMethod -Method Patch -Uri "$ApiBaseUrl/api/admin/users/$komandanId/approve" -Headers @{ Authorization = "Bearer $adminToken" } | Out-Null
    } catch {
      Write-Host "Komandan mungkin sudah approved, lanjutkan..."
    }

    try {
      $komandanUnblockBody = @{ is_blocked = $false; blocked_reason = $null } | ConvertTo-Json
      Invoke-RestMethod -Method Put -Uri "$ApiBaseUrl/api/admin/users/$komandanId" -Headers @{ Authorization = "Bearer $adminToken" } -ContentType "application/json" -Body $komandanUnblockBody | Out-Null
    } catch {
      Write-Host "Gagal memastikan unblock Komandan (mungkin sudah unblocked), lanjutkan..."
    }

    Force-UserActiveDirect $komandanAttemptPhoneE164

    $komandanOtpRequested = $false
    if ($UseOtpBypassOnly) {
      $komandanOtpRequested = $true
      $komandanOtp = $OtpBypassCode
    } else {
      $komandanOtpBody = @{ phone_number = $komandanAttemptPhoneE164 } | ConvertTo-Json
      for ($otpAttempt = 1; $otpAttempt -le 2 -and -not $komandanOtpRequested; $otpAttempt++) {
        try {
          Invoke-RestMethod -Method Post -Uri "$ApiBaseUrl/api/auth/request-otp" -ContentType "application/json" -Body $komandanOtpBody | Out-Null
          $komandanOtpRequested = $true
        } catch {
          $errorMessage = $_.ErrorDetails.Message
          if ($errorMessage -and $errorMessage -match "Terlalu sering meminta OTP") {
            Write-Host "OTP cooldown Komandan aktif, tunggu 65 detik lalu coba lagi..."
            Start-Sleep -Seconds 65
            continue
          }
          throw
        }
      }
      if (-not $komandanOtpRequested) { throw "Gagal request OTP Komandan setelah retry." }
      $komandanOtp = (Invoke-Compose @("exec", "-T", "redis", "redis-cli", "GET", "otp:$komandanAttemptPhoneE164")).Trim()
      if (-not $komandanOtp) { $komandanOtp = $OtpBypassCode }
    }
    if (-not $komandanOtp) { throw "OTP Komandan tidak ditemukan di Redis." }

    $komandanVerifyBody = @{ phone_number = $komandanAttemptPhoneE164; otp = $komandanOtp; hotspot_login_context = $false } | ConvertTo-Json
    $komandanVerify = Invoke-RestMethod -Method Post -Uri "$ApiBaseUrl/api/auth/verify-otp" -ContentType "application/json" -Body $komandanVerifyBody
    $komandanToken = $komandanVerify.access_token
    if ($komandanVerify.hotspot_login_required -eq $true) {
      if (-not $komandanVerify.hotspot_username -or -not $komandanVerify.hotspot_password) {
        Write-Host "[WARN] hotspot_login_required=true tapi kredensial hotspot Komandan tidak tersedia (kemungkinan MikroTik tidak aktif/terkonfigurasi). Lanjutkan simulasi tanpa login hotspot Komandan." -ForegroundColor Yellow
      }
    }

    Invoke-RestMethod -Method Get -Uri "$ApiBaseUrl/api/users/me/devices" -Headers @{ Authorization = "Bearer $komandanToken" } | Out-Null
    Invoke-RestMethod -Method Post -Uri "$ApiBaseUrl/api/users/me/devices/bind-current" -Headers @{ Authorization = "Bearer $komandanToken" } | Out-Null

    $komandanRequestBody = @{
      request_type = "QUOTA"
      requested_mb = $KomandanRequestMb
      requested_duration_days = $KomandanRequestDays
    } | ConvertTo-Json

    try {
      Invoke-RestMethod -Method Post -Uri "$ApiBaseUrl/api/komandan/requests" -ContentType "application/json" -Body $komandanRequestBody -Headers @{ Authorization = "Bearer $komandanToken" } | Out-Null
      $komandanRequestCreated = $true
    } catch {
      $errorMessage = $_.ErrorDetails.Message
      if ($errorMessage -and $errorMessage -match "sudah memiliki permintaan") {
        Write-Host "Komandan sudah punya permintaan yang sedang diproses; lanjutkan dengan mengambil request PENDING yang ada." -ForegroundColor Yellow
        $komandanRequestCreated = $true
        break
      }
      if ($errorMessage -and $errorMessage -match "Batas permintaan") {
        Write-Host "Limit permintaan Komandan tercapai. Mencoba ulang..."
        continue
      }
      throw
    }
  }

  if (-not $komandanRequestCreated) {
    throw "Permintaan Komandan gagal karena batas periode."
  }

  $pendingKomandan = Invoke-RestMethod -Method Get -Uri "$ApiBaseUrl/api/admin/quota-requests?status=PENDING&itemsPerPage=50" -Headers @{ Authorization = "Bearer $adminToken" }
  $komandanReq = $pendingKomandan.items | Where-Object {
    $_.requester.phone_number -eq $komandanAttemptPhoneE164 -or $_.requester.phone_number -eq $komandanAttemptPhone
  } | Select-Object -First 1
  if (-not $komandanReq) { throw "Permintaan Komandan tidak ditemukan." }

  $komandanProcessBody = @{ action = "APPROVE" } | ConvertTo-Json
  Invoke-RestMethod -Method Post -Uri "$ApiBaseUrl/api/admin/quota-requests/$($komandanReq.id)/process" -Headers @{ Authorization = "Bearer $adminToken" } -ContentType "application/json" -Body $komandanProcessBody | Out-Null
  Write-Host "Komandan request approved."

  if ($CleanupAddressList) {
    Write-Host "[12.9/14] Cleanup address-list setelah Komandan"
    Clear-AddressListForIp $SimulatedKomandanIp
    Clear-AddressListForIp $SimulatedClientIp
  }
} else {
  Write-Host "[12/14] Komandan flow dilewati (RunKomandanFlow=false)"
}

Write-Host "[13/14] Simulasi transaksi paket (SUCCESS)"
Invoke-Compose @("exec", "backend", "env", "PYTHONPATH=/app", "python", "/app/scripts/simulate_transaction.py", "--phone", $UserPhoneE164)

Write-Host "[14/17] Simulasi FUP/Habis/Expired + Walled-Garden"
Write-Host "[14/17] (OTP-only) Simulasi status kuota"
$applyArgs = @()
if ($ApplyMikrotikOnQuotaSimulation -and $EnableMikrotikOps) {
  $applyArgs = @("--apply-mikrotik")
}
$quotaArgs1 = @("exec", "backend", "env", "PYTHONPATH=/app", "python", "/app/scripts/simulate_quota.py", "--phone", $UserPhoneE164, "--status", "fup", "--total-mb", "1000") + $applyArgs
$quotaArgs2 = @("exec", "backend", "env", "PYTHONPATH=/app", "python", "/app/scripts/simulate_quota.py", "--phone", $UserPhoneE164, "--status", "habis", "--total-mb", "1000") + $applyArgs
$quotaArgs3 = @("exec", "backend", "env", "PYTHONPATH=/app", "python", "/app/scripts/simulate_quota.py", "--phone", $UserPhoneE164, "--status", "expired", "--total-mb", "1000") + $applyArgs
Invoke-Compose $quotaArgs1
Invoke-Compose $quotaArgs2
Invoke-Compose $quotaArgs3

Write-Host "[14.3/17] Simulasi auto debt >= limit (blocked profile+address-list, ip-binding tetap regular)"
Invoke-AutoDebtThresholdSimulation $UserPhoneE164 $SimulatedClientIp $SimulatedClientMac
if ($EnableMikrotikOps -and $ApplyMikrotikOnQuotaSimulation) {
  Assert-AddressListStatus -ipAddress $SimulatedClientIp -expectedStatus "blocked" -phoneNumber $UserPhoneE164 -clientMac $SimulatedClientMac
  Assert-AutoDebtBindingRegular -phoneNumber $UserPhoneE164 -clientMac $SimulatedClientMac
}

Write-Host "[14.5/17] Simulasi status blocked/inactive via admin"
$blockBody = @{ is_blocked = $true; blocked_reason = "SIMULATED" } | ConvertTo-Json
Invoke-RestMethod -Method Put -Uri "$ApiBaseUrl/api/admin/users/$userId" -Headers @{ Authorization = "Bearer $adminToken" } -ContentType "application/json" -Body $blockBody | Out-Null
try {
  $me = Invoke-RestMethod -Method Get -Uri "$ApiBaseUrl/api/auth/me" -Headers @{ Authorization = "Bearer $userToken" }
  $status = Get-AccessStatusFromUser $me
  Write-Host "Status (blocked) => $status, expected redirect: $(Show-ExpectedRedirect $status 'login')"
} catch {
  Write-Host "Status (blocked) => backend refused (expected)."
}

$unblockBody = @{ is_blocked = $false; blocked_reason = $null } | ConvertTo-Json
Invoke-RestMethod -Method Put -Uri "$ApiBaseUrl/api/admin/users/$userId" -Headers @{ Authorization = "Bearer $adminToken" } -ContentType "application/json" -Body $unblockBody | Out-Null

$inactiveBody = @{ is_active = $false } | ConvertTo-Json
Invoke-RestMethod -Method Put -Uri "$ApiBaseUrl/api/admin/users/$userId" -Headers @{ Authorization = "Bearer $adminToken" } -ContentType "application/json" -Body $inactiveBody | Out-Null
try {
  $me = Invoke-RestMethod -Method Get -Uri "$ApiBaseUrl/api/auth/me" -Headers @{ Authorization = "Bearer $userToken" }
  $status = Get-AccessStatusFromUser $me
  Write-Host "Status (inactive) => $status, expected redirect: $(Show-ExpectedRedirect $status 'login')"
} catch {
  Write-Host "Status (inactive) => backend refused (expected)."
}

$reactivateBody = @{ is_active = $true } | ConvertTo-Json
Invoke-RestMethod -Method Put -Uri "$ApiBaseUrl/api/admin/users/$userId" -Headers @{ Authorization = "Bearer $adminToken" } -ContentType "application/json" -Body $reactivateBody | Out-Null

Write-Host "[14.6/17] Status akhir user"
try {
  $me = Invoke-RestMethod -Method Get -Uri "$ApiBaseUrl/api/auth/me" -Headers @{ Authorization = "Bearer $userToken" }
  $finalStatus = Get-AccessStatusFromUser $me
  Write-Host "Status akhir => $finalStatus, expected redirect: $(Show-ExpectedRedirect $finalStatus 'login')"
} catch {
  Write-Host "Tidak bisa mengambil /auth/me pada status akhir."
}

Write-Host "[15/17] (skip) Redis/MikroTik usage sync smoke (OTP-only)"

Write-Host "[16/17] Verify OTP (OTP-only; tanpa client_ip/client_mac)"
$noContextOtpRequested = $true
$noContextOtp = $OtpBypassCode
$noContextVerifyBody = @{ phone_number = $UserPhoneE164; otp = $noContextOtp; hotspot_login_context = $false } | ConvertTo-Json
try {
  Invoke-RestMethod -Method Post -Uri "$ApiBaseUrl/api/auth/verify-otp" -ContentType "application/json" -Body $noContextVerifyBody | Out-Null
} catch {
  Write-Host "Verify OTP no-context gagal (skip)."
}

Write-Host "[17/17] Mock webhook smoke (Midtrans)"
try {
  $midtransBody = @{ transaction_status = "settlement"; order_id = "SIM-ORDER"; status_code = "200"; gross_amount = "10000"; signature_key = "test" } | ConvertTo-Json
  Invoke-RestMethod -Method Post -Uri "$ApiBaseUrl/api/transactions/notification" -ContentType "application/json" -Body $midtransBody | Out-Null
  Write-Host "Mock Midtrans webhook accepted."
} catch {
  Write-Host "Mock Midtrans webhook ditolak (expected jika signature invalid)."
}

Write-Host "Done. Cek log IP di backend:"
Write-Host "docker compose logs --tail=200 backend | Select-String 'IP determined|X-Forwarded-For'"
Write-Host "Verify-OTP binding context (tail=2000):"
Invoke-Compose @("logs", "--tail=2000", "backend") | Select-String -Pattern "Verify-OTP binding context" | ForEach-Object { $_.Line }
Stop-Transcript | Out-Null
