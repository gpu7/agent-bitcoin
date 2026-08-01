#!/usr/bin/env bash
# signet-dress-rehearsal-env.sh — print Phase 7 pilot-like env for signet.
#
# Usage:
#   ./signet-dress-rehearsal-env.sh mac
#   ./signet-dress-rehearsal-env.sh aws
#   eval "$(./signet-dress-rehearsal-env.sh mac)"   # load into current shell
#
# Does not export wallet passwords or print macaroon contents.

set -euo pipefail

ROLE=${1:-}
if [[ "$ROLE" != "mac" && "$ROLE" != "aws" ]]; then
  echo "Usage: $0 mac|aws" >&2
  exit 1
fi

if [[ "$ROLE" == "mac" ]]; then
  cat <<'EOF'
export LND_NETWORK=signet
export LND_TRANSPORT=grpc
export LND_GRPC_HOST=127.0.0.1
export LND_GRPC_PORT=30009
export LND_TLS_CERT_PATH="${LND_TLS_CERT_PATH:-$HOME/.lnd-export/signet-mac/tls.cert}"
export LND_MACAROON_PATH="${LND_MACAROON_PATH:-$HOME/.lnd-export/signet-mac/admin.macaroon}"
export MAX_PAYMENT_SATS=50000
export MAX_DAILY_PAYMENT_SATS=100000
export AGENT_BITCOIN_SPEND_LEDGER="${AGENT_BITCOIN_SPEND_LEDGER:-$HOME/.config/agent-bitcoin/dress-rehearsal-spend.json}"
# Lab allows pay by default; set ALLOW_AUTOPAY=1 explicitly to practice mainnet flag:
export AGENT_BITCOIN_ALLOW_AUTOPAY="${AGENT_BITCOIN_ALLOW_AUTOPAY:-1}"
# Docker fallback for scripts that still use docker exec:
export LND_CONTAINER=agent-bitcoin-lnd-signet
export LND_DIR=/home/lnd/.lnd
EOF
else
  cat <<'EOF'
export LND_NETWORK=signet
export LND_TRANSPORT=grpc
export LND_GRPC_HOST=127.0.0.1
export LND_GRPC_PORT=20009
export LND_TLS_CERT_PATH="${LND_TLS_CERT_PATH:-$HOME/.lnd-export/signet-aws/tls.cert}"
export LND_MACAROON_PATH="${LND_MACAROON_PATH:-$HOME/.lnd-export/signet-aws/admin.macaroon}"
export MAX_PAYMENT_SATS=50000
export MAX_DAILY_PAYMENT_SATS=100000
export AGENT_BITCOIN_SPEND_LEDGER="${AGENT_BITCOIN_SPEND_LEDGER:-$HOME/.config/agent-bitcoin/dress-rehearsal-spend.json}"
export AGENT_BITCOIN_ALLOW_AUTOPAY="${AGENT_BITCOIN_ALLOW_AUTOPAY:-1}"
export LND_CONTAINER=agent-payment-decision-lnd-signet
export LND_DIR=/home/lnd/.lnd
EOF
fi
