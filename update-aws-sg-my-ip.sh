#!/usr/bin/env bash
# update-aws-sg-my-ip.sh
#
# Detect this machine's public IPv4 and ADD that /32 on admin/Mac ports.
# Additive: does not wipe client-pack /32s. Revokes only older rules whose
# Description is Mac/admin and whose CIDR is not the current IP (ISP change).
# Never 0.0.0.0/0. Never 10009.
#
# Usage (typically on your Mac when home IP changes):
#   ./update-aws-sg-my-ip.sh
#   ./update-aws-sg-my-ip.sh --dry-run
#   MY_IP=1.2.3.4 ./update-aws-sg-my-ip.sh
#   ./update-aws-sg-my-ip.sh --keep-world-p2p
#
# Env:
#   AWS_REGION  default: us-east-1
#   SG_ID       default: sg-04e9e86b18199e18f
#   PORTS       default: 22 8000 8081 18443 18444 28332 28333 9735 19735
#               (9735 = regtest LND P2P, 19735 = signet LND P2P on AWS,
#                8081 = Aperture L402 HTTP gateway)
#   MY_IP       default: auto-detect via checkip.amazonaws.com
#
# Run this first on the Mac each day (or after ISP IP change) before
# Mac→AWS connect / openchannel. Home IPv4 often changes overnight.
# Do not pass MY_IP=<client>; admit clients with Description "client pack".
#
# Requires: aws CLI, credentials with ec2:Authorize/Revoke/Describe on the SG, python3, curl

set -euo pipefail

DRY_RUN=0
KEEP_WORLD_P2P=0
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=1 ;;
    --keep-world-p2p) KEEP_WORLD_P2P=1 ;;
    -h|--help)
      sed -n '2,27p' "$0" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *)
      echo "Unknown option: $arg" >&2
      exit 1
      ;;
  esac
done

AWS_REGION=${AWS_REGION:-us-east-1}
SG_ID=${SG_ID:-sg-04e9e86b18199e18f}
# Include 18444 so leftover world-open bitcoind P2P/RPC rules get removed.
# 19735 = AWS signet LND host port (docker-compose.signet.aws.yml).
PORTS_STR=${PORTS:-"22 8000 8081 18443 18444 28332 28333 9735 19735"}
if [[ " $PORTS_STR " == *" 10009 "* ]]; then
  echo "Refuse PORTS containing 10009 (LND gRPC stays closed)." >&2
  exit 1
fi
ROOT="$(cd "$(dirname "$0")" && pwd)"

# Prevent aws CLI from opening `less` and stopping on (END)
export AWS_PAGER=""
export AWS_CLI_AUTO_PROMPT=off

for cmd in aws python3 curl; do
  command -v "$cmd" >/dev/null 2>&1 || {
    echo "Missing required command: $cmd" >&2
    exit 1
  }
done

