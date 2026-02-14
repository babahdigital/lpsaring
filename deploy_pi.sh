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
  --clean                       Run docker compose down -v --remove-orphans before deploy
  --allow-placeholders          Allow deploy even if .env.prod still contains CHANGE_ME_* values
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

PI_USER="pi"
PI_HOST=""
PI_PORT="1983"
SSH_KEY="~/.ssh/id_raspi_ed25519"
REMOTE_DIR="/opt/lpsaring"
LOCAL_DIR="$PWD"
SSL_FULLCHAIN=""
SSL_PRIVKEY=""
SKIP_PULL="false"
SKIP_HEALTH="false"
DO_CLEAN="false"
ALLOW_PLACEHOLDERS="false"
DRY_RUN="false"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --host) PI_HOST="${2:-}"; shift 2 ;;
    --user) PI_USER="${2:-}"; shift 2 ;;
    --port) PI_PORT="${2:-}"; shift 2 ;;
    --key) SSH_KEY="${2:-}"; shift 2 ;;
    --remote-dir) REMOTE_DIR="${2:-}"; shift 2 ;;
    --local-dir) LOCAL_DIR="${2:-}"; shift 2 ;;
    --ssl-fullchain) SSL_FULLCHAIN="${2:-}"; shift 2 ;;
    --ssl-privkey) SSL_PRIVKEY="${2:-}"; shift 2 ;;
    --skip-pull) SKIP_PULL="true"; shift ;;
    --skip-health) SKIP_HEALTH="true"; shift ;;
    --clean) DO_CLEAN="true"; shift ;;
    --allow-placeholders) ALLOW_PLACEHOLDERS="true"; shift ;;
    --dry-run) DRY_RUN="true"; shift ;;
    -h|--help) usage; exit 0 ;;
    *)
      echo "ERROR: unknown argument: $1" >&2
      usage
      exit 1
      ;;
  esac
done

if [[ -z "$PI_HOST" ]]; then
  echo "ERROR: --host is required" >&2
  usage
  exit 1
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
  ".env.public.prod"
  "infrastructure/nginx/conf.d/app.prod.conf"
)

for rel in "${FILES[@]}"; do
  if [[ ! -f "$LOCAL_DIR/$rel" ]]; then
    echo "ERROR: required file missing: $LOCAL_DIR/$rel" >&2
    exit 1
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

echo "==> Target        : $SSH_TARGET:$REMOTE_DIR"
echo "==> Local dir     : $LOCAL_DIR"
echo "==> SSH key       : $SSH_KEY_EXPANDED"
echo "==> SSH port      : $PI_PORT"
echo "==> Rsync         : $HAS_RSYNC"
echo "==> Dry run       : $DRY_RUN"

timestamp=$(date +%Y%m%d_%H%M%S)
remote_prepare_cmd=$(cat <<EOF
set -e
mkdir -p "$REMOTE_DIR/infrastructure/nginx/conf.d"
mkdir -p "$REMOTE_DIR/infrastructure/nginx/ssl"
mkdir -p "$REMOTE_DIR/infrastructure/nginx/logs"
mkdir -p "$REMOTE_DIR/backend/backups"
mkdir -p "$REMOTE_DIR/.deploy_backups/$timestamp"
for f in docker-compose.prod.yml .env.prod .env.public.prod infrastructure/nginx/conf.d/app.prod.conf; do
  if [ -f "$REMOTE_DIR/\$f" ]; then
    cp -a "$REMOTE_DIR/\$f" "$REMOTE_DIR/.deploy_backups/$timestamp/"
  fi
done
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
    "$LOCAL_DIR/.env.public.prod" \
    "$LOCAL_DIR/infrastructure/nginx/conf.d/app.prod.conf" \
    "$SSH_TARGET:$REMOTE_DIR/"
else
  if [[ "$DRY_RUN" == "true" ]]; then
    echo "[DRY-RUN] scp compose+env+nginx conf"
  else
    scp "${SCP_OPTS[@]}" "$LOCAL_DIR/docker-compose.prod.yml" "$SSH_TARGET:$REMOTE_DIR/"
    scp "${SCP_OPTS[@]}" "$LOCAL_DIR/.env.prod" "$SSH_TARGET:$REMOTE_DIR/"
    scp "${SCP_OPTS[@]}" "$LOCAL_DIR/.env.public.prod" "$SSH_TARGET:$REMOTE_DIR/"
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

remote_deploy_cmd=$(cat <<EOF
set -e
cd "$REMOTE_DIR"
if [ "$DO_CLEAN" = "true" ]; then
  docker compose --env-file .env.prod -f docker-compose.prod.yml down -v --remove-orphans || true
fi
if [ "$SKIP_PULL" = "false" ]; then
  docker compose --env-file .env.prod -f docker-compose.prod.yml pull
fi
docker compose --env-file .env.prod -f docker-compose.prod.yml up -d
docker compose -f docker-compose.prod.yml ps
if ! docker compose -f docker-compose.prod.yml ps --services --status running | grep -qx frontend; then
  echo "ERROR: frontend container is not running after deploy" >&2
  exit 1
fi
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
curl -fsS http://localhost/api/ping
EOF
)

  if [[ "$DRY_RUN" == "true" ]]; then
    echo "[DRY-RUN] ssh ${SSH_OPTS[*]} $SSH_TARGET 'curl http://localhost/api/ping'"
  else
    ssh "${SSH_OPTS[@]}" "$SSH_TARGET" "$remote_health_cmd"
    echo "==> Health check OK: /api/ping"
  fi
fi

echo "==> Deploy selesai"
