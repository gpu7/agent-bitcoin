#!/usr/bin/env bash
# configure-autoloop-regtest.sh
#
# Phase 2: configure Lightning Labs Loop Autoloop for a receive-heavy node
# on regtest. Default is DRY-RUN. Does not enable Autoloop unless
# --apply --enable.
#
# Usage (on AWS):
#   LOOP_CLI='docker exec -i loopclient loop' ./configure-autoloop-regtest.sh
#   LOOP_CLI='docker exec -i loopclient loop' ./configure-autoloop-regtest.sh --apply
#   LOOP_CLI='docker exec -i loopclient loop' ./configure-autoloop-regtest.sh --apply --enable
#   LOOP_CLI='docker exec -i loopclient loop' ./configure-autoloop-regtest.sh --status
#
# Env:
#   LOOP_CLI, NETWORK (default regtest)
#   AUTOLOOP_LOCAL_BALANCE_SAT   Easy Autoloop local cap (default 500000)
#   AUTOLOOP_BUDGET_SATS         fee budget (default 50000)
#   AUTOLOOP_BUDGET_REFRESH      default 86400s
#   AUTOLOOP_EASY                true|false (default true)
#   AUTOLOOP_SWEEP_CONF          default 100
#   AUTOLOOP_INFLIGHT            default 1
#   AUTOLOOP_FEE_PPM             optional fee ppm cap
#
# Notes:
# - setparams does NOT take --type; type is set via setrule (we use Easy Autoloop Out by default).
# - Parameters may not persist across loopd restart; re-run after restarts.
# - loopd must target agent-payment-decision-lnd for your real channels.
# - See docs/loop-autoloop.md

set -euo pipefail

APPLY=0
ENABLE=""
STATUS_ONLY=0

for arg in "$@"; do
  case "$arg" in
    --apply) APPLY=1 ;;
    --enable) ENABLE=true ;;
    --disable) ENABLE=false ;;
    --status) STATUS_ONLY=1 ;;
    -h|--help)
      sed -n '2,32p' "$0" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *)
      echo "Unknown option: $arg" >&2
      exit 1
      ;;
  esac
done

NETWORK=${NETWORK:-regtest}
LOOP_CLI=${LOOP_CLI:-loop}
LOCAL_BAL=${AUTOLOOP_LOCAL_BALANCE_SAT:-500000}
BUDGET=${AUTOLOOP_BUDGET_SATS:-50000}
BUDGET_REFRESH=${AUTOLOOP_BUDGET_REFRESH:-86400s}
EASY=${AUTOLOOP_EASY:-true}
SWEEP_CONF=${AUTOLOOP_SWEEP_CONF:-100}
INFLIGHT=${AUTOLOOP_INFLIGHT:-1}
FEE_PPM=${AUTOLOOP_FEE_PPM:-}

loop_cmd() {
  # shellcheck disable=SC2086
  $LOOP_CLI --network="$NETWORK" "$@"
}

echo "=== configure-autoloop-regtest ==="
echo "LOOP_CLI=$LOOP_CLI  NETWORK=$NETWORK  APPLY=$APPLY  ENABLE=${ENABLE:-<unchanged>}"
echo "easy=$EASY localbalancesat=$LOCAL_BAL budget=$BUDGET refresh=$BUDGET_REFRESH"
echo ""

if ! loop_cmd getinfo >/tmp/loop-getinfo.$$ 2>&1; then
  echo "ERROR: cannot run: $LOOP_CLI --network=$NETWORK getinfo" >&2
  cat /tmp/loop-getinfo.$$ >&2 || true
  rm -f /tmp/loop-getinfo.$$
  echo "" >&2
  echo "Hints:" >&2
  echo "  - Try: LOOP_CLI='docker exec -i loopclient loop' $0 ..." >&2
  echo "  - Ensure loopd is pointed at agent-payment-decision-lnd if that is the node you manage." >&2
  exit 1
