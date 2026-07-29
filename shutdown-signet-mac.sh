#!/usr/bin/env bash
# Stop Mac signet LND without deleting its volume.
set -euo pipefail
COMPOSE_FILE="docker-compose.signet.mac.yml"
echo "=== Signet Mac shutdown ==="
docker compose -f "$COMPOSE_FILE" down --timeout 30 || true
echo "✅ Stopped. Volume agent-bitcoin-lnd-signet-data preserved."
echo "   Wipe: docker compose -f $COMPOSE_FILE down -v"
