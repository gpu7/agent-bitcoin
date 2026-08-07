#!/usr/bin/env bash
# wire-loopd.sh — run loopd beside an agent-bitcoin LND on regtest, signet, or mainnet.
#
# Regtest: requires local Loop stack (aperture + loopserver) — same as wire-agent-loopd.sh.
# Signet/mainnet: connects to Lightning Labs public Loop servers (no local loopserver).
#
# Usage:
#   ./wire-loopd.sh regtest              # AWS agent LND + local Loop regtest
#   ./wire-loopd.sh signet               # AWS signet LND (when stack is up)
#   ./wire-loopd.sh mainnet              # AWS mainnet LND — Autoloop stays OFF
#   ./wire-loopd.sh mainnet --host mac   # Mac mainnet peer LND
#   ./wire-loopd.sh <network> --status
#   ./wire-loopd.sh <network> --recreate
#   ./wire-loopd.sh <network> --stop
#
# After start:
#   export LOOP_CLI='docker exec -i agent-loopd-<network> loop'
#   $LOOP_CLI --network=<network> getinfo
#   $LOOP_CLI --network=<network> terms
#
# NEVER enable Autoloop on mainnet without an explicit operator decision
# (see docs/mainnet-pilot.md — BIP-110 freeze: no channels until after 961632).
#
# Env overrides: AGENT_LND_CONTAINER, AGENT_LND_NETWORK, AGENT_LND_VOLUME,
#                AGENT_LOOPD_NAME, AGENT_LOOPD_VOLUME, LOOPD_IMAGE, NETWORK_NAME

set -euo pipefail

NETWORK="${1:-}"
shift || true

STATUS_ONLY=0
RECREATE=0
STOP=0
HOST_ROLE=aws

while [[ $# -gt 0 ]]; do
  case "$1" in
    --status) STATUS_ONLY=1 ;;
    --recreate) RECREATE=1 ;;
    --stop) STOP=1 ;;
    --host)
      HOST_ROLE=${2:-}
      shift
      ;;
    --host=*) HOST_ROLE=${1#--host=} ;;
    -h|--help)
      sed -n '2,28p' "$0" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      exit 1
      ;;
  esac
  shift
done

if [[ -z "$NETWORK" || ! "$NETWORK" =~ ^(regtest|signet|mainnet)$ ]]; then
  echo "Usage: $0 regtest|signet|mainnet [--host aws|mac] [--status|--recreate|--stop]" >&2
  exit 1
fi

if [[ "$HOST_ROLE" != "aws" && "$HOST_ROLE" != "mac" ]]; then
  echo "ERROR: --host must be aws or mac" >&2
  exit 1
fi

# Defaults per network + host
case "$NETWORK:$HOST_ROLE" in
  regtest:aws)
    AGENT_LND_CONTAINER=${AGENT_LND_CONTAINER:-agent-payment-decision-lnd}
    AGENT_LND_NETWORK=${AGENT_LND_NETWORK:-regtest_regtest}
    AGENT_LND_VOLUME=${AGENT_LND_VOLUME:-agent-bitcoin_lnd-data}
    USE_LOCAL_LOOP_SERVER=1
    ;;
  regtest:mac)
    AGENT_LND_CONTAINER=${AGENT_LND_CONTAINER:-agent-bitcoin-lnd}
    AGENT_LND_NETWORK=${AGENT_LND_NETWORK:-agent-bitcoin_default}
    AGENT_LND_VOLUME=${AGENT_LND_VOLUME:-agent-bitcoin_agent-bitcoin-lnd-data}
    USE_LOCAL_LOOP_SERVER=0
    echo "NOTE: regtest Loop server stack is usually AWS-only; Mac regtest loopd may not have terms." >&2
    ;;
  signet:aws)
    AGENT_LND_CONTAINER=${AGENT_LND_CONTAINER:-agent-payment-decision-lnd-signet}
    AGENT_LND_NETWORK=${AGENT_LND_NETWORK:-agent-bitcoin-signet}
    AGENT_LND_VOLUME=${AGENT_LND_VOLUME:-agent-bitcoin_lnd-signet-data}
    USE_LOCAL_LOOP_SERVER=0
    ;;
  signet:mac)
    AGENT_LND_CONTAINER=${AGENT_LND_CONTAINER:-agent-bitcoin-lnd-signet}
    AGENT_LND_NETWORK=${AGENT_LND_NETWORK:-agent-bitcoin_agent-signet-net}
    AGENT_LND_VOLUME=${AGENT_LND_VOLUME:-agent-bitcoin_agent-bitcoin-lnd-signet-data}
    USE_LOCAL_LOOP_SERVER=0
    ;;
  mainnet:aws)
    AGENT_LND_CONTAINER=${AGENT_LND_CONTAINER:-agent-payment-decision-lnd-mainnet}
    AGENT_LND_NETWORK=${AGENT_LND_NETWORK:-agent-bitcoin-mainnet}
    AGENT_LND_VOLUME=${AGENT_LND_VOLUME:-agent-bitcoin_lnd-mainnet-data}
    USE_LOCAL_LOOP_SERVER=0
    ;;
  mainnet:mac)
    AGENT_LND_CONTAINER=${AGENT_LND_CONTAINER:-agent-bitcoin-lnd-mainnet}
    AGENT_LND_NETWORK=${AGENT_LND_NETWORK:-agent-bitcoin_agent-mainnet-net}
    AGENT_LND_VOLUME=${AGENT_LND_VOLUME:-agent-bitcoin_agent-bitcoin-lnd-mainnet-data}
    USE_LOCAL_LOOP_SERVER=0
    ;;
