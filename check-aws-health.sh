#!/usr/bin/env bash
# check-aws-health.sh
#
# Lightweight health / integrity check for the AWS regtest backend host.
# Run on the AWS instance (manually or via cron). Exit 0 = healthy, 1 = problems.
#
# Usage:
#   ./check-aws-health.sh
#   ./check-aws-health.sh --json
#   AGENT_BITCOIN_API_KEY=... ./check-aws-health.sh   # also probes /balance
#
# Channel liquidity floors (Phase 1 — receive-heavy node monitoring):
#   CHANNEL_MIN_LOCAL_SATS   default 5000   (outbound / can send)
#   CHANNEL_MIN_REMOTE_SATS  default 5000   (inbound / can receive)
#   CHANNEL_LIQUIDITY_STRICT=1  treat floor breaches as FAIL instead of WARN
#   CHANNEL_MIN_ACTIVE=1        fail if zero active channels (default: warn)
#
# Does not print secrets. Does not unlock LND.

set -euo pipefail

JSON=0
[[ "${1:-}" == "--json" ]] && JSON=1

BACKEND_URL=${BACKEND_URL:-http://127.0.0.1:8000}
LND_CONTAINER=${LND_CONTAINER:-agent-payment-decision-lnd}
BITCOIND_CONTAINER=${BITCOIND_CONTAINER:-bitcoind}
DISK_WARN_PCT=${DISK_WARN_PCT:-90}
REQUIRED_CONTAINERS=${REQUIRED_CONTAINERS:-"bitcoind agent-payment-decision-lnd"}
CHANNEL_MIN_LOCAL_SATS=${CHANNEL_MIN_LOCAL_SATS:-5000}
CHANNEL_MIN_REMOTE_SATS=${CHANNEL_MIN_REMOTE_SATS:-5000}
CHANNEL_LIQUIDITY_STRICT=${CHANNEL_LIQUIDITY_STRICT:-0}
CHANNEL_MIN_ACTIVE=${CHANNEL_MIN_ACTIVE:-1}

FAIL=0
WARN=0
declare -a MESSAGES=()

note() { MESSAGES+=("$1"); }
fail() { FAIL=1; note "FAIL: $1"; }
warn() { WARN=1; note "WARN: $1"; }
ok() { note "OK: $1"; }

# --- Disk ---
if command -v df >/dev/null 2>&1; then
  USE=$(df -P / | awk 'NR==2 {gsub(/%/,"",$5); print $5}')
  if [[ -n "$USE" ]]; then
    if (( USE >= DISK_WARN_PCT )); then
      fail "disk root ${USE}% used (threshold ${DISK_WARN_PCT}%)"
    else
      ok "disk root ${USE}% used"
    fi
  fi
fi

# --- Docker daemon ---
if ! docker info >/dev/null 2>&1; then
  fail "docker daemon not available"
else
  ok "docker daemon up"
fi

# --- Required containers ---
for c in $REQUIRED_CONTAINERS; do
  if docker ps --format '{{.Names}}' 2>/dev/null | grep -qx "$c"; then
    ok "container $c running"
  else
    fail "container $c not running"
  fi
done

# --- bitcoind RPC ---
if docker ps --format '{{.Names}}' 2>/dev/null | grep -qx "$BITCOIND_CONTAINER"; then
  if H=$(docker exec "$BITCOIND_CONTAINER" bitcoin-cli -regtest getblockcount 2>/dev/null); then
    ok "bitcoind height=$H"
  else
    fail "bitcoind RPC getblockcount failed"
  fi
fi

# --- LND ---
if docker ps --format '{{.Names}}' 2>/dev/null | grep -qx "$LND_CONTAINER"; then
  INFO=$(docker exec "$LND_CONTAINER" lncli --lnddir=/home/lnd/.lnd --network=regtest getinfo 2>&1 || true)
  if echo "$INFO" | grep -qi 'wallet locked'; then
    warn "LND wallet locked (unlock when operating)"
  elif echo "$INFO" | grep -q 'synced_to_chain'; then
    SYNC=$(echo "$INFO" | grep synced_to_chain | head -1 | tr -d ',' | awk '{print $2}')
    HEIGHT=$(echo "$INFO" | grep block_height | head -1 | tr -d ',' | awk '{print $2}')
    if [[ "$SYNC" == "true" ]]; then
      ok "LND synced height=$HEIGHT"
    else
      warn "LND not synced_to_chain height=$HEIGHT"
    fi
  else
    fail "LND getinfo unexpected: $(echo "$INFO" | head -1 | cut -c1-80)"
  fi

  # --- Channel liquidity floors (local = outbound, remote = inbound) ---
  if echo "$INFO" | grep -qi 'wallet locked'; then
    note "SKIP: channel liquidity (wallet locked)"
  elif command -v python3 >/dev/null 2>&1; then
    CHANS_JSON=$(
      docker exec "$LND_CONTAINER" lncli --lnddir=/home/lnd/.lnd --network=regtest listchannels 2>/dev/null || echo ""
    )
    if [[ -z "$CHANS_JSON" ]]; then
      warn "channel liquidity: listchannels failed"
    else
      # shellcheck disable=SC2016
      LIQ_REPORT=$(
        CHANNEL_MIN_LOCAL_SATS="$CHANNEL_MIN_LOCAL_SATS" \
        CHANNEL_MIN_REMOTE_SATS="$CHANNEL_MIN_REMOTE_SATS" \
        CHANNEL_LIQUIDITY_STRICT="$CHANNEL_LIQUIDITY_STRICT" \
        CHANNEL_MIN_ACTIVE="$CHANNEL_MIN_ACTIVE" \
        python3 -c '
import json, os, sys

raw = sys.stdin.read()
try:
    data = json.loads(raw)
except json.JSONDecodeError:
    print("ERROR|listchannels JSON parse failed")
    sys.exit(0)

chans = data.get("channels") or []
min_local = int(os.environ.get("CHANNEL_MIN_LOCAL_SATS", "5000"))
min_remote = int(os.environ.get("CHANNEL_MIN_REMOTE_SATS", "5000"))
strict = os.environ.get("CHANNEL_LIQUIDITY_STRICT", "0") == "1"
min_active = os.environ.get("CHANNEL_MIN_ACTIVE", "1") == "1"

active = [c for c in chans if c.get("active")]
level = "FAIL" if strict else "WARN"

if not chans:
    print("WARN|no channels (open or inactive)")
elif min_active and not active:
    print(f"{level}|zero active channels (total={len(chans)})")
else:
    print(f"OK|channels total={len(chans)} active={len(active)}")
    for c in active:
        local = int(c.get("local_balance") or 0)
        remote = int(c.get("remote_balance") or 0)
        cap = int(c.get("capacity") or 0)
        peer = (c.get("remote_pubkey") or "")[:16]
        cp = (c.get("channel_point") or "")[:20]
        label = f"peer={peer}… chan={cp}… cap={cap}"
        if local < min_local:
            print(f"{level}|low outbound local={local} < {min_local} ({label})")
        if remote < min_remote:
            print(f"{level}|low inbound remote={remote} < {min_remote} ({label})")
        if local >= min_local and remote >= min_remote:
            print(f"OK|liquidity local={local} remote={remote} ({label})")
' <<<"$CHANS_JSON"
      )
      while IFS= read -r line; do
        [[ -z "$line" ]] && continue
        kind=${line%%|*}
        msg=${line#*|}
        case "$kind" in
          OK) ok "channel $msg" ;;
          WARN) warn "channel $msg" ;;
          FAIL) fail "channel $msg" ;;
          ERROR) warn "channel $msg" ;;
          *) note "channel $line" ;;
        esac
      done <<<"$LIQ_REPORT"
    fi
  else
    note "SKIP: channel liquidity (python3 required)"
  fi
