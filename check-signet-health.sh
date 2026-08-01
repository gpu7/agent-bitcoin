#!/usr/bin/env bash
# check-signet-health.sh — signet dual-node health (Mac peer or AWS agent).
#
# Usage:
#   ./check-signet-health.sh              # auto-detect role from running containers
#   ./check-signet-health.sh --role mac
#   ./check-signet-health.sh --role aws
#   ./check-signet-health.sh --json
#
# Env overrides:
#   LND_CONTAINER  BITCOIND_CONTAINER  LND_NETWORK (default signet)
#   EXPECT_PEER_PUBKEY   if set, require a peer with this pubkey
#   CHANNEL_MIN_ACTIVE=1 (default)  fail if no active channel
#   CHANNEL_MIN_LOCAL_SATS / CHANNEL_MIN_REMOTE_SATS  (default 0 = no floor warn)
#   HEALTH_WEBHOOK_URL   optional POST JSON on failure
#   HEALTH_LOG           append one line summary (default: none)
#
# Exit: 0 healthy or warnings only; 1 unhealthy.
# Does not unlock wallets or print seeds/macaroons.

set -euo pipefail

JSON=0
ROLE=${SIGNET_ROLE:-auto}
while [[ $# -gt 0 ]]; do
  case "$1" in
    --json) JSON=1; shift ;;
    --role) ROLE=${2:-}; shift 2 ;;
    --role=*) ROLE=${1#--role=}; shift ;;
    mac|aws|auto) ROLE=$1; shift ;;
    -h|--help)
      sed -n '2,22p' "$0" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      exit 1
      ;;
  esac
done

LND_NETWORK=${LND_NETWORK:-signet}
LND_DIR=${LND_DIR:-/home/lnd/.lnd}
DISK_WARN_PCT=${DISK_WARN_PCT:-90}
CHANNEL_MIN_ACTIVE=${CHANNEL_MIN_ACTIVE:-1}
CHANNEL_MIN_LOCAL_SATS=${CHANNEL_MIN_LOCAL_SATS:-0}
CHANNEL_MIN_REMOTE_SATS=${CHANNEL_MIN_REMOTE_SATS:-0}
CHANNEL_LIQUIDITY_STRICT=${CHANNEL_LIQUIDITY_STRICT:-0}

detect_role() {
  if docker ps --format '{{.Names}}' 2>/dev/null | grep -qx 'agent-payment-decision-lnd-signet'; then
    if docker ps --format '{{.Names}}' 2>/dev/null | grep -qx 'agent-bitcoin-lnd-signet'; then
      echo "both"  # unusual same host
      return
    fi
    echo "aws"
    return
  fi
  if docker ps --format '{{.Names}}' 2>/dev/null | grep -qx 'agent-bitcoin-lnd-signet'; then
    echo "mac"
    return
  fi
  echo "unknown"
}

if [[ "$ROLE" == "auto" ]]; then
  ROLE=$(detect_role)
fi

case "$ROLE" in
  mac)
    LND_CONTAINER=${LND_CONTAINER:-agent-bitcoin-lnd-signet}
    BITCOIND_CONTAINER=${BITCOIND_CONTAINER:-agent-bitcoin-bitcoind-signet}
    REQUIRED_CONTAINERS=${REQUIRED_CONTAINERS:-"agent-bitcoin-lnd-signet agent-bitcoin-bitcoind-signet"}
    EXPECT_PEER_PUBKEY=${EXPECT_PEER_PUBKEY:-02102808588d8aece7e27af6eb5843810d04ffd88975136e3045e0ed4d45efebea}
    ROLE_LABEL="Mac peer"
    ;;
  aws)
    LND_CONTAINER=${LND_CONTAINER:-agent-payment-decision-lnd-signet}
    BITCOIND_CONTAINER=${BITCOIND_CONTAINER:-none}
    REQUIRED_CONTAINERS=${REQUIRED_CONTAINERS:-"agent-payment-decision-lnd-signet"}
    EXPECT_PEER_PUBKEY=${EXPECT_PEER_PUBKEY:-02f9302e39df4dd679ab127ecdf9ca7b179f359f2e6c90820603dafb50e2e502dc}
    ROLE_LABEL="AWS agent"
    ;;
  both)
    LND_CONTAINER=${LND_CONTAINER:-agent-payment-decision-lnd-signet}
    BITCOIND_CONTAINER=${BITCOIND_CONTAINER:-agent-bitcoin-bitcoind-signet}
    REQUIRED_CONTAINERS=${REQUIRED_CONTAINERS:-"agent-payment-decision-lnd-signet agent-bitcoin-lnd-signet"}
    EXPECT_PEER_PUBKEY=${EXPECT_PEER_PUBKEY:-}
    ROLE_LABEL="both-on-one-host"
    ;;
  *)
    echo "ERROR: could not detect signet role. Pass --role mac or --role aws" >&2
    echo "  (no agent-bitcoin-lnd-signet or agent-payment-decision-lnd-signet running?)" >&2
    exit 1
    ;;
