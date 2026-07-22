#!/bin/bash
#
# watch-lnd-sync.sh
#
# This script monitors the sync status between Bitcoin Core and LND in real time.
# It shows:
#   - Current block height of Bitcoin Core
#   - LND's reported block height and sync status
#   - How many blocks LND is behind (if not synced)
#   - Recent LND logs so you can see what it's doing during catch-up
#
# Run with: ./watch-lnd-sync.sh
# Stop with: Ctrl + C
#

echo "=== LND Sync Watcher ==="
echo "Press Ctrl+C to stop"
echo ""

while true; do
    clear
    echo "=== LND Sync Status (updated every 5s) ==="
    echo ""
    
    # Bitcoin Core height
    BTC_HEIGHT=$(docker exec bitcoind bitcoin-cli -regtest getblockcount 2>/dev/null || echo "N/A")
    echo "Bitcoin Core height: $BTC_HEIGHT"
    
    # LND status
    LND_INFO=$(docker exec agent-payment-decision-lnd lncli --lnddir=/home/lnd/.lnd --network=regtest getinfo 2>/dev/null)
    
    LND_HEIGHT=$(echo "$LND_INFO" | grep block_height | awk '{print $2}' | tr -d ',')
    SYNCED=$(echo "$LND_INFO" | grep synced_to_chain | awk '{print $2}' | tr -d ',')
    
    echo "LND height:          $LND_HEIGHT"
    echo "synced_to_chain:     $SYNCED"
    
    if [[ "$SYNCED" == "true" ]]; then
        echo "✅ LND is fully synced!"
    else
        DIFF=$((BTC_HEIGHT - LND_HEIGHT))
        echo "Blocks behind:       $DIFF"
    fi
    
    echo ""
    echo "=== Recent LND Logs ==="
    docker compose -f docker-compose.regtest.aws.yml logs --tail 25 agent-payment-decision-lnd 2>/dev/null | tail -20
    
    sleep 5
done
