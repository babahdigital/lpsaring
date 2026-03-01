#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Deploy lpsaring minimal package to Raspberry Pi and restart production stack.

Usage:
  ./deploy_pi.sh --host <PI_HOST> [options]

Required:
  --host <PI_HOST>              Raspberry Pi host/IP

Optional:
  --user <PI_USER>              SSH user (default: pi)
  --port <SSH_PORT>             SSH port (default: 1983)
  --key <SSH_KEY_PATH>          SSH private key (default: ~/.ssh/id_raspi_ed25519)
  --remote-dir <REMOTE_DIR>     Remote deploy dir (default: /opt/lpsaring)
  --local-dir <LOCAL_DIR>       Local project dir (default: current directory)
  --ssl-fullchain <FILE>        Local fullchain.pem path to upload (optional)
  --ssl-privkey <FILE>          Local privkey.pem path to upload (optional)
  --skip-pull                   Skip docker compose pull
  --skip-health                 Skip health check (curl /api/ping)
  --clean                       Backup remote state, copy bundle to local tmp/, then run docker compose down -v --remove-orphans
  --prune                       Run safe docker prune on remote (containers/images/networks/build cache; keeps volumes)
  --strict-minimal              Keep remote dir strictly minimal: only infrastructure/, docker-compose.prod.yml, .env.prod, .env.public.prod, backend/backups (no .deploy_backups)
  --sync-phones                 After deploy, run phone normalization report (dry-run) inside backend container
  --sync-phones-apply           After deploy, APPLY phone normalization to DB (aborts on duplicates)
  --allow-placeholders          Allow deploy even if .env.prod still contains CHANGE_ME_* values
  --wait-ci                     Wait for GitHub Actions/Checks to be green for current commit before deploying
  --wait-ci-timeout <SECONDS>   Max seconds to wait for CI (default: 1800)
  --wait-ci-interval <SECONDS>  Poll interval seconds for CI status (default: 15)
  --wait-ci-ref <REF>           Git ref/sha to check (default: HEAD)
  --github-owner <OWNER>        Override GitHub owner (auto-detected from origin)
  --github-repo <REPO>          Override GitHub repo (auto-detected from origin)
  --dry-run                     Show actions without changing remote
  -h, --help                    Show this help

Examples:
  ./deploy_pi.sh --host 192.168.1.20

  ./deploy_pi.sh --host 10.10.83.10 --user ubuntu --port 1983 \
    --key ~/.ssh/id_raspi_ed25519 --remote-dir /opt/lpsaring

  ./deploy_pi.sh --host 192.168.1.20 \
    --ssl-fullchain ~/certs/fullchain.pem \
    --ssl-privkey ~/certs/privkey.pem
EOF
}

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

PI_USER="pi"
PI_HOST=""
PI_PORT="1983"
SSH_KEY="~/.ssh/id_raspi_ed25519"
REMOTE_DIR="/opt/lpsaring"
REMOTE_DIR_WAS_EXPLICIT="false"
LOCAL_DIR="$PWD"
SSL_FULLCHAIN=""
SSL_PRIVKEY=""
SKIP_PULL="false"
SKIP_HEALTH="false"
DO_CLEAN="false"
DO_PRUNE="false"
ALLOW_PLACEHOLDERS="false"
DRY_RUN="false"
SYNC_PHONES="false"
SYNC_PHONES_APPLY="false"
STRICT_MINIMAL="false"

