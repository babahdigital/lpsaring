#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Reset semua user ter-approve ke kuota tertentu (default 10GB) setelah restore database.

Mode default adalah PREVIEW (tidak mengubah data). Tambahkan --execute untuk benar-benar apply.

Usage:
  ./backend/scripts/reset_all_users_quota.sh [options]

Options:
  --execute                    Jalankan update (tanpa ini hanya preview)
  --quota-gb <N>               Kuota baru per user dalam GB (default: 10)
  --set-expiry-days <N>        Set ulang expiry menjadi sekarang + N hari (opsional)
  --no-sync                    Skip sinkronisasi ke Mikrotik setelah update
  --compose-file <FILE>        Compose file (default: docker-compose.prod.yml)
  --env-file <FILE>            Env file compose (default: .env.prod)
  --service <NAME>             Nama service backend (default: backend)
  -h, --help                   Tampilkan bantuan

Contoh:
  # Preview dulu
  ./backend/scripts/reset_all_users_quota.sh

  # Apply 10GB + set expiry 30 hari + sync Mikrotik
  ./backend/scripts/reset_all_users_quota.sh --execute --quota-gb 10 --set-expiry-days 30

  # Apply tanpa sync Mikrotik
  ./backend/scripts/reset_all_users_quota.sh --execute --no-sync
EOF
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "ERROR: command '$1' tidak ditemukan" >&2
    exit 1
  }
}

EXECUTE="false"
SYNC_AFTER="true"
QUOTA_GB="10"
SET_EXPIRY_DAYS=""
COMPOSE_FILE="docker-compose.prod.yml"
ENV_FILE=".env.prod"
SERVICE_NAME="backend"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --execute) EXECUTE="true"; shift ;;
    --no-sync) SYNC_AFTER="false"; shift ;;
    --quota-gb) QUOTA_GB="${2:-}"; shift 2 ;;
    --set-expiry-days) SET_EXPIRY_DAYS="${2:-}"; shift 2 ;;
    --compose-file) COMPOSE_FILE="${2:-}"; shift 2 ;;
    --env-file) ENV_FILE="${2:-}"; shift 2 ;;
    --service) SERVICE_NAME="${2:-}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *)
      echo "ERROR: argumen tidak dikenal: $1" >&2
      usage
      exit 1
      ;;
  esac
done

require_cmd docker

if ! [[ "$QUOTA_GB" =~ ^[0-9]+([.][0-9]+)?$ ]]; then
  echo "ERROR: --quota-gb harus angka positif (contoh: 10 atau 10.5)" >&2
  exit 1
fi

if [[ -n "$SET_EXPIRY_DAYS" ]] && ! [[ "$SET_EXPIRY_DAYS" =~ ^[0-9]+$ ]]; then
  echo "ERROR: --set-expiry-days harus bilangan bulat >= 0" >&2
  exit 1
fi

if [[ ! -f "$COMPOSE_FILE" ]]; then
  echo "ERROR: compose file tidak ditemukan: $COMPOSE_FILE" >&2
  exit 1
fi

if [[ ! -f "$ENV_FILE" ]]; then
  echo "ERROR: env file tidak ditemukan: $ENV_FILE" >&2
  exit 1
fi

QUOTA_MB=$(awk -v gb="$QUOTA_GB" 'BEGIN { printf "%d", gb * 1024 }')

echo "==> Compose file     : $COMPOSE_FILE"
echo "==> Env file         : $ENV_FILE"
echo "==> Service          : $SERVICE_NAME"
echo "==> Quota target     : ${QUOTA_GB}GB (${QUOTA_MB}MB)"
if [[ -n "$SET_EXPIRY_DAYS" ]]; then
  echo "==> Expiry policy    : reset ke now + ${SET_EXPIRY_DAYS} hari"
else
  echo "==> Expiry policy    : pertahankan expiry lama"
fi
echo "==> Mode             : $([[ "$EXECUTE" == "true" ]] && echo "EXECUTE" || echo "PREVIEW")"

preview_code=$(cat <<'PY'
from app import create_app
from app.extensions import db
from app.infrastructure.db.models import User, UserRole, ApprovalStatus

app = create_app()
with app.app_context():
    q = db.select(User).where(
        User.role == UserRole.USER,
        User.approval_status == ApprovalStatus.APPROVED,
    )
    users = db.session.execute(q).scalars().all()
    print(f"total_target_users={len(users)}")
    for user in users[:10]:
        print(f"sample={user.phone_number}|{user.full_name}|active={user.is_active}|quota={user.total_quota_purchased_mb}|used={float(user.total_quota_used_mb or 0):.2f}|expiry={user.quota_expiry_date}")
PY
)

docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" exec -T "$SERVICE_NAME" python - <<PY
$preview_code
PY

if [[ "$EXECUTE" != "true" ]]; then
  echo "\nPreview selesai. Tambahkan --execute untuk menerapkan perubahan."
  exit 0
fi

apply_code=$(cat <<PY
from datetime import datetime, timezone, timedelta
from app import create_app
from app.extensions import db
from app.infrastructure.db.models import User, UserRole, ApprovalStatus

quota_mb = int("$QUOTA_MB")
expiry_days_raw = "$SET_EXPIRY_DAYS".strip()
set_expiry = bool(expiry_days_raw)
expiry_days = int(expiry_days_raw) if set_expiry else None
now = datetime.now(timezone.utc)

app = create_app()
with app.app_context():
    q = db.select(User).where(
        User.role == UserRole.USER,
        User.approval_status == ApprovalStatus.APPROVED,
    )
    users = db.session.execute(q).scalars().all()

    updated = 0
    for user in users:
        user.total_quota_purchased_mb = quota_mb
        user.total_quota_used_mb = 0
        user.is_unlimited_user = False
        if set_expiry:
            user.quota_expiry_date = now + timedelta(days=expiry_days)
        user.updated_at = now
        updated += 1

    db.session.commit()
    print(f"updated_users={updated}")
PY
)

echo "\n==> Menjalankan mass update..."
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" exec -T "$SERVICE_NAME" python - <<PY
$apply_code
PY

if [[ "$SYNC_AFTER" == "true" ]]; then
  echo "\n==> Menjalankan sinkronisasi profil/kuota ke Mikrotik (flask sync-usage)..."
  docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" exec -T "$SERVICE_NAME" flask sync-usage
else
  echo "\n==> Sinkronisasi Mikrotik di-skip (--no-sync)."
fi

echo "\nSelesai."
