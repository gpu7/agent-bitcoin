#!/usr/bin/env bash
# Start the Aperture L402 gateway + dummy origin on AWS.
# Does not start LND, Loop, or the FastAPI backend.
#
# Usage:
#   ./startup-l402-aws.sh              # regtest (default)
#   ./startup-l402-aws.sh regtest
#   ./startup-l402-aws.sh signet
#   ./startup-l402-aws.sh mainnet
#
# Only one L402 stack can bind :8081. Stop the other network first.

set -euo pipefail

NETWORK=${1:-regtest}

case "$NETWORK" in
  regtest)
    COMPOSE=docker-compose.l402.regtest.yml
    DOCKER_NET=regtest_regtest
    LND=agent-payment-decision-lnd
    START_HINT="./startup-aws.sh regtest <EIP>"
    ;;
  signet)
    COMPOSE=docker-compose.l402.signet.yml
    DOCKER_NET=agent-bitcoin-signet
    LND=agent-payment-decision-lnd-signet
    START_HINT="./startup-signet-aws.sh <EIP>"
    ;;
  mainnet)
    COMPOSE=docker-compose.l402.mainnet.yml
    DOCKER_NET=agent-bitcoin-mainnet
    LND=agent-payment-decision-lnd-mainnet
    START_HINT="./startup-mainnet-aws.sh <EIP>"
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

if ! docker network inspect "$DOCKER_NET" >/dev/null 2>&1; then
  echo "ERROR: docker network $DOCKER_NET is missing." >&2
  echo "Start the AWS $NETWORK stack first ($START_HINT)." >&2
  exit 1
fi

if ! docker inspect -f '{{.State.Running}}' "$LND" 2>/dev/null | grep -qx true; then
  echo "ERROR: $LND is not running." >&2
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
echo "Paid PDF / PNG:    /paid/report.pdf  /paid/badge.png"
echo "From Mac:          ./update-aws-sg-my-ip.sh   # include port 8081"
echo "                   LND_NETWORK=$NETWORK LND_CONTAINER=<mac-lnd> \\"
echo "                     uv run python examples/l402_pay.py --url http://<AWS_EIP>:8081/paid/hello"
echo
docker compose -f "$COMPOSE" ps
