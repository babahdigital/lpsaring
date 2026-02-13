Param(
  [string]$BaseUrl = "http://localhost",
  [string]$AdminPhone = "0817701083",
  [string]$AdminName = "Super Admin",
  [string]$AdminPassword = "alhabsyi",
  [string]$AdminBlok = "A",
  [string]$AdminKamar = "Kamar_1",
  [string]$UserPhone = "0811580039",
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
  [bool]$FreshStart = $true,
  [bool]$CleanupAddressList = $true,
  [bool]$RunKomandanFlow = $true,
  [string]$AppEnv = "local",
  [string]$ComposeEnvProfile = "",
  [bool]$ForceOtpBypass = $true,
  [string]$OtpBypassCode = "000000",
  [string]$BindingTypeAllowed = "regular",
  [bool]$UseOtpBypassOnly = $true
)

$ErrorActionPreference = "Stop"

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

[string]$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
[string]$ProjectRoot = Split-Path -Parent $ScriptDir
[string]$ComposeFile = Join-Path $ProjectRoot "docker-compose.yml"
[string]$ComposeOverrideFile = Join-Path $ScriptDir "docker-compose.e2e.override.yml"
$TranscriptPath = Join-Path $ScriptDir ("simulate_end_to_end_{0}.log" -f (Get-Date -Format "yyyyMMdd_HHmmss"))
Start-Transcript -Path $TranscriptPath | Out-Null

if (-not (Test-Path $ComposeFile)) {
  throw "Compose file tidak ditemukan: $ComposeFile"
}

$resolvedComposeEnv = $ComposeEnvProfile
if (-not $resolvedComposeEnv) {
  if ($AppEnv -eq "local") {
    $resolvedComposeEnv = "public"
  } else {
    $resolvedComposeEnv = $AppEnv
  }
}
$env:APP_ENV = $resolvedComposeEnv
Write-Host "Compose APP_ENV profile: $resolvedComposeEnv (runtime flag AppEnv=$AppEnv)"
if (-not $UseOtpBypassOnly) {
  Write-Host "PERINGATAN: UseOtpBypassOnly=false. Untuk simulasi dev disarankan true sesuai flow OTP bypass-only."
}

function Invoke-Compose([string[]]$ComposeArgs) {
  $cmd = @("compose", "-f", $ComposeFile)
  if (Test-Path $ComposeOverrideFile) {
    $cmd += @("-f", $ComposeOverrideFile)
  }
  $cmd += @("--project-directory", $ProjectRoot) + $ComposeArgs
  & docker @cmd
}

if ($ForceOtpBypass) {
  $overrideContent = @"
services:
  backend:
    environment:
      OTP_ALLOW_BYPASS: "True"
      OTP_BYPASS_CODE: "$OtpBypassCode"
"@
  Set-Content -Path $ComposeOverrideFile -Value $overrideContent -Encoding utf8
  Write-Host "Compose override OTP bypass aktif: $ComposeOverrideFile"
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
  Invoke-Compose $cmdArgs
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
  Invoke-Compose $cmdArgs
}

Write-Host "[1/14] Start containers"
if ($FreshStart) {
  Write-Host "[0/14] Fresh start (down + remove volumes)"
  Invoke-Compose @("down", "-v", "--remove-orphans")
}
Invoke-Compose @("up", "-d", "db", "redis", "backend", "celery_worker", "celery_beat", "frontend", "nginx")

