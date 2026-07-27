#!/usr/bin/env bash
# Connect Mac agent-bitcoin-lnd to AWS agent-payment-decision-lnd (Lightning P2P).
#
# Usage:
#   ./connect-mac-to-aws.sh <AWS_IP> <AWS_LND_PUBKEY> [network]
#
# Requires AWS security group to allow TCP 9735 from this Mac.

set -euo pipefail

echo "=== Trying to connect Mac LND to AWS LND ==="

if [ -z "${1:-}" ] || [ -z "${2:-}" ]; then
  echo "Usage: $0 <AWS_IP> <AWS_LND_PUBKEY> [network]"
  echo "Example: $0 3.90.159.146 02abc...def regtest"
  echo ""
  echo "Get AWS pubkey on the instance:"
  echo "  docker exec agent-payment-decision-lnd lncli \\"
  echo "    --lnddir=/home/lnd/.lnd --network=regtest getinfo | jq -r .identity_pubkey"
  exit 1
fi

AWS_IP=$1
LND_PUBKEY=$2
NETWORK=${3:-regtest}
MAX_ATTEMPTS=${MAX_ATTEMPTS:-50}
SLEEP_SECS=${SLEEP_SECS:-5}

CONTAINER="agent-bitcoin-lnd"
LNDDIR="/home/lnd/.lnd"
TARGET="${LND_PUBKEY}@${AWS_IP}:9735"

echo "Network:  $NETWORK"
echo "Target:   $TARGET"
echo ""

show_peers() {
  echo ""
  echo "Peers:"
  docker exec "$CONTAINER" lncli \
    --lnddir="$LNDDIR" \
    --network="$NETWORK" \
    listpeers | grep -E 'pub_key|address|sync_type' || true
}

for i in $(seq 1 "$MAX_ATTEMPTS"); do
  echo "Trying connect... (attempt $i/$MAX_ATTEMPTS)"
  set +e
  OUT=$(
    docker exec "$CONTAINER" lncli \
      --lnddir="$LNDDIR" \
      --network="$NETWORK" \
      connect "$TARGET" 2>&1
  )
  RC=$?
  set -e

  if [[ $RC -eq 0 ]]; then
    echo ""
    echo "✅ Successfully connected to AWS node!"
    show_peers
    exit 0
  fi

  # Already connected is success (lncli exits non-zero)
  if echo "$OUT" | grep -qi 'already connected'; then
    echo ""
    echo "✅ Already connected to AWS node!"
    show_peers
    exit 0
  fi

  # Transient: Mac LND still starting / graph catch-up
  if echo "$OUT" | grep -qi 'still in the process of starting'; then
    echo "Mac LND still starting. Retrying in ${SLEEP_SECS}s..."
    sleep "$SLEEP_SECS"
    continue
  fi

  echo "$OUT"
  echo "Not ready yet. Retrying in ${SLEEP_SECS}s..."
  sleep "$SLEEP_SECS"
done

echo ""
echo "❌ Failed to connect after ${MAX_ATTEMPTS} attempts."
echo "Check:"
echo "  - Mac LND state is SERVER_ACTIVE (not only RPC_ACTIVE)"
echo "  - AWS_IP is the current public EIP"
echo "  - Pubkey matches AWS getinfo identity_pubkey"
echo "  - Security group allows TCP 9735 from this Mac (./update-aws-sg-my-ip.sh)"
echo "  - AWS LND is unlocked and listening"
exit 1
