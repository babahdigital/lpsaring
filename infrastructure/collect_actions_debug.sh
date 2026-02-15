#!/usr/bin/env bash
set -euo pipefail

# Kumpulkan artefak debug GitHub Actions ke satu folder.
# Usage:
#   infrastructure/collect_actions_debug.sh [owner/repo] [output_dir] [max_runs]
# Example:
#   infrastructure/collect_actions_debug.sh babahdigital/lpsaring tmp/actions-debug 5

REPO="${1:-babahdigital/lpsaring}"
OUTPUT_DIR="${2:-tmp/actions-debug}"
MAX_RUNS="${3:-5}"

mkdir -p "$OUTPUT_DIR"

echo "[1/4] Fetching runs list for $REPO ..."
gh api "repos/$REPO/actions/runs?per_page=50" > "$OUTPUT_DIR/actions_runs_latest.json"
gh api --paginate "repos/$REPO/actions/runs" > "$OUTPUT_DIR/runs_all.json"
cp "$OUTPUT_DIR/actions_runs_latest.json" "$OUTPUT_DIR/actions_runs.json"

echo "[2/4] Extracting latest run IDs ..."
RUN_IDS=$(python - <<'PY' "$OUTPUT_DIR/actions_runs_latest.json" "$MAX_RUNS"
import json, sys
path = sys.argv[1]
max_runs = int(sys.argv[2])
with open(path, 'r', encoding='utf-8') as f:
    data = json.load(f)
runs = data.get('workflow_runs', [])[:max_runs]
print("\n".join(str(r.get('id')) for r in runs if r.get('id')))
PY
)

echo "[3/4] Fetching run details + jobs ..."
while IFS= read -r run_id; do
  [[ -z "$run_id" ]] && continue
  gh api "repos/$REPO/actions/runs/$run_id" > "$OUTPUT_DIR/run_${run_id}.json"
  gh api "repos/$REPO/actions/runs/$run_id/jobs" > "$OUTPUT_DIR/run_${run_id}_jobs.json"
done <<< "$RUN_IDS"

echo "[4/4] Fetching failed job logs (best effort) ..."
while IFS= read -r run_id; do
  [[ -z "$run_id" ]] && continue
  python - <<'PY' "$OUTPUT_DIR" "$run_id" "$REPO"
import json, sys, pathlib, subprocess
out_dir = pathlib.Path(sys.argv[1])
run_id = sys.argv[2]
repo = sys.argv[3]
jobs_file = out_dir / f"run_{run_id}_jobs.json"
if not jobs_file.exists():
    raise SystemExit(0)
with jobs_file.open('r', encoding='utf-8') as f:
    jobs = json.load(f).get('jobs', [])
for job in jobs:
    jid = job.get('id')
    conclusion = job.get('conclusion')
    if not jid or conclusion not in {'failure', 'cancelled'}:
        continue
    txt_target = out_dir / f"job_{jid}_logs.txt"
    zip_target = out_dir / f"job_{jid}_logs.zip"
    for ext_target, accept in ((txt_target, 'application/vnd.github.v3.raw'), (zip_target, 'application/zip')):
        cmd = [
            'gh', 'api',
            f"repos/{repo}/actions/jobs/{jid}/logs",
            '-H', f"Accept: {accept}",
        ]
        with ext_target.open('wb') as out:
            proc = subprocess.run(cmd, stdout=out, stderr=subprocess.PIPE)
        if proc.returncode != 0:
            ext_target.write_text(proc.stderr.decode('utf-8', errors='replace'), encoding='utf-8')
PY
done <<< "$RUN_IDS"

echo "Done. Artifacts saved in: $OUTPUT_DIR"
