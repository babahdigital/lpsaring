function Get-AccessStatusFromUser($user) {
  if ($user.is_blocked -eq $true) { return 'blocked' }
  if ($user.is_active -ne $true -or $user.approval_status -ne 'APPROVED') { return 'inactive' }
  if ($user.is_unlimited_user -eq $true) { return 'ok' }

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
  if ($null -ne $expiryDate) { $isExpired = $expiryDate.ToUniversalTime() -lt (Get-Date).ToUniversalTime() }
  $profileNameRaw = $user.mikrotik_profile_name
  if ($null -eq $profileNameRaw) { $profileNameRaw = '' }
  $profileName = $profileNameRaw.ToString().ToLower()

  if ($isExpired) { return 'expired' }
  if ($total -le 0) { return 'habis' }
  if ($total -gt 0 -and $remaining -le 0) { return 'habis' }
  if ($profileName.Contains('fup')) { return 'fup' }
  return 'ok'
}

function Show-ExpectedRedirect($status, $context) {
  $base = if ($context -eq 'captive') { '/captive' } else { '/login' }
  $map = @{
    ok       = ''
    blocked  = if ($context -eq 'captive') { 'blokir' } else { 'blocked' }
    inactive = 'inactive'
    expired  = 'expired'
    habis    = 'habis'
    fup      = 'fup'
  }
  $slug = $map[$status]
  if (-not $slug) { return $base }
  return "$base/$slug"
}

function ConvertFrom-ErrorJson($err) {
  $message = $err.ErrorDetails.Message
  if (-not $message) { return $null }
  try {
    return $message | ConvertFrom-Json
  }
  catch {
    return $null
  }
}

function Test-RedirectWithCookie($baseUrl, $cookieValue, $label) {
  $paths = @(
    '/dashboard',
    '/beli',
    '/payment/finish',
    '/login/expired',
    '/login/habis',
    '/login/fup'
  )
  Write-Host "--- Redirect check ($label) ---"
  foreach ($path in $paths) {
    $headers = curl.exe -s -o NUL -D - -H "Cookie: $cookieValue" "$baseUrl$path"
    $statusLine = ($headers | Select-String -Pattern '^HTTP/').Line
    $location = ($headers | Select-String -Pattern '^Location:' -CaseSensitive:$false | Select-Object -First 1).Line
    if (-not $location) { $location = '' }
    Write-Host "Page $path => $statusLine $location"
  }
}

function Test-SignedStatusPage($baseUrl, $status, $sig) {
  if (-not $status -or -not $sig) { return }
  $path = if ($status -eq 'blocked') { '/login/blocked' } elseif ($status -eq 'inactive') { '/login/inactive' } else { "/login/$status" }
  $url = "$baseUrl$path?status=$status&sig=$sig"
  $headers = curl.exe -s -o NUL -D - $url
  $statusLine = ($headers | Select-String -Pattern '^HTTP/').Line
  $location = ($headers | Select-String -Pattern '^Location:' -CaseSensitive:$false | Select-Object -First 1).Line
  if (-not $location) { $location = '' }
  Write-Host "Signed page $path => $statusLine $location"
}

function Test-StatusPages($baseUrl, [bool]$failOnNotFound = $true) {
  $paths = @(
    '/login/blocked',
    '/login/inactive',
    '/login/expired',
    '/login/habis',
    '/login/fup',
    '/captive/blokir',
    '/captive/inactive',
    '/captive/expired',
    '/captive/habis',
    '/captive/fup'
  )
  foreach ($path in $paths) {
    $headers = curl.exe -s -o NUL -D - "$baseUrl$path"
    $statusLine = ($headers | Select-String -Pattern '^HTTP/').Line
    $location = ($headers | Select-String -Pattern '^Location:' -CaseSensitive:$false | Select-Object -First 1).Line
    if (-not $location) { $location = '' }
    Write-Host "Page $path => $statusLine $location"
    if ($failOnNotFound -and $statusLine -match '\s404\s') {
      throw "Status page tidak ditemukan: $path"
    }
  }
}