esac

NETWORK_NAME=${NETWORK_NAME:-$NETWORK}
AGENT_LOOPD_NAME=${AGENT_LOOPD_NAME:-agent-loopd-${NETWORK}}
AGENT_LOOPD_VOLUME=${AGENT_LOOPD_VOLUME:-agent-loopd-${NETWORK}-data}
APERTURE_HOST=${APERTURE_HOST:-aperture:11018}
APERTURE_TLS_SRC=${APERTURE_TLS_SRC:-loopclient:/root/.loop/aperture-tls.cert}
LND_MACAROON=/lnd/data/chain/bitcoin/${NETWORK_NAME}/admin.macaroon
LND_TLS=/lnd/tls.cert
APERTURE_TLS_IN_CONTAINER=/root/.loop/aperture-tls.cert

echo "=== wire-loopd ==="
echo "network=$NETWORK host=$HOST_ROLE"
echo "LND=$AGENT_LND_CONTAINER  loopd=$AGENT_LOOPD_NAME  docker_net=$AGENT_LND_NETWORK"
echo "volume_lnd=$AGENT_LND_VOLUME  volume_loopd=$AGENT_LOOPD_VOLUME"
echo "local_loop_server=$USE_LOCAL_LOOP_SERVER"
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
  echo "--- agent LND identity ---"
  echo "${AGENT_LND_CONTAINER}: $(agent_pubkey || echo '<unavailable>')"
  echo ""
  if container_running "$AGENT_LOOPD_NAME"; then
    echo "--- loop getinfo ---"
    docker exec -i "$AGENT_LOOPD_NAME" loop --network="$NETWORK_NAME" getinfo 2>&1 | head -25 || true
    echo ""
    echo "--- loop terms (head) ---"
    docker exec -i "$AGENT_LOOPD_NAME" loop --network="$NETWORK_NAME" terms 2>&1 | head -30 || true
    echo ""
    echo "LOOP_CLI='docker exec -i $AGENT_LOOPD_NAME loop'"
    echo "Autoloop: leave DISABLED on mainnet (BIP-110 / pilot policy)."
  else
    echo "STATUS: $AGENT_LOOPD_NAME exists but is not running"
    docker logs --tail 40 "$AGENT_LOOPD_NAME" 2>&1 || true
    return 1
  fi
}

if [[ "$STATUS_ONLY" -eq 1 ]]; then
  show_status
  exit $?
fi

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
  echo "Hint: docker volume ls | grep -E 'lnd|mainnet|signet'" >&2
  exit 1
fi

if ! docker network inspect "$AGENT_LND_NETWORK" >/dev/null 2>&1; then
  echo "ERROR: docker network not found: $AGENT_LND_NETWORK" >&2
  echo "Hint: docker network ls" >&2
  # try to discover
  docker network ls
  exit 1
fi

if [[ "$USE_LOCAL_LOOP_SERVER" -eq 1 ]]; then
  for c in aperture loopserver; do
    if ! container_running "$c"; then
      echo "ERROR: $c is not running (regtest Loop stack). See docs/loop-autoloop.md." >&2
      exit 1
    fi
  done
fi

LOOPD_IMAGE=${LOOPD_IMAGE:-}
if [[ -z "$LOOPD_IMAGE" ]]; then
  if container_running loopclient; then
    LOOPD_IMAGE=$(docker inspect loopclient --format '{{.Config.Image}}')
  else
    # Public image used by Lightning Labs / common packages
    LOOPD_IMAGE=${LOOPD_IMAGE:-lightninglabs/loop:latest}
  fi
