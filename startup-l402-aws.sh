#!/usr/bin/env bash
# Start the Aperture L402 gateway + dummy origin on AWS.
# Does not start LND, Loop, or the FastAPI backend.
#
# Usage:
#   ./startup-l402-aws.sh              # regtest (default)
#   ./startup-l402-aws.sh regtest
#
# Signet/mainnet overlays land in later PRs.

set -euo pipefail

NETWORK=${1:-regtest}

case "$NETWORK" in
  regtest)
    COMPOSE=docker-compose.l402.regtest.yml
    ;;
  signet|mainnet)
    echo "ERROR: $NETWORK L402 compose is not in this PR. Use regtest." >&2
    exit 1
    ;;
  *)
    echo "ERROR: unknown network '$NETWORK'" >&2
    exit 1
    ;;
esac

if ! docker info >/dev/null 2>&1; then
  echo "ERROR: docker is not available" >&2
  exit 1
fi

if ! docker network inspect regtest_regtest >/dev/null 2>&1; then
  echo "ERROR: docker network regtest_regtest is missing." >&2
  echo "Start the AWS regtest stack first (./startup-aws.sh regtest <EIP>)." >&2
  exit 1
fi

if ! docker inspect -f '{{.State.Running}}' agent-payment-decision-lnd 2>/dev/null | grep -qx true; then
  echo "ERROR: agent-payment-decision-lnd is not running." >&2
  echo "Start/unlock AWS LND before Aperture." >&2
  exit 1
fi

ROOT=$(cd "$(dirname "$0")" && pwd)
cd "$ROOT"

echo "=== Starting L402 Aperture ($NETWORK) ==="
docker compose -f "$COMPOSE" up -d --build

echo
echo "Health (free):     curl -sS http://127.0.0.1:8081/health"
echo "Paid challenge:    curl -sSi http://127.0.0.1:8081/paid/hello"
echo "From Mac:          ./update-aws-sg-my-ip.sh   # include port 8081"
echo "                   uv run python examples/l402_pay.py --url http://<AWS_EIP>:8081/paid/hello"
echo
docker compose -f "$COMPOSE" ps
