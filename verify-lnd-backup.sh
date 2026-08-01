#!/usr/bin/env bash
# verify-lnd-backup.sh — check a directory from export-lnd-backup.sh looks usable.
#
# Usage:
#   ./verify-lnd-backup.sh ~/lnd-backups/agent-bitcoin-lnd-signet/signet/20260801T120000Z

set -euo pipefail

DIR=${1:-}
if [[ -z "$DIR" || ! -d "$DIR" ]]; then
  echo "Usage: $0 <backup-dir>" >&2
  exit 1
fi

echo "=== Verify backup: $DIR ==="
ok=1

check_file() {
  local f=$1
  local label=$2
  local required=${3:-0}
  if [[ -f "$DIR/$f" && -s "$DIR/$f" ]]; then
    echo "✅ $label ($f) $(wc -c <"$DIR/$f" | tr -d ' ') bytes"
  else
    if [[ "$required" == "1" ]]; then
      echo "❌ missing/empty required: $f"
      ok=0
    else
      echo "⚠️  optional missing: $f"
    fi
  fi
}

check_file MANIFEST.txt "manifest" 1
# SCB: either auto path or lncli export
if [[ -f "$DIR/channel.backup" && -s "$DIR/channel.backup" ]] || \
   [[ -f "$DIR/channel-all.backup" && -s "$DIR/channel-all.backup" ]]; then
  echo "✅ static channel backup present"
else
  echo "❌ no channel.backup or channel-all.backup (cannot SCB-recover channels)"
  ok=0
fi

check_file tls.cert "tls cert" 0
check_file lnd-volume.tgz "full volume snapshot" 0

if [[ -f "$DIR/MANIFEST.txt" ]]; then
  echo "--- MANIFEST ---"
  cat "$DIR/MANIFEST.txt"
fi

echo ""
if [[ "$ok" -eq 1 ]]; then
  echo "PASS: backup directory looks usable for SCB (and volume restore if tgz present)."
  exit 0
else
  echo "FAIL: fix missing pieces before relying on this backup."
  exit 1
fi
