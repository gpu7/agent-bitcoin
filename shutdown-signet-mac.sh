#!/usr/bin/env bash
# Stop Mac signet bitcoind + LND without deleting volumes.
set -euo pipefail
COMPOSE_FILE="docker-compose.signet.mac.yml"
echo "=== Signet Mac shutdown ==="
docker compose -f "$COMPOSE_FILE" down --timeout 60 || true
echo "✅ Stopped. Volumes preserved:"
echo "   agent-bitcoin-bitcoind-signet-data  (chain)"
echo "   agent-bitcoin-lnd-signet-data       (wallet)"
echo "   Full wipe: docker compose -f $COMPOSE_FILE down -v"
