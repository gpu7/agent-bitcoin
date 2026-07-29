#!/usr/bin/env bash
# shutdown-signet-aws.sh — stop signet LND without deleting the signet volume.
#
# Usage: ./shutdown-signet-aws.sh
# Full wipe (destroys signet wallet): docker compose -f docker-compose.signet.aws.yml down -v

set -euo pipefail

COMPOSE_FILE="docker-compose.signet.aws.yml"

echo "=== Agent-Bitcoin Signet Shutdown (AWS) ==="
if [[ ! -f "$COMPOSE_FILE" ]]; then
  echo "ERROR: $COMPOSE_FILE not found (run from repo root)."
  exit 1
fi

docker compose -f "$COMPOSE_FILE" down --timeout 30 || true

echo "✅ Signet stack stopped."
echo "   Volume preserved: agent-bitcoin_lnd-signet-data"
echo "   To destroy wallet/chain data: docker compose -f $COMPOSE_FILE down -v"