esac

FAIL=0
WARN=0
declare -a MESSAGES=()
note() { MESSAGES+=("$1"); }
fail() { FAIL=1; note "FAIL: $1"; }
warn() { WARN=1; note "WARN: $1"; }
ok() { note "OK: $1"; }

# --- Disk ---
if command -v df >/dev/null 2>&1; then
  USE=$(df -P / | awk 'NR==2 {gsub(/%/,"",$5); print $5}')
  if [[ -n "${USE:-}" ]]; then
    if (( USE >= DISK_WARN_PCT )); then
      fail "disk root ${USE}% used (threshold ${DISK_WARN_PCT}%)"
    else
      ok "disk root ${USE}% used"
    fi
  fi
fi

# --- Docker ---
if ! docker info >/dev/null 2>&1; then
  fail "docker daemon not available"
else
  ok "docker daemon up"
fi

# --- Containers ---
for c in $REQUIRED_CONTAINERS; do
  if docker ps --format '{{.Names}}' 2>/dev/null | grep -qx "$c"; then
    ok "container $c running"
  else
    fail "container $c not running"
  fi
done

# --- bitcoind (Mac) ---
if [[ "$BITCOIND_CONTAINER" != "none" && "$BITCOIND_CONTAINER" != "-" ]]; then
  if docker ps --format '{{.Names}}' 2>/dev/null | grep -qx "$BITCOIND_CONTAINER"; then
    if H=$(docker exec "$BITCOIND_CONTAINER" bitcoin-cli -signet \
      -rpcuser=lightning -rpcpassword=lightning -rpcport=38332 getblockcount 2>/dev/null); then
      IBD=$(docker exec "$BITCOIND_CONTAINER" bitcoin-cli -signet \
        -rpcuser=lightning -rpcpassword=lightning -rpcport=38332 getblockchaininfo 2>/dev/null \
        | grep initialblockdownload | head -1 || true)
      if echo "$IBD" | grep -q 'true'; then
        warn "bitcoind still IBD height=$H"
      else
        ok "bitcoind height=$H"
      fi
    else
      fail "bitcoind RPC getblockcount failed"
    fi
  fi
fi

# --- LND ---
if docker ps --format '{{.Names}}' 2>/dev/null | grep -qx "$LND_CONTAINER"; then
  INFO=$(docker exec "$LND_CONTAINER" lncli --lnddir="$LND_DIR" --network="$LND_NETWORK" getinfo 2>&1 || true)
  if echo "$INFO" | grep -qi 'wallet locked'; then
    warn "LND wallet locked (unlock before operating)"
  elif echo "$INFO" | grep -q 'synced_to_chain'; then
    SYNC=$(echo "$INFO" | grep synced_to_chain | head -1 | tr -d ',"' | awk '{print $2}')
    HEIGHT=$(echo "$INFO" | grep block_height | head -1 | tr -d ',"' | awk '{print $2}')
    PUB=$(echo "$INFO" | grep identity_pubkey | head -1 | tr -d ',"' | awk '{print $2}')
    if [[ "$SYNC" == "true" ]]; then
      ok "LND synced height=$HEIGHT pub=${PUB:0:16}…"
    else
      warn "LND not synced_to_chain height=$HEIGHT"
    fi
  else
    fail "LND getinfo unexpected: $(echo "$INFO" | head -1 | cut -c1-100)"
  fi

  # Peers
  if echo "$INFO" | grep -qi 'wallet locked'; then
    note "SKIP: peers/channels (wallet locked)"
  else
    PEERS_JSON=$(docker exec "$LND_CONTAINER" lncli --lnddir="$LND_DIR" --network="$LND_NETWORK" listpeers 2>/dev/null || echo '{}')
    NUM_PEERS=$(echo "$PEERS_JSON" | python3 -c 'import json,sys
try:
  d=json.load(sys.stdin); print(len(d.get("peers") or []))
except Exception:
  print(0)' 2>/dev/null || echo 0)
    if [[ "${NUM_PEERS:-0}" -gt 0 ]]; then
      ok "peers count=$NUM_PEERS"
    else
      warn "no peers (Mac: connect to AWS; check SG 19735 + unlock AWS)"
    fi

    if [[ -n "${EXPECT_PEER_PUBKEY:-}" && "${NUM_PEERS:-0}" -gt 0 ]]; then
      if echo "$PEERS_JSON" | grep -q "$EXPECT_PEER_PUBKEY"; then
        ok "expected peer present ${EXPECT_PEER_PUBKEY:0:16}…"
      else
        warn "expected peer missing ${EXPECT_PEER_PUBKEY:0:16}… (reconnect dual-node)"
      fi
    fi

    # Channels
    CHANS_JSON=$(docker exec "$LND_CONTAINER" lncli --lnddir="$LND_DIR" --network="$LND_NETWORK" listchannels 2>/dev/null || echo '')
    if [[ -z "$CHANS_JSON" ]]; then
      warn "listchannels failed"
    else
      LIQ_REPORT=$(
        CHANNEL_MIN_LOCAL_SATS="$CHANNEL_MIN_LOCAL_SATS" \
        CHANNEL_MIN_REMOTE_SATS="$CHANNEL_MIN_REMOTE_SATS" \
        CHANNEL_LIQUIDITY_STRICT="$CHANNEL_LIQUIDITY_STRICT" \
        CHANNEL_MIN_ACTIVE="$CHANNEL_MIN_ACTIVE" \
        python3 -c '
import json, os, sys
raw = sys.stdin.read()
try:
    data = json.loads(raw)
except json.JSONDecodeError:
    print("ERROR|listchannels JSON parse failed")
    raise SystemExit(0)
chans = data.get("channels") or []
min_local = int(os.environ.get("CHANNEL_MIN_LOCAL_SATS", "0"))
min_remote = int(os.environ.get("CHANNEL_MIN_REMOTE_SATS", "0"))
strict = os.environ.get("CHANNEL_LIQUIDITY_STRICT", "0") == "1"
min_active = os.environ.get("CHANNEL_MIN_ACTIVE", "1") == "1"
active = [c for c in chans if c.get("active")]
level = "FAIL" if strict else "WARN"
if not chans:
    print("WARN|no channels")
elif min_active and not active:
    print(f"{level}|zero active channels (total={len(chans)}) — reconnect peer")
else:
    print(f"OK|channels total={len(chans)} active={len(active)}")
    for c in active:
        local = int(c.get("local_balance") or 0)
        remote = int(c.get("remote_balance") or 0)
        peer = (c.get("remote_pubkey") or "")[:16]
        if min_local and local < min_local:
            print(f"{level}|low outbound local={local} < {min_local} peer={peer}…")
        if min_remote and remote < min_remote:
            print(f"{level}|low inbound remote={remote} < {min_remote} peer={peer}…")
        print(f"OK|liquidity local={local} remote={remote} peer={peer}…")
' <<<"$CHANS_JSON"
      )
      while IFS= read -r line; do
        [[ -z "$line" ]] && continue
        kind=${line%%|*}
        msg=${line#*|}
        case "$kind" in
          OK) ok "channel $msg" ;;
          WARN) warn "channel $msg" ;;
          FAIL) fail "channel $msg" ;;
          ERROR) warn "channel $msg" ;;
          *) note "channel $line" ;;
        esac
      done <<<"$LIQ_REPORT"
    fi
  fi
