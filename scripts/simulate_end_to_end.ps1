Param(
  [string]$BaseUrl = "http://localhost",
  [string]$AdminPhone = "0817701083",
  [string]$AdminName = "Super Admin",
  [Alias('AdminPassword')]
  [string]$AdminPortalSecret = "alhabsyi",
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

[string]$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $ScriptDir "e2e/lib/Common.ps1")
. (Join-Path $ScriptDir "e2e/lib/StatusPolicy.ps1")
. (Join-Path $ScriptDir "e2e/lib/BackendStateOps.ps1")

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

if ($env:E2E_BASE_URL) { $BaseUrl = $env:E2E_BASE_URL }
if ($env:E2E_ADMIN_PHONE) { $AdminPhone = $env:E2E_ADMIN_PHONE }
if ($env:E2E_ADMIN_NAME) { $AdminName = $env:E2E_ADMIN_NAME }
if ($env:E2E_ADMIN_PASSWORD) { $AdminPortalSecret = $env:E2E_ADMIN_PASSWORD }
if ($env:E2E_USER_PHONE) { $UserPhone = $env:E2E_USER_PHONE }
if ($env:E2E_USER_NAME) { $UserName = $env:E2E_USER_NAME }
if ($env:E2E_USER_BLOK) { $UserBlok = $env:E2E_USER_BLOK }
if ($env:E2E_USER_KAMAR) { $UserKamar = $env:E2E_USER_KAMAR }
if ($env:E2E_CLIENT_IP) { $SimulatedClientIp = $env:E2E_CLIENT_IP }
if ($env:E2E_CLIENT_MAC) { $SimulatedClientMac = $env:E2E_CLIENT_MAC }

# Normalisasi nomor agar konsisten dengan backend (OTP Redis key menggunakan nomor yang sudah dinormalisasi).
$UserPhoneE164 = Normalize-PhoneToE164 $UserPhone

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
  Invoke-Compose @("exec", "-T", "backend", "flask", "user", "create-admin", "--phone", $AdminPhone, "--name", $AdminName, "--role", "1", "--portal-password", $AdminPortalSecret, "--blok", $AdminBlok, "--kamar", $AdminKamar)
} catch {
  Write-Host "Admin mungkin sudah ada, lanjutkan..."
}

Write-Host "[5/14] Admin login"
$adminLoginBody = @{ username = $AdminPhone; password = $AdminPortalSecret } | ConvertTo-Json
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
Set-UserLifecycleState $UserPhoneE164

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

    Set-UserLifecycleState $komandanAttemptPhoneE164

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
