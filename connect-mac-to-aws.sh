#!/bin/bash
# Connect Mac agent-bitcoin-lnd to AWS agent-payment-decision-lnd (Lightning P2P).
#
# Usage:
#   ./connect-mac-to-aws.sh <AWS_IP> <AWS_LND_PUBKEY> [network]
#
# Example:
#   # On AWS, get pubkey:
#   #   docker exec agent-payment-decision-lnd lncli \
#   #     --lnddir=/home/lnd/.lnd --network=regtest getinfo | grep identity_pubkey
#   ./connect-mac-to-aws.sh 3.90.42.241 024024c3d664a14e961a1d6c577ed65eba67017aca3f21e6d499f2a807d18c3b70
#
# Requires AWS security group to allow TCP 9735 from this Mac.

set -euo pipefail

echo "=== Trying to connect Mac LND to AWS LND ==="

if [ -z "${1:-}" ] || [ -z "${2:-}" ]; then
  echo "Usage: $0 <AWS_IP> <AWS_LND_PUBKEY> [network]"
  echo "Example: $0 3.90.42.241 02abc...def regtest"
  echo ""
  echo "Get AWS pubkey on the instance:"
  echo "  docker exec agent-payment-decision-lnd lncli \\"
  echo "    --lnddir=/home/lnd/.lnd --network=regtest getinfo | grep identity_pubkey"
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

for i in $(seq 1 "$MAX_ATTEMPTS"); do
  echo "Trying connect... (attempt $i/$MAX_ATTEMPTS)"
  if docker exec "$CONTAINER" lncli \
    --lnddir="$LNDDIR" \
    --network="$NETWORK" \
    connect "$TARGET"; then
    echo ""
    echo "✅ Successfully connected to AWS node!"
    echo ""
    echo "Peers:"
    docker exec "$CONTAINER" lncli \
      --lnddir="$LNDDIR" \
      --network="$NETWORK" \
      listpeers | grep -E 'pub_key|address|sync_type' || true
    exit 0
  fi
  echo "Not ready yet. Retrying in ${SLEEP_SECS}s..."
  sleep "$SLEEP_SECS"
done

echo ""
echo "❌ Failed to connect after ${MAX_ATTEMPTS} attempts."
echo "Check:"
echo "  - AWS_IP is the current public IP"
echo "  - Pubkey matches AWS getinfo identity_pubkey (wallet recreate changes it)"
echo "  - Security group allows TCP 9735 from this Mac"
echo "  - AWS LND is unlocked and listening (uris / getinfo)"
exit 1