detect_ip() {
  local ip
  ip=$(curl -4 -sS --max-time 10 https://checkip.amazonaws.com | tr -d '[:space:]' || true)
  if [[ ! "$ip" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    ip=$(curl -4 -sS --max-time 10 https://ifconfig.me | tr -d '[:space:]' || true)
  fi
  if [[ ! "$ip" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    echo "Could not detect public IPv4. Set MY_IP=x.x.x.x" >&2
    exit 1
  fi
  printf '%s\n' "$ip"
}

MY_IP=${MY_IP:-$(detect_ip)}
MY_CIDR="${MY_IP}/32"

echo "=== update-aws-sg-my-ip ==="
echo "Region:  $AWS_REGION"
echo "SG:      $SG_ID"
echo "New IP:  $MY_CIDR"
echo "Ports:   $PORTS_STR"
echo "Dry-run: $DRY_RUN"
echo ""

WORKDIR=$(mktemp -d)
trap 'rm -rf "$WORKDIR"' EXIT
SG_JSON="$WORKDIR/sg.json"
PLAN_JSON="$WORKDIR/plan.json"

aws ec2 describe-security-groups \
  --region "$AWS_REGION" \
  --group-ids "$SG_ID" \
  --output json >"$SG_JSON"

KEEP_WORLD_P2P="$KEEP_WORLD_P2P" MY_CIDR="$MY_CIDR" PORTS_STR="$PORTS_STR" \
  PYTHONPATH="$ROOT" python3 - "$SG_JSON" "$PLAN_JSON" <<'PY'
import json, os, sys
from scripts.sg_ingress_plan import plan

sg_path, plan_path = sys.argv[1], sys.argv[2]
ports = {int(p) for p in os.environ["PORTS_STR"].split()}
doc = json.load(open(sg_path))
out = plan(
    doc,
    ports=ports,
    my_cidr=os.environ["MY_CIDR"],
    keep_world_p2p=os.environ.get("KEEP_WORLD_P2P", "0") == "1",
)
json.dump(out, open(plan_path, "w"), indent=2)
PY

python3 - "$PLAN_JSON" "$MY_CIDR" <<'PY'
import json, sys
plan = json.load(open(sys.argv[1]))
my = sys.argv[2]
print("Plan (additive; keeps client pack /32s):")
if not plan["add"] and not plan["revoke"]:
    print("  No changes needed.")
else:
    for p in plan["add"]:
        print(f"  + authorize tcp/{p} from {my}  (agent-bitcoin admin/Mac)")
    for r in plan["revoke"]:
        print(f"  - revoke   tcp/{r['port']} from {r['cidr']}  ({r.get('description','')})")
print("Remaining 8081/9735 after this plan:")
for port in ("8081", "9735"):
    rows = plan.get("remaining", {}).get(port) or []
    if not rows:
        print(f"  tcp/{port}: (none tracked)")
        continue
    for r in rows:
        print(f"  tcp/{port} {r['cidr']}  {r.get('description','')}")
PY

if [[ "$DRY_RUN" -eq 1 ]]; then
  echo ""
  echo "Dry-run only. Re-run without --dry-run to apply."
  exit 0
fi

desc_for_port() {
  case "$1" in
    22) echo "SSH admin" ;;
    8000) echo "Agent Bitcoin API" ;;
    18443) echo "bitcoind RPC Mac" ;;
    28332) echo "ZMQ blocks Mac" ;;
    28333) echo "ZMQ txs Mac" ;;
    9735) echo "LND P2P regtest Mac" ;;
    19735) echo "LND P2P signet Mac" ;;
    *) echo "agent-bitcoin admin/Mac" ;;
  esac
}

# 1) Authorize new IP first
while IFS= read -r port; do
  [[ -z "$port" ]] && continue
  echo "Authorizing tcp/$port $MY_CIDR ..."
  DESC=$(desc_for_port "$port")
  if ! aws ec2 authorize-security-group-ingress \
    --region "$AWS_REGION" \
    --group-id "$SG_ID" \
    --ip-permissions "[{\"IpProtocol\":\"tcp\",\"FromPort\":${port},\"ToPort\":${port},\"IpRanges\":[{\"CidrIp\":\"${MY_CIDR}\",\"Description\":\"${DESC}\"}]}]"; then
    echo "  (authorize failed or already exists — continuing)"
  fi
done < <(python3 -c "import json;print('\n'.join(str(p) for p in json.load(open('$PLAN_JSON'))['add']))")

# 2) Revoke old CIDRs
while IFS= read -r line; do
  [[ -z "$line" ]] && continue
  port=${line%% *}
  cidr=${line#* }
  echo "Revoking tcp/$port $cidr ..."
  if ! aws ec2 revoke-security-group-ingress \
    --region "$AWS_REGION" \
    --group-id "$SG_ID" \
    --protocol tcp \
    --port "$port" \
    --cidr "$cidr"; then
    echo "  (revoke failed — check manually)"
  fi
done < <(python3 -c "import json;print('\n'.join(f\"{r['port']} {r['cidr']}\" for r in json.load(open('$PLAN_JSON'))['revoke']))")

STATE_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/agent-bitcoin"
mkdir -p "$STATE_DIR"
echo "$MY_IP" >"$STATE_DIR/last-sg-ip"

echo ""
echo "Done. Recorded IP in $STATE_DIR/last-sg-ip"
echo ""
echo "Remaining 8081 / 9735:"
aws ec2 describe-security-groups --region "$AWS_REGION" --group-ids "$SG_ID" \
  --query 'SecurityGroups[0].IpPermissions[?FromPort==`8081` || FromPort==`9735`].{Port:FromPort,Ranges:IpRanges[].{Cidr:CidrIp,Desc:Description}}' \
  --output table
