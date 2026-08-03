#!/usr/bin/env bash
# startup-mainnet-aws.sh — AWS mainnet agent (bitcoind + LND). Volumes preserved.
#
# Usage:
#   export MAINNET_BITCOIND_RPCUSER='…'
#   export MAINNET_BITCOIND_RPCPASS='…'
#   ./startup-mainnet-aws.sh <AWS_EIP>
#
# Does NOT create wallet funds or open channels. See docs/mainnet-infra.md.

set -euo pipefail

AWS_IP=${1:-${AWS_IP:-}}
COMPOSE_FILE="docker-compose.mainnet.aws.yml"
CONTAINER="agent-payment-decision-lnd-mainnet"
BTC="agent-payment-decision-bitcoind-mainnet"

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

if [[ -z "${AWS_IP}" ]]; then
  echo "ERROR: AWS public IP / EIP required (LND --externalip)."
  echo "Usage: $0 <AWS_EIP>"
  exit 1
fi
if [[ -z "${MAINNET_BITCOIND_RPCUSER:-}" || -z "${MAINNET_BITCOIND_RPCPASS:-}" ]]; then
  echo "ERROR: set MAINNET_BITCOIND_RPCUSER and MAINNET_BITCOIND_RPCPASS (unique mainnet secrets)."
  exit 1
fi
if [[ "${MAINNET_BITCOIND_RPCUSER}" == "lightning" ]] || [[ "${MAINNET_BITCOIND_RPCPASS}" == "lightning" ]]; then
  echo "ERROR: refusing lab default RPC user/pass on mainnet. Use unique credentials."
  exit 1
fi

export AWS_IP
export MAINNET_BITCOIND_RPCUSER MAINNET_BITCOIND_RPCPASS
export LND_NETWORK=mainnet
export LND_CONTAINER="${LND_CONTAINER:-$CONTAINER}"

echo "=== Agent-Bitcoin Mainnet Startup (AWS, bitcoind) ==="
echo "AWS_IP=$AWS_IP"
echo "WARNING: mainnet real funds risk. Do not proceed to fund without Phase 8 go."
echo "Volumes: agent-bitcoin_lnd-mainnet-data , agent-bitcoin_bitcoind-mainnet-data (NEW only)"
echo ""

if [[ ! -f "$COMPOSE_FILE" ]]; then
  echo "ERROR: $COMPOSE_FILE not found (run from repo root)."
  exit 1
fi

docker compose -f "$COMPOSE_FILE" config >/dev/null
docker compose -f "$COMPOSE_FILE" up -d

echo "→ Waiting for bitcoind container..."
for i in $(seq 1 60); do
  if docker inspect -f '{{.State.Running}}' "$BTC" 2>/dev/null | grep -qx true; then
    break
  fi
  sleep 2
done

echo "→ Waiting for LND container..."
for i in $(seq 1 90); do
  if docker inspect -f '{{.State.Running}}' "$CONTAINER" 2>/dev/null | grep -qx true; then
    break
  fi
  sleep 2
done

if ! docker inspect -f '{{.State.Running}}' "$CONTAINER" 2>/dev/null | grep -qx true; then
  echo "ERROR: $CONTAINER not running (bitcoind may still be syncing/healthchecking)."
  docker logs --tail 40 "$BTC" || true
  docker logs --tail 40 "$CONTAINER" || true
  exit 1
fi

echo ""
echo "→ Wallet create/unlock (human only)..."
if docker exec "$CONTAINER" test -f /home/lnd/.lnd/data/chain/bitcoin/mainnet/wallet.db 2>/dev/null; then
  echo "Wallet exists. Unlock:"
  echo "  docker exec -it $CONTAINER lncli --lnddir=/home/lnd/.lnd --network=mainnet unlock"
  docker exec -it "$CONTAINER" lncli --lnddir=/home/lnd/.lnd --network=mainnet unlock || true
else
  echo "No mainnet wallet yet. Create NEW seed (offline backup first):"
  echo "  docker exec -it $CONTAINER lncli --lnddir=/home/lnd/.lnd --network=mainnet create"
  docker exec -it "$CONTAINER" lncli --lnddir=/home/lnd/.lnd --network=mainnet create || true
fi

echo ""
echo "✅ Mainnet AWS stack containers up (IBD may continue for a long time)."
echo "  export LND_NETWORK=mainnet"
echo "  export LND_CONTAINER=$CONTAINER"
echo "  export AGENT_BITCOIN_ALLOW_MAINNET=1   # only when intentionally operating mainnet"
echo "  gRPC: 127.0.0.1:10009 (not public)"
echo "  P2P:  ${AWS_IP}:9735 (SG: Mac /32)"
echo ""
echo "Do NOT fund until Phase 8 go/no-go. Monitor:"
echo "  docker exec $BTC bitcoin-cli -rpcuser=\"\$MAINNET_BITCOIND_RPCUSER\" -rpcpassword=\"\$MAINNET_BITCOIND_RPCPASS\" getblockchaininfo"
echo "  docker exec $CONTAINER lncli --lnddir=/home/lnd/.lnd --network=mainnet getinfo"