fi
echo "Using image: $LOOPD_IMAGE"

docker volume create "$AGENT_LOOPD_VOLUME" >/dev/null

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

# Build loopd args
LOOPD_ARGS=(
  loopd
  --experimental
  --network="$NETWORK_NAME"
  --debuglevel=info
  --lnd.host="${AGENT_LND_CONTAINER}:10009"
  --lnd.macaroonpath="$LND_MACAROON"
  --lnd.tlspath="$LND_TLS"
)

if [[ "$USE_LOCAL_LOOP_SERVER" -eq 1 ]]; then
  # Seed aperture TLS (regtest)
  tmp=$(mktemp)
  if [[ "$APERTURE_TLS_SRC" == *:* ]] && [[ "$APERTURE_TLS_SRC" != /* ]]; then
    docker cp "$APERTURE_TLS_SRC" "$tmp"
  else
    cp "$APERTURE_TLS_SRC" "$tmp"
  fi
  docker rm -f agent-loopd-seed >/dev/null 2>&1 || true
  docker run -d --name agent-loopd-seed --entrypoint sleep \
    -v "${AGENT_LOOPD_VOLUME}:/root/.loop" "$LOOPD_IMAGE" 60 >/dev/null
  docker exec agent-loopd-seed mkdir -p /root/.loop
  docker cp "$tmp" "agent-loopd-seed:${APERTURE_TLS_IN_CONTAINER}"
  docker rm -f agent-loopd-seed >/dev/null 2>&1 || true
  rm -f "$tmp"
  LOOPD_ARGS+=(
    --server.host="$APERTURE_HOST"
    --server.tlspath="$APERTURE_TLS_IN_CONTAINER"
  )
  echo "Regtest: using local aperture/loopserver"
else
  echo "Public Loop: default Lightning Labs servers for network=$NETWORK_NAME"
  echo "(No local loopserver; outbound HTTPS/gRPC from this host required.)"
fi

echo "Starting $AGENT_LOOPD_NAME..."
docker run -d \
  --name "$AGENT_LOOPD_NAME" \
  --restart unless-stopped \
  --network "$AGENT_LND_NETWORK" \
  -v "${AGENT_LND_VOLUME}:/lnd:ro" \
  -v "${AGENT_LOOPD_VOLUME}:/root/.loop" \
  "$LOOPD_IMAGE" \
  "${LOOPD_ARGS[@]}" \
  >/dev/null

echo "Waiting for loopd RPC..."
ok=0
for i in $(seq 1 45); do
  if docker exec -i "$AGENT_LOOPD_NAME" loop --network="$NETWORK_NAME" getinfo >/dev/null 2>&1; then
    ok=1
    break
  fi
  sleep 2
done

if [[ "$ok" -ne 1 ]]; then
  echo "ERROR: loop getinfo failed after start. Logs:" >&2
  docker logs --tail 50 "$AGENT_LOOPD_NAME" 2>&1 || true
  echo "" >&2
  echo "Hints:" >&2
  echo "  - LND tls.cert SAN must include container hostname ($AGENT_LND_CONTAINER)" >&2
  echo "  - Wallet unlocked; network=$NETWORK_NAME" >&2
  echo "  - docker network / volume names: docker network ls; docker volume ls" >&2
  if [[ "$NETWORK" == "signet" ]]; then
    echo "  - Public Loop may not support signet; regtest (local) or mainnet (public) are primary" >&2
  fi
  exit 1
fi

echo ""
echo "OK: $AGENT_LOOPD_NAME is up"
echo ""
show_status || true

echo ""
echo "Next:"
echo "  export LOOP_CLI='docker exec -i $AGENT_LOOPD_NAME loop'"
echo "  \$LOOP_CLI --network=$NETWORK_NAME getinfo"
echo "  \$LOOP_CLI --network=$NETWORK_NAME terms"
if [[ "$NETWORK" == "regtest" ]]; then
  echo "  ./configure-autoloop-regtest.sh --apply   # Autoloop params; enable only when ready"
elif [[ "$NETWORK" == "mainnet" ]]; then
  echo "  MAINNET: do NOT enable Autoloop; do NOT open channels until after BIP-110 window (block 961632+)."
  echo "  Install-only is OK. See docs/loop-multi-network.md and docs/mainnet-pilot.md"
fi
