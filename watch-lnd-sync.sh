#!/usr/bin/env bash
#
# watch-lnd-sync.sh
#
# Monitor Bitcoin Core vs LND chain sync in real time.
#
# Run on the AWS host (where containers bitcoind + agent-payment-decision-lnd run).
# On Mac-only, bitcoind is remote — this script will show N/A for Core height.
#
# Usage: ./watch-lnd-sync.sh
# Stop:  Ctrl+C
#
# Env:
#   BITCOIND_CONTAINER   default: bitcoind
#   LND_CONTAINER        default: agent-payment-decision-lnd
#   NETWORK              default: regtest
#   SLEEP_SECS           default: 5

set -uo pipefail

BITCOIND_CONTAINER=${BITCOIND_CONTAINER:-bitcoind}
LND_CONTAINER=${LND_CONTAINER:-agent-payment-decision-lnd}
NETWORK=${NETWORK:-regtest}
SLEEP_SECS=${SLEEP_SECS:-5}

is_int() {
  [[ "${1:-}" =~ ^[0-9]+$ ]]
}

echo "=== LND Sync Watcher ==="
echo "Containers: $BITCOIND_CONTAINER + $LND_CONTAINER (network=$NETWORK)"
echo "Press Ctrl+C to stop"
echo ""

while true; do
  clear
  echo "=== LND Sync Status (updated every ${SLEEP_SECS}s) ==="
  echo ""

  BTC_HEIGHT=$(
    docker exec "$BITCOIND_CONTAINER" bitcoin-cli -regtest getblockcount 2>/dev/null || echo "N/A"
  )
  echo "Bitcoin Core height: $BTC_HEIGHT"

  LND_INFO=$(
    docker exec "$LND_CONTAINER" lncli \
      --lnddir=/home/lnd/.lnd --network="$NETWORK" getinfo 2>/dev/null || true
  )

  if [[ -z "$LND_INFO" ]]; then
    LND_HEIGHT="N/A"
    SYNCED="N/A"
    echo "LND height:          N/A"
    echo "synced_to_chain:     N/A"
    echo "⚠️  LND getinfo failed (container down or wallet locked?)"
  else
    if command -v jq >/dev/null 2>&1; then
      LND_HEIGHT=$(echo "$LND_INFO" | jq -r '.block_height // empty')
      SYNCED=$(echo "$LND_INFO" | jq -r '.synced_to_chain // empty')
    else
      LND_HEIGHT=$(echo "$LND_INFO" | grep block_height | head -1 | awk '{print $2}' | tr -d ',\"')
      SYNCED=$(echo "$LND_INFO" | grep synced_to_chain | head -1 | awk '{print $2}' | tr -d ',\"')
    fi
    [[ -z "$LND_HEIGHT" ]] && LND_HEIGHT="N/A"
    [[ -z "$SYNCED" ]] && SYNCED="N/A"

    echo "LND height:          $LND_HEIGHT"
    echo "synced_to_chain:     $SYNCED"

    if [[ "$SYNCED" == "true" ]]; then
      echo "✅ LND reports synced_to_chain=true"
    elif is_int "$BTC_HEIGHT" && is_int "$LND_HEIGHT"; then
      DIFF=$((BTC_HEIGHT - LND_HEIGHT))
      if (( DIFF > 0 )); then
        echo "Blocks behind:       $DIFF"
      elif (( DIFF < 0 )); then
        echo "LND ahead of Core:   $((-DIFF)) (unusual — check bitcoind)"
      else
        echo "Heights match; sync flag still false (wallet/graph catch-up?)"
      fi
    else
      echo "Blocks behind:       n/a (need numeric heights)"
      if [[ "$BTC_HEIGHT" == "N/A" ]]; then
        echo "⚠️  bitcoind not reachable — run this script on AWS, or start bitcoind."
      fi
    fi
  fi

  echo ""
  echo "=== Recent LND Logs ==="
  if [[ -f docker-compose.regtest.aws.yml ]]; then
    docker compose -f docker-compose.regtest.aws.yml logs --tail 25 "$LND_CONTAINER" 2>/dev/null | tail -20 \
      || docker logs --tail 25 "$LND_CONTAINER" 2>/dev/null | tail -20
  else
    docker logs --tail 25 "$LND_CONTAINER" 2>/dev/null | tail -20
  fi

  sleep "$SLEEP_SECS"
done
