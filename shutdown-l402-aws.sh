#!/usr/bin/env bash
# Stop Aperture L402 + dummy origin. Preserves Aperture sqlite volume.
#
# Usage:
#   ./shutdown-l402-aws.sh
#   ./shutdown-l402-aws.sh regtest

set -euo pipefail

NETWORK=${1:-regtest}

case "$NETWORK" in
  regtest) COMPOSE=docker-compose.l402.regtest.yml ;;
  *)
    echo "ERROR: unknown network '$NETWORK' (this PR: regtest only)" >&2
    exit 1
    ;;
esac

ROOT=$(cd "$(dirname "$0")" && pwd)
cd "$ROOT"

echo "=== Stopping L402 Aperture ($NETWORK) ==="
docker compose -f "$COMPOSE" down --timeout 30 || true
echo "Volumes preserved: agent-bitcoin_l402-aperture-regtest, agent-bitcoin_lnd-data"
