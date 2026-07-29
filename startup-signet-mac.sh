#!/usr/bin/env bash
# startup-signet-mac.sh — Mac counterparty LND on Bitcoin signet (Neutrino).
#
# Usage:
#   ./startup-signet-mac.sh
#
# Then connect to AWS signet agent (see docs/signet.md Option 1 dual-node).

set -euo pipefail

COMPOSE_FILE="docker-compose.signet.mac.yml"
CONTAINER="agent-bitcoin-lnd-signet"

echo "=== Agent-Bitcoin Signet Startup (Mac) ==="

if [[ ! -f "$COMPOSE_FILE" ]]; then
  echo "ERROR: $COMPOSE_FILE not found (run from repo root)."
  exit 1
fi

docker compose -f "$COMPOSE_FILE" up -d

echo "→ Waiting for container..."
for i in $(seq 1 30); do
  if docker inspect -f '{{.State.Running}}' "$CONTAINER" 2>/dev/null | grep -qx true; then
    break
  fi
  sleep 1
done

if ! docker inspect -f '{{.State.Running}}' "$CONTAINER" 2>/dev/null | grep -qx true; then
  echo "ERROR: $CONTAINER not running. Logs:"
  docker logs --tail 40 "$CONTAINER" || true
  exit 1
fi

echo "→ Wallet create/unlock..."
if docker exec "$CONTAINER" test -f /home/lnd/.lnd/data/chain/bitcoin/signet/wallet.db 2>/dev/null; then
  echo "Wallet exists — unlock:"
  docker exec -it "$CONTAINER" lncli --lnddir=/home/lnd/.lnd --network=signet unlock || true
else
  echo "Create wallet (save seed offline):"
  docker exec -it "$CONTAINER" lncli --lnddir=/home/lnd/.lnd --network=signet create || true
fi

echo ""
docker exec "$CONTAINER" lncli --lnddir=/home/lnd/.lnd --network=signet getinfo 2>/dev/null \
  | grep -E 'identity_pubkey|block_height|synced_to_chain' || \
  echo "(unlock if needed; wait for synced_to_chain=true)"

echo ""
echo "✅ Mac signet LND up: $CONTAINER"
echo "   Host P2P port: 29735  gRPC: 30009"
echo ""
echo "Next: wait for sync, then connect to AWS (see docs/signet.md):"
echo "  AWS_PUB=02102808588d8aece7e27af6eb5843810d04ffd88975136e3045e0ed4d45efebea"
echo "  AWS_EIP=3.90.159.146   # your EIP"
echo "  docker exec $CONTAINER lncli --lnddir=/home/lnd/.lnd --network=signet \\"
echo "    connect \${AWS_PUB}@\${AWS_EIP}:19735"
