Param(
  [switch]$SkipFrontend,
  [switch]$SkipBackend
)

$ErrorActionPreference = "Stop"

[string]$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
[string]$LpsaringRoot = Split-Path -Parent $ScriptDir
[string]$RepoRoot = Split-Path -Parent $LpsaringRoot

$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
  throw "Python venv tidak ditemukan: $Python (buat venv di repo root terlebih dulu)"
}

function Invoke-Checked([string]$Title, [ScriptBlock]$Block) {
  Write-Host "[STEP] $Title" -ForegroundColor Cyan
  & $Block
  if ($LASTEXITCODE -ne 0) {
    throw "$Title gagal (exit=$LASTEXITCODE)"
  }
}

if (-not $SkipBackend) {
  $BackendDir = Join-Path $LpsaringRoot "backend"
  if (-not (Test-Path $BackendDir)) {
    throw "Folder backend tidak ditemukan: $BackendDir"
  }

  Push-Location $BackendDir
  try {
    Invoke-Checked "Backend lint (ruff)" { & $Python -m ruff check . }

    Invoke-Checked "Backend tests (pytest focused)" {
      & $Python -m pytest -q `
        tests/test_hotspot_sync_debt_limit.py `
        tests/test_access_policy_block_rules.py `
        tests/test_policy_invariants_matrix.py `
        tests/test_admin_routes.py `
        tests/test_transactions_lifecycle.py
    }
  } finally {
    Pop-Location
  }
}

Push-Location $LpsaringRoot
try {
  Invoke-Checked "API quality gate (OpenAPI + generated contracts)" {
    & $Python scripts/api_quality_gate.py
  }
} finally {
  Pop-Location
}

if (-not $SkipFrontend) {
  $FrontendDir = Join-Path $LpsaringRoot "frontend"
  if (-not (Test-Path $FrontendDir)) {
    throw "Folder frontend tidak ditemukan: $FrontendDir"
  }

  Push-Location $FrontendDir
  try {
    Invoke-Checked "Frontend lint" { pnpm -s lint }
    Invoke-Checked "Frontend typecheck" { pnpm -s typecheck }
  } finally {
    Pop-Location
  }
}

Write-Host "[OK] Focused checks passed." -ForegroundColor Green