else
  fail "LND container $LND_CONTAINER not running"
fi

# --- Report ---
RESULT="HEALTHY"
if [[ "$FAIL" -ne 0 ]]; then
  RESULT="UNHEALTHY"
elif [[ "$WARN" -ne 0 ]]; then
  RESULT="OK_WITH_WARNINGS"
fi

if [[ -n "${HEALTH_LOG:-}" ]]; then
  mkdir -p "$(dirname "$HEALTH_LOG")" 2>/dev/null || true
  echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) role=$ROLE result=$RESULT fail=$FAIL warn=$WARN" >>"$HEALTH_LOG"
fi

if [[ "$FAIL" -ne 0 && -n "${HEALTH_WEBHOOK_URL:-}" ]]; then
  curl -sS -X POST --max-time 10 \
    -H "Content-Type: application/json" \
    -d "{\"text\":\"signet health UNHEALTHY role=$ROLE host=$(hostname)\"}" \
    "$HEALTH_WEBHOOK_URL" >/dev/null 2>&1 || true
fi

if [[ "$JSON" -eq 1 ]]; then
  python3 - <<PY
import json
print(json.dumps({
  "ok": ${FAIL} == 0,
  "fail": $FAIL,
  "warn": $WARN,
  "role": "$ROLE",
  "result": "$RESULT",
  "messages": $(printf '%s\n' "${MESSAGES[@]}" | python3 -c 'import json,sys; print(json.dumps([l.strip() for l in sys.stdin if l.strip()]))'),
}, indent=2))
PY
else
  echo "=== Signet health ($ROLE_LABEL / role=$ROLE) ==="
  printf '%s\n' "${MESSAGES[@]}"
  echo ""
  echo "RESULT: $RESULT"
fi

if [[ "$FAIL" -ne 0 ]]; then
  echo ""
  echo "Hints:"
  echo "  - Wallet locked: docker exec -it $LND_CONTAINER lncli --lnddir=$LND_DIR --network=$LND_NETWORK unlock"
  if [[ "$ROLE" == "mac" ]]; then
    echo "  - SG / IP: ./update-aws-sg-my-ip.sh"
    echo "  - Connect: AWS_PUB=02102808… AWS_EIP=… connect \${AWS_PUB}@\${AWS_EIP}:19735"
  fi
  if [[ "$ROLE" == "aws" ]]; then
    echo "  - Wait for Mac connect; ensure SG allows Mac IP on TCP 19735"
  fi
  echo "  - Daily SOP: docs/daily-ops-signet.md"
  exit 1
fi
exit 0
