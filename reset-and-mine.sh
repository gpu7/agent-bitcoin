#!/bin/bash
set -e

echo "=== Regtest Clean Reset + Mine ==="

BLOCKS=${1:-300}

cd ~/agent-bitcoin

echo "→ Stopping services and removing volumes..."
docker compose -f docker-compose.regtest.yml down --remove-orphans -v

echo "→ Removing bitcoin-data volume completely..."
docker volume rm agent-bitcoin_bitcoin-data -f 2>/dev/null || true

echo "→ Starting fresh bitcoind..."
docker compose -f docker-compose.regtest.yml up -d --remove-orphans bitcoind

echo "→ Waiting for initial start..."
sleep 40

echo "→ Aggressive clean of all bitcoin data..."
docker exec bitcoind rm -rf /home/bitcoin/.bitcoin/* 2>/dev/null || true

echo "→ Restarting bitcoind..."
docker compose -f docker-compose.regtest.yml restart bitcoind

echo "→ Waiting for RPC to become ready..."
for i in {1..25}; do
    if docker exec bitcoind bitcoin-cli -regtest -rpcuser=btc -rpcpassword=btc getblockcount &>/dev/null; then
        echo "RPC is ready!"
        break
    fi
    echo "Waiting... ($i/25)"
    sleep 10
done

echo "→ Checking current height..."
docker exec bitcoind bitcoin-cli -regtest -rpcuser=btc -rpcpassword=btc getblockcount

echo "→ Mining $BLOCKS blocks..."
ADDR=$(docker exec bitcoind bitcoin-cli -regtest -rpcuser=btc -rpcpassword=btc getnewaddress)
docker exec bitcoind bitcoin-cli -regtest -rpcuser=btc -rpcpassword=btc generatetoaddress $BLOCKS $ADDR

echo "→ Final height:"
docker exec bitcoind bitcoin-cli -regtest -rpcuser=btc -rpcpassword=btc getblockcount

echo ""
echo "✅ Done! Clean chain + $BLOCKS blocks mined."
