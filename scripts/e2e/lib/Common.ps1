function ConvertTo-BooleanValue([object]$Value, [bool]$Default) {
  if ($null -eq $Value) { return $Default }
  if ($Value -is [bool]) { return [bool]$Value }
  $s = ("$Value").Trim().ToLowerInvariant()
  if ($s -in @('1', 'true', 't', 'yes', 'y', 'on')) { return $true }
  if ($s -in @('0', 'false', 'f', 'no', 'n', 'off')) { return $false }
  return $Default
}

function ConvertTo-E164PhoneNumber([string]$Phone) {
  if (-not $Phone) { return $Phone }
  $raw = ("$Phone").Trim()
  if (-not $raw) { return $raw }

  if ($raw.StartsWith('+')) {
    $digits = ($raw -replace '[^0-9]', '')
    return ('+' + $digits)
  }

  $digits = ($raw -replace '[^0-9]', '')
  if (-not $digits) { return $raw }

  if ($digits.StartsWith('00') -and $digits.Length -gt 2) {
    return ('+' + $digits.Substring(2))
  }

  if ($digits.StartsWith('0')) {
    return ('+62' + $digits.Substring(1))
  }
  if ($digits.StartsWith('8')) {
    return ('+62' + $digits)
  }
  if ($digits.StartsWith('62')) {
    return ('+' + $digits)
  }

  return ('+' + $digits)
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
  }
  catch {
    return $null
  }
}

function Invoke-Compose([string[]]$ComposeArgs) {
  $cmd = @('compose', '-f', $script:ComposeFile)
  if ($script:UseIsolatedCompose) {
    $cmd += @('-p', $script:ComposeProjectName)
  }
  $cmd += @('--project-directory', $script:ProjectRoot) + $ComposeArgs
  & docker @cmd
  if ($LASTEXITCODE -ne 0) {
    throw "docker compose gagal (exit=$LASTEXITCODE): docker $($cmd -join ' ')"
  }
}
