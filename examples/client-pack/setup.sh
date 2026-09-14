#!/usr/bin/env bash
# Client pack: local Neutrino LND, hello JSON (IP + pubkey only), connect to AWS.
# Wallet seed stays on this machine. Do not send it to AWS. Do not open 8081 yourself.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
COMPOSE="$HERE/docker-compose.yml"
CONTAINER=l402-client-lnd
AWS_PEER="0290ec8b1733192e5dcbc5d32f8fec5ae345ff777fc48dafed757c2d14781d4967@3.90.159.146:9735"
HELLO="$HERE/client-hello.json"
OPEN_SATS=""

usage() {
  cat <<'EOF'
setup.sh — start client LND (Neutrino mainnet), write client-hello.json, connect to AWS.

Usage:
  ./setup.sh
  ./setup.sh --open-channel 20000
  ./setup.sh --help

Env:
  WALLET_PASSWORD_FILE  optional local file (gitignored) for lncli unlock
  MY_IP                 skip auto-detect of egress IPv4

Does not: change AWS security groups, copy seeds, or pay L402 (see smoke-l402.sh).
Send only client-hello.json (egress_ip + identity_pubkey) to the operator.
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    -h|--help) usage; exit 0 ;;
    --open-channel)
      shift
      OPEN_SATS="${1:-}"
      if [ -z "$OPEN_SATS" ]; then
        echo "--open-channel needs a satoshi amount" >&2
        exit 1
      fi
      shift
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

lncli_cmd() {
  docker exec "$CONTAINER" lncli --lnddir=/home/lnd/.lnd --network=mainnet "$@"
}

detect_ip() {
  local ip
  ip=$(curl -4 -sS --max-time 10 https://checkip.amazonaws.com | tr -d '[:space:]' || true)
  if ! printf '%s' "$ip" | grep -Eq '^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$'; then
    ip=$(curl -4 -sS --max-time 10 https://ifconfig.me | tr -d '[:space:]' || true)
  fi
  if ! printf '%s' "$ip" | grep -Eq '^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$'; then
    echo "Could not detect public IPv4. Set MY_IP=x.x.x.x" >&2
    exit 1
  fi
  printf '%s\n' "$ip"
}

if ! command -v docker >/dev/null 2>&1; then
  echo "Need docker." >&2
  exit 1
fi

echo "=== compose up ($COMPOSE) ==="
mkdir -p "$HERE/data/lnd"
docker compose -f "$COMPOSE" up -d

WALLET_DB=/home/lnd/.lnd/data/chain/bitcoin/mainnet/wallet.db
echo "Waiting for LND…"
i=0
while [ "$i" -lt 60 ]; do
  if docker exec "$CONTAINER" test -f "$WALLET_DB" 2>/dev/null; then
    break
  fi
  if lncli_cmd getinfo >/dev/null 2>&1; then
    break
  fi
  i=$((i + 1))
  sleep 2
done

if ! docker exec "$CONTAINER" test -f "$WALLET_DB" 2>/dev/null; then
  cat <<EOF
No wallet.db yet. Create it on THIS machine (seed stays here):

  docker exec -it $CONTAINER lncli --lnddir=/home/lnd/.lnd --network=mainnet create

Do not paste the seed into chat, git, or AWS. Then re-run ./setup.sh
EOF
  exit 2
fi

if ! lncli_cmd getinfo >/dev/null 2>&1; then
  PW_FILE="${WALLET_PASSWORD_FILE:-$HERE/.wallet-password}"
  if [ -f "$PW_FILE" ]; then
    echo "Unlocking with WALLET_PASSWORD_FILE…"
    docker exec -i "$CONTAINER" lncli --lnddir=/home/lnd/.lnd --network=mainnet unlock <"$PW_FILE" || true
  fi
  if ! lncli_cmd getinfo >/dev/null 2>&1; then
    echo "Wallet locked. Unlock:" >&2
    echo "  docker exec -it $CONTAINER lncli --lnddir=/home/lnd/.lnd --network=mainnet unlock" >&2
    exit 3
  fi
fi

PUB=$(lncli_cmd getinfo | python3 -c "import json,sys; print(json.load(sys.stdin)['identity_pubkey'])")
IP="${MY_IP:-$(detect_ip)}"
python3 - "$HELLO" "$IP" "$PUB" <<'PY'
import json, sys
path, ip, pub = sys.argv[1], sys.argv[2], sys.argv[3]
doc = {
    "egress_ip": ip,
    "identity_pubkey": pub,
    "l402_host": "http://3.90.159.146:8081",
}
open(path, "w", encoding="utf-8").write(json.dumps(doc, indent=2) + "\n")
print("Wrote", path)
PY

echo "Connecting to AWS LND (outbound)…"
lncli_cmd connect "$AWS_PEER" || echo "connect: already connected or AWS 9735 not yet allowlisted for $IP/32"

if [ -n "$OPEN_SATS" ]; then
  BAL=$(lncli_cmd walletbalance | python3 -c "import json,sys; print(json.load(sys.stdin).get('confirmed_balance','0'))")
  echo "Confirmed on-chain sats: $BAL (need $OPEN_SATS + fees for --open-channel)"
  if [ "${BAL:-0}" -ge "$OPEN_SATS" ] 2>/dev/null; then
    DEST="${AWS_PEER%%@*}"
    echo "Opening PRIVATE channel $OPEN_SATS sats to $DEST"
    lncli_cmd openchannel --private --node_key="$DEST" --local_amt="$OPEN_SATS"
  else
    ADDR=$(lncli_cmd newaddress p2wkh | python3 -c "import json,sys; print(json.load(sys.stdin)['address'])")
    echo "Fund this address on-chain, wait for confirm, re-run with --open-channel $OPEN_SATS"
    echo "address: $ADDR"
    exit 4
  fi
fi

echo "Send $HELLO to the operator (IP + pubkey only). They add $IP/32 on 8081 and 9735."
echo "Repo root for smoke: $ROOT"
echo "Then: ./smoke-l402.sh"
