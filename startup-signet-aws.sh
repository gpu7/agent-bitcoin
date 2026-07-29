#!/usr/bin/env bash
# startup-signet-aws.sh
#
# Start agent-bitcoin LND on Bitcoin signet (Neutrino). Does NOT start:
#   - regtest bitcoind / Loop stack
#   - mining loops
#
# Usage:
#   ./startup-signet-aws.sh <AWS_EIP>
#   ./startup-signet-aws.sh 3.90.159.146
#
# After start: create or unlock wallet, wait for synced_to_chain, fund via faucet.
# See docs/signet.md

set -euo pipefail

AWS_IP=${1:-${AWS_IP:-}}
COMPOSE_FILE="docker-compose.signet.aws.yml"
CONTAINER="agent-payment-decision-lnd-signet"
NETWORK=signet

if [[ -f .env ]]; then
  # shellcheck disable=SC1091
  set -a
  # shellcheck disable=SC1090
  source .env
  set +a
fi

if [[ -z "${AWS_IP}" ]]; then
  echo "ERROR: AWS public IP / EIP is required (LND --externalip)."
  echo "Usage: $0 <AWS_EIP>"
  exit 1
fi

export AWS_IP
export LND_NETWORK=signet
export LND_CONTAINER="${LND_CONTAINER:-$CONTAINER}"

echo "=== Agent-Bitcoin Signet Startup (AWS) ==="
echo "AWS_IP=$AWS_IP"
echo "Compose=$COMPOSE_FILE  container=$CONTAINER"
echo ""
echo "Note: first Neutrino sync can take a long time. Do not reuse regtest volumes."
echo ""

if [[ ! -f "$COMPOSE_FILE" ]]; then
  echo "ERROR: $COMPOSE_FILE not found (run from repo root)."
  exit 1
fi

echo "→ Starting signet LND..."
docker compose -f "$COMPOSE_FILE" up -d

echo "→ Waiting for container..."
for i in $(seq 1 30); do
  if docker inspect -f '{{.State.Running}}' "$CONTAINER" 2>/dev/null | grep -qx true; then
    break
  fi
  sleep 1
done

if ! docker inspect -f '{{.State.Running}}' "$CONTAINER" 2>/dev/null | grep -qx true; then
  echo "ERROR: $CONTAINER is not running. Logs:"
  docker logs --tail 40 "$CONTAINER" || true
  exit 1
fi

echo ""
echo "→ Wallet create/unlock (interactive if needed)..."
if docker exec "$CONTAINER" test -f /home/lnd/.lnd/data/chain/bitcoin/signet/wallet.db 2>/dev/null; then
  echo "Wallet exists. Unlock:"
  echo "  docker exec -it $CONTAINER lncli --lnddir=/home/lnd/.lnd --network=signet unlock"
  docker exec -it "$CONTAINER" lncli --lnddir=/home/lnd/.lnd --network=signet unlock || true
else
  echo "No wallet yet. Create:"
  echo "  docker exec -it $CONTAINER lncli --lnddir=/home/lnd/.lnd --network=signet create"
  docker exec -it "$CONTAINER" lncli --lnddir=/home/lnd/.lnd --network=signet create || true
fi

echo ""
echo "→ Quick getinfo (may fail until unlocked / still syncing)..."
docker exec "$CONTAINER" lncli --lnddir=/home/lnd/.lnd --network=signet getinfo 2>/dev/null \
  | grep -E 'identity_pubkey|block_height|synced_to_chain|version' || \
  echo "(unlock and re-run getinfo; wait for synced_to_chain=true)"

echo ""
echo "✅ Signet LND container is up."
echo ""
echo "Env for SDK / backend on this host:"
echo "  export LND_NETWORK=signet"
echo "  export LND_CONTAINER=$CONTAINER"
echo "  export AWS_IP=$AWS_IP"
echo ""
echo "Next steps (see docs/signet.md):"
echo "  1) Wait until: lncli --network=signet getinfo | grep synced_to_chain"
echo "  2) Fund: lncli --network=signet newaddress p2wkh  → signet faucet"
echo "  3) Backend: LND_NETWORK=signet LND_CONTAINER=$CONTAINER  + API key"
echo "  4) Open a channel to a signet peer (Phase 5)"
echo ""
echo "Health (signet — no local bitcoind):"
echo "  LND_CONTAINER=$CONTAINER REQUIRED_CONTAINERS=$CONTAINER \\"
echo "    BITCOIND_CONTAINER=none ./check-aws-health.sh"
echo "  (bitcoind checks may WARN/FAIL without local bitcoind; prefer getinfo + docs)"
echo ""
echo "Stop: ./shutdown-signet-aws.sh"
