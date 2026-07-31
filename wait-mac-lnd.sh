#!/bin/bash
# Wait for Mac LND to unlock and reach synced_to_chain=true.
#
# Usage (network usually auto-detected — no arg needed):
#   ./wait-mac-lnd.sh
#
# Optional override (only if both stacks exist / ambiguous):
#   ./wait-mac-lnd.sh regtest
#   ./wait-mac-lnd.sh signet
#   LND_NETWORK=signet ./wait-mac-lnd.sh
#
# Optional env:
#   LND_NETWORK         Force network: regtest | signet (same as first arg)
#   SYNC_MAX_ATTEMPTS   Max poll iterations for chain sync (default: 120 ≈ 10 min at 5s)
#   SYNC_SLEEP_SECS     Seconds between polls (default: 5)
#   RPC_MAX_ATTEMPTS    Max poll iterations for RPC (default: 30)
#   AWS_IP              Optional; only relevant for regtest compose warnings (not required)
#
# Progress each poll: block_height, synced flags, tip age, recent LNWL log lines.
# Detection: prefers a *running* container (agent-bitcoin-lnd-signet vs agent-bitcoin-lnd).

set -euo pipefail

LNDDIR="/home/lnd/.lnd"
SYNC_MAX_ATTEMPTS=${SYNC_MAX_ATTEMPTS:-120}
SYNC_SLEEP_SECS=${SYNC_SLEEP_SECS:-5}
RPC_MAX_ATTEMPTS=${RPC_MAX_ATTEMPTS:-30}

container_running() {
  docker inspect -f '{{.State.Running}}' "$1" 2>/dev/null | grep -qx true
}

resolve_stack() {
  # Sets NETWORK, CONTAINER, COMPOSE_FILE, STACK_LABEL
  local requested="${1:-${LND_NETWORK:-}}"

  if [[ -n "$requested" ]]; then
    case "$requested" in
      regtest|signet) ;;
      *)
        echo "ERROR: network must be regtest or signet (got: $requested)"
        exit 1
        ;;
    esac
    NETWORK="$requested"
  else
    local signet_up=0 regtest_up=0
    container_running agent-bitcoin-lnd-signet && signet_up=1
    container_running agent-bitcoin-lnd && regtest_up=1

    if [[ "$signet_up" -eq 1 && "$regtest_up" -eq 1 ]]; then
      echo "ERROR: both Mac LND stacks are running:"
      echo "  - agent-bitcoin-lnd (regtest)"
      echo "  - agent-bitcoin-lnd-signet (signet)"
      echo "Set one explicitly:  LND_NETWORK=signet ./wait-mac-lnd.sh"
      echo "                 or:  ./wait-mac-lnd.sh regtest"
      exit 1
    fi
    if [[ "$signet_up" -eq 1 ]]; then
      NETWORK=signet
    elif [[ "$regtest_up" -eq 1 ]]; then
      NETWORK=regtest
    else
      echo "ERROR: no Mac LND container is running."
      echo "  Start regtest:  ./startup-mac.sh"
      echo "  Start signet:   ./startup-signet-mac.sh"
      echo "  Or force:       ./wait-mac-lnd.sh signet   # after start"
      exit 1
    fi
  fi

  case "$NETWORK" in
    signet)
      CONTAINER="agent-bitcoin-lnd-signet"
      COMPOSE_FILE="docker-compose.signet.mac.yml"
      STACK_LABEL="Mac signet LND (local bitcoind)"
      ;;
    regtest)
      CONTAINER="agent-bitcoin-lnd"
      COMPOSE_FILE="docker-compose.regtest.mac.yml"
      STACK_LABEL="Mac regtest LND (AWS bitcoind tip)"
      ;;
  esac
  export NETWORK
}

resolve_stack "${1:-}"

echo "=== Waiting for ${STACK_LABEL} to be ready ==="
echo "   network=${NETWORK}  container=${CONTAINER}"
echo ""

lncli_cmd() {
  # Prefer docker exec to avoid AWS_IP compose interpolation warnings on every call.
  docker exec "$CONTAINER" lncli --lnddir="$LNDDIR" --network="$NETWORK" "$@"
}

getinfo_json() {
  lncli_cmd getinfo 2>/dev/null || echo "{}"
}

# Flexible match for pretty-printed JSON ("key": true / "key":  true)
json_true() {
  local key=$1
  local json=$2
  echo "$json" | grep -qE "\"${key}\"[[:space:]]*:[[:space:]]*true"
}

extract_field() {
  local key=$1
  local json=$2
  echo "$json" | grep -E "\"${key}\"" | head -1 | sed -E 's/.*:[[:space:]]*"?([^",}]+)"?.*/\1/' | tr -d ' ,'
}

tip_age_secs() {
  local ts=$1
  if [[ -z "$ts" || "$ts" == "{}" || ! "$ts" =~ ^[0-9]+$ ]]; then
    echo "?"
    return
  fi
  local now
  now=$(date -u +%s)
  echo $((now - ts))
}

# === Check and unlock wallet if locked ===
echo "→ Checking ${CONTAINER} wallet status..."
if lncli_cmd getinfo &>/dev/null; then
  echo "Wallet is unlocked."
