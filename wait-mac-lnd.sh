#!/bin/bash
echo "=== Waiting for Mac LND to be ready ==="

# === Check and unlock wallet if locked ===
echo "→ Checking wallet status..."
if docker compose -f docker-compose.regtest.mac.yml exec agent-bitcoin-lnd \
  lncli --lnddir=/home/lnd/.lnd --network=regtest getinfo &>/dev/null; then
    echo "Wallet is unlocked."
else
    echo "→ Wallet is locked. Unlocking..."
    docker compose -f docker-compose.regtest.mac.yml exec -it agent-bitcoin-lnd \
      lncli --lnddir=/home/lnd/.lnd --network=regtest unlock
fi

# === Wait for full readiness ===
for i in {1..90}; do
    echo "Waiting... ($i/90)"
    if docker compose -f docker-compose.regtest.mac.yml exec agent-bitcoin-lnd \
      lncli --lnddir=/home/lnd/.lnd --network=regtest getinfo &>/dev/null; then
        echo "✅ LND is ready!"
        break
    fi
    sleep 5
done

# Show final status
echo ""
echo "Final status:"
docker compose -f docker-compose.regtest.mac.yml exec agent-bitcoin-lnd \
  lncli --lnddir=/home/lnd/.lnd --network=regtest getinfo | grep -E "block_height|synced_to_chain|synced_to_graph"