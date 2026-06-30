#!/bin/bash
set -e

echo "=== Regtest Clean Reset + Mine ==="

BLOCKS=${1:-300}   # Default = 300 blocks. Change by running: ./reset-and-mine.sh 500

cd ~/agent-bitcoin

echo "→ Stopping services and removing volumes..."
docker compose -f docker-compose.regtest.yml down -v

echo "→ Starting fresh bitcoind..."
docker compose -f docker-compose.regtest.yml up -d bitcoind

echo "→ Waiting for bitcoind to initialize..."
sleep 25

echo "→ Forcing clean regtest chain..."
docker exec bitcoind rm -rf /home/bitcoin/.bitcoin/regtest || true

echo "→ Restarting bitcoind..."
docker compose -f docker-compose.regtest.yml restart bitcoind

echo "→ Waiting after restart..."
sleep 40

echo "→ Checking current height..."
HEIGHT=$(docker exec bitcoind bitcoin-cli -regtest -rpcuser=btc -rpcpassword=btc getblockcount 2>/dev/null || echo "0")
echo "Current height: $HEIGHT"

echo "→ Mining $BLOCKS blocks..."
ADDR=$(docker exec bitcoind bitcoin-cli -regtest -rpcuser=btc -rpcpassword=btc getnewaddress)
docker exec bitcoind bitcoin-cli -regtest -rpcuser=btc -rpcpassword=btc generatetoaddress $BLOCKS $ADDR

echo "→ New height:"
docker exec bitcoind bitcoin-cli -regtest -rpcuser=btc -rpcpassword=btc getblockcount

echo ""
echo "✅ Done! Chain is clean and mined."
echo "You can now unlock LND and start the backend."
