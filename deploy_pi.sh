#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Deploy lpsaring minimal package to Raspberry Pi and restart production stack.

Usage:
  ./deploy_pi.sh [options]

Target wajib (dikunci):
  ssh -i ~/.ssh/id_raspi_ed25519 -p 1983 abdullah@159.89.192.31
  Remote path: /home/abdullah/lpsaring/app

Optional:
  --host <PI_HOST>              Harus 159.89.192.31 (opsional, divalidasi)
  --user <PI_USER>              Harus abdullah (opsional, divalidasi)
  --port <SSH_PORT>             SSH port (default: 1983)
  --key <SSH_KEY_PATH>          SSH private key (default: ~/.ssh/id_raspi_ed25519)
  --remote-dir <REMOTE_DIR>     Harus /home/abdullah/lpsaring/app (opsional, divalidasi)
  --sync-nginx-conf             Upload nginx/conf.d/lpsaring.conf ke server nginx stack lalu reload/restart nginx
  --nginx-conf-local <FILE>     Local nginx conf path (default: ../nginx/conf.d/lpsaring.conf dari --local-dir)
  --nginx-remote-dir <DIR>      Remote nginx stack dir (default: /home/abdullah/nginx)
  --local-dir <LOCAL_DIR>       Local project dir (default: current directory)
  --ssl-fullchain <FILE>        Deprecated (ignored; nginx dikelola terpisah)
  --ssl-privkey <FILE>          Deprecated (ignored; nginx dikelola terpisah)
  --skip-pull                   Skip docker compose pull (tidak kompatibel dengan --recreate)
  --recreate                    Force recreate container app tanpa hapus volume (wajib pull image terbaru)
  --recreated                   Alias untuk --recreate
  --recretaed                   Alias typo untuk --recreate
  --backup-only                 Hanya jalankan backup DB ke ../backups lalu selesai (tanpa deploy)
  --skip-health                 Skip health check (curl /api/ping)
  --clean                       Backup database 2-lapis (_safe_backups + ../backups), lalu jalankan docker compose down -v --remove-orphans
  --clean-reset-data            Mode clean tanpa auto-restore data setelah deploy sukses
  --confirm-clean-data-loss     Required with --clean (acknowledge volume/data loss risk)
  --prune                       Dinonaktifkan (ditolak) demi keamanan: host-wide prune bisa menyentuh service lain
  --strict-minimal              Backup database 2-lapis (_safe_backups + ../backups), lalu bersihkan app dir (pertahankan docker-compose.prod.yml, .env.prod, .env.public.prod, dan _safe_backups)
  --sync-phones                 After deploy, run phone normalization report (dry-run) inside backend container
  --sync-phones-apply           After deploy, APPLY phone normalization to DB (aborts on duplicates)
  --no-auto-stamp-alembic-drift Disable auto-stamp for known Alembic drift on 20260302 public-update revisions
  --allow-placeholders          Allow deploy even if .env.prod still contains CHANGE_ME_* values
  --allow-small-backup          Izinkan lanjut clean/strict meski ukuran backup DB kecil (override safety guard)
  --min-backup-bytes <BYTES>    Ambang minimum ukuran backup DB (default: 102400 bytes)
  --wait-ci                     Wait for GitHub Actions/Checks to be green for current commit before deploying
  --wait-ci-timeout <SECONDS>   Max seconds to wait for CI (default: 1800)
  --wait-ci-interval <SECONDS>  Poll interval seconds for CI status (default: 15)
  --wait-ci-ref <REF>           Git ref/sha to check (default: HEAD)
  --github-owner <OWNER>        Override GitHub owner (auto-detected from origin)
  --github-repo <REPO>          Override GitHub repo (auto-detected from origin)
  (auto) backup retention       Simpan 14 backup terbaru (remote _safe_backups + local ../backups)
  --dry-run                     Show actions without changing remote
  --detach-local                Jalankan script ini sebagai background job lokal (nohup) agar tidak putus saat terminal VS Code ter-close/interupt
  -h, --help                    Show this help

Examples:
  ./deploy_pi.sh

  # ekuivalen eksplisit (tetap target yang sama):
  ./deploy_pi.sh --host 159.89.192.31 --user abdullah --port 1983 \
    --key ~/.ssh/id_raspi_ed25519 --remote-dir /home/abdullah/lpsaring/app

  # Jika nginx/conf.d/lpsaring.conf berubah, sinkronkan sekalian:
  ./deploy_pi.sh --host 159.89.192.31 --user abdullah --port 1983 \
    --key ~/.ssh/id_raspi_ed25519 --remote-dir /home/abdullah/lpsaring/app \
    --sync-nginx-conf
EOF
}

ORIGINAL_ARGS=("$@")

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "ERROR: command '$1' not found" >&2
    exit 1
  }
}

has_cmd() {
  command -v "$1" >/dev/null 2>&1
}

pick_python() {
  if has_cmd python; then
    echo python
    return 0
  fi
  if has_cmd python3; then
    echo python3
    return 0
  fi
  return 1
}

