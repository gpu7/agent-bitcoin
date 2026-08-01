#!/usr/bin/env bash
# export-lnd-backup.sh — export LND static channel backup (SCB) + optional volume snapshot.
#
# Usage (from repo root, host that has the LND container):
#   export LND_CONTAINER=agent-bitcoin-lnd-signet
#   export LND_NETWORK=signet
#   ./export-lnd-backup.sh
#
#   LND_CONTAINER=agent-payment-decision-lnd-signet LND_NETWORK=signet ./export-lnd-backup.sh
#
# Optional:
#   BACKUP_ROOT=~/lnd-backups     # default: ~/lnd-backups
#   SNAPSHOT_VOLUME=1            # also tar the docker volume (large)
#   LND_DIR=/home/lnd/.lnd
#
# Does NOT unlock the wallet or stop the node. Safe to run while LND is up.
# Never commit backup dirs to git. chmod 700 the output directory.

set -euo pipefail

LND_CONTAINER=${LND_CONTAINER:-}
LND_NETWORK=${LND_NETWORK:-signet}
LND_DIR=${LND_DIR:-/home/lnd/.lnd}
BACKUP_ROOT=${BACKUP_ROOT:-"$HOME/lnd-backups"}
SNAPSHOT_VOLUME=${SNAPSHOT_VOLUME:-0}

if [[ -z "$LND_CONTAINER" ]]; then
  echo "ERROR: set LND_CONTAINER (e.g. agent-bitcoin-lnd-signet or agent-payment-decision-lnd-signet)" >&2
  exit 1
fi

if ! docker inspect -f '{{.State.Running}}' "$LND_CONTAINER" 2>/dev/null | grep -qx true; then
  echo "ERROR: container not running: $LND_CONTAINER" >&2
  exit 1
fi

# chain path inside container: data/chain/bitcoin/<network>/
CHAIN_REL="data/chain/bitcoin/${LND_NETWORK}"
SCB_IN="${LND_DIR}/${CHAIN_REL}/channel.backup"
TS=$(date -u +%Y%m%dT%H%M%SZ)
OUT="${BACKUP_ROOT}/${LND_CONTAINER}/${LND_NETWORK}/${TS}"
mkdir -p "$OUT"
chmod 700 "$BACKUP_ROOT" 2>/dev/null || true
chmod 700 "$OUT"

echo "=== LND backup export ==="
echo "container: $LND_CONTAINER"
echo "network:   $LND_NETWORK"
echo "output:    $OUT"
echo ""

# Static channel backup (SCB)
if docker exec "$LND_CONTAINER" test -f "$SCB_IN"; then
  docker cp "${LND_CONTAINER}:${SCB_IN}" "$OUT/channel.backup"
  echo "✅ channel.backup"
else
  echo "⚠️  No channel.backup at $SCB_IN (no channels yet, or path differs)"
fi

# Also ask lncli for multi-backup if wallet unlocked (best-effort)
if docker exec "$LND_CONTAINER" lncli --lnddir="$LND_DIR" --network="$LND_NETWORK" getinfo &>/dev/null; then
  if docker exec "$LND_CONTAINER" lncli --lnddir="$LND_DIR" --network="$LND_NETWORK" \
    exportchanbackup --all --output_file=/tmp/channel-all.backup 2>/dev/null; then
    docker cp "${LND_CONTAINER}:/tmp/channel-all.backup" "$OUT/channel-all.backup" 2>/dev/null || true
    docker exec "$LND_CONTAINER" rm -f /tmp/channel-all.backup 2>/dev/null || true
    if [[ -f "$OUT/channel-all.backup" ]]; then
      echo "✅ channel-all.backup (lncli exportchanbackup --all)"
    fi
  fi
else
  echo "ℹ️  Wallet locked or RPC unavailable — skipped lncli exportchanbackup (file SCB still copied if present)"
fi

# TLS cert only (not secret seed; macaroon optional — treat as secret if copied)
docker cp "${LND_CONTAINER}:${LND_DIR}/tls.cert" "$OUT/tls.cert" 2>/dev/null && echo "✅ tls.cert" || true

# Manifest (no secrets)
{
  echo "timestamp_utc=$TS"
  echo "container=$LND_CONTAINER"
  echo "network=$LND_NETWORK"
  echo "lnd_dir=$LND_DIR"
  echo "host=$(hostname 2>/dev/null || echo unknown)"
  if docker exec "$LND_CONTAINER" lncli --lnddir="$LND_DIR" --network="$LND_NETWORK" getinfo &>/dev/null; then
    docker exec "$LND_CONTAINER" lncli --lnddir="$LND_DIR" --network="$LND_NETWORK" getinfo \
      | grep -E 'identity_pubkey|block_height|synced_to_chain' || true
  fi
  echo "files:"
  ls -la "$OUT" | sed 's/^/  /'
} >"$OUT/MANIFEST.txt"
echo "✅ MANIFEST.txt"

# Optional full volume tarball
if [[ "$SNAPSHOT_VOLUME" == "1" ]]; then
  VOL=$(docker inspect -f '{{range .Mounts}}{{if eq .Destination "/home/lnd/.lnd"}}{{.Name}}{{end}}{{end}}' "$LND_CONTAINER" 2>/dev/null || true)
  if [[ -z "$VOL" ]]; then
    VOL=$(docker inspect -f '{{range .Mounts}}{{.Name}} {{.Destination}}{{"\n"}}{{end}}' "$LND_CONTAINER" | awk '/\.lnd/{print $1; exit}')
  fi
  if [[ -n "$VOL" ]]; then
    echo "→ Snapshotting volume $VOL (this may take a while)..."
    docker run --rm \
      -v "${VOL}:/lnddata:ro" \
      -v "$OUT:/backup" \
      alpine:3.20 \
      tar czf "/backup/lnd-volume.tgz" -C /lnddata .
    echo "✅ lnd-volume.tgz"
  else
    echo "⚠️  Could not resolve docker volume for ${LND_DIR}; skip SNAPSHOT_VOLUME"
  fi
fi

chmod -R go-rwx "$OUT" 2>/dev/null || true
echo ""
echo "Done. Keep $OUT offline/encrypted. See docs/lnd-backup-restore.md"
echo "Verify: ./verify-lnd-backup.sh $OUT"
