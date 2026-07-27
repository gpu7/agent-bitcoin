#!/usr/bin/env bash
# configure-autoloop-regtest.sh
#
# Phase 2: configure Lightning Labs Loop Autoloop for a receive-heavy node
# on regtest. Default is DRY-RUN (print plan + suggestswaps). Does not enable
# Autoloop unless --apply --enable.
#
# Usage (on AWS, with Loop CLI available):
#   ./configure-autoloop-regtest.sh                 # dry-run
#   ./configure-autoloop-regtest.sh --apply          # set params, autoloop=false
#   ./configure-autoloop-regtest.sh --apply --enable # set params, autoloop=true
#   ./configure-autoloop-regtest.sh --apply --disable
#   ./configure-autoloop-regtest.sh --status
#
# Env:
#   LOOP_CLI   default: "loop"  (e.g. 'docker exec -i loopclient loop')
#   NETWORK    default: regtest
#   AUTOLOOP_LOCAL_BALANCE_SAT   Easy Autoloop local cap (default 500000)
#   AUTOLOOP_BUDGET_SATS         fee budget (default 50000)
#   AUTOLOOP_BUDGET_REFRESH      default 86400s
#   AUTOLOOP_TYPE                out|in  (default out — restore inbound)
#   AUTOLOOP_EASY                true|false (default true)
#   AUTOLOOP_SWEEP_CONF          default 100
#   AUTOLOOP_INFLIGHT            default 1
#
# Notes:
# - Autoloop parameters are NOT persisted across loopd restart; re-run after restarts.
# - loopd must target the LND node whose channels you manage (agent-payment-decision-lnd).
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
      sed -n '2,35p' "$0" | sed 's/^# \{0,1\}//'
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
TYPE=${AUTOLOOP_TYPE:-out}
EASY=${AUTOLOOP_EASY:-true}
SWEEP_CONF=${AUTOLOOP_SWEEP_CONF:-100}
INFLIGHT=${AUTOLOOP_INFLIGHT:-1}

loop_cmd() {
  # shellcheck disable=SC2086
  $LOOP_CLI --network="$NETWORK" "$@"
}

echo "=== configure-autoloop-regtest ==="
echo "LOOP_CLI=$LOOP_CLI  NETWORK=$NETWORK  APPLY=$APPLY  ENABLE=${ENABLE:-<unchanged>}"
echo "easy=$EASY type=$TYPE localbalancesat=$LOCAL_BAL budget=$BUDGET refresh=$BUDGET_REFRESH"
echo ""

if ! $LOOP_CLI --network="$NETWORK" getinfo >/tmp/loop-getinfo.$$ 2>&1; then
  echo "ERROR: cannot run: $LOOP_CLI --network=$NETWORK getinfo" >&2
  echo "---" >&2
  cat /tmp/loop-getinfo.$$ >&2 || true
  rm -f /tmp/loop-getinfo.$$
  echo "" >&2
  echo "Hints:" >&2
  echo "  - Is Loop up? (docker ps | grep loop)" >&2
  echo "  - Try: LOOP_CLI='docker exec -i loopclient loop' $0 ..." >&2
  echo "  - Ensure loopd is pointed at agent-payment-decision-lnd if that is the node you manage." >&2
  exit 1
fi
rm -f /tmp/loop-getinfo.$$
echo "OK: loop getinfo succeeded"
echo ""

if [[ "$STATUS_ONLY" -eq 1 ]]; then
  echo "--- getparams (if supported) ---"
  loop_cmd getparams 2>/dev/null || loop_cmd getinfo 2>/dev/null || true
  echo ""
  echo "--- suggestswaps ---"
  loop_cmd suggestswaps 2>/dev/null || echo "(suggestswaps failed or unavailable)"
  echo ""
  echo "--- listswaps (recent) ---"
  loop_cmd listswaps 2>/dev/null | head -c 4000 || true
  echo ""
  exit 0
fi

# Build setparams argument list (Easy Autoloop + budget; Autoloop off unless --enable)
setparams_args=(
  --type="$TYPE"
  --autobudget="$BUDGET"
  --autobudgetrefreshperiod="$BUDGET_REFRESH"
  --autoinflight="$INFLIGHT"
  --sweepconf="$SWEEP_CONF"
)

if [[ "$EASY" == "true" || "$EASY" == "1" ]]; then
  setparams_args+=(--easyautoloop=true --localbalancesat="$LOCAL_BAL")
else
  setparams_args+=(--easyautoloop=false)
fi

if [[ "$ENABLE" == "true" ]]; then
  setparams_args+=(--autoloop=true)
elif [[ "$ENABLE" == "false" ]] || [[ "$APPLY" -eq 1 && -z "$ENABLE" ]]; then
  # Default on --apply: leave automation off
  setparams_args+=(--autoloop=false)
fi

echo "Planned command:"
echo "  $LOOP_CLI --network=$NETWORK setparams ${setparams_args[*]}"
echo ""

if [[ "$APPLY" -eq 0 ]]; then
  echo "DRY-RUN: not applying setparams. Re-run with --apply to write params."
  echo ""
  echo "--- suggestswaps (current recommendations) ---"
  loop_cmd suggestswaps 2>/dev/null || echo "(suggestswaps failed — set rules/params first with --apply)"
  echo ""
  echo "Next steps:"
  echo "  1) ./configure-autoloop-regtest.sh --apply"
  echo "  2) Review: ./configure-autoloop-regtest.sh --status"
  echo "  3) Enable only when ready: ./configure-autoloop-regtest.sh --apply --enable"
  echo "  See docs/loop-autoloop.md"
  exit 0
fi

echo "Applying setparams..."
loop_cmd setparams "${setparams_args[@]}"
echo "setparams OK"
echo ""

echo "--- suggestswaps after apply ---"
loop_cmd suggestswaps 2>/dev/null || echo "(suggestswaps unavailable)"
echo ""

if [[ "$ENABLE" == "true" ]]; then
  echo "Autoloop is ENABLED (type=$TYPE). Monitor: loop listswaps / health script."
elif [[ "$ENABLE" == "false" ]]; then
  echo "Autoloop is DISABLED. Params/budget still applied for dry observation."
else
  echo "Autoloop left DISABLED by default. Use --enable when ready."
fi

echo ""
echo "Remember: re-run this after loopd restarts (params not always persisted)."