fi
rm -f /tmp/loop-getinfo.$$
echo "OK: loop getinfo succeeded"
echo ""

if [[ "$STATUS_ONLY" -eq 1 ]]; then
  echo "--- getparams ---"
  loop_cmd getparams 2>/dev/null || true
  echo ""
  echo "--- suggestswaps ---"
  loop_cmd suggestswaps 2>&1 || echo "(suggestswaps failed or unavailable)"
  echo ""
  echo "--- listswaps ---"
  loop_cmd listswaps 2>/dev/null | head -c 4000 || true
  echo ""
  exit 0
fi

# Flags accepted by current loop setparams (no --type here; type is setrule-only)
# Easy Autoloop is Loop Out when total local balance exceeds localbalancesat.
setparams_args=(
  --autobudget="$BUDGET"
  --autobudgetrefreshperiod="$BUDGET_REFRESH"
  --autoinflight="$INFLIGHT"
  --sweepconf="$SWEEP_CONF"
)

if [[ -n "$FEE_PPM" ]]; then
  setparams_args+=(--feepercent="$FEE_PPM")
fi

if [[ "$EASY" == "true" || "$EASY" == "1" ]]; then
  setparams_args+=(--easyautoloop=true --localbalancesat="$LOCAL_BAL")
else
  setparams_args+=(--easyautoloop=false)
fi

if [[ "$ENABLE" == "true" ]]; then
  setparams_args+=(--autoloop=true)
elif [[ "$ENABLE" == "false" ]] || [[ "$APPLY" -eq 1 ]]; then
  setparams_args+=(--autoloop=false)
fi

echo "Planned command:"
echo "  $LOOP_CLI --network=$NETWORK setparams ${setparams_args[*]}"
echo ""
echo "Note: Easy Autoloop uses Loop Out only (good for receive-heavy / restoring inbound)."
echo "      Per-channel --type is set via: loop setrule ... (not setparams)."
echo ""

if [[ "$APPLY" -eq 0 ]]; then
  echo "DRY-RUN: not applying setparams. Re-run with --apply to write params."
  echo ""
  echo "--- suggestswaps (current) ---"
  loop_cmd suggestswaps 2>&1 || echo "(suggestswaps failed — apply params first)"
  echo ""
  echo "Next steps:"
  echo "  1) LOOP_CLI='docker exec -i loopclient loop' $0 --apply"
  echo "  2) LOOP_CLI='docker exec -i loopclient loop' $0 --status"
  echo "  3) LOOP_CLI='docker exec -i loopclient loop' $0 --apply --enable"
  echo "  See docs/loop-autoloop.md"
  exit 0
fi

echo "Applying setparams..."
if ! loop_cmd setparams "${setparams_args[@]}" 2>/tmp/loop-setparams-err.$$; then
  echo "setparams failed. CLI help (if available):" >&2
  cat /tmp/loop-setparams-err.$$ >&2 || true
  loop_cmd setparams -h 2>&1 | head -80 || true
  rm -f /tmp/loop-setparams-err.$$
  exit 1
fi
rm -f /tmp/loop-setparams-err.$$
echo "setparams OK"
echo ""

echo "--- getparams ---"
loop_cmd getparams 2>/dev/null || true
echo ""
echo "--- suggestswaps ---"
loop_cmd suggestswaps 2>&1 || echo "(suggestswaps failed or unavailable)"
echo ""

if [[ "$ENABLE" == "true" ]]; then
  echo "Autoloop is ENABLED (Easy Out when local total > $LOCAL_BAL sats)."
  echo "Monitor: loop listswaps / ./check-aws-health.sh"
elif [[ "$ENABLE" == "false" ]]; then
  echo "Autoloop is DISABLED. Params/budget applied for observation."
else
  echo "Autoloop left DISABLED by default. Use --enable when ready."
fi

echo ""
echo "Remember: re-run after loopd restarts (params often not persisted)."
