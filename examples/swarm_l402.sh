#!/usr/bin/env bash
# Run swarm_l402_negotiate.py with Python 3.12 + pynostr (.venv-nostr).
# Do not use: uv run python  — on 3.13/3.14 it recreates .venv and skips .[nostr].
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="$ROOT/.venv-nostr/bin/python"
if [[ ! -x "$PY" ]]; then
  echo "Missing .venv-nostr (Python 3.12 + pynostr)." >&2
  echo "Do not use: uv run python   # picks 3.13/3.14 and skips .[nostr]" >&2
  echo "  cd \"$ROOT\"" >&2
  echo "  uv venv -p 3.12 .venv-nostr" >&2
  echo "  uv pip install --python .venv-nostr/bin/python -e '.[nostr]'" >&2
  exit 1
fi
exec "$PY" "$ROOT/examples/swarm_l402_negotiate.py" "$@"
