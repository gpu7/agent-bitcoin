#!/usr/bin/env bash
# startup-signet-mac.sh — Mac counterparty LND on Bitcoin signet (local bitcoind).
#
# Usage:
#   ./startup-signet-mac.sh
#
# Migrating from Neutrino: wipe LND volume once (backend switch unsupported):
#   docker compose -f docker-compose.signet.mac.yml down
#   docker volume rm agent-bitcoin_agent-bitcoin-lnd-signet-data 2>/dev/null || true
#   # exact name: docker volume ls | grep lnd-signet
#
# Then connect to AWS signet agent (see docs/signet.md Option 1 dual-node).

set -euo pipefail

COMPOSE_FILE="docker-compose.signet.mac.yml"
LND_CONTAINER="agent-bitcoin-lnd-signet"
BTC_CONTAINER="agent-bitcoin-bitcoind-signet"

echo "=== Agent-Bitcoin Signet Startup (Mac, bitcoind) ==="

if [[ ! -f "$COMPOSE_FILE" ]]; then
  echo "ERROR: $COMPOSE_FILE not found (run from repo root)."
  exit 1
fi

docker compose -f "$COMPOSE_FILE" up -d

echo "→ Waiting for bitcoind RPC..."
for i in $(seq 1 60); do
  if docker exec "$BTC_CONTAINER" bitcoin-cli -signet \
    -rpcuser=lightning -rpcpassword=lightning -rpcport=38332 \
    getblockchaininfo &>/dev/null; then
    break
  fi
  sleep 2
done

if ! docker exec "$BTC_CONTAINER" bitcoin-cli -signet \
  -rpcuser=lightning -rpcpassword=lightning -rpcport=38332 \
  getblockchaininfo &>/dev/null; then
  echo "ERROR: $BTC_CONTAINER RPC not ready. Logs:"
  docker logs --tail 40 "$BTC_CONTAINER" || true
  exit 1
fi

echo "→ bitcoind chain status:"
docker exec "$BTC_CONTAINER" bitcoin-cli -signet \
  -rpcuser=lightning -rpcpassword=lightning -rpcport=38332 \
  getblockchaininfo | grep -E '"chain"|"blocks"|"headers"|"verificationprogress"|"initialblockdownload"' || true

echo "→ Waiting for LND container..."
for i in $(seq 1 60); do
  if docker inspect -f '{{.State.Running}}' "$LND_CONTAINER" 2>/dev/null | grep -qx true; then
    break
  fi
  sleep 1
done

if ! docker inspect -f '{{.State.Running}}' "$LND_CONTAINER" 2>/dev/null | grep -qx true; then
  echo "ERROR: $LND_CONTAINER not running. Logs:"
  docker logs --tail 40 "$LND_CONTAINER" || true
  exit 1
fi

echo "→ Wallet create/unlock..."
if docker exec "$LND_CONTAINER" test -f /home/lnd/.lnd/data/chain/bitcoin/signet/wallet.db 2>/dev/null; then
  echo "Wallet exists — unlock:"
  docker exec -it "$LND_CONTAINER" lncli --lnddir=/home/lnd/.lnd --network=signet unlock || true
else
  echo "Create wallet (save seed offline):"
  docker exec -it "$LND_CONTAINER" lncli --lnddir=/home/lnd/.lnd --network=signet create || true
fi

echo ""
docker exec "$LND_CONTAINER" lncli --lnddir=/home/lnd/.lnd --network=signet getinfo 2>/dev/null \
  | grep -E 'identity_pubkey|block_height|synced_to_chain' || \
  echo "(unlock if needed; wait for bitcoind IBD then LND synced_to_chain=true)"

echo ""
echo "✅ Mac signet stack up:"
echo "   bitcoind: $BTC_CONTAINER  (RPC host :38332, P2P :38333)"
echo "   LND:      $LND_CONTAINER  (P2P host :29735, gRPC :30009)"
echo ""
echo "Watch bitcoind sync (height should rise):"
echo "  docker exec $BTC_CONTAINER bitcoin-cli -signet -rpcuser=lightning -rpcpassword=lightning -rpcport=38332 getblockcount"
echo ""
echo "Watch LND (tracks bitcoind tip once unlocked):"
echo "  docker exec $LND_CONTAINER lncli --lnddir=/home/lnd/.lnd --network=signet getinfo | grep block_height"
echo ""
echo "Next: after both synced, connect to AWS (see docs/signet.md):"
echo "  AWS_PUB=02102808588d8aece7e27af6eb5843810d04ffd88975136e3045e0ed4d45efebea"
echo "  AWS_EIP=3.90.159.146   # your EIP"
echo "  docker exec $LND_CONTAINER lncli --lnddir=/home/lnd/.lnd --network=signet \\"
echo "    connect \${AWS_PUB}@\${AWS_EIP}:19735"