else
  echo "→ Wallet is locked. Unlocking..."
  docker exec -it "$CONTAINER" lncli --lnddir="$LNDDIR" --network="$NETWORK" unlock
fi

# === Wait for RPC ===
echo "→ Waiting for ${CONTAINER} RPC..."
RPC_READY=0
for i in $(seq 1 "$RPC_MAX_ATTEMPTS"); do
  echo "  RPC check ($i/$RPC_MAX_ATTEMPTS)..."
  if lncli_cmd getinfo &>/dev/null; then
    echo "✅ RPC is ready!"
    RPC_READY=1
    break
  fi
  sleep "$SYNC_SLEEP_SECS"
done

if [[ "$RPC_READY" -ne 1 ]]; then
  echo "❌ RPC did not become ready. Is the container running?"
  docker ps -a --filter "name=${CONTAINER}"
  exit 1
fi

# === Wait for chain sync (not graph — graph needs peers) ===
echo "→ Waiting for chain sync (synced_to_chain=true)..."
echo "   Polling every ${SYNC_SLEEP_SECS}s, up to ${SYNC_MAX_ATTEMPTS} attempts" \
  "($((SYNC_MAX_ATTEMPTS * SYNC_SLEEP_SECS / 60)) min max)."
echo "   synced_to_graph is ignored here (stays false until peers/channels exist)."
echo ""

SYNCED=0
PREV_HEIGHT=""
for i in $(seq 1 "$SYNC_MAX_ATTEMPTS"); do
  STATUS=$(getinfo_json)
  HEIGHT=$(extract_field block_height "$STATUS")
  TIP_TS=$(extract_field best_header_timestamp "$STATUS")
  AGE=$(tip_age_secs "$TIP_TS")
  CHAIN_SYNC="false"
  GRAPH_SYNC="false"
  json_true synced_to_chain "$STATUS" && CHAIN_SYNC="true"
  json_true synced_to_graph "$STATUS" && GRAPH_SYNC="true"

  HEIGHT_NOTE=""
  if [[ -n "$PREV_HEIGHT" && "$HEIGHT" != "$PREV_HEIGHT" && "$HEIGHT" != "?" ]]; then
    HEIGHT_NOTE=" (↑ from ${PREV_HEIGHT})"
  fi
  PREV_HEIGHT=$HEIGHT

  echo "  Sync check ($i/$SYNC_MAX_ATTEMPTS): height=${HEIGHT}${HEIGHT_NOTE}  " \
    "synced_to_chain=${CHAIN_SYNC}  synced_to_graph=${GRAPH_SYNC}  tip_age=${AGE}s"

  # Progress breadcrumbs from LND wallet logs (rescan / errors)
  if (( i == 1 || i % 6 == 0 )); then
    LOG_SNIP=$(docker logs --tail 30 "$CONTAINER" 2>&1 \
      | grep -iE 'Finished rescan|Birthday|Unable to synchronize|out of range|is synced=|Waiting for chain' \
      | tail -3 || true)
    if [[ -n "$LOG_SNIP" ]]; then
      echo "    recent logs:"
      echo "$LOG_SNIP" | sed 's/^/      /'
    fi
  fi

  if [[ "$CHAIN_SYNC" == "true" ]]; then
    echo ""
    echo "✅ Chain sync complete (synced_to_chain=true)!"
    SYNCED=1
    break
  fi

  sleep "$SYNC_SLEEP_SECS"
done

echo ""
echo "Final status:"
getinfo_json | grep -E "block_height|best_header_timestamp|synced_to_chain|synced_to_graph" || true
echo "LND state: $(lncli_cmd state 2>/dev/null || echo 'n/a')"

if [[ "$SYNCED" -ne 1 ]]; then
  echo ""
  echo "❌ Timed out waiting for synced_to_chain=true (network=${NETWORK})."
  echo "Hints:"
  if [[ "$NETWORK" == "regtest" ]]; then
    echo "  - Confirm Mac LND points at current AWS bitcoind IP:"
    echo "      docker inspect ${CONTAINER} --format '{{json .Config.Cmd}}'"
    echo "  - Mine on AWS only if tip is stale / height behind AWS."
  else
    echo "  - Confirm local bitcoind is synced first:"
    echo "      docker exec agent-bitcoin-bitcoind-signet bitcoin-cli -signet \\"
    echo "        -rpcuser=lightning -rpcpassword=lightning -rpcport=38332 getblockcount"
    echo "  - LND follows bitcoind; if bitcoind is still in IBD, wait longer."
  fi
  echo "  - Restart LND + unlock:"
  echo "      docker compose -f ${COMPOSE_FILE} restart"
  echo "  - Longer budget:"
  echo "      SYNC_MAX_ATTEMPTS=180 ./wait-mac-lnd.sh"
  exit 1
fi

echo ""
echo "Note: synced_to_graph may still be false until you connect peers / open channels."
if [[ "$NETWORK" == "signet" ]]; then
  echo "Ready for connect to AWS signet (see docs/signet.md)."
else
  echo "Ready for connect + channel open (and Mac funding if wallet balance is 0)."
fi
