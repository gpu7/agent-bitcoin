#!/usr/bin/env bash
# shutdown-mainnet-aws.sh — stop mainnet AWS stack; keep volumes.
set -euo pipefail
COMPOSE_FILE="docker-compose.mainnet.aws.yml"

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

if [[ -z "${MAINNET_BITCOIND_RPCUSER:-}" || -z "${MAINNET_BITCOIND_RPCPASS:-}" ]]; then
  echo "ERROR: set MAINNET_BITCOIND_RPCUSER and MAINNET_BITCOIND_RPCPASS (or put them in .env)."
  echo "Compose interpolates these even for 'down'."
  exit 1
fi
# Compose interpolates --externalip=${AWS_IP:?…} even on down
export AWS_IP="${AWS_IP:-${AWS_EIP:-3.90.159.146}}"

echo "=== Mainnet AWS shutdown (volumes preserved) ==="
docker compose -f "$COMPOSE_FILE" down
echo "✅ Stopped. Volumes kept: agent-bitcoin_lnd-mainnet-data , agent-bitcoin_bitcoind-mainnet-data"
echo "   Full wipe (DESTRUCTIVE): docker compose -f $COMPOSE_FILE down -v"
