#!/usr/bin/env bash
# startup-mainnet-mac.sh — Mac mainnet peer (bitcoind + LND). Volumes preserved.
#
# Usage:
#   export MAINNET_BITCOIND_RPCUSER='…'
#   export MAINNET_BITCOIND_RPCPASS='…'
#   ./startup-mainnet-mac.sh
#
# Does NOT fund wallets or open channels. See docs/mainnet-infra.md.

set -euo pipefail

COMPOSE_FILE="docker-compose.mainnet.mac.yml"
LND_NAME="agent-bitcoin-lnd-mainnet"
BTC_CONTAINER="agent-bitcoin-bitcoind-mainnet"
LND_CONTAINER="${LND_CONTAINER:-$LND_NAME}"

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

if [[ -z "${MAINNET_BITCOIND_RPCUSER:-}" || -z "${MAINNET_BITCOIND_RPCPASS:-}" ]]; then
  echo "ERROR: set MAINNET_BITCOIND_RPCUSER and MAINNET_BITCOIND_RPCPASS (unique mainnet secrets)."
  exit 1
fi
if [[ "${MAINNET_BITCOIND_RPCUSER}" == "lightning" ]] || [[ "${MAINNET_BITCOIND_RPCPASS}" == "lightning" ]]; then
  echo "ERROR: refusing lab default RPC user/pass on mainnet. Use unique credentials."
  exit 1
fi

export MAINNET_BITCOIND_RPCUSER MAINNET_BITCOIND_RPCPASS
export LND_NETWORK=mainnet
export LND_CONTAINER

echo "=== Agent-Bitcoin Mainnet Startup (Mac, bitcoind) ==="
echo "WARNING: mainnet real funds risk. Do not fund without Phase 8 go."
echo ""

if [[ ! -f "$COMPOSE_FILE" ]]; then
  echo "ERROR: $COMPOSE_FILE not found (run from repo root)."
  exit 1
fi

docker compose -f "$COMPOSE_FILE" config >/dev/null
docker compose -f "$COMPOSE_FILE" up -d

echo "→ Waiting for bitcoind..."
for i in $(seq 1 90); do
  if docker exec "$BTC_CONTAINER" bitcoin-cli \
    -rpcuser="$MAINNET_BITCOIND_RPCUSER" \
    -rpcpassword="$MAINNET_BITCOIND_RPCPASS" \
    -rpcport=8332 getblockchaininfo &>/dev/null; then
    break
  fi
  sleep 3
done

echo "→ bitcoind status (may still be IBD):"
docker exec "$BTC_CONTAINER" bitcoin-cli \
  -rpcuser="$MAINNET_BITCOIND_RPCUSER" \
  -rpcpassword="$MAINNET_BITCOIND_RPCPASS" \
  -rpcport=8332 getblockchaininfo 2>/dev/null \
  | grep -E '"chain"|"blocks"|"headers"|"verificationprogress"|"initialblockdownload"|"pruned"' || true

echo "→ Waiting for LND container..."
for i in $(seq 1 60); do
  if docker inspect -f '{{.State.Running}}' "$LND_CONTAINER" 2>/dev/null | grep -qx true; then
    break
  fi
  sleep 2
done

echo ""
echo "→ Wallet create/unlock (human only)..."
if docker exec "$LND_CONTAINER" test -f /home/lnd/.lnd/data/chain/bitcoin/mainnet/wallet.db 2>/dev/null; then
  echo "Wallet exists. Unlock:"
  echo "  docker exec -it $LND_CONTAINER lncli --lnddir=/home/lnd/.lnd --network=mainnet unlock"
  docker exec -it "$LND_CONTAINER" lncli --lnddir=/home/lnd/.lnd --network=mainnet unlock || true
else
  echo "No mainnet wallet yet. Create NEW seed (offline backup first):"
  echo "  docker exec -it $LND_CONTAINER lncli --lnddir=/home/lnd/.lnd --network=mainnet create"
  docker exec -it "$LND_CONTAINER" lncli --lnddir=/home/lnd/.lnd --network=mainnet create || true
fi

echo ""
echo "✅ Mainnet Mac stack containers up."
echo "  LND P2P host :39735   gRPC 127.0.0.1:40009"
echo "  export LND_NETWORK=mainnet"
echo "  export LND_CONTAINER=$LND_CONTAINER"
echo "  export LND_TRANSPORT=grpc LND_GRPC_HOST=127.0.0.1 LND_GRPC_PORT=40009"
echo ""
echo "After Phase 8 go + both synced, connect to AWS:"
echo "  docker exec $LND_CONTAINER lncli --lnddir=/home/lnd/.lnd --network=mainnet \\"
echo "    connect \${AWS_PUB}@\${AWS_IP}:9735"
