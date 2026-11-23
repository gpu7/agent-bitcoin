#!/usr/bin/env bash
# Buyer checklist for the Agensi invoice decode and preflight skill.
#
# Requirements: Python 3.10+ and pip install agent-bitcoin. This script
# installs the package and checks inspect_payment_hashes on an invalid
# invoice. It does not sign in to Agensi, does not set the mainnet latch,
# does not need an unlocked node, and does not pay.
#
# uv equivalent of the install:
#   uv venv /tmp/agensi-invoice-buyer
#   uv pip install --python /tmp/agensi-invoice-buyer/bin/python agent-bitcoin
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="${PYTHON:-python3}"

"$PY" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' || {
  echo "Python 3.10+ is required. This interpreter is $("$PY" -V)." >&2
  exit 1
}

cd /tmp
rm -rf /tmp/agensi-invoice-buyer
"$PY" -m venv /tmp/agensi-invoice-buyer
env -u PYTHONPATH /tmp/agensi-invoice-buyer/bin/pip install --upgrade pip
env -u PYTHONPATH /tmp/agensi-invoice-buyer/bin/pip install agent-bitcoin
env -u PYTHONPATH -u AGENT_BITCOIN_ALLOW_MAINNET \
  /tmp/agensi-invoice-buyer/bin/python \
  "$ROOT/tests/deployment/agensi_invoice_buyer.py" --phase install