detect_github_owner_repo_from_origin() {
  # Supports:
  # - git@github.com:OWNER/REPO.git
  # - https://github.com/OWNER/REPO.git
  # - https://github.com/OWNER/REPO
  local origin_url="$1"
  local cleaned
  cleaned="$origin_url"
  cleaned="${cleaned%.git}"
  cleaned="${cleaned#git@github.com:}"
  cleaned="${cleaned#https://github.com/}"
  cleaned="${cleaned#http://github.com/}"

  if [[ "$cleaned" != */* ]]; then
    return 1
  fi

  echo "$cleaned"
}

github_api_get() {
  # Args: <url>
  # Uses GH_TOKEN or GITHUB_TOKEN
  local url="$1"
  local token="${GH_TOKEN:-${GITHUB_TOKEN:-}}"

  if [[ -z "$token" ]]; then
    echo "ERROR: --wait-ci membutuhkan GH_TOKEN atau GITHUB_TOKEN di environment" >&2
    return 2
  fi

  curl -sS \
    -H "Authorization: Bearer $token" \
    -H "Accept: application/vnd.github+json" \
    "$url"
}

compute_ci_state() {
  # Returns: success | pending | failure | unknown
  # Uses GitHub checks API first (check-runs), falls back to combined status.
  local owner="$1"
  local repo="$2"
  local sha="$3"

  local py
  py=$(pick_python 2>/dev/null || true)

  local checks_url="https://api.github.com/repos/$owner/$repo/commits/$sha/check-runs"
  local status_url="https://api.github.com/repos/$owner/$repo/commits/$sha/status"

  local checks_json
  checks_json=$(github_api_get "$checks_url")
  rc=$?
  if [[ $rc -eq 2 ]]; then
    return 2
  fi
  if [[ $rc -ne 0 ]]; then
    checks_json=""
  fi

  if [[ -n "$checks_json" && -n "$py" ]]; then
    "$py" - <<'PY' "$checks_json" || echo unknown
import json, sys

raw = sys.argv[1]
try:
    data = json.loads(raw)
except Exception:
    print('unknown')
    raise SystemExit(0)

check_runs = data.get('check_runs')
if not isinstance(check_runs, list) or len(check_runs) == 0:
    print('unknown')
    raise SystemExit(0)

any_pending = False
any_failure = False

for cr in check_runs:
    if not isinstance(cr, dict):
        continue
    status = (cr.get('status') or '').lower()
    conclusion = (cr.get('conclusion') or '').lower()

    if status in ('queued', 'in_progress', 'pending'):
        any_pending = True
        continue

    if conclusion in ('failure', 'cancelled', 'timed_out', 'action_required', 'stale'):
        any_failure = True
    elif conclusion in ('success', 'neutral', 'skipped'):
        pass
    elif conclusion == '':
        any_pending = True
    else:
        any_pending = True

if any_failure:
    print('failure')
elif any_pending:
    print('pending')
else:
    print('success')
PY
    return 0
  fi

  local status_json
  status_json=$(github_api_get "$status_url")
  rc=$?
  if [[ $rc -eq 2 ]]; then
    return 2
  fi
  if [[ $rc -ne 0 ]]; then
    status_json=""
  fi
  if [[ -n "$status_json" && -n "$py" ]]; then
    "$py" - <<'PY' "$status_json" || echo unknown
import json, sys

raw = sys.argv[1]
try:
    data = json.loads(raw)
except Exception:
    print('unknown')
    raise SystemExit(0)

state = (data.get('state') or '').lower()
if state in ('success', 'pending', 'failure', 'error'):
    print('failure' if state in ('failure', 'error') else state)
else:
    print('unknown')
PY
    return 0
  fi

  echo unknown
}

wait_for_ci_green() {
  local owner="$1"
  local repo="$2"
  local sha="$3"
  local timeout_s="$4"
  local interval_s="$5"

  echo "==> CI Guard      : waiting for GitHub checks to be green ($owner/$repo@$sha)"
  echo "==> CI Timeout    : ${timeout_s}s (poll=${interval_s}s)"

  local start
  start=$(date +%s)

  while true; do
    local state
    state=$(compute_ci_state "$owner" "$repo" "$sha")
    rc=$?
    if [[ $rc -eq 2 ]]; then
      # Missing token or auth failure message already printed.
      return 2
    fi
    if [[ $rc -ne 0 ]]; then
      state="unknown"
    fi

    case "$state" in
      success)
        echo "==> CI Status     : success"
        return 0
        ;;
      failure)
        echo "ERROR: CI status is failure for $owner/$repo@$sha. Abort deploy." >&2
        return 1
        ;;
      pending)
        echo "==> CI Status     : pending"
        ;;
      *)
        echo "WARN: tidak bisa menentukan status CI (unknown). Akan coba lagi..." >&2
        ;;
    esac

    local now elapsed
    now=$(date +%s)
    elapsed=$((now - start))
    if (( elapsed >= timeout_s )); then
      echo "ERROR: timeout menunggu CI hijau (${timeout_s}s). Abort deploy." >&2
      return 1
    fi

    sleep "$interval_s"
  done
}

LOCKED_PI_USER="abdullah"
LOCKED_PI_HOST="159.89.192.31"
LOCKED_PI_PORT="1983"
LOCKED_REMOTE_DIR="/home/abdullah/lpsaring/app"

PI_USER="$LOCKED_PI_USER"
PI_HOST="$LOCKED_PI_HOST"
PI_PORT="1983"
SSH_KEY="~/.ssh/id_raspi_ed25519"
REMOTE_DIR="$LOCKED_REMOTE_DIR"
REMOTE_DIR_WAS_EXPLICIT="true"
LOCAL_DIR="$PWD"
SSL_FULLCHAIN=""
SSL_PRIVKEY=""
SKIP_PULL="false"
FORCE_RECREATE="false"
BACKUP_ONLY="false"
SKIP_HEALTH="false"
DO_CLEAN="false"
CLEAN_RESET_DATA="false"
CONFIRM_CLEAN_DATA_LOSS="false"
DO_PRUNE="false"
ALLOW_PLACEHOLDERS="false"
ALLOW_SMALL_BACKUP="false"
DRY_RUN="false"
DETACH_LOCAL="false"
SYNC_PHONES="false"
SYNC_PHONES_APPLY="false"
STRICT_MINIMAL="false"
AUTO_STAMP_ALEMBIC_DRIFT="true"
SYNC_NGINX_CONF="false"
NGINX_REMOTE_DIR="/home/abdullah/nginx"
NGINX_CONF_LOCAL=""
ROLLBACK_ARMED="false"
LOCAL_DESTRUCTIVE_DUMP=""
REMOTE_ROLLBACK_DUMP=""

WAIT_CI="false"
WAIT_CI_TIMEOUT="1800"
WAIT_CI_INTERVAL="15"
WAIT_CI_REF="HEAD"
GITHUB_OWNER=""
GITHUB_REPO=""
BACKUP_RETENTION_COUNT="14"
MIN_BACKUP_BYTES="102400"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --host) PI_HOST="${2:-}"; shift 2 ;;
    --user) PI_USER="${2:-}"; shift 2 ;;
    --port) PI_PORT="${2:-}"; shift 2 ;;
    --key) SSH_KEY="${2:-}"; shift 2 ;;
    --remote-dir) REMOTE_DIR="${2:-}"; REMOTE_DIR_WAS_EXPLICIT="true"; shift 2 ;;
    --sync-nginx-conf) SYNC_NGINX_CONF="true"; shift ;;
    --nginx-conf-local) NGINX_CONF_LOCAL="${2:-}"; shift 2 ;;
    --nginx-remote-dir) NGINX_REMOTE_DIR="${2:-}"; shift 2 ;;
    --local-dir) LOCAL_DIR="${2:-}"; shift 2 ;;
    --ssl-fullchain) SSL_FULLCHAIN="${2:-}"; shift 2 ;;
    --ssl-privkey) SSL_PRIVKEY="${2:-}"; shift 2 ;;
    --skip-pull) SKIP_PULL="true"; shift ;;
    --recreate|--recreated|--recretaed) FORCE_RECREATE="true"; shift ;;
    --backup-only) BACKUP_ONLY="true"; shift ;;
    --skip-health) SKIP_HEALTH="true"; shift ;;
    --clean) DO_CLEAN="true"; shift ;;
    --clean-reset-data) CLEAN_RESET_DATA="true"; shift ;;
    --confirm-clean-data-loss) CONFIRM_CLEAN_DATA_LOSS="true"; shift ;;
    --prune) DO_PRUNE="true"; shift ;;
    --strict-minimal) STRICT_MINIMAL="true"; shift ;;
    --sync-phones) SYNC_PHONES="true"; shift ;;
    --sync-phones-apply) SYNC_PHONES_APPLY="true"; shift ;;
    --no-auto-stamp-alembic-drift) AUTO_STAMP_ALEMBIC_DRIFT="false"; shift ;;
    --allow-placeholders) ALLOW_PLACEHOLDERS="true"; shift ;;
    --allow-small-backup) ALLOW_SMALL_BACKUP="true"; shift ;;
    --min-backup-bytes) MIN_BACKUP_BYTES="${2:-}"; shift 2 ;;
    --wait-ci) WAIT_CI="true"; shift ;;
    --wait-ci-timeout) WAIT_CI_TIMEOUT="${2:-}"; shift 2 ;;
    --wait-ci-interval) WAIT_CI_INTERVAL="${2:-}"; shift 2 ;;
    --wait-ci-ref) WAIT_CI_REF="${2:-}"; shift 2 ;;
    --github-owner) GITHUB_OWNER="${2:-}"; shift 2 ;;
    --github-repo) GITHUB_REPO="${2:-}"; shift 2 ;;
    --dry-run) DRY_RUN="true"; shift ;;
    --detach-local) DETACH_LOCAL="true"; shift ;;
    -h|--help) usage; exit 0 ;;
    *)
      echo "ERROR: unknown argument: $1" >&2
      usage
      exit 1
      ;;
  esac
done

if [[ "$DETACH_LOCAL" == "true" ]] && [[ "${DEPLOY_DETACHED_RUN:-0}" != "1" ]]; then
  DETACHED_ARGS=()
  for arg in "${ORIGINAL_ARGS[@]}"; do
    if [[ "$arg" != "--detach-local" ]]; then
      DETACHED_ARGS+=("$arg")
    fi
  done

  DETACHED_LOG_DIR="$LOCAL_DIR/../tmp"
  mkdir -p "$DETACHED_LOG_DIR"
  DETACHED_TS=$(date +%Y%m%d_%H%M%S)
  DETACHED_LOG="$DETACHED_LOG_DIR/deploy_detached_${DETACHED_TS}.log"

  nohup env DEPLOY_DETACHED_RUN=1 bash "$0" "${DETACHED_ARGS[@]}" >"$DETACHED_LOG" 2>&1 &
  DETACHED_PID=$!

  echo "==> Detached run dimulai"
  echo "==> PID          : $DETACHED_PID"
  echo "==> Log file     : $DETACHED_LOG"
  echo "==> Pantau log   : tail -f $DETACHED_LOG"
  exit 0
fi

# If apply is requested, sync must run.
if [[ "$SYNC_PHONES_APPLY" == "true" ]]; then
  SYNC_PHONES="true"
fi

if [[ "$FORCE_RECREATE" == "true" && "$SKIP_PULL" == "true" ]]; then
  echo "ERROR: --recreate tidak boleh dipakai bersama --skip-pull karena berisiko menjalankan image lama." >&2
  echo "       Hapus --skip-pull agar deploy recreate selalu memakai image terbaru." >&2
  exit 1
fi

if [[ "$PI_HOST" != "$LOCKED_PI_HOST" ]]; then
  echo "ERROR: host wajib $LOCKED_PI_HOST (nilai saat ini: $PI_HOST)" >&2
  exit 1
fi

if [[ "$PI_USER" != "$LOCKED_PI_USER" ]]; then
  echo "ERROR: user wajib $LOCKED_PI_USER (nilai saat ini: $PI_USER)" >&2
  exit 1
fi

if [[ "$PI_PORT" != "$LOCKED_PI_PORT" ]]; then
  echo "ERROR: port wajib $LOCKED_PI_PORT (nilai saat ini: $PI_PORT)" >&2
  exit 1
fi

if [[ "$REMOTE_DIR" != "$LOCKED_REMOTE_DIR" ]]; then
  echo "ERROR: remote-dir wajib $LOCKED_REMOTE_DIR (nilai saat ini: $REMOTE_DIR)" >&2
  exit 1
fi

if [[ "$DO_CLEAN" == "true" ]] && [[ "$CONFIRM_CLEAN_DATA_LOSS" != "true" ]]; then
  echo "ERROR: --clean memerlukan --confirm-clean-data-loss karena akan menjalankan 'docker compose down -v' (hapus volumes/data)." >&2
  exit 1
fi

if [[ "$WAIT_CI" == "true" ]]; then
  require_cmd curl
  require_cmd git

  py_bin=$(pick_python 2>/dev/null || true)
  if [[ -z "$py_bin" ]]; then
    echo "ERROR: python tidak ditemukan. Install python atau pastikan 'python' ada di PATH untuk --wait-ci" >&2
    exit 1
  fi

  # Resolve repo owner/name
  if [[ -z "$GITHUB_OWNER" || -z "$GITHUB_REPO" ]]; then
    origin_url=$(git -C "$LOCAL_DIR" remote get-url origin 2>/dev/null || true)
    if [[ -n "$origin_url" ]]; then
      owner_repo=$(detect_github_owner_repo_from_origin "$origin_url" 2>/dev/null || true)
      if [[ -n "$owner_repo" ]]; then
        if [[ -z "$GITHUB_OWNER" ]]; then
          GITHUB_OWNER="${owner_repo%%/*}"
        fi
        if [[ -z "$GITHUB_REPO" ]]; then
          GITHUB_REPO="${owner_repo##*/}"
        fi
      fi
    fi
  fi

  if [[ -z "$GITHUB_OWNER" || -z "$GITHUB_REPO" ]]; then
    echo "ERROR: tidak bisa auto-detect GitHub owner/repo. Isi dengan --github-owner dan --github-repo" >&2
    exit 1
  fi

  ci_sha=$(git -C "$LOCAL_DIR" rev-parse "$WAIT_CI_REF" 2>/dev/null || true)
  if [[ -z "$ci_sha" ]]; then
    echo "ERROR: tidak bisa resolve --wait-ci-ref '$WAIT_CI_REF'" >&2
    exit 1
  fi

  wait_for_ci_green "$GITHUB_OWNER" "$GITHUB_REPO" "$ci_sha" "$WAIT_CI_TIMEOUT" "$WAIT_CI_INTERVAL"
fi

require_cmd ssh
require_cmd scp

if command -v rsync >/dev/null 2>&1; then
  HAS_RSYNC="true"
else
  HAS_RSYNC="false"
fi

SSH_KEY_EXPANDED="${SSH_KEY/#\~/$HOME}"
if [[ ! -f "$SSH_KEY_EXPANDED" ]]; then
  echo "ERROR: SSH key not found: $SSH_KEY_EXPANDED" >&2
  exit 1
fi

FILES=(
  "docker-compose.prod.yml"
  ".env.prod"
)

OPTIONAL_FILES=(
  ".env.public.prod"
)

for rel in "${FILES[@]}"; do
  if [[ ! -f "$LOCAL_DIR/$rel" ]]; then
    echo "ERROR: required file missing: $LOCAL_DIR/$rel" >&2
    exit 1
  fi
done

for rel in "${OPTIONAL_FILES[@]}"; do
  if [[ ! -f "$LOCAL_DIR/$rel" ]]; then
    echo "WARN: optional file missing (will not overwrite remote): $LOCAL_DIR/$rel" >&2
  fi
done

if [[ "$ALLOW_PLACEHOLDERS" == "false" ]] && grep -q 'CHANGE_ME_' "$LOCAL_DIR/.env.prod"; then
  echo "ERROR: .env.prod masih berisi placeholder CHANGE_ME_. Isi dulu atau jalankan dengan --allow-placeholders" >&2
  exit 1
fi

if [[ -n "$SSL_FULLCHAIN" ]] && [[ ! -f "$SSL_FULLCHAIN" ]]; then
  echo "ERROR: ssl fullchain file not found: $SSL_FULLCHAIN" >&2
  exit 1
fi
if [[ -n "$SSL_PRIVKEY" ]] && [[ ! -f "$SSL_PRIVKEY" ]]; then
  echo "ERROR: ssl privkey file not found: $SSL_PRIVKEY" >&2
  exit 1
fi

if [[ -n "$SSL_FULLCHAIN" || -n "$SSL_PRIVKEY" ]]; then
  echo "WARN: --ssl-fullchain/--ssl-privkey diabaikan karena nginx/ssl tidak lagi dikelola oleh app deploy script ini." >&2
fi

if [[ -z "$NGINX_CONF_LOCAL" ]]; then
  NGINX_CONF_LOCAL="$LOCAL_DIR/../nginx/conf.d/lpsaring.conf"
fi

if [[ "$SYNC_NGINX_CONF" == "true" ]] && [[ ! -f "$NGINX_CONF_LOCAL" ]]; then
  echo "ERROR: nginx conf lokal tidak ditemukan: $NGINX_CONF_LOCAL" >&2
  exit 1
fi

SSH_TARGET="$PI_USER@$PI_HOST"
SSH_OPTS=(
  -p "$PI_PORT"
  -i "$SSH_KEY_EXPANDED"
  -o StrictHostKeyChecking=accept-new
  -o BatchMode=yes
  -o ConnectTimeout=15
  -o ConnectionAttempts=3
  -o ServerAliveInterval=20
  -o ServerAliveCountMax=6
  -o TCPKeepAlive=yes
)
SCP_OPTS=(
  -P "$PI_PORT"
  -i "$SSH_KEY_EXPANDED"
  -o StrictHostKeyChecking=accept-new
  -o BatchMode=yes
  -o ConnectTimeout=15
  -o ConnectionAttempts=3
  -o ServerAliveInterval=20
  -o ServerAliveCountMax=6
  -o TCPKeepAlive=yes
)
MAX_SSH_RETRIES="${MAX_SSH_RETRIES:-3}"
SSH_RETRY_DELAY_SECONDS="${SSH_RETRY_DELAY_SECONDS:-5}"

run_ssh() {
  local attempt rc
  for attempt in $(seq 1 "$MAX_SSH_RETRIES"); do
    set +e
    ssh "${SSH_OPTS[@]}" "$SSH_TARGET" "$@"
    rc=$?
    set -e

    if [[ $rc -eq 0 ]]; then
      return 0
    fi

    if [[ $rc -eq 255 && $attempt -lt $MAX_SSH_RETRIES ]]; then
      echo "WARN: SSH terputus (exit 255). Retry $attempt/$MAX_SSH_RETRIES dalam ${SSH_RETRY_DELAY_SECONDS}s..." >&2
      sleep "$SSH_RETRY_DELAY_SECONDS"
      continue
    fi

    return "$rc"
  done

  return 255
}

run_scp() {
  local attempt rc
  for attempt in $(seq 1 "$MAX_SSH_RETRIES"); do
    set +e
    scp "${SCP_OPTS[@]}" "$@"
    rc=$?
    set -e

    if [[ $rc -eq 0 ]]; then
      return 0
    fi

    if [[ $rc -eq 255 && $attempt -lt $MAX_SSH_RETRIES ]]; then
      echo "WARN: SCP terputus (exit 255). Retry $attempt/$MAX_SSH_RETRIES dalam ${SSH_RETRY_DELAY_SECONDS}s..." >&2
      sleep "$SSH_RETRY_DELAY_SECONDS"
      continue
    fi

    return "$rc"
  done

  return 255
}

restore_db_from_local_backup() {
  if [[ -z "${LOCAL_DESTRUCTIVE_DUMP:-}" || ! -f "${LOCAL_DESTRUCTIVE_DUMP:-}" ]]; then
    echo "WARN: Auto-restore dilewati: file backup lokal tidak ditemukan." >&2
    return 1
  fi

  if [[ -z "${REMOTE_ROLLBACK_DUMP:-}" ]]; then
    echo "WARN: Auto-restore dilewati: path rollback remote belum disiapkan." >&2
    return 1
  fi

  echo "==> Auto-restore  : upload backup lokal ke remote untuk rollback DB"
  run_scp "$LOCAL_DESTRUCTIVE_DUMP" "$SSH_TARGET:$REMOTE_ROLLBACK_DUMP"

  local remote_restore_cmd
  remote_restore_cmd=$(cat <<EOF
set -e
cd "$REMOTE_DIR"
docker compose --env-file .env.prod -f docker-compose.prod.yml up -d db >/dev/null 2>&1 || true
docker compose --env-file .env.prod -f docker-compose.prod.yml exec -T db sh -lc 'psql -v ON_ERROR_STOP=1 -U "\$POSTGRES_USER" -d "\$POSTGRES_DB" -c "DROP SCHEMA IF EXISTS public CASCADE; CREATE SCHEMA public;"'
cat "$REMOTE_ROLLBACK_DUMP" | docker compose --env-file .env.prod -f docker-compose.prod.yml exec -T db sh -lc 'psql -v ON_ERROR_STOP=1 -U "\$POSTGRES_USER" -d "\$POSTGRES_DB"'
rm -f "$REMOTE_ROLLBACK_DUMP"
EOF
)

  run_ssh "$remote_restore_cmd"
  return 0
}

on_deploy_error() {
  local exit_code="${1:-1}"

  if [[ "${ROLLBACK_ARMED:-false}" != "true" ]]; then
    exit "$exit_code"
  fi

  ROLLBACK_ARMED="false"

  if [[ "${DRY_RUN:-false}" == "true" ]]; then
    exit "$exit_code"
  fi

  echo "WARN: Deploy gagal pada mode clean/strict. Mencoba auto-restore DB dari backup lokal..." >&2

  set +e
  restore_db_from_local_backup
  local restore_rc=$?
  set -e

  if [[ $restore_rc -eq 0 ]]; then
    echo "==> Auto-restore  : sukses (DB dipulihkan dari backup lokal)." >&2

    local remote_recover_stack_cmd
    remote_recover_stack_cmd=$(cat <<EOF
set -e
cd "$REMOTE_DIR"
docker compose --env-file .env.prod -f docker-compose.prod.yml up -d --remove-orphans || true
EOF
)

    set +e
    run_ssh "$remote_recover_stack_cmd"
    local recover_stack_rc=$?
    set -e

    if [[ $recover_stack_rc -eq 0 ]]; then
      echo "==> Auto-recover  : full stack diupayakan naik kembali setelah restore." >&2
    else
      echo "WARN: Auto-recover stack gagal. Cek status compose di server." >&2
    fi
  else
    echo "ERROR: Auto-restore gagal. Lakukan restore manual dari backup lokal: $LOCAL_DESTRUCTIVE_DUMP" >&2
  fi

  exit "$exit_code"
}

trap 'on_deploy_error $?' ERR

echo "==> Target        : $SSH_TARGET:$REMOTE_DIR"
echo "==> Quick SSH     : ssh -i $SSH_KEY_EXPANDED -p $PI_PORT $SSH_TARGET"
echo "==> Local dir     : $LOCAL_DIR"
echo "==> SSH key       : $SSH_KEY_EXPANDED"
echo "==> SSH port      : $PI_PORT"
echo "==> Rsync         : $HAS_RSYNC"
echo "==> Dry run       : $DRY_RUN"
echo "==> Skip pull     : $SKIP_PULL"
echo "==> Recreate      : $FORCE_RECREATE (tanpa hapus volume)"
echo "==> Backup only   : $BACKUP_ONLY"
echo "==> Sync phones   : $SYNC_PHONES (apply=$SYNC_PHONES_APPLY)"
echo "==> Prune remote  : $DO_PRUNE (DISABLED for app-only safety)"
echo "==> Auto-stamp drift: $AUTO_STAMP_ALEMBIC_DRIFT"
echo "==> Retention     : keep last $BACKUP_RETENTION_COUNT backups (remote+local)"
echo "==> Min backup    : ${MIN_BACKUP_BYTES} bytes (allow-small=$ALLOW_SMALL_BACKUP)"
echo "==> Nginx sync    : $SYNC_NGINX_CONF"
if [[ "$SYNC_NGINX_CONF" == "true" ]]; then
  echo "==> Nginx local   : $NGINX_CONF_LOCAL"
  echo "==> Nginx remote  : $NGINX_REMOTE_DIR/conf.d/lpsaring.conf"
fi

if [[ "$DRY_RUN" == "true" ]]; then
  remote_dry_run_preflight_cmd=$(cat <<EOF
set -e
arch=\$(uname -m)
if [ "\$arch" != "x86_64" ] && [ "\$arch" != "amd64" ]; then
  echo "ERROR: host architecture harus x86_64/amd64. Terdeteksi: \$arch" >&2
  exit 1
fi
if [ "$REMOTE_DIR" != "/home/abdullah/lpsaring/app" ]; then
  echo "ERROR: safety check gagal. Remote dir harus /home/abdullah/lpsaring/app" >&2
  exit 1
fi
if [ ! -d "$REMOTE_DIR" ]; then
  echo "ERROR: remote app dir tidak ditemukan: $REMOTE_DIR" >&2
  exit 1
fi
if [ ! -d "$REMOTE_DIR/backend" ]; then
  echo "WARN: remote backend dir belum ada: $REMOTE_DIR/backend" >&2
fi
if [ "$SYNC_NGINX_CONF" = "true" ] && [ ! -d "$NGINX_REMOTE_DIR/conf.d" ]; then
  echo "ERROR: remote nginx conf dir tidak ditemukan: $NGINX_REMOTE_DIR/conf.d" >&2
  exit 1
fi
echo "==> Dry-run preflight OK (ssh + target dir valid)"
EOF
)

  run_ssh "$remote_dry_run_preflight_cmd"
fi

if [[ "$DO_CLEAN" == "true" ]]; then
  echo "==> Clean mode    : enabled (auto DB backup before destructive step + copy ke ../backups)"
  echo "==> Clean restore : $([[ "$CLEAN_RESET_DATA" == "true" ]] && echo 'disabled (--clean-reset-data)' || echo 'enabled (default preserve data)')"
fi
if [[ "$STRICT_MINIMAL" == "true" ]]; then
  echo "==> Strict minimal: enabled (auto DB backup before destructive step + copy ke ../backups)"
fi

if [[ "$DO_PRUNE" == "true" ]]; then
  echo "ERROR: --prune dinonaktifkan. Untuk keamanan, deploy ini WAJIB app-only dan tidak boleh menjalankan host-wide prune." >&2
  exit 1
fi

if ! [[ "$MIN_BACKUP_BYTES" =~ ^[0-9]+$ ]]; then
  echo "ERROR: --min-backup-bytes harus angka bulat non-negatif (nilai saat ini: $MIN_BACKUP_BYTES)" >&2
  exit 1
fi

timestamp=$(date +%Y%m%d_%H%M%S)
REMOTE_ROLLBACK_DUMP="/tmp/auto_restore_${timestamp}.sql"

{
  DESTRUCTIVE_BACKUP_MODE="deploy"
  if [[ "$STRICT_MINIMAL" == "true" ]]; then
    DESTRUCTIVE_BACKUP_MODE="strict-minimal"
  elif [[ "$DO_CLEAN" == "true" ]]; then
    DESTRUCTIVE_BACKUP_MODE="clean"
  fi

  DESTRUCTIVE_BACKUP_NAME="${DESTRUCTIVE_BACKUP_MODE//-/_}_predeploy_${timestamp}"
  REMOTE_SAFE_BACKUP_DIR="$REMOTE_DIR/_safe_backups/$DESTRUCTIVE_BACKUP_NAME"
  REMOTE_DB_DUMP="$REMOTE_SAFE_BACKUP_DIR/postgres_dump.sql"
  LOCAL_DESTRUCTIVE_TMP_DIR="$LOCAL_DIR/../backups"
  LOCAL_DESTRUCTIVE_DUMP="$LOCAL_DESTRUCTIVE_TMP_DIR/${PI_HOST}_${DESTRUCTIVE_BACKUP_NAME}.sql"

  echo "==> Backup mode   : $DESTRUCTIVE_BACKUP_MODE"
  echo "==> Remote backup : $REMOTE_DB_DUMP"
  echo "==> Local backup  : $LOCAL_DESTRUCTIVE_DUMP"

  remote_pre_destructive_backup_cmd=$(cat <<EOF
set -e
cd "$REMOTE_DIR"
mkdir -p "$REMOTE_SAFE_BACKUP_DIR"

echo "==> Pre-destructive backup: ensure db is running"
docker compose --env-file .env.prod -f docker-compose.prod.yml up -d db >/dev/null 2>&1 || true

echo "==> Pre-destructive backup: wait db ready"
db_ready=0
for i in \$(seq 1 60); do
  if docker compose --env-file .env.prod -f docker-compose.prod.yml exec -T db sh -lc 'pg_isready -U "\$POSTGRES_USER" -d "\$POSTGRES_DB" >/dev/null 2>&1'; then
    db_ready=1
    break
  fi
  sleep 2
done

if [ "\$db_ready" -ne 1 ]; then
  echo "ERROR: database belum ready untuk backup (timeout 120 detik)." >&2
  exit 1
fi

echo "==> Pre-destructive backup: dump postgres only"
docker compose --env-file .env.prod -f docker-compose.prod.yml exec -T db sh -lc 'pg_dump -U "\$POSTGRES_USER" "\$POSTGRES_DB"' > "$REMOTE_DB_DUMP"
echo "created_at_utc=\$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$REMOTE_SAFE_BACKUP_DIR/backup_meta.txt"
echo "host=$PI_HOST" >> "$REMOTE_SAFE_BACKUP_DIR/backup_meta.txt"
echo "remote_dir=$REMOTE_DIR" >> "$REMOTE_SAFE_BACKUP_DIR/backup_meta.txt"
echo "mode=$DESTRUCTIVE_BACKUP_MODE" >> "$REMOTE_SAFE_BACKUP_DIR/backup_meta.txt"
echo "==> Pre-destructive backup: apply remote retention (keep $BACKUP_RETENTION_COUNT)"
mkdir -p "$REMOTE_DIR/_safe_backups"
ls -1dt "$REMOTE_DIR"/_safe_backups/*_predeploy_* 2>/dev/null | tail -n +$((BACKUP_RETENTION_COUNT + 1)) | xargs -r rm -rf -- || true
echo "$REMOTE_DB_DUMP"
EOF
)

  if [[ "$DRY_RUN" == "true" ]]; then
    echo "[DRY-RUN] ssh ${SSH_OPTS[*]} $SSH_TARGET '<pre-destructive DB backup dump>'"
    echo "[DRY-RUN] mkdir -p $LOCAL_DESTRUCTIVE_TMP_DIR"
    echo "[DRY-RUN] scp ${SCP_OPTS[*]} $SSH_TARGET:$REMOTE_DB_DUMP $LOCAL_DESTRUCTIVE_DUMP"
    echo "[DRY-RUN] apply local retention keep $BACKUP_RETENTION_COUNT files in $LOCAL_DESTRUCTIVE_TMP_DIR"
  else
    mkdir -p "$LOCAL_DESTRUCTIVE_TMP_DIR"
    run_ssh "$remote_pre_destructive_backup_cmd"
    run_scp "$SSH_TARGET:$REMOTE_DB_DUMP" "$LOCAL_DESTRUCTIVE_DUMP"
    find "$LOCAL_DESTRUCTIVE_TMP_DIR" -maxdepth 1 -type f -name "${PI_HOST}_*_predeploy_*.sql" -printf '%T@ %p\n' \
      | sort -nr \
      | awk 'NR>'"$BACKUP_RETENTION_COUNT"' {sub(/^[^ ]+ /,""); print}' \
      | xargs -r rm -f --

    local_backup_size_bytes=$(wc -c < "$LOCAL_DESTRUCTIVE_DUMP" | tr -d '[:space:]')
    echo "==> Backup size   : ${local_backup_size_bytes} bytes"

    if [[ "$local_backup_size_bytes" -lt "$MIN_BACKUP_BYTES" ]]; then
      echo "WARN: ukuran backup DB lebih kecil dari ambang minimum (${MIN_BACKUP_BYTES} bytes)." >&2

      if [[ ( "$DO_CLEAN" == "true" || "$STRICT_MINIMAL" == "true" ) && "$ALLOW_SMALL_BACKUP" != "true" ]]; then
        echo "ERROR: backup terlalu kecil untuk mode destruktif clean/strict. Aborting untuk keamanan data." >&2
        echo "       Jika memang sengaja, jalankan ulang dengan --allow-small-backup" >&2
        exit 1
      fi
    fi

    echo "==> Pre-destructive DB backup (remote kept): $REMOTE_DB_DUMP"
    echo "==> Pre-destructive DB backup copied to local: $LOCAL_DESTRUCTIVE_DUMP"
  fi

  if [[ "$DRY_RUN" != "true" && ( "$DO_CLEAN" == "true" || "$STRICT_MINIMAL" == "true" ) ]]; then
    ROLLBACK_ARMED="true"
    echo "==> Auto-restore  : armed (jika deploy clean/strict gagal, DB dipulihkan dari backup lokal)"
  fi
}

if [[ "$BACKUP_ONLY" == "true" ]]; then
  echo "==> Backup-only mode: selesai setelah backup DB (deploy dilewati)."
  exit 0
fi

remote_prepare_cmd=$(cat <<EOF
set -e
if [ "$REMOTE_DIR" != "/home/abdullah/lpsaring/app" ]; then
  echo "ERROR: safety check gagal. Remote dir harus /home/abdullah/lpsaring/app" >&2
  exit 1
fi
mkdir -p "$REMOTE_DIR/backend/backups"

if [ "$STRICT_MINIMAL" = "true" ]; then
  # Hapus semua kecuali: docker-compose.prod.yml, .env.prod, .env.public.prod, backend/, _safe_backups/
  # Lalu bersihkan backend/ termasuk isi backups/ (folder backups tetap dibuat ulang untuk bind mount)
  find "$REMOTE_DIR" -mindepth 1 -maxdepth 1 \
    \( ! -name backend ! -name docker-compose.prod.yml ! -name .env.prod ! -name .env.public.prod ! -name _safe_backups \) \
    -exec rm -rf {} +

  mkdir -p "$REMOTE_DIR/backend/backups"
  # Bersihkan semua isi backend termasuk isi backups, lalu pastikan folder backups ada.
  find "$REMOTE_DIR/backend" -mindepth 1 -maxdepth 1 \( ! -name backups \) -exec rm -rf {} +

  # Self-healing: jika ada file backup ber-owner root/permission ketat, coba auto-fix lalu retry.
  if ! find "$REMOTE_DIR/backend/backups" -mindepth 1 -maxdepth 1 -exec rm -rf {} + >/dev/null 2>&1; then
    echo "WARN: cleanup backend/backups gagal (permission). Mencoba auto-fix permission..." >&2
    if command -v sudo >/dev/null 2>&1 && sudo -n true >/dev/null 2>&1; then
      sudo chown -R "$PI_USER:$PI_USER" "$REMOTE_DIR/backend/backups" >/dev/null 2>&1 || true
      sudo find "$REMOTE_DIR/backend/backups" -type d -exec chmod 775 {} + >/dev/null 2>&1 || true
      sudo find "$REMOTE_DIR/backend/backups" -type f -exec chmod 664 {} + >/dev/null 2>&1 || true
    else
      chown -R "$PI_USER:$PI_USER" "$REMOTE_DIR/backend/backups" >/dev/null 2>&1 || true
      find "$REMOTE_DIR/backend/backups" -type d -exec chmod 775 {} + >/dev/null 2>&1 || true
      find "$REMOTE_DIR/backend/backups" -type f -exec chmod 664 {} + >/dev/null 2>&1 || true
    fi

    if ! find "$REMOTE_DIR/backend/backups" -mindepth 1 -maxdepth 1 -exec rm -rf {} + >/dev/null 2>&1; then
      echo "WARN: tidak semua file backend/backups bisa dihapus setelah auto-fix. Lanjut deploy." >&2
    else
      echo "==> Strict cleanup: backend/backups auto-heal permission berhasil" >&2
    fi
  fi
else
  # Default: buat backup ringan agar gampang rollback.
  mkdir -p "$REMOTE_DIR/.deploy_backups/$timestamp"
  for f in docker-compose.prod.yml .env.prod; do
    if [ -f "$REMOTE_DIR/\$f" ]; then
      cp -a "$REMOTE_DIR/\$f" "$REMOTE_DIR/.deploy_backups/$timestamp/"
    fi
  done

  if [ -f "$REMOTE_DIR/.env.public.prod" ]; then
    cp -a "$REMOTE_DIR/.env.public.prod" "$REMOTE_DIR/.deploy_backups/$timestamp/" || true
  fi
fi
EOF
)

if [[ "$DRY_RUN" == "true" ]]; then
  echo "[DRY-RUN] ssh ${SSH_OPTS[*]} $SSH_TARGET '<prepare dirs & backup>'"
else
  run_ssh "$remote_prepare_cmd"
fi

if [[ "$HAS_RSYNC" == "true" ]]; then
  rsync_cmd=(rsync -avz --progress -e "ssh -p $PI_PORT -i $SSH_KEY_EXPANDED -o StrictHostKeyChecking=accept-new -o BatchMode=yes -o ConnectTimeout=15 -o ConnectionAttempts=3 -o ServerAliveInterval=20 -o ServerAliveCountMax=6 -o TCPKeepAlive=yes")
  if [[ "$DRY_RUN" == "true" ]]; then
    rsync_cmd+=(--dry-run)
  fi

  "${rsync_cmd[@]}" \
    "$LOCAL_DIR/docker-compose.prod.yml" \
    "$LOCAL_DIR/.env.prod" \
    "$SSH_TARGET:$REMOTE_DIR/"

  if [[ -f "$LOCAL_DIR/.env.public.prod" ]]; then
    "${rsync_cmd[@]}" \
      "$LOCAL_DIR/.env.public.prod" \
      "$SSH_TARGET:$REMOTE_DIR/"
  fi
else
  if [[ "$DRY_RUN" == "true" ]]; then
    echo "[DRY-RUN] scp compose+env(.public optional) ke remote app dir"
  else
    run_scp "$LOCAL_DIR/docker-compose.prod.yml" "$SSH_TARGET:$REMOTE_DIR/"
    run_scp "$LOCAL_DIR/.env.prod" "$SSH_TARGET:$REMOTE_DIR/"
    if [[ -f "$LOCAL_DIR/.env.public.prod" ]]; then
      run_scp "$LOCAL_DIR/.env.public.prod" "$SSH_TARGET:$REMOTE_DIR/"
    fi
  fi
fi

if [[ -n "$SSL_FULLCHAIN" || -n "$SSL_PRIVKEY" ]]; then
  if [[ "$DRY_RUN" == "true" ]]; then
    echo "[DRY-RUN] legacy SSL args supplied, but ignored in split-stack mode"
  else
    echo "==> Info: legacy SSL args di-skip (nginx stack terpisah)"
  fi
fi

remote_deploy_cmd=$(cat <<EOF
set -e
cd "$REMOTE_DIR"
host_arch=\$(uname -m)
if [ "\$host_arch" != "x86_64" ] && [ "\$host_arch" != "amd64" ]; then
  echo "ERROR: host architecture harus x86_64/amd64. Terdeteksi: \$host_arch" >&2
  exit 1
fi
if [ "$REMOTE_DIR" != "/home/abdullah/lpsaring/app" ]; then
  echo "ERROR: safety check gagal. Remote dir harus /home/abdullah/lpsaring/app" >&2
  exit 1
fi
if [ "$DO_CLEAN" = "true" ]; then
  echo "==> Clean mode: backend/backups (bind mount host) tidak dihapus oleh down -v"
  docker compose --env-file .env.prod -f docker-compose.prod.yml down -v --remove-orphans || true
fi
if [ "$SKIP_PULL" = "false" ]; then
  echo "==> Pull app images (backend/frontend/celery/migrate/backups_init)..."
  docker compose --env-file .env.prod -f docker-compose.prod.yml pull backend celery_worker celery_beat migrate backups_init frontend
fi

backend_arch=\$(docker image inspect babahdigital/sobigidul_backend:latest --format '{{.Architecture}}' 2>/dev/null || true)
frontend_arch=\$(docker image inspect babahdigital/sobigidul_frontend:latest --format '{{.Architecture}}' 2>/dev/null || true)
if [ "\$backend_arch" != "amd64" ]; then
  echo "ERROR: image backend bukan amd64 (terdeteksi: \${backend_arch:-missing})." >&2
  exit 1
fi
if [ "\$frontend_arch" != "amd64" ]; then
  echo "ERROR: image frontend bukan amd64 (terdeteksi: \${frontend_arch:-missing})." >&2
  exit 1
fi

echo "==> Ensure db/redis running for migration..."
docker compose --env-file .env.prod -f docker-compose.prod.yml up -d db redis

echo "==> Preflight Alembic drift check..."
drift_out=\$(docker compose --env-file .env.prod -f docker-compose.prod.yml run --rm migrate python - <<'PY'
from sqlalchemy import text
from app import create_app
from app.extensions import db

CHAIN = [
  "20260302_add_public_db_update_submissions",
  "20260302_add_public_update_submission_whatsapp_tracking",
  "20260302_add_public_update_submission_approval_fields",
  "20260302_alter_public_update_submission_role_fields",
]

def get_current_rev(session):
  try:
    row = session.execute(text("select version_num from alembic_version")).fetchone()
    if row and row[0]:
      return str(row[0])
  except Exception:
    return None
  return None

app = create_app()
with app.app_context():
  session = db.session
  current_rev = get_current_rev(session)

  # Query alembic_version bisa gagal (mis. tabel belum ada) dan meninggalkan
  # transaksi dalam state aborted. Lakukan rollback sebelum query berikutnya.
  try:
    session.rollback()
  except Exception:
    pass

  def safe_scalar(sql_text, default=None):
    try:
      return session.execute(text(sql_text)).scalar()
    except Exception:
      try:
        session.rollback()
      except Exception:
        pass
      return default

  def safe_fetchall(sql_text):
    try:
      return session.execute(text(sql_text)).fetchall()
    except Exception:
      try:
        session.rollback()
      except Exception:
        pass
      return []

  table_exists = bool(safe_scalar("select to_regclass('public.public_database_update_submissions') is not null", False))

  cols = set()
  if table_exists:
    rows = safe_fetchall("""
      select column_name
      from information_schema.columns
      where table_schema = 'public' and table_name = 'public_database_update_submissions'
    """)
    cols = {r[0] for r in rows}

  target = None
  if table_exists:
    target = CHAIN[0]
  if "whatsapp_notify_attempts" in cols:
    target = CHAIN[1]
  if "approval_status" in cols:
    target = CHAIN[2]
  if "tamping_type" in cols:
    target = CHAIN[3]

  drift = bool(target and current_rev != target and (current_rev not in CHAIN or CHAIN.index(current_rev) < CHAIN.index(target)))

  print(f"CURRENT_REV={current_rev or 'NONE'}")
  print(f"DRIFT_TARGET={target or 'NONE'}")
  print(f"DRIFT_DETECTED={'1' if drift else '0'}")
PY
)

echo "\$drift_out"
drift_detected=\$(printf '%s\n' "\$drift_out" | awk -F= '/^DRIFT_DETECTED=/{print \$2}' | tail -n1)
drift_target=\$(printf '%s\n' "\$drift_out" | awk -F= '/^DRIFT_TARGET=/{print \$2}' | tail -n1)

if [ "\$drift_detected" = "1" ]; then
  echo "WARN: Alembic drift terdeteksi (target=\$drift_target)."
  if [ "$AUTO_STAMP_ALEMBIC_DRIFT" = "true" ] && [ -n "\$drift_target" ] && [ "\$drift_target" != "NONE" ]; then
  echo "==> Auto-stamp drift ke revision \$drift_target"
  docker compose --env-file .env.prod -f docker-compose.prod.yml run --rm migrate flask db stamp "\$drift_target"
  else
  echo "ERROR: drift Alembic terdeteksi. Jalankan stamp manual atau deploy ulang tanpa --no-auto-stamp-alembic-drift." >&2
  exit 1
  fi
fi

echo "==> Run explicit migration (idempotent)..."
docker compose --env-file .env.prod -f docker-compose.prod.yml run --rm migrate

echo "==> Start updated stack..."
if [ "$FORCE_RECREATE" = "true" ]; then
  docker compose --env-file .env.prod -f docker-compose.prod.yml up -d --force-recreate --remove-orphans
else
  docker compose --env-file .env.prod -f docker-compose.prod.yml up -d --remove-orphans
fi
docker compose --env-file .env.prod -f docker-compose.prod.yml ps
if ! docker compose --env-file .env.prod -f docker-compose.prod.yml ps --services --status running | grep -qx frontend; then
  echo "ERROR: frontend container is not running after deploy" >&2
  exit 1
fi

echo "==> Menunggu frontend siap melayani request..."
frontend_ready=0
for i in \$(seq 1 60); do
  if [ "\$(docker inspect -f '{{.State.Health.Status}}' hotspot_prod_nuxt_frontend 2>/dev/null || true)" = "healthy" ]; then
    frontend_ready=1
    break
  fi
  sleep 2
done

if [ "\$frontend_ready" -ne 1 ]; then
  echo "ERROR: frontend belum siap setelah 120 detik" >&2
  docker compose --env-file .env.prod -f docker-compose.prod.yml logs --tail=120 frontend || true
  exit 1
fi

echo "==> Frontend readiness OK"
EOF
)

if [[ "$DRY_RUN" == "true" ]]; then
  echo "[DRY-RUN] ssh ${SSH_OPTS[*]} $SSH_TARGET '<deploy compose>'"
else
  run_ssh "$remote_deploy_cmd"
fi

if [[ "$SYNC_NGINX_CONF" == "true" ]]; then
  remote_nginx_reload_cmd=$(cat <<EOF
set -e
if [ ! -d "$NGINX_REMOTE_DIR/conf.d" ]; then
  echo "ERROR: remote nginx conf dir tidak ditemukan: $NGINX_REMOTE_DIR/conf.d" >&2
  exit 1
fi

if [ -f "$NGINX_REMOTE_DIR/conf.d/lpsaring.conf" ]; then
  cp -a "$NGINX_REMOTE_DIR/conf.d/lpsaring.conf" "$NGINX_REMOTE_DIR/conf.d/lpsaring.conf.bak.$timestamp"
fi

if docker ps --format '{{.Names}}' | grep -qx global-nginx-proxy; then
  docker exec global-nginx-proxy nginx -t
  docker exec global-nginx-proxy nginx -s reload || docker restart global-nginx-proxy
else
  echo "ERROR: container global-nginx-proxy tidak ditemukan. Tidak bisa reload/restart nginx otomatis." >&2
  exit 1
fi
EOF
)

  if [[ "$DRY_RUN" == "true" ]]; then
    echo "[DRY-RUN] scp ${SCP_OPTS[*]} $NGINX_CONF_LOCAL $SSH_TARGET:$NGINX_REMOTE_DIR/conf.d/lpsaring.conf"
    echo "[DRY-RUN] ssh ${SSH_OPTS[*]} $SSH_TARGET '<backup nginx conf + test + reload/restart global-nginx-proxy>'"
  else
    run_scp "$NGINX_CONF_LOCAL" "$SSH_TARGET:$NGINX_REMOTE_DIR/conf.d/lpsaring.conf"
    run_ssh "$remote_nginx_reload_cmd"
    echo "==> Nginx conf synced and reloaded: $NGINX_REMOTE_DIR/conf.d/lpsaring.conf"
  fi
fi

if [[ "$SKIP_HEALTH" == "false" ]]; then
  remote_health_cmd=$(cat <<EOF
set -e
cd "$REMOTE_DIR"
# Healthcheck utama: via global nginx proxy (arsitektur DO split-stack).
if docker ps --format '{{.Names}}' | grep -qx global-nginx-proxy; then
  # Dengan nginx terpisah, /login tetap divalidasi via localhost di dalam container global-nginx-proxy.
  health_ok=0
  for i in \$(seq 1 10); do
    if docker exec global-nginx-proxy wget -T 15 -qO- --header='Host: lpsaring.babahdigital.net' http://127.0.0.1/api/ping >/dev/null 2>&1 \
      && docker exec global-nginx-proxy sh -lc '
        set -e
        wget -T 15 -q -O /tmp/login.html --header="Host: lpsaring.babahdigital.net" http://127.0.0.1/login
        asset_path=\$(tr "\"" "\n" < /tmp/login.html | grep "^/_nuxt/" | grep -v "^/_nuxt/\$" | head -n 1 || true)
        if [ -z "\$asset_path" ]; then
          exit 1
        fi
        wget -T 15 -q -O /dev/null --header="Host: lpsaring.babahdigital.net" "http://127.0.0.1\$asset_path"
      ' >/dev/null 2>&1; then
      health_ok=1
      break
    fi
    sleep 3
  done

  if [ "\$health_ok" -ne 1 ]; then
    echo "ERROR: health check via global-nginx-proxy gagal (timeout/retry exhausted)." >&2
    exit 1
  fi
else
  # Fallback legacy: jika masih ada service nginx di app compose.
  if docker compose --env-file .env.prod -f docker-compose.prod.yml ps --services --status running | grep -qx nginx; then
    docker compose --env-file .env.prod -f docker-compose.prod.yml exec -T nginx wget -qO- http://127.0.0.1/api/ping
  else
    echo "ERROR: global-nginx-proxy tidak ditemukan dan service nginx legacy tidak running." >&2
    exit 1
  fi
fi
EOF
)

  if [[ "$DRY_RUN" == "true" ]]; then
    echo "[DRY-RUN] ssh ${SSH_OPTS[*]} $SSH_TARGET 'health check /api/ping + /login + sample _nuxt asset'"
  else
    run_ssh "$remote_health_cmd"
    echo "==> Health check OK: /api/ping + /login + _nuxt asset"
  fi
fi

if [[ "$DO_CLEAN" == "true" && "$DRY_RUN" != "true" && "$CLEAN_RESET_DATA" != "true" ]]; then
  echo "==> Clean post-step: restore data dari backup pre-clean"

  set +e
  restore_db_from_local_backup
  clean_restore_rc=$?
  set -e

  if [[ $clean_restore_rc -ne 0 ]]; then
    echo "ERROR: restore data pasca-clean gagal. Cek backup lokal: $LOCAL_DESTRUCTIVE_DUMP" >&2
    exit 1
  fi

  remote_post_restore_cmd=$(cat <<EOF
set -e
cd "$REMOTE_DIR"
docker compose --env-file .env.prod -f docker-compose.prod.yml run --rm migrate
docker compose --env-file .env.prod -f docker-compose.prod.yml up -d --remove-orphans
EOF
)

  run_ssh "$remote_post_restore_cmd"
  echo "==> Clean post-step: data restored + migrate re-run selesai"
fi

if [[ "$SYNC_PHONES" == "true" ]]; then
  remote_sync_phones_cmd=$(cat <<EOF
set -e
cd "$REMOTE_DIR"
script="/app/scripts/normalize_phone_numbers.py"

echo "==> Phone sync: starting (apply=$SYNC_PHONES_APPLY)"
if ! docker compose --env-file .env.prod -f docker-compose.prod.yml exec -T backend test -f "\$script"; then
  echo "ERROR: phone sync script not found in backend container: \$script" >&2
  echo "       Pastikan image babahdigital/sobigidul_backend:latest sudah terbaru (docker compose pull) dan berisi script tersebut." >&2
  exit 1
fi

if [ "$SYNC_PHONES_APPLY" = "true" ]; then
  docker compose --env-file .env.prod -f docker-compose.prod.yml exec -T backend python "\$script" --apply
else
  docker compose --env-file .env.prod -f docker-compose.prod.yml exec -T backend python "\$script"
fi
echo "==> Phone sync: done"
EOF
)

  if [[ "$DRY_RUN" == "true" ]]; then
    echo "[DRY-RUN] ssh ${SSH_OPTS[*]} $SSH_TARGET '<sync phones>'"
  else
    run_ssh "$remote_sync_phones_cmd"
  fi
fi

echo "==> Deploy selesai"