Write-Host "[1.5/14] Wait for backend readiness"
$maxAttempts = 90
$candidateApiBases = @(
  $BaseUrl,
  "http://localhost:5010",
  "http://localhost"
)
$candidateFrontendBases = @(
  "http://localhost",
  $BaseUrl
)
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
foreach ($base in $candidateFrontendBases) {
  try {
    Invoke-RestMethod -Method Get -Uri "$base/" | Out-Null
    $FrontendBaseUrl = $base.TrimEnd("/")
    break
  } catch {
    continue
  }
}
if (-not $FrontendBaseUrl) {
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
Invoke-Compose @("exec", "backend", "flask", "db", "upgrade")

Write-Host "[3/14] Seed database"
Invoke-Compose @("exec", "backend", "flask", "seed-db")

Write-Host "[4/14] Create super admin (skip if already exists)"
try {
  Invoke-Compose @("exec", "backend", "flask", "user", "create-admin", "--phone", $AdminPhone, "--name", $AdminName, "--role", "1", "--portal-password", $AdminPassword, "--blok", $AdminBlok, "--kamar", $AdminKamar)
} catch {
  Write-Host "Admin mungkin sudah ada, lanjutkan..."
}

Write-Host "[5/14] Admin login"
$adminLoginBody = @{ username = $AdminPhone; password = $AdminPassword } | ConvertTo-Json
$adminLogin = Invoke-RestMethod -Method Post -Uri "$ApiBaseUrl/api/auth/admin/login" -ContentType "application/json" -Body $adminLoginBody
$adminToken = $adminLogin.access_token

Write-Host "[5.5/14] Set settings for simulation (fail-open IP binding + walled-garden)"
$settingsBody = @{ settings = @{ 
  IP_BINDING_FAIL_OPEN = "True"
  IP_BINDING_TYPE_ALLOWED = $BindingTypeAllowed
  REQUIRE_EXPLICIT_DEVICE_AUTH = "False"
  LOG_BINDING_DEBUG = "True"
  WALLED_GARDEN_ENABLED = "True"
  WALLED_GARDEN_ALLOWED_HOSTS = "['localhost','lpsaring.babahdigital.net']"
  WALLED_GARDEN_ALLOWED_IPS = "['172.16.15.254']"
  MIKROTIK_EXPIRED_PROFILE = "profile-expired"
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

if ($UseOtpBypassOnly) {
  Write-Host "[8/14] Request OTP (bypass)"
  $otp = "000000"
} else {
  Write-Host "[8/14] Request OTP"
  $otpBody = @{ phone_number = $UserPhone } | ConvertTo-Json
  $otpRequested = $false
  for ($attempt = 1; $attempt -le 2 -and -not $otpRequested; $attempt++) {
    try {
      Invoke-RestMethod -Method Post -Uri "$ApiBaseUrl/api/auth/request-otp" -ContentType "application/json" -Body $otpBody
      $otpRequested = $true
    } catch {
      $errorMessage = $_.ErrorDetails.Message
      if ($errorMessage -and $errorMessage -match "Terlalu sering meminta OTP") {
        Write-Host "OTP cooldown aktif, tunggu 65 detik lalu coba lagi..."
        Start-Sleep -Seconds 65
        continue
      }
      throw
    }
  }
  if (-not $otpRequested) { throw "Gagal request OTP setelah retry." }

  Write-Host "[9/14] Bypass OTP via Redis"
  $otp = (Invoke-Compose @("exec", "-T", "redis", "redis-cli", "GET", "otp:$UserPhone")).Trim()
  if (-not $otp) { throw "OTP tidak ditemukan di Redis." }
}

Write-Host "[10/14] Verify OTP via Nginx (X-Forwarded-For)"
$verifyBody = @{ phone_number = $UserPhone; otp = $otp; client_ip = $SimulatedClientIp; client_mac = $SimulatedClientMac; hotspot_login_context = $true } | ConvertTo-Json
$headers = @{ "X-Forwarded-For" = $SimulatedClientIp }
$verify = Invoke-RestMethod -Method Post -Uri "$ApiBaseUrl/api/auth/verify-otp" -ContentType "application/json" -Body $verifyBody -Headers $headers
$userToken = $verify.access_token
if ($verify.hotspot_login_required -eq $true) {
  if (-not $verify.hotspot_username -or -not $verify.hotspot_password) {
    throw "Kredensial hotspot tidak tersedia meskipun hotspot_login_required=true."
  }
}

Write-Host "[10.2/14] Uji fallback ip-binding via MAC (tanpa client_ip)"
$fallbackStart = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
Write-Host "[10.2/14] Fallback start at $fallbackStart"
if ($UseOtpBypassOnly) {
  $fallbackOtpRequested = $true
  $fallbackOtp = "000000"
} else {
  $fallbackOtpBody = @{ phone_number = $UserPhone } | ConvertTo-Json
  $fallbackOtpRequested = $false
  for ($attempt = 1; $attempt -le 2 -and -not $fallbackOtpRequested; $attempt++) {
    try {
      Invoke-RestMethod -Method Post -Uri "$ApiBaseUrl/api/auth/request-otp" -ContentType "application/json" -Body $fallbackOtpBody | Out-Null
      $fallbackOtpRequested = $true
    } catch {
      $errorMessage = $_.ErrorDetails.Message
      if ($errorMessage -and $errorMessage -match "Terlalu sering meminta OTP") {
        Write-Host "OTP cooldown aktif (fallback), tunggu 65 detik lalu coba lagi..."
        Start-Sleep -Seconds 65
        continue
      }
      throw
    }
  }
  if ($fallbackOtpRequested) {
    $fallbackOtp = (Invoke-Compose @("exec", "-T", "redis", "redis-cli", "GET", "otp:$UserPhone")).Trim()
    if (-not $fallbackOtp) {
      Write-Host "Fallback OTP tidak ditemukan di Redis."
    }
  }
}
if ($fallbackOtpRequested -and $fallbackOtp) {
  $fallbackVerifyBody = @{ phone_number = $UserPhone; otp = $fallbackOtp; client_ip = $null; client_mac = $SimulatedClientMac; hotspot_login_context = $true } | ConvertTo-Json
  try {
    $fallbackVerify = Invoke-RestMethod -Method Post -Uri "$ApiBaseUrl/api/auth/verify-otp" -ContentType "application/json" -Body $fallbackVerifyBody -Headers @{}
    $fallbackSummary = $fallbackVerify | ConvertTo-Json -Compress
    Write-Host "Fallback verify OTP sukses. Response: $fallbackSummary"
  } catch {
    Write-Host "Fallback verify OTP gagal (non-blocking): $($_.Exception.Message)"
  }
} elseif (-not $fallbackOtpRequested) {
  Write-Host "Fallback request OTP gagal (non-blocking)."
}

Write-Host "[10.5/14] Cek ip-binding & address-list (baseline)"
Invoke-Compose @("exec", "backend", "env", "PYTHONPATH=/app", "python", "/app/scripts/check_mikrotik_state.py", "--phone", $UserPhone, "--client-ip", $SimulatedClientIp, "--client-mac", $SimulatedClientMac)

Write-Host "[10.6/14] Debug binding resolution"
Test-BindingDebug $ApiBaseUrl $adminToken "local-ip" $userId $SimulatedClientIp $SimulatedClientMac
Test-BindingDebug $ApiBaseUrl $adminToken "public-ip" $userId $SimulatedPublicIp $SimulatedClientMac

Write-Host "[11/14] Device endpoints"
Invoke-RestMethod -Method Get -Uri "$ApiBaseUrl/api/users/me/devices" -Headers @{ Authorization = "Bearer $userToken" }
Invoke-RestMethod -Method Post -Uri "$ApiBaseUrl/api/users/me/devices/bind-current" -Headers @{ Authorization = "Bearer $userToken" }

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

function Invoke-JsonPostNoThrow($url, $jsonBody) {
  $responseFile = [System.IO.Path]::GetTempFileName()
  try {
    $statusCodeRaw = curl.exe -s -o $responseFile -w "%{http_code}" -H "Content-Type: application/json" -X POST --data-raw $jsonBody $url
    $rawBody = Get-Content -Path $responseFile -Raw -ErrorAction SilentlyContinue
    $parsedJson = $null
    if ($rawBody) {
      try {
        $parsedJson = $rawBody | ConvertFrom-Json
      } catch {
        $parsedJson = $null
      }
    }

    $statusCode = 0
    if ($statusCodeRaw) {
      [void][int]::TryParse(($statusCodeRaw.ToString().Trim()), [ref]$statusCode)
    }

    return @{
      status_code = $statusCode
      raw_body = $rawBody
      json = $parsedJson
    }
  } finally {
    Remove-Item -Path $responseFile -ErrorAction SilentlyContinue
  }
}

function Assert-HotspotLoginRequiredForStatus($status, $totalMb, $usedMb, $expiryDays, $profileName, [bool]$expectedRequired) {
  Set-UserStatus $status $totalMb $usedMb $expiryDays $profileName

  if ($UseOtpBypassOnly) {
    $statusOtp = "000000"
  } else {
    $statusOtpBody = @{ phone_number = $UserPhone } | ConvertTo-Json
    Invoke-RestMethod -Method Post -Uri "$ApiBaseUrl/api/auth/request-otp" -ContentType "application/json" -Body $statusOtpBody | Out-Null
    $statusOtp = (Invoke-Compose @("exec", "-T", "redis", "redis-cli", "GET", "otp:$UserPhone")).Trim()
    if (-not $statusOtp) { throw "OTP status-check tidak ditemukan di Redis." }
  }

  $statusVerifyBody = @{
    phone_number = $UserPhone
    otp = $statusOtp
    client_ip = $SimulatedClientIp
    client_mac = $SimulatedClientMac
    hotspot_login_context = $true
  } | ConvertTo-Json

  $statusVerify = Invoke-RestMethod -Method Post -Uri "$ApiBaseUrl/api/auth/verify-otp" -ContentType "application/json" -Body $statusVerifyBody -Headers @{ "X-Forwarded-For" = $SimulatedClientIp }
  $actual = [bool]$statusVerify.hotspot_login_required
  if ($actual -ne $expectedRequired) {
    throw "hotspot_login_required mismatch untuk status '$status': expected=$expectedRequired actual=$actual"
  }

  Write-Host "Policy check status=$status => hotspot_login_required=$actual (expected=$expectedRequired)"
}

function Test-QuotaWhatsappNotificationSimulation($phoneNumber) {
  $envArgs = @(
    "-e", "TARGET_PHONE=$phoneNumber"
  )

  $py = @'
from datetime import datetime, timezone, timedelta
from app import create_app
from app.extensions import db
from app.infrastructure.db.models import User
from app.services.hotspot_sync_service import _calculate_remaining, _send_quota_notifications, _send_expiry_notifications
from app.utils.formatters import get_phone_number_variations
import app.services.hotspot_sync_service as hotspot_sync_service

app = create_app()
with app.app_context():
    phone = __import__('os').environ.get('TARGET_PHONE')
    user = db.session.query(User).filter(User.phone_number.in_(get_phone_number_variations(phone))).first()
    if not user:
        raise SystemExit("User not found for WA notification simulation")

    user.is_unlimited_user = False
    user.total_quota_purchased_mb = 1000
    user.total_quota_used_mb = 900
    user.quota_expiry_date = datetime.now(timezone.utc) + timedelta(days=1)
    user.last_quota_notification_level = None
    user.last_expiry_notification_level = None
    user.last_low_quota_notif_at = None
    user.last_expiry_notif_at = None
    db.session.commit()

    sent_messages = []
    original_sender = hotspot_sync_service.send_whatsapp_message

    def fake_sender(number, message):
        sent_messages.append((number, (message or "")[:80]))
        return True

    try:
        hotspot_sync_service.send_whatsapp_message = fake_sender
        remaining_mb, remaining_percent = _calculate_remaining(user)
        _send_quota_notifications(user, remaining_percent, remaining_mb)
        _send_expiry_notifications(user)
        db.session.commit()
    finally:
        hotspot_sync_service.send_whatsapp_message = original_sender

    if user.last_quota_notification_level is None:
        raise SystemExit("WA quota-low notification level was not updated")
    if user.last_expiry_notification_level is None:
        raise SystemExit("WA expiry notification level was not updated")
    if len(sent_messages) < 2:
        raise SystemExit(f"Expected >=2 WA notifications (quota+expiry), got {len(sent_messages)}")

    print(
        f"WA notification simulation OK: sent={len(sent_messages)} "
        f"quota_level={user.last_quota_notification_level} expiry_level={user.last_expiry_notification_level}"
    )
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
  $headers = curl.exe -s -o NUL -D - -I $url
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
    $headers = curl.exe -s -o NUL -D - -I "$baseUrl$path"
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
if ($UseOtpBypassOnly) {
  $blockedOtpRequested = $true
  $blockedOtp = "000000"
} else {
  $blockedOtpBody = @{ phone_number = $UserPhone } | ConvertTo-Json
  for ($attempt = 1; $attempt -le 2 -and -not $blockedOtpRequested; $attempt++) {
    try {
      Invoke-RestMethod -Method Post -Uri "$ApiBaseUrl/api/auth/request-otp" -ContentType "application/json" -Body $blockedOtpBody | Out-Null
      $blockedOtpRequested = $true
    } catch {
      $errorMessage = $_.ErrorDetails.Message
      if ($_.Exception.Message -match "closed" -or $_.Exception.Message -match "timed out") {
        Write-Host "Koneksi terputus saat request OTP (blocked), tunggu 5 detik lalu coba lagi..."
        Start-Sleep -Seconds 5
        continue
      }
      if ($errorMessage -and $errorMessage -match "Terlalu sering meminta OTP") {
        Write-Host "OTP cooldown aktif (blocked), tunggu 65 detik lalu coba lagi..."
        Start-Sleep -Seconds 65
        continue
      }
      throw
    }
  }
  if (-not $blockedOtpRequested) {
    Write-Host "Gagal request OTP (blocked), gunakan bypass code..."
  }
  $blockedOtp = (Invoke-Compose @("exec", "-T", "redis", "redis-cli", "GET", "otp:$UserPhone")).Trim()
  if (-not $blockedOtp) {
    Write-Host "OTP tidak tersedia (blocked), gunakan bypass code..."
    $blockedOtp = "000000"
  }
}
$blockedVerifyBody = @{ phone_number = $UserPhone; otp = $blockedOtp; client_ip = $SimulatedClientIp; client_mac = $SimulatedClientMac; hotspot_login_context = $true } | ConvertTo-Json
$blockedVerifyResult = Invoke-JsonPostNoThrow "$ApiBaseUrl/api/auth/verify-otp" $blockedVerifyBody
if ($blockedVerifyResult.status_code -ge 400) {
  $payload = $blockedVerifyResult.json
  if ($payload) {
    Test-SignedStatusPage $FrontendBaseUrl $payload.status $payload.status_token
  } else {
    Write-Host "Verify blocked mengembalikan HTTP $($blockedVerifyResult.status_code) tanpa JSON ter-parse."
  }
}

Set-UserStatus "inactive" 1024 0 0 "user"
$inactiveOtpRequested = $false
if ($UseOtpBypassOnly) {
  $inactiveOtpRequested = $true
  $inactiveOtp = "000000"
} else {
  $inactiveOtpBody = @{ phone_number = $UserPhone } | ConvertTo-Json
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
  $inactiveOtp = (Invoke-Compose @("exec", "-T", "redis", "redis-cli", "GET", "otp:$UserPhone")).Trim()
  if (-not $inactiveOtp) { $inactiveOtp = "000000" }
}

Write-Host "[11.8/14] Validasi mixed policy hotspot_login_required"
Assert-HotspotLoginRequiredForStatus "active" 1000 100 7 "user" $false
Assert-HotspotLoginRequiredForStatus "fup" 1000 850 7 "profile-fup" $false
Assert-HotspotLoginRequiredForStatus "habis" 100 100 7 "profile-expired" $true
Assert-HotspotLoginRequiredForStatus "expired" 1000 200 -1 "profile-expired" $true

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

    $komandanOtpRequested = $false
    if ($UseOtpBypassOnly) {
      $komandanOtpRequested = $true
      $komandanOtp = "000000"
    } else {
      $komandanOtpBody = @{ phone_number = $komandanAttemptPhone } | ConvertTo-Json
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
      $komandanOtp = (Invoke-Compose @("exec", "-T", "redis", "redis-cli", "GET", "otp:$komandanAttemptPhone")).Trim()
      if (-not $komandanOtp) { $komandanOtp = "000000" }
    }
    if (-not $komandanOtp) { throw "OTP Komandan tidak ditemukan di Redis." }

    $komandanVerifyBody = @{ phone_number = $komandanAttemptPhone; otp = $komandanOtp; client_ip = $SimulatedKomandanIp; client_mac = $SimulatedClientMac; hotspot_login_context = $true } | ConvertTo-Json
    $komandanHeaders = @{ "X-Forwarded-For" = $SimulatedKomandanIp }
    $komandanVerify = Invoke-RestMethod -Method Post -Uri "$ApiBaseUrl/api/auth/verify-otp" -ContentType "application/json" -Body $komandanVerifyBody -Headers $komandanHeaders
    $komandanToken = $komandanVerify.access_token
    if ($komandanVerify.hotspot_login_required -eq $true) {
      if (-not $komandanVerify.hotspot_username -or -not $komandanVerify.hotspot_password) {
        throw "Kredensial hotspot Komandan tidak tersedia meskipun hotspot_login_required=true."
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
  $komandanReq = $pendingKomandan.items | Where-Object { $_.requester.phone_number -eq $komandanAttemptPhone } | Select-Object -First 1
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
Invoke-Compose @("exec", "backend", "env", "PYTHONPATH=/app", "python", "/app/scripts/simulate_transaction.py", "--phone", $UserPhone)

Write-Host "[14/17] Simulasi FUP/Habis/Expired + Walled-Garden"
Invoke-Compose @("exec", "backend", "env", "PYTHONPATH=/app", "python", "/app/scripts/ensure_mikrotik_profile.py", "--name", "profile-expired", "--comment", "auto-created")
Invoke-Compose @("exec", "backend", "env", "PYTHONPATH=/app", "python", "/app/scripts/simulate_quota.py", "--phone", $UserPhone, "--status", "fup", "--total-mb", "1000", "--apply-mikrotik")
Invoke-Compose @("exec", "backend", "env", "PYTHONPATH=/app", "python", "/app/scripts/check_mikrotik_state.py", "--phone", $UserPhone, "--client-ip", $SimulatedClientIp, "--client-mac", $SimulatedClientMac)
Assert-AddressListStatus $SimulatedClientIp "fup" $UserPhone $SimulatedClientMac
Invoke-Compose @("exec", "backend", "env", "PYTHONPATH=/app", "python", "/app/scripts/simulate_quota.py", "--phone", $UserPhone, "--status", "habis", "--total-mb", "1000", "--apply-mikrotik")
Invoke-Compose @("exec", "backend", "env", "PYTHONPATH=/app", "python", "/app/scripts/check_mikrotik_state.py", "--phone", $UserPhone, "--client-ip", $SimulatedClientIp, "--client-mac", $SimulatedClientMac)
Assert-AddressListStatus $SimulatedClientIp "habis" $UserPhone $SimulatedClientMac
Invoke-Compose @("exec", "backend", "env", "PYTHONPATH=/app", "python", "/app/scripts/simulate_quota.py", "--phone", $UserPhone, "--status", "expired", "--total-mb", "1000", "--apply-mikrotik")
Invoke-Compose @("exec", "backend", "env", "PYTHONPATH=/app", "python", "/app/scripts/check_mikrotik_state.py", "--phone", $UserPhone, "--client-ip", $SimulatedClientIp, "--client-mac", $SimulatedClientMac)
Assert-AddressListStatus $SimulatedClientIp "expired" $UserPhone $SimulatedClientMac
Invoke-Compose @("exec", "backend", "env", "PYTHONPATH=/app", "python", "/app/scripts/run_walled_garden_sync.py")

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

Write-Host "[15/17] Redis persistence smoke (clear last_bytes keys + sync)"
try {
  Invoke-Compose @("exec", "redis", "sh", "-c", "redis-cli --raw KEYS 'quota:last_bytes:mac:*' | xargs -r redis-cli DEL") | Out-Null
} catch {
  Write-Host "Gagal clear last_bytes keys (skip)."
}
try {
  Invoke-Compose @("exec", "-T", "backend", "python", "-c", "from app import create_app; from app.services.hotspot_sync_service import sync_hotspot_usage_and_profiles; app=create_app(); ctx=app.app_context(); ctx.push(); print(sync_hotspot_usage_and_profiles()); ctx.pop()") | Out-Null
} catch {
  Write-Host "Sync quota setelah clear last_bytes gagal (skip)."
}

Write-Host "[15.5/17] Simulasi WhatsApp notifikasi kuota/masa aktif (stub sender)"
Test-QuotaWhatsappNotificationSimulation $UserPhone
Write-Host "WA notification simulation passed (quota low + expiry warning)."

Write-Host "[16/17] Verify OTP tanpa client_ip/client_mac (captive context)"
if ($UseOtpBypassOnly) {
  $noContextOtpRequested = $true
  $noContextOtp = "000000"
} else {
  $noContextOtpBody = @{ phone_number = $UserPhone } | ConvertTo-Json
  $noContextOtpRequested = $false
  for ($attempt = 1; $attempt -le 2 -and -not $noContextOtpRequested; $attempt++) {
    try {
      Invoke-RestMethod -Method Post -Uri "$ApiBaseUrl/api/auth/request-otp" -ContentType "application/json" -Body $noContextOtpBody | Out-Null
      $noContextOtpRequested = $true
    } catch {
      $errorMessage = $_.ErrorDetails.Message
      if ($errorMessage -and $errorMessage -match "Terlalu sering meminta OTP") {
        Write-Host "OTP cooldown aktif (no-context), tunggu 65 detik lalu coba lagi..."
        Start-Sleep -Seconds 65
        continue
      }
      Write-Host "Request OTP no-context gagal, lanjut pakai bypass."
      break
    }
  }
  $noContextOtp = (Invoke-Compose @("exec", "-T", "redis", "redis-cli", "GET", "otp:$UserPhone")).Trim()
  if (-not $noContextOtp) {
    Write-Host "OTP no-context tidak tersedia, gunakan bypass code..."
    $noContextOtp = "000000"
  }
}
$noContextVerifyBody = @{ phone_number = $UserPhone; otp = $noContextOtp; hotspot_login_context = $true } | ConvertTo-Json
try {
  $noContextVerify = Invoke-RestMethod -Method Post -Uri "$ApiBaseUrl/api/auth/verify-otp" -ContentType "application/json" -Body $noContextVerifyBody
  if (-not $noContextVerify.hotspot_username -or -not $noContextVerify.hotspot_password) {
    Write-Host "Hotspot credentials tidak tersedia pada no-context verify."
  }
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
& docker compose -f $ComposeFile --project-directory $ProjectRoot logs --tail=2000 backend | Select-String -Pattern "Verify-OTP binding context" | ForEach-Object { $_.Line }

if (Test-Path $ComposeOverrideFile) {
  Remove-Item -Path $ComposeOverrideFile -Force -ErrorAction SilentlyContinue
}
Stop-Transcript | Out-Null
