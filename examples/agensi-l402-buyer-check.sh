#!/usr/bin/env bash
# Buyer checklist for the Agensi L402 merchant skill.
#
# Requirements: Python 3.10+, pip install agent-bitcoin, and an unlocked LND
# node. This script installs the package and checks L402Client.fetch plus the
# mainnet and autopay latches. It does not sign in to Agensi, does not leave
# the latches set, and does not pay.
#
# uv equivalent of the install:
#   uv venv /tmp/agensi-l402-buyer
#   uv pip install --python /tmp/agensi-l402-buyer/bin/python agent-bitcoin
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="${PYTHON:-python3}"

"$PY" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' || {
  echo "Python 3.10+ is required. This interpreter is $("$PY" -V)." >&2
  exit 1
}

cd /tmp
rm -rf /tmp/agensi-l402-buyer
"$PY" -m venv /tmp/agensi-l402-buyer
env -u PYTHONPATH /tmp/agensi-l402-buyer/bin/pip install --upgrade pip
env -u PYTHONPATH /tmp/agensi-l402-buyer/bin/pip install agent-bitcoin
env -u PYTHONPATH /tmp/agensi-l402-buyer/bin/python \
  "$ROOT/tests/deployment/agensi_l402_buyer.py" --phase install
