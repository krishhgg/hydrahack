#!/usr/bin/env bash
# Runs the locust test headless and prints a markdown summary (p50/p95/rps/failures).
#   LOAD_HOST=https://app.example.com load/run.sh [users] [spawn-rate] [duration]
set -euo pipefail
cd "$(dirname "$0")/.."
: "${LOAD_HOST:?set LOAD_HOST to the app URL}"
users="${1:-50}"; rate="${2:-10}"; duration="${3:-60s}"
out="${LOAD_OUT:-load/results}"
mkdir -p "$out"
uv run --with locust locust -f load/locustfile.py --headless -u "$users" -r "$rate" -t "$duration" \
  --host "$LOAD_HOST" --csv "$out/run" --only-summary --exit-code-on-error 0 >/dev/null 2>"$out/locust.log" || { tail -20 "$out/locust.log"; exit 1; }
python3 - "$out/run_stats.csv" "$users" "$duration" <<'EOF'
import csv, sys
rows = list(csv.DictReader(open(sys.argv[1])))
print(f"users={sys.argv[2]} duration={sys.argv[3]}")
print("| endpoint | requests | failures | rps | p50 ms | p95 ms | p99 ms |")
print("|---|---|---|---|---|---|---|")
for r in rows:
    name = "TOTAL" if r["Name"] == "Aggregated" else r["Name"]
    print(f"| {name} | {r['Request Count']} | {r['Failure Count']} | {float(r['Requests/s']):.1f} | "
          f"{r['50%']} | {r['95%']} | {r['99%']} |")
EOF
