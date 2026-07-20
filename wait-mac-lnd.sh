#!/bin/bash
echo "=== Waiting for Mac agent-bitcoin-lnd to be ready ==="

# Get arguments
NETWORK=${1}
export NETWORK

# === Check and unlock agent-bitcoin-lnd wallet if locked ===
echo "→ Checking agent-bitcoin-lnd wallet status..."
if docker compose -f docker-compose.regtest.mac.yml exec agent-bitcoin-lnd \
  lncli --lnddir=/home/lnd/.lnd --network=$NETWORK getinfo &>/dev/null; then
    echo "agent-bitcoin-lnd wallet is unlocked."
else
    echo "→ agent-bitcoin-lnd wallet is locked. Unlocking..."
    docker compose -f docker-compose.regtest.mac.yml exec -it agent-bitcoin-lnd \
      lncli --lnddir=/home/lnd/.lnd --network=$NETWORK unlock
fi

# === Wait for agent-bitcoin-lnd RPC to be available ===
for i in {1..50}; do
    echo "Waiting for agent-bitcoin-lnd RPC... ($i/50)"
    if docker compose -f docker-compose.regtest.mac.yml exec agent-bitcoin-lnd \
      lncli --lnddir=/home/lnd/.lnd --network=$NETWORK getinfo &>/dev/null; then
        echo "✅ agent-bitcoin-lnd RPC is ready!"
        break
    fi
    sleep 5
done

# === Wait for full agent-bitcoin-lnd chain + graph sync ===
# For testing, sync_to_chain is almost always true before sync_to_graph.
# Break out of loop as soon as sync_to_chain is true.
# May have to change this in production mode.
echo "→ Waiting for full agent-bitcoin-lnd chain + graph sync..."
for i in {1..50}; do
    echo "Sync check... ($i/50)"
    STATUS=$(docker compose -f docker-compose.regtest.mac.yml exec agent-bitcoin-lnd \
      lncli --lnddir=/home/lnd/.lnd --network=$NETWORK getinfo 2>/dev/null || echo "{}")

    if echo "$STATUS" | grep -q '"synced_to_chain": true' || \
       echo "$STATUS" | grep -q '"synced_to_graph": true'; then
        echo "✅ Full sync complete!"
        break
    fi

    # Show status every 50 iterations
    if (( i % 50 == 0 )); then
        echo "Current sync status:"
        echo "$STATUS" | grep -E "synced_to_chain|synced_to_graph|block_height"
    fi

    sleep 8
done

# Show final status
echo ""
echo "Final status:"
docker compose -f docker-compose.regtest.mac.yml exec agent-bitcoin-lnd \
  lncli --lnddir=/home/lnd/.lnd --network=$NETWORK getinfo | grep -E "block_height|synced_to_chain|synced_to_graph"

echo ""
echo "If sync_to_chain is still false, mine additional bitcoin blocks on AWS and run wait-mac-lnd.sh again."
echo "See README.md for more explanation."