WAIT_CI="false"
WAIT_CI_TIMEOUT="1800"
WAIT_CI_INTERVAL="15"
WAIT_CI_REF="HEAD"
GITHUB_OWNER=""
GITHUB_REPO=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --host) PI_HOST="${2:-}"; shift 2 ;;
    --user) PI_USER="${2:-}"; shift 2 ;;
    --port) PI_PORT="${2:-}"; shift 2 ;;
    --key) SSH_KEY="${2:-}"; shift 2 ;;
    --remote-dir) REMOTE_DIR="${2:-}"; REMOTE_DIR_WAS_EXPLICIT="true"; shift 2 ;;
    --local-dir) LOCAL_DIR="${2:-}"; shift 2 ;;
    --ssl-fullchain) SSL_FULLCHAIN="${2:-}"; shift 2 ;;
    --ssl-privkey) SSL_PRIVKEY="${2:-}"; shift 2 ;;
    --skip-pull) SKIP_PULL="true"; shift ;;
    --skip-health) SKIP_HEALTH="true"; shift ;;
    --clean) DO_CLEAN="true"; shift ;;
    --prune) DO_PRUNE="true"; shift ;;
    --strict-minimal) STRICT_MINIMAL="true"; shift ;;
    --sync-phones) SYNC_PHONES="true"; shift ;;
    --sync-phones-apply) SYNC_PHONES_APPLY="true"; shift ;;
    --allow-placeholders) ALLOW_PLACEHOLDERS="true"; shift ;;
    --wait-ci) WAIT_CI="true"; shift ;;
    --wait-ci-timeout) WAIT_CI_TIMEOUT="${2:-}"; shift 2 ;;
    --wait-ci-interval) WAIT_CI_INTERVAL="${2:-}"; shift 2 ;;
    --wait-ci-ref) WAIT_CI_REF="${2:-}"; shift 2 ;;
    --github-owner) GITHUB_OWNER="${2:-}"; shift 2 ;;
    --github-repo) GITHUB_REPO="${2:-}"; shift 2 ;;
    --dry-run) DRY_RUN="true"; shift ;;
    -h|--help) usage; exit 0 ;;
    *)
      echo "ERROR: unknown argument: $1" >&2
      usage
      exit 1
      ;;
  esac
done

# If apply is requested, sync must run.
if [[ "$SYNC_PHONES_APPLY" == "true" ]]; then
  SYNC_PHONES="true"
fi

if [[ -z "$PI_HOST" ]]; then
  echo "ERROR: --host is required" >&2
  usage
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
  "infrastructure/nginx/conf.d/app.prod.conf"
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

SSH_TARGET="$PI_USER@$PI_HOST"
SSH_OPTS=(-p "$PI_PORT" -i "$SSH_KEY_EXPANDED" -o StrictHostKeyChecking=accept-new)
SCP_OPTS=(-P "$PI_PORT" -i "$SSH_KEY_EXPANDED" -o StrictHostKeyChecking=accept-new)

if [[ "$REMOTE_DIR_WAS_EXPLICIT" == "false" ]]; then
  # Auto-detect remote directory (legacy installs differ).
  # Prefer /home/<user>/sobigidul if present, else fall back to /opt/lpsaring.
  detected_remote_dir=$(ssh "${SSH_OPTS[@]}" "$SSH_TARGET" 'set -e; for d in "$HOME/sobigidul" "/opt/lpsaring" "$HOME/lpsaring"; do if [ -d "$d" ]; then echo "$d"; exit 0; fi; done; echo "/opt/lpsaring"')
  REMOTE_DIR="$detected_remote_dir"
fi

echo "==> Target        : $SSH_TARGET:$REMOTE_DIR"
echo "==> Local dir     : $LOCAL_DIR"
echo "==> SSH key       : $SSH_KEY_EXPANDED"
echo "==> SSH port      : $PI_PORT"
echo "==> Rsync         : $HAS_RSYNC"
echo "==> Dry run       : $DRY_RUN"
echo "==> Sync phones   : $SYNC_PHONES (apply=$SYNC_PHONES_APPLY)"
echo "==> Prune remote  : $DO_PRUNE (keeps volumes)"

if [[ "$DO_CLEAN" == "true" ]]; then
  echo "==> Clean mode    : enabled (auto backup before clean + copy to local tmp/)"
fi