fi

# --- Backend HTTP ---
CODE=$(curl -s -o /tmp/ab-health-body.$$ -w "%{http_code}" --max-time 5 "$BACKEND_URL/" || echo "000")
BODY=$(cat /tmp/ab-health-body.$$ 2>/dev/null || true)
rm -f /tmp/ab-health-body.$$
if [[ "$CODE" == "200" ]]; then
  ok "backend GET / -> 200"
else
  fail "backend GET / -> HTTP $CODE"
fi

# Optional authenticated balance (no amounts printed if JSON fails)
if [[ -n "${AGENT_BITCOIN_API_KEY:-}" ]]; then
  BCODE=$(curl -s -o /tmp/ab-bal.$$ -w "%{http_code}" --max-time 15 \
    -H "X-API-Key: ${AGENT_BITCOIN_API_KEY}" "$BACKEND_URL/balance" || echo "000")
  rm -f /tmp/ab-bal.$$
  if [[ "$BCODE" == "200" ]]; then
    ok "backend GET /balance -> 200 (auth ok)"
  else
    fail "backend GET /balance -> HTTP $BCODE"
  fi
else
  note "SKIP: /balance (set AGENT_BITCOIN_API_KEY to probe auth)"
fi

# --- Report ---
if [[ "$JSON" -eq 1 ]]; then
  python3 - <<PY
import json
print(json.dumps({
  "ok": ${FAIL} == 0,
  "fail": $FAIL,
  "warn": $WARN,
  "messages": $(printf '%s\n' "${MESSAGES[@]}" | python3 -c 'import json,sys; print(json.dumps([l.strip() for l in sys.stdin if l.strip()]))'),
}, indent=2))
PY
else
  echo "=== Agent-Bitcoin AWS health ==="
  printf '%s\n' "${MESSAGES[@]}"
  echo ""
  if [[ "$FAIL" -ne 0 ]]; then
    echo "RESULT: UNHEALTHY"
    exit 1
  fi
  if [[ "$WARN" -ne 0 ]]; then
    echo "RESULT: OK_WITH_WARNINGS"
    exit 0
  fi
  echo "RESULT: HEALTHY"
fi

exit 0
