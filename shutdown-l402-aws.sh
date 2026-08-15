#!/usr/bin/env bash
# Stop Aperture L402 + dummy origin. Preserves Aperture sqlite volume.
#
# Usage:
#   ./shutdown-l402-aws.sh
#   ./shutdown-l402-aws.sh regtest
#   ./shutdown-l402-aws.sh signet

set -euo pipefail

NETWORK=${1:-regtest}

case "$NETWORK" in
  regtest)
    COMPOSE=docker-compose.l402.regtest.yml
    VOLS="agent-bitcoin_l402-aperture-regtest, agent-bitcoin_lnd-data"
    ;;
  signet)
    COMPOSE=docker-compose.l402.signet.yml
    VOLS="agent-bitcoin_l402-aperture-signet, agent-bitcoin_lnd-signet-data"
    ;;
  *)
    echo "ERROR: unknown network '$NETWORK'" >&2
    exit 1
    ;;
esac

ROOT=$(cd "$(dirname "$0")" && pwd)
cd "$ROOT"

echo "=== Stopping L402 Aperture ($NETWORK) ==="
docker compose -f "$COMPOSE" down --timeout 30 || true
echo "Volumes preserved: $VOLS"