timestamp=$(date +%Y%m%d_%H%M%S)
remote_prepare_cmd=$(cat <<EOF
set -e
mkdir -p "$REMOTE_DIR/infrastructure/nginx/conf.d"
mkdir -p "$REMOTE_DIR/infrastructure/nginx/ssl"
mkdir -p "$REMOTE_DIR/infrastructure/nginx/logs"
mkdir -p "$REMOTE_DIR/backend/backups"

if [ "$STRICT_MINIMAL" = "true" ]; then
  # Hapus semua kecuali: infrastructure/, docker-compose.prod.yml, .env.prod, .env.public.prod, backend/
  # Lalu bersihkan backend/ kecuali backups/
  find "$REMOTE_DIR" -mindepth 1 -maxdepth 1 \
    \( ! -name infrastructure ! -name backend ! -name docker-compose.prod.yml ! -name .env.prod ! -name .env.public.prod \) \
    -exec rm -rf {} +

  mkdir -p "$REMOTE_DIR/backend/backups"
  find "$REMOTE_DIR/backend" -mindepth 1 -maxdepth 1 \( ! -name backups \) -exec rm -rf {} +
else
  # Default: buat backup ringan agar gampang rollback.
  mkdir -p "$REMOTE_DIR/.deploy_backups/$timestamp"
  for f in docker-compose.prod.yml .env.prod infrastructure/nginx/conf.d/app.prod.conf; do
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
  ssh "${SSH_OPTS[@]}" "$SSH_TARGET" "$remote_prepare_cmd"
fi

if [[ "$HAS_RSYNC" == "true" ]]; then
  rsync_cmd=(rsync -avz --progress -e "ssh -p $PI_PORT -i $SSH_KEY_EXPANDED -o StrictHostKeyChecking=accept-new")
  if [[ "$DRY_RUN" == "true" ]]; then
    rsync_cmd+=(--dry-run)
  fi

  "${rsync_cmd[@]}" \
    "$LOCAL_DIR/docker-compose.prod.yml" \
    "$LOCAL_DIR/.env.prod" \
    "$LOCAL_DIR/infrastructure/nginx/conf.d/app.prod.conf" \
    "$SSH_TARGET:$REMOTE_DIR/"

  if [[ -f "$LOCAL_DIR/.env.public.prod" ]]; then
    "${rsync_cmd[@]}" \
      "$LOCAL_DIR/.env.public.prod" \
      "$SSH_TARGET:$REMOTE_DIR/"
  fi
else
  if [[ "$DRY_RUN" == "true" ]]; then
    echo "[DRY-RUN] scp compose+env+nginx conf"
  else
    scp "${SCP_OPTS[@]}" "$LOCAL_DIR/docker-compose.prod.yml" "$SSH_TARGET:$REMOTE_DIR/"
    scp "${SCP_OPTS[@]}" "$LOCAL_DIR/.env.prod" "$SSH_TARGET:$REMOTE_DIR/"
    if [[ -f "$LOCAL_DIR/.env.public.prod" ]]; then
      scp "${SCP_OPTS[@]}" "$LOCAL_DIR/.env.public.prod" "$SSH_TARGET:$REMOTE_DIR/"
    fi
    scp "${SCP_OPTS[@]}" "$LOCAL_DIR/infrastructure/nginx/conf.d/app.prod.conf" "$SSH_TARGET:$REMOTE_DIR/infrastructure/nginx/conf.d/"
  fi
fi

if [[ -n "$SSL_FULLCHAIN" ]]; then
  if [[ "$DRY_RUN" == "true" ]]; then
    echo "[DRY-RUN] upload SSL fullchain -> $REMOTE_DIR/infrastructure/nginx/ssl/fullchain.pem"
  else
    scp "${SCP_OPTS[@]}" "$SSL_FULLCHAIN" "$SSH_TARGET:$REMOTE_DIR/infrastructure/nginx/ssl/fullchain.pem"
  fi
fi

if [[ -n "$SSL_PRIVKEY" ]]; then
  if [[ "$DRY_RUN" == "true" ]]; then
    echo "[DRY-RUN] upload SSL privkey -> $REMOTE_DIR/infrastructure/nginx/ssl/privkey.pem"
  else
    scp "${SCP_OPTS[@]}" "$SSL_PRIVKEY" "$SSH_TARGET:$REMOTE_DIR/infrastructure/nginx/ssl/privkey.pem"
  fi
fi

if [[ "$DO_CLEAN" == "true" ]]; then
  CLEAN_BACKUP_NAME="clean_predeploy_${timestamp}"
  REMOTE_CLEAN_BACKUP_DIR="$REMOTE_DIR/_safe_backups/$CLEAN_BACKUP_NAME"
  REMOTE_CLEAN_BUNDLE="/tmp/${CLEAN_BACKUP_NAME}.tar.gz"
  LOCAL_CLEAN_TMP_DIR="$LOCAL_DIR/tmp"
  LOCAL_CLEAN_BUNDLE="$LOCAL_CLEAN_TMP_DIR/${PI_HOST}_${CLEAN_BACKUP_NAME}.tar.gz"

  remote_preclean_backup_cmd=$(cat <<EOF
set -e
cd "$REMOTE_DIR"
mkdir -p "$REMOTE_CLEAN_BACKUP_DIR"

echo "==> Pre-clean backup: ensure db is running"
docker compose --env-file .env.prod -f docker-compose.prod.yml up -d db >/dev/null 2>&1 || true

echo "==> Pre-clean backup: dump postgres"
docker compose --env-file .env.prod -f docker-compose.prod.yml exec -T db sh -lc 'pg_dump -U "\$POSTGRES_USER" "\$POSTGRES_DB"' > "$REMOTE_CLEAN_BACKUP_DIR/postgres_dump.sql"

echo "==> Pre-clean backup: snapshot critical deploy files"
for f in docker-compose.prod.yml .env.prod .env.public.prod infrastructure/nginx/conf.d/app.prod.conf; do
  if [ -f "$REMOTE_DIR/\$f" ]; then
    dst_dir="$REMOTE_CLEAN_BACKUP_DIR/\$(dirname "\$f")"
    mkdir -p "\$dst_dir"
    cp -a "$REMOTE_DIR/\$f" "$dst_dir/"
  fi
done

echo "created_at_utc=\$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$REMOTE_CLEAN_BACKUP_DIR/backup_meta.txt"
echo "host=$PI_HOST" >> "$REMOTE_CLEAN_BACKUP_DIR/backup_meta.txt"
echo "remote_dir=$REMOTE_DIR" >> "$REMOTE_CLEAN_BACKUP_DIR/backup_meta.txt"
echo "mode=clean_predeploy" >> "$REMOTE_CLEAN_BACKUP_DIR/backup_meta.txt"

tar -C "$REMOTE_DIR/_safe_backups" -czf "$REMOTE_CLEAN_BUNDLE" "$CLEAN_BACKUP_NAME"
echo "$REMOTE_CLEAN_BUNDLE"
EOF
)

  if [[ "$DRY_RUN" == "true" ]]; then
    echo "[DRY-RUN] ssh ${SSH_OPTS[*]} $SSH_TARGET '<pre-clean backup + bundle>'"
    echo "[DRY-RUN] mkdir -p $LOCAL_CLEAN_TMP_DIR"
    echo "[DRY-RUN] scp ${SCP_OPTS[*]} $SSH_TARGET:$REMOTE_CLEAN_BUNDLE $LOCAL_CLEAN_BUNDLE"
  else
    mkdir -p "$LOCAL_CLEAN_TMP_DIR"
    ssh "${SSH_OPTS[@]}" "$SSH_TARGET" "$remote_preclean_backup_cmd"
    scp "${SCP_OPTS[@]}" "$SSH_TARGET:$REMOTE_CLEAN_BUNDLE" "$LOCAL_CLEAN_BUNDLE"
    ssh "${SSH_OPTS[@]}" "$SSH_TARGET" "rm -f '$REMOTE_CLEAN_BUNDLE'"
    echo "==> Pre-clean backup copied to local: $LOCAL_CLEAN_BUNDLE"
  fi
fi

remote_deploy_cmd=$(cat <<EOF
set -e
cd "$REMOTE_DIR"
if [ "$DO_CLEAN" = "true" ]; then
  docker compose --env-file .env.prod -f docker-compose.prod.yml down -v --remove-orphans || true
fi
if [ "$DO_PRUNE" = "true" ]; then
  echo "==> Prune: removing unused Docker resources (keeping volumes)"
  docker container prune -f || true
  docker image prune -af || true
  docker network prune -f || true
  docker builder prune -af || true
fi
if [ "$SKIP_PULL" = "false" ]; then
  docker compose --env-file .env.prod -f docker-compose.prod.yml pull
fi
echo "==> Ensure db/redis running for migration..."
docker compose --env-file .env.prod -f docker-compose.prod.yml up -d db redis

echo "==> Run explicit migration (idempotent)..."
docker compose --env-file .env.prod -f docker-compose.prod.yml run --rm migrate

echo "==> Start updated stack..."
docker compose --env-file .env.prod -f docker-compose.prod.yml up -d --remove-orphans
docker compose --env-file .env.prod -f docker-compose.prod.yml ps
if ! docker compose --env-file .env.prod -f docker-compose.prod.yml ps --services --status running | grep -qx frontend; then
  echo "ERROR: frontend container is not running after deploy" >&2
  exit 1
fi

echo "==> Menunggu frontend siap melayani request..."
frontend_ready=0
for i in \$(seq 1 60); do
  if docker compose --env-file .env.prod -f docker-compose.prod.yml exec -T nginx sh -lc "wget -q -O /dev/null http://frontend:3010/login" >/dev/null 2>&1; then
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
  ssh "${SSH_OPTS[@]}" "$SSH_TARGET" "$remote_deploy_cmd"
fi

if [[ "$SKIP_HEALTH" == "false" ]]; then
  remote_health_cmd=$(cat <<EOF
set -e
cd "$REMOTE_DIR"
# nginx tidak wajib expose port 80 ke host (produksi bisa full via cloudflared).
# Jadi health check dilakukan dari dalam container nginx.
docker compose --env-file .env.prod -f docker-compose.prod.yml exec -T nginx wget -qO- http://127.0.0.1/api/ping

# Validasi jalur frontend dan static assets _nuxt melalui ingress nginx
docker compose --env-file .env.prod -f docker-compose.prod.yml exec -T nginx sh -lc '
set -e
wget -q -O /tmp/login.html http://127.0.0.1/login
asset_path=\$(tr "\"" "\n" < /tmp/login.html | grep "^/_nuxt/" | grep -v "^/_nuxt/\$" | head -n 1 || true)
if [ -z "\$asset_path" ]; then
  echo "ERROR: tidak menemukan referensi _nuxt asset dari /login" >&2
  exit 1
fi
wget -q -O /dev/null "http://127.0.0.1\$asset_path"
'
EOF
)

  if [[ "$DRY_RUN" == "true" ]]; then
    echo "[DRY-RUN] ssh ${SSH_OPTS[*]} $SSH_TARGET 'health check /api/ping + /login + sample _nuxt asset'"
  else
    ssh "${SSH_OPTS[@]}" "$SSH_TARGET" "$remote_health_cmd"
    echo "==> Health check OK: /api/ping + /login + _nuxt asset"
  fi
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
    ssh "${SSH_OPTS[@]}" "$SSH_TARGET" "$remote_sync_phones_cmd"
  fi
fi

echo "==> Deploy selesai"
