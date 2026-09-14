#!/usr/bin/env bash
# Pay GET /paid/finance/mempool-feerate (100 sats) with THIS machine's LND.
# Not our Mac LND. Not AWS invoice LND (self-pay).
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
URL="${L402_URL:-http://3.90.159.146:8081/paid/finance/mempool-feerate}"

usage() {
  cat <<'EOF'
smoke-l402.sh — one 100-sat L402 GET using container l402-client-lnd.

Usage:
  ./smoke-l402.sh
  ./smoke-l402.sh --help

Requires: Docker LND unlocked, operator /32 on 8081, a path that can send 100 sats
(prefer a private channel to AWS). Sets AGENT_BITCOIN_ALLOW_MAINNET and ALLOW_AUTOPAY.
EOF
}

if [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ]; then
  usage
  exit 0
fi

export LND_NETWORK=mainnet
export LND_CONTAINER=l402-client-lnd
export LND_TRANSPORT=docker
export AGENT_BITCOIN_ALLOW_MAINNET=1
export AGENT_BITCOIN_ALLOW_AUTOPAY=1

cd "$ROOT"
if command -v uv >/dev/null 2>&1; then
  exec uv run python examples/l402_pay.py --url "$URL" --price 100
fi
exec python3 examples/l402_pay.py --url "$URL" --price 100
