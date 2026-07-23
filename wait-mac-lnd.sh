#!/bin/bash
# Wait for Mac agent-bitcoin-lnd to unlock and sync to the AWS bitcoind tip.
#
# Usage:
#   ./wait-mac-lnd.sh [network]
#   ./wait-mac-lnd.sh regtest
#
# Optional env:
#   SYNC_MAX_ATTEMPTS  Max poll iterations for chain sync (default: 120 ≈ 10 min at 5s)
#   SYNC_SLEEP_SECS    Seconds between polls (default: 5)
#   AWS_IP             Optional; silences compose warnings if set (not required for wait)
#
# Progress each poll: block_height, synced flags, tip age, recent LNWL log lines.
# Does NOT need AWS_IP for correctness — the container already has bitcoind host baked in.

set -euo pipefail

echo "=== Waiting for Mac agent-bitcoin-lnd to be ready ==="

NETWORK=${1:-regtest}
export NETWORK

COMPOSE_FILE="docker-compose.regtest.mac.yml"
CONTAINER="agent-bitcoin-lnd"
LNDDIR="/home/lnd/.lnd"

SYNC_MAX_ATTEMPTS=${SYNC_MAX_ATTEMPTS:-120}
SYNC_SLEEP_SECS=${SYNC_SLEEP_SECS:-5}
RPC_MAX_ATTEMPTS=${RPC_MAX_ATTEMPTS:-30}

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

# === Check and unlock agent-bitcoin-lnd wallet if locked ===
echo "→ Checking agent-bitcoin-lnd wallet status..."
if lncli_cmd getinfo &>/dev/null; then
  echo "agent-bitcoin-lnd wallet is unlocked."
else
  echo "→ agent-bitcoin-lnd wallet is locked. Unlocking..."
  docker exec -it "$CONTAINER" lncli --lnddir="$LNDDIR" --network="$NETWORK" unlock
fi

# === Wait for agent-bitcoin-lnd RPC to be available ===
echo "→ Waiting for agent-bitcoin-lnd RPC..."
RPC_READY=0
for i in $(seq 1 "$RPC_MAX_ATTEMPTS"); do
  echo "  RPC check ($i/$RPC_MAX_ATTEMPTS)..."
  if lncli_cmd getinfo &>/dev/null; then
    echo "✅ agent-bitcoin-lnd RPC is ready!"
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
# tall regtest tips need a long wallet rescan; 50×5s (~4 min) is often too short.
echo "→ Waiting for agent-bitcoin-lnd chain sync (synced_to_chain=true)..."
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
      | grep -iE 'Finished rescan|Birthday|Unable to synchronize|out of range|is synced=' \
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
  echo "❌ Timed out waiting for synced_to_chain=true."
  echo "Hints:"
  echo "  - Confirm Mac LND points at current AWS IP:"
  echo "      docker inspect ${CONTAINER} --format '{{json .Config.Cmd}}' | jq ."
  echo "  - Confirm tip advances when you mine on AWS (height should rise here)."
  echo "  - If height matches AWS but flag stays false, wait longer or restart LND + unlock:"
  echo "      docker compose -f ${COMPOSE_FILE} restart ${CONTAINER}"
  echo "  - Re-run with a longer budget, e.g.:"
  echo "      SYNC_MAX_ATTEMPTS=180 ./wait-mac-lnd.sh ${NETWORK}"
  echo "  - Only mine on AWS if tip_age is large (stale tip) or height is behind AWS."
  exit 1
fi

echo ""
echo "Note: synced_to_graph may still be false until you connect peers / open channels."
echo "Ready for connect + channel open (and Mac funding if wallet balance is 0)."
