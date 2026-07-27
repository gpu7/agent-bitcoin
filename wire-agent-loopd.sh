#!/usr/bin/env bash
# wire-agent-loopd.sh
#
# Phase 2C: run a dedicated loopd sidecar bound to agent-payment-decision-lnd
# (not the demo lndclient used by stock loopclient).
#
# Prerequisites (AWS regtest):
#   - agent-payment-decision-lnd up, unlocked, on network regtest_regtest
#   - Loop stack healthy: aperture + loopserver Up (see docs/loop-autoloop.md)
#   - aperture TLS available on loopclient (or set APERTURE_TLS_SRC)
#
# Usage:
#   ./wire-agent-loopd.sh              # create/start agent-loopd
#   ./wire-agent-loopd.sh --status     # show container + identity check
#   ./wire-agent-loopd.sh --recreate   # force recreate
#   ./wire-agent-loopd.sh --stop       # stop and remove container (keeps volume)
#
# After start:
#   export LOOP_CLI='docker exec -i agent-loopd loop'
#   ./configure-autoloop-regtest.sh --apply
#   ./configure-autoloop-regtest.sh --status
#
# Env:
#   AGENT_LND_CONTAINER   default agent-payment-decision-lnd
#   AGENT_LND_NETWORK     docker network (default regtest_regtest)
#   AGENT_LND_VOLUME      LND data volume (default agent-bitcoin_lnd-data)
#   AGENT_LOOPD_NAME      container name (default agent-loopd)
#   AGENT_LOOPD_VOLUME    loopd data volume (default agent-loopd-data)
#   LOOPD_IMAGE           default: image of running loopclient, else loopd
#   APERTURE_HOST         default aperture:11018
#   APERTURE_TLS_SRC      host path or container:path for aperture TLS cert
#                         default: loopclient:/root/.loop/aperture-tls.cert

set -euo pipefail

STATUS_ONLY=0
RECREATE=0
STOP=0

for arg in "$@"; do
  case "$arg" in
    --status) STATUS_ONLY=1 ;;
    --recreate) RECREATE=1 ;;
    --stop) STOP=1 ;;
    -h|--help)
      sed -n '2,36p' "$0" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *)
      echo "Unknown option: $arg" >&2
      exit 1
      ;;
  esac
done

AGENT_LND_CONTAINER=${AGENT_LND_CONTAINER:-agent-payment-decision-lnd}
AGENT_LND_NETWORK=${AGENT_LND_NETWORK:-regtest_regtest}
AGENT_LND_VOLUME=${AGENT_LND_VOLUME:-agent-bitcoin_lnd-data}
AGENT_LOOPD_NAME=${AGENT_LOOPD_NAME:-agent-loopd}
AGENT_LOOPD_VOLUME=${AGENT_LOOPD_VOLUME:-agent-loopd-data}
APERTURE_HOST=${APERTURE_HOST:-aperture:11018}
APERTURE_TLS_SRC=${APERTURE_TLS_SRC:-loopclient:/root/.loop/aperture-tls.cert}
NETWORK_NAME=${NETWORK_NAME:-regtest}

LND_MACAROON=/lnd/data/chain/bitcoin/${NETWORK_NAME}/admin.macaroon
LND_TLS=/lnd/tls.cert
APERTURE_TLS_IN_CONTAINER=/root/.loop/aperture-tls.cert

echo "=== wire-agent-loopd ==="
echo "LND=$AGENT_LND_CONTAINER  loopd=$AGENT_LOOPD_NAME  network=$AGENT_LND_NETWORK"
echo ""

if [[ "$STOP" -eq 1 ]]; then
  docker rm -f "$AGENT_LOOPD_NAME" 2>/dev/null || true
  echo "Stopped/removed $AGENT_LOOPD_NAME (volume $AGENT_LOOPD_VOLUME kept)."
  exit 0
fi

container_running() {
  docker inspect -f '{{.State.Running}}' "$1" 2>/dev/null | grep -qx true
}

