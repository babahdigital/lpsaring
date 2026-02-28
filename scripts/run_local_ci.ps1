Param(
  # Jalankan checks dengan compose E2E standalone supaya tidak mengganggu stack dev.
  [string]$ComposeFile = "docker-compose.e2e.yml",
  [string]$ComposeProjectName = "hotspot-portal-e2e",
  [string]$AppEnv = "local",

  # Kalau build image sudah dilakukan sebelumnya, pakai -SkipBuild agar lebih cepat.
  [switch]$SkipBuild,

  # Opsional: jalankan unit tests backend (bisa butuh konfigurasi DB).
  [switch]$RunBackendTests
)

$ErrorActionPreference = "Stop"

[string]$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
[string]$ProjectRoot = Split-Path -Parent $ScriptDir

function Resolve-ComposePath([string]$InputPath) {
  if (-not $InputPath) { return $null }

  $candidates = @()
  if ([System.IO.Path]::IsPathRooted($InputPath)) {
    $candidates += $InputPath
  } else {
    $candidates += (Join-Path $ProjectRoot $InputPath)
    $candidates += (Join-Path (Split-Path -Parent $ProjectRoot) $InputPath)
    $candidates += (Join-Path (Get-Location).Path $InputPath)
  }

  foreach ($candidate in $candidates) {
    if (Test-Path $candidate) {
      return (Resolve-Path $candidate).Path
    }
  }

  return $null
}

[string]$ComposePath = Resolve-ComposePath $ComposeFile

if (-not (Test-Path $ComposePath)) {
  throw "Compose file tidak ditemukan: $ComposeFile"
}

# Compose E2E pakai APP_ENV untuk memilih env_file.
$env:APP_ENV = $AppEnv

function Invoke-Compose([string[]]$ComposeArgs) {
  # Jangan pakai nama parameter $Args karena bentrok dengan variabel otomatis PowerShell $args.
  $cmd = @("compose", "-f", $ComposePath, "-p", $ComposeProjectName, "--project-directory", $ProjectRoot) + $ComposeArgs
  & docker @cmd
  if ($LASTEXITCODE -ne 0) {
    throw "docker compose gagal (exit=$LASTEXITCODE): docker $($cmd -join ' ')"
  }
}

function Invoke-FrontendHost([string[]]$PnpmArgs) {
  $frontendDir = Join-Path $ProjectRoot "frontend"
  if (-not (Test-Path $frontendDir)) {
    throw "Folder frontend tidak ditemukan: $frontendDir"
  }
  Push-Location $frontendDir
  try {
    & pnpm @PnpmArgs
    if ($LASTEXITCODE -ne 0) {
      throw "pnpm gagal (exit=$LASTEXITCODE): pnpm $($PnpmArgs -join ' ')"
    }
  } finally {
    Pop-Location
  }
}

Write-Host "[INFO] Compose: $ComposePath"
Write-Host "[INFO] Project: $ComposeProjectName"
Write-Host "[INFO] APP_ENV: $AppEnv"

if (-not $SkipBuild) {
  Write-Host "[STEP] Build images (backend, frontend)" -ForegroundColor Cyan
  Invoke-Compose @("build", "backend", "frontend")
}

Write-Host "[STEP] Backend lint (ruff)" -ForegroundColor Cyan
Invoke-Compose @("run", "--rm", "backend", "ruff", "check", ".")

if ($RunBackendTests) {
  Write-Host "[STEP] Backend tests (pytest)" -ForegroundColor Cyan
  Invoke-Compose @("run", "--rm", "backend", "pytest", "-q")
}

Write-Host "[STEP] Frontend lint (eslint)" -ForegroundColor Cyan
try {
  Invoke-Compose @("run", "--rm", "frontend", "pnpm", "run", "lint")
} catch {
  Write-Host "[WARN] Frontend lint via docker compose gagal. Fallback ke pnpm host..." -ForegroundColor Yellow
  Write-Host "[WARN] $($_.Exception.Message)" -ForegroundColor Yellow
  Invoke-FrontendHost @("run", "lint")
}

Write-Host "[STEP] Frontend typecheck (nuxt typecheck)" -ForegroundColor Cyan
try {
  Invoke-Compose @("run", "--rm", "frontend", "pnpm", "run", "typecheck")
} catch {
  Write-Host "[WARN] Frontend typecheck via docker compose gagal. Fallback ke pnpm host..." -ForegroundColor Yellow
  Write-Host "[WARN] $($_.Exception.Message)" -ForegroundColor Yellow
  Invoke-FrontendHost @("run", "typecheck")
}

Write-Host "[OK] Local CI checks passed." -ForegroundColor Green
