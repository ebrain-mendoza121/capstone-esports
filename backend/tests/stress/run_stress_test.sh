#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# run_stress_test.sh — headless Locust stress test for the Esports API
#
# Usage:
#   ./tests/stress/run_stress_test.sh [HOST] [USERS] [SPAWN_RATE] [RUN_TIME]
#
# Defaults:
#   HOST       = http://localhost:8000
#   USERS      = 50
#   SPAWN_RATE = 5
#   RUN_TIME   = 60s
# ---------------------------------------------------------------------------

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

HOST="${1:-http://localhost:8000}"
USERS="${2:-50}"
SPAWN_RATE="${3:-5}"
RUN_TIME="${4:-60s}"

HTML_REPORT="$SCRIPT_DIR/stress_results.html"
CSV_PREFIX="$SCRIPT_DIR/stress_results"

echo "============================================================"
echo "  Esports Analytics Platform — Stress Test"
echo "  Host       : $HOST"
echo "  Users      : $USERS"
echo "  Spawn rate : $SPAWN_RATE users/s"
echo "  Run time   : $RUN_TIME"
echo "  HTML report: $HTML_REPORT"
echo "  CSV prefix : ${CSV_PREFIX}_*.csv"
echo "============================================================"
echo ""

# Verify the API is reachable before starting
echo "→ Checking API health…"
if ! curl -sf "${HOST}/health" > /dev/null 2>&1; then
    echo "ERROR: Cannot reach ${HOST}/health — is the backend running?"
    exit 1
fi
echo "  API is up."
echo ""

# Locate the locust binary (prefer venv)
LOCUST_BIN=""
for candidate in \
    "$BACKEND_DIR/.venv/bin/locust" \
    "$(command -v locust 2>/dev/null || true)"
do
    if [[ -x "$candidate" ]]; then
        LOCUST_BIN="$candidate"
        break
    fi
done

if [[ -z "$LOCUST_BIN" ]]; then
    echo "ERROR: locust not found. Install it:"
    echo "  pip install locust"
    exit 1
fi

echo "→ Using locust: $LOCUST_BIN"
echo "→ Running test…"
echo ""

"$LOCUST_BIN" \
    --locustfile "$SCRIPT_DIR/locustfile.py" \
    --host "$HOST" \
    --headless \
    --users "$USERS" \
    --spawn-rate "$SPAWN_RATE" \
    --run-time "$RUN_TIME" \
    --html "$HTML_REPORT" \
    --csv "$CSV_PREFIX" \
    --csv-full-history \
    2>&1

echo ""
echo "============================================================"
echo "  SUMMARY"
echo "============================================================"

STATS_CSV="${CSV_PREFIX}_stats.csv"

if [[ ! -f "$STATS_CSV" ]]; then
    echo "  WARNING: stats CSV not found at $STATS_CSV"
    exit 0
fi

# Print header + per-endpoint stats using awk
awk -F',' '
NR == 1 {
    for (i = 1; i <= NF; i++) {
        gsub(/"/, "", $i)
        col[$i] = i
    }
    printf "  %-45s %8s %8s %8s %8s\n", "Endpoint", "Median", "p95", "RPS", "Fail%"
    printf "  %-45s %8s %8s %8s %8s\n", \
        "─────────────────────────────────────────────", \
        "────────", "────────", "───────", "───────"
    next
}
{
    name   = $col["Name"];      gsub(/"/, "", name)
    med    = $col["50%"];       gsub(/"/, "", med)
    p95    = $col["95%"];       gsub(/"/, "", p95)
    rps    = $col["Requests/s"]; gsub(/"/, "", rps)
    fails  = $col["Failure Count"]; gsub(/"/, "", fails)
    total  = $col["Request Count"]; gsub(/"/, "", total)

    fail_pct = (total+0 > 0) ? (fails+0) / (total+0) * 100 : 0

    # Highlight rows that breach the 2 000 ms p95 target
    flag = (p95+0 > 2000) ? " ⚠" : ""

    printf "  %-45s %7sms %7sms %7s/s %7.1f%%%s\n", \
        name, med, p95, rps, fail_pct, flag
}
' "$STATS_CSV"

echo ""
echo "  Target: p95 < 2 000 ms, failure rate < 1%"
echo "  ⚠  = endpoint exceeded p95 target"
echo ""
echo "  Full HTML report : $HTML_REPORT"
echo "  Raw CSV          : ${CSV_PREFIX}_stats.csv"
echo "============================================================"
