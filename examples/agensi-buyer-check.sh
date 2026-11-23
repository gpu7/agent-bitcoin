#!/usr/bin/env bash
# Buyer checklist for the public Agensi listing:
# https://www.agensi.io/skills/agent-to-agent-lightning-payment
#
# Listing requirements: Python 3.10+, pip install agent-bitcoin, and an
# unlocked LND node. This script installs the package and checks
# agent_bitcoin.pay_invoice. It does not sign in to Agensi, does not set
# AGENT_BITCOIN_ALLOW_MAINNET, and does not pay.
#
# uv equivalent of the install:
#   uv venv /tmp/agensi-buyer
#   uv pip install --python /tmp/agensi-buyer/bin/python agent-bitcoin
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="${PYTHON:-python3}"

"$PY" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' || {
  echo "Python 3.10+ is required. This interpreter is $("$PY" -V)." >&2
  exit 1
}

cd /tmp
rm -rf /tmp/agensi-buyer
"$PY" -m venv /tmp/agensi-buyer
env -u PYTHONPATH /tmp/agensi-buyer/bin/pip install --upgrade pip
env -u PYTHONPATH /tmp/agensi-buyer/bin/pip install agent-bitcoin
env -u PYTHONPATH /tmp/agensi-buyer/bin/python -c 'from agent_bitcoin import pay_invoice; import agent_bitcoin; print(agent_bitcoin.__version__)'
env -u PYTHONPATH /tmp/agensi-buyer/bin/python "$ROOT/tests/deployment/agensi_public_buyer.py" --phase install
