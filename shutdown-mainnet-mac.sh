#!/usr/bin/env bash
# shutdown-mainnet-mac.sh — stop mainnet Mac stack; keep volumes.
set -euo pipefail
COMPOSE_FILE="docker-compose.mainnet.mac.yml"
echo "=== Mainnet Mac shutdown (volumes preserved) ==="
docker compose -f "$COMPOSE_FILE" down
echo "✅ Stopped. Volumes preserved (bitcoind + LND mainnet data)."
echo "   Full wipe (DESTRUCTIVE): docker compose -f $COMPOSE_FILE down -v"
