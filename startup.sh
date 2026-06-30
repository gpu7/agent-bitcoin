#!/bin/bash
set -e

echo "=== Agent-Bitcoin Startup (m5d) ==="

BLOCKS=${1:-300}

cd ~/agent-bitcoin

# === Clean Reset + Mine ===
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

echo "→ Creating wallet (if needed)..."
docker exec bitcoind bitcoin-cli -regtest -rpcuser=btc -rpcpassword=btc createwallet "default" 2>/dev/null || true

echo "→ Mining $BLOCKS blocks..."
ADDR=$(docker exec bitcoind bitcoin-cli -regtest -rpcuser=btc -rpcpassword=btc getnewaddress)
docker exec bitcoind bitcoin-cli -regtest -rpcuser=btc -rpcpassword=btc generatetoaddress $BLOCKS $ADDR

echo "→ Final height:"
docker exec bitcoind bitcoin-cli -regtest -rpcuser=btc -rpcpassword=btc getblockcount

# === Start LND + Backend ===
echo "→ Starting LND + all services..."
docker compose -f docker-compose.regtest.yml up -d

echo ""
echo "✅ Services started."
echo ""
echo "LND Commands:"
echo "   Create wallet (first time):"
echo "   docker exec -it agent-payment-decision-lnd lncli --lnddir=/home/lnd/.lnd create"
echo ""
echo "   Unlock wallet:"
echo "   docker exec -it agent-payment-decision-lnd lncli --lnddir=/home/lnd/.lnd unlock"
echo ""
echo "Test API:"
echo "   curl http://localhost:8000/balance"
echo ""

# Start backend API in tmux
echo "Starting backend API in tmux (backend)..."
tmux kill-session -t backend 2>/dev/null || true
tmux new-session -d -s backend 'cd ~/agent-bitcoin && PYTHONPATH=. uv run python backend/main.py'

sleep 15

echo "✅ Full startup complete!"
echo "   → Backend running at http://localhost:8000"
echo ""
echo "Useful commands:"
echo "   curl http://localhost:8000/balance"
echo "   tmux attach -t backend     # to see logs"
echo "   ./shutdown.sh              # clean stop"
