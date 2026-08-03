#!/usr/bin/env bash
# shutdown-mainnet-aws.sh — stop mainnet AWS stack; keep volumes.
set -euo pipefail
COMPOSE_FILE="docker-compose.mainnet.aws.yml"
echo "=== Mainnet AWS shutdown (volumes preserved) ==="
docker compose -f "$COMPOSE_FILE" down
echo "✅ Stopped. Volumes kept: agent-bitcoin_lnd-mainnet-data , agent-bitcoin_bitcoind-mainnet-data"
echo "   Full wipe (DESTRUCTIVE): docker compose -f $COMPOSE_FILE down -v"
