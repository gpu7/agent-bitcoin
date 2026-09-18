#!/usr/bin/env bash
# Two LND nodes A2A pay. Python 3.12 + pynostr (.venv-nostr). Not uv run python.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="$ROOT/.venv-nostr/bin/python"
if [[ ! -x "$PY" ]]; then
  echo "Missing .venv-nostr (Python 3.12 + pynostr)." >&2
  echo "Do not use: uv run python" >&2
  echo "  uv venv -p 3.12 .venv-nostr" >&2
  echo "  uv pip install --python .venv-nostr/bin/python -e '.[nostr]'" >&2
  exit 1
fi
exec "$PY" "$ROOT/examples/agent-to-agent-pay.py" "$@"
