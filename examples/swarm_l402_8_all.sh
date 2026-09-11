#!/usr/bin/env bash
# Start a1…a8 as background jobs on one bus dir. Wait for all.
# Pass through flags, e.g. --offline-bus --no-llm
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DIR="${NOSTR_POC_DIR:-$ROOT/.nostr-poc}"
LOGDIR="$DIR/logs"
mkdir -p "$LOGDIR"
WRAP="$ROOT/examples/swarm_l402_8.sh"
if [[ ! -x "$WRAP" ]]; then
  echo "missing $WRAP" >&2
  exit 1
fi
pids=""
for i in 1 2 3 4 5 6 7 8; do
  "$WRAP" --role "a$i" "$@" >"$LOGDIR/a$i.log" 2>&1 &
  pid=$!
  pids="$pids $pid"
  echo "[all] started a$i pid=$pid log=$LOGDIR/a$i.log"
done
fail=0
idx=1
for pid in $pids; do
  if ! wait "$pid"; then
    echo "[all] a$idx exited non-zero" >&2
    fail=1
  fi
  idx=$((idx + 1))
done
echo "[all] done fail=$fail  tail: tail -f $LOGDIR/a*.log"
exit "$fail"