agent_pubkey() {
  docker exec "$AGENT_LND_CONTAINER" \
    lncli --lnddir=/home/lnd/.lnd --network="$NETWORK_NAME" getinfo 2>/dev/null \
    | sed -n 's/.*"identity_pubkey"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1
}

show_status() {
  if ! docker inspect "$AGENT_LOOPD_NAME" >/dev/null 2>&1; then
    echo "STATUS: $AGENT_LOOPD_NAME not present"
    return 1
  fi
  docker ps -a --filter "name=^/${AGENT_LOOPD_NAME}$" --format 'table {{.Names}}\t{{.Status}}\t{{.Image}}'
  echo ""
  echo "--- loopd command ---"
  docker inspect "$AGENT_LOOPD_NAME" --format '{{json .Config.Cmd}}' | tr ',' '\n' || true
  echo ""
  echo "--- agent LND identity ---"
  local pk
  pk=$(agent_pubkey || true)
  echo "agent-payment-decision-lnd: ${pk:-<unavailable>}"
  echo ""
  if container_running "$AGENT_LOOPD_NAME"; then
    echo "--- loop getinfo (via agent-loopd) ---"
    docker exec -i "$AGENT_LOOPD_NAME" loop --network="$NETWORK_NAME" getinfo 2>&1 | head -20 || true
    echo ""
    echo "--- loop getparams (head) ---"
    docker exec -i "$AGENT_LOOPD_NAME" loop --network="$NETWORK_NAME" getparams 2>&1 | head -25 || true
    echo ""
    echo "LOOP_CLI='docker exec -i $AGENT_LOOPD_NAME loop'"
  else
    echo "STATUS: $AGENT_LOOPD_NAME exists but is not running"
    docker logs --tail 30 "$AGENT_LOOPD_NAME" 2>&1 || true
    return 1
  fi
}

if [[ "$STATUS_ONLY" -eq 1 ]]; then
  show_status
  exit $?
fi

# --- prerequisites ---
if ! container_running "$AGENT_LND_CONTAINER"; then
  echo "ERROR: $AGENT_LND_CONTAINER is not running." >&2
  exit 1
fi

if ! docker exec "$AGENT_LND_CONTAINER" \
    lncli --lnddir=/home/lnd/.lnd --network="$NETWORK_NAME" getinfo >/dev/null 2>&1; then
  echo "ERROR: cannot getinfo on $AGENT_LND_CONTAINER (unlock wallet?)." >&2
  exit 1
fi

if ! docker volume inspect "$AGENT_LND_VOLUME" >/dev/null 2>&1; then
  echo "ERROR: LND volume not found: $AGENT_LND_VOLUME" >&2
  echo "Hint: docker volume ls | grep lnd" >&2
  exit 1
fi

if ! docker network inspect "$AGENT_LND_NETWORK" >/dev/null 2>&1; then
  echo "ERROR: docker network not found: $AGENT_LND_NETWORK" >&2
  exit 1
fi

for c in aperture loopserver; do
  if ! container_running "$c"; then
    echo "ERROR: $c is not running. Fix Loop server stack first (docs/loop-autoloop.md)." >&2
    exit 1
  fi
done

# loopserver must not be crash-looping
ls_status=$(docker inspect -f '{{.State.Status}}' loopserver 2>/dev/null || echo missing)
if [[ "$ls_status" != "running" ]]; then
  echo "ERROR: loopserver status is '$ls_status' (need running)." >&2
  exit 1
fi

LOOPD_IMAGE=${LOOPD_IMAGE:-}
if [[ -z "$LOOPD_IMAGE" ]]; then
  if container_running loopclient; then
    LOOPD_IMAGE=$(docker inspect loopclient --format '{{.Config.Image}}')
  else
    LOOPD_IMAGE=loopd
  fi
fi
echo "Using image: $LOOPD_IMAGE"

