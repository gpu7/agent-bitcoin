#!/usr/bin/env bash
# Start the Agent Bitcoin infrastructure dashboard on the Mac.
# Listens only on 127.0.0.1:8765.
set -euo pipefail

cd "$(dirname "$0")"

export DASHBOARD_APERTURE_URL="${DASHBOARD_APERTURE_URL:-http://3.90.159.146:8081}"

echo "=== Agent Bitcoin Dashboard ==="
echo "Aperture: ${DASHBOARD_APERTURE_URL}"
echo "Open:     http://127.0.0.1:8765"
echo

exec uv run python -m agent_bitcoin.dashboard
