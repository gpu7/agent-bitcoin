#!/usr/bin/env bash
# reset-aperture-services.sh — drop persisted Aperture services so the YAML whitelist applies.
# Restarts only agent-l402-aperture. Leaves LND, bitcoind, and the database file in place.
set -euo pipefail
cd "$(dirname "$0")"

VOLUME="${APERTURE_VOLUME:-agent-bitcoin_l402-aperture-mainnet}"
IMAGE="${L402_ORIGIN_IMAGE:-agent-bitcoin/l402-origin:mainnet}"
CONTAINER="agent-l402-aperture"

echo "=== Stop Aperture only ==="
docker stop "$CONTAINER"

echo "=== Delete rows from services (keep the database file) ==="
docker run --rm \
  -v "${VOLUME}:/data:rw" \
  --entrypoint python \
  "$IMAGE" \
  -c 'import os, sqlite3, sys
path = "/data/aperture.db"
if not os.path.isfile(path):
    sys.exit("aperture.db is not on the volume")
c = sqlite3.connect(path)
c.execute("DELETE FROM services")
c.commit()
left = c.execute("select count(*) from services").fetchone()[0]
print("services rows left", left)
if left != 0:
    sys.exit(1)
'

echo "=== Start Aperture ==="
docker start "$CONTAINER"

echo "=== Check /health ==="
code=""
ok=0
for _ in 1 2 3 4 5 6 7 8 9 10; do
  headers="$(curl -sS -D - -o /dev/null --max-time 2 http://127.0.0.1:8081/health 2>/dev/null || true)"
  code="$(printf '%s\n' "$headers" | awk 'toupper($1) ~ /^HTTP/ { print $2; exit }')"
  if [[ "$code" == "200" ]] && ! printf '%s\n' "$headers" | grep -qi '^WWW-Authenticate:'; then
    echo "Aperture /health: 200"
    ok=1
    break
  fi
  sleep 1
done
if [[ "$ok" -ne 1 ]]; then
  echo "Aperture /health did not return 200 without WWW-Authenticate (last status: ${code:-none})" >&2
  exit 1
fi