# --- seed aperture TLS into loopd volume ---
docker volume create "$AGENT_LOOPD_VOLUME" >/dev/null

seed_aperture_tls() {
  local tmp
  tmp=$(mktemp)
  # shellcheck disable=SC2086
  if [[ "$APERTURE_TLS_SRC" == *:* ]] && [[ "$APERTURE_TLS_SRC" != /* ]]; then
    # container:path
    docker cp "$APERTURE_TLS_SRC" "$tmp"
  else
    cp "$APERTURE_TLS_SRC" "$tmp"
  fi
  # Use a short-lived helper to write into the named volume (same image as loopd)
  docker rm -f agent-loopd-seed >/dev/null 2>&1 || true
  docker run -d --name agent-loopd-seed \
    --entrypoint sleep \
    -v "${AGENT_LOOPD_VOLUME}:/root/.loop" \
    "$LOOPD_IMAGE" 60 >/dev/null
  docker exec agent-loopd-seed mkdir -p /root/.loop
  docker cp "$tmp" agent-loopd-seed:"$APERTURE_TLS_IN_CONTAINER"
  docker rm -f agent-loopd-seed >/dev/null 2>&1 || true
  rm -f "$tmp"
  echo "Seeded aperture TLS into volume $AGENT_LOOPD_VOLUME"
}

if [[ "$RECREATE" -eq 1 ]]; then
  docker rm -f "$AGENT_LOOPD_NAME" 2>/dev/null || true
fi

if container_running "$AGENT_LOOPD_NAME" && [[ "$RECREATE" -eq 0 ]]; then
  echo "$AGENT_LOOPD_NAME already running. Use --recreate to replace, --status to inspect."
  show_status
  exit 0
fi

if docker inspect "$AGENT_LOOPD_NAME" >/dev/null 2>&1; then
  docker rm -f "$AGENT_LOOPD_NAME" >/dev/null 2>&1 || true
fi

seed_aperture_tls

echo "Starting $AGENT_LOOPD_NAME..."
docker run -d \
  --name "$AGENT_LOOPD_NAME" \
  --restart unless-stopped \
  --network "$AGENT_LND_NETWORK" \
  -v "${AGENT_LND_VOLUME}:/lnd:ro" \
  -v "${AGENT_LOOPD_VOLUME}:/root/.loop" \
  "$LOOPD_IMAGE" \
  loopd \
  --experimental \
  --network="$NETWORK_NAME" \
  --debuglevel=debug \
  --server.host="$APERTURE_HOST" \
  --server.tlspath="$APERTURE_TLS_IN_CONTAINER" \
  --lnd.host="${AGENT_LND_CONTAINER}:10009" \
  --lnd.macaroonpath="$LND_MACAROON" \
  --lnd.tlspath="$LND_TLS" \
  >/dev/null

echo "Waiting for loopd RPC..."
ok=0
for i in $(seq 1 30); do
  if docker exec -i "$AGENT_LOOPD_NAME" loop --network="$NETWORK_NAME" getinfo >/dev/null 2>&1; then
    ok=1
    break
  fi
  sleep 2
done

if [[ "$ok" -ne 1 ]]; then
  echo "ERROR: loop getinfo failed after start. Logs:" >&2
  docker logs --tail 40 "$AGENT_LOOPD_NAME" 2>&1 || true
  exit 1
fi

echo ""
echo "OK: $AGENT_LOOPD_NAME is up and talking to $AGENT_LND_CONTAINER"
echo ""
show_status || true

echo ""
echo "Next:"
echo "  export LOOP_CLI='docker exec -i $AGENT_LOOPD_NAME loop'"
echo "  # confirm this is the agent node (pubkey above), then:"
echo "  ./configure-autoloop-regtest.sh --apply"
echo "  ./configure-autoloop-regtest.sh --status"
echo "  # only when ready: ./configure-autoloop-regtest.sh --apply --enable"
echo ""
echo "Note: leave stock loopclient alone (demo lndclient). Use agent-loopd for agent channels."
