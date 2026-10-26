#!/usr/bin/env bash
# bring-up-mainnet.sh — restore mainnet stack + unlock wallet so the dashboard can probe it
set -euo pipefail
cd "$(dirname "$0")"

echo "=== 1. Ensure mainnet containers are running ==="
./startup-mainnet-aws.sh 3.90.159.146 || true

echo "=== 2. Ensure L402 stack is running ==="
./startup-l402-aws.sh mainnet || true

echo "=== 3. Unlock LND wallet (interactive) ==="
docker exec -it agent-payment-decision-lnd-mainnet \
  lncli --lnddir=/home/lnd/.lnd --network=mainnet unlock

echo "=== 4. Wait for chain sync and show status ==="
sleep 5
docker exec agent-payment-decision-lnd-mainnet \
  lncli --lnddir=/home/lnd/.lnd --network=mainnet getinfo | \
  grep -E 'synced_to_chain|block_height|num_peers|num_active_channels'

echo "=== 5. Show channels ==="
docker exec agent-payment-decision-lnd-mainnet \
  lncli --lnddir=/home/lnd/.lnd --network=mainnet listchannels | \
  grep -E 'active|capacity|local_balance|remote_balance|remote_pubkey'

echo "=== 6. Restart Aperture so it reconnects to unlocked LND ==="
docker restart agent-l402-aperture
sleep 3
curl -sS -o /dev/null -w "Aperture health: %{http_code}\n" --max-time 5 http://127.0.0.1:8081/health

echo "Done. On the Mac, refresh the dashboard (or restart it)."
