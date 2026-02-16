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
[string]$ComposePath = Join-Path $ProjectRoot $ComposeFile

if (-not (Test-Path $ComposePath)) {
  throw "Compose file tidak ditemukan: $ComposePath"
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
Invoke-Compose @("run", "--rm", "frontend", "pnpm", "run", "lint")

Write-Host "[STEP] Frontend typecheck (nuxt typecheck)" -ForegroundColor Cyan
Invoke-Compose @("run", "--rm", "frontend", "pnpm", "run", "typecheck")

Write-Host "[OK] Local CI checks passed." -ForegroundColor Green
