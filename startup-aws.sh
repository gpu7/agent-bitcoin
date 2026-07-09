#!/bin/bash
set -e

# Load .env if it exists
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
fi

echo "=== Agent-Bitcoin Startup AWS ==="

BLOCKS=${1:-50}

cd ~/agent-bitcoin

# === Clean Reset + Mine ===
echo "→ Stopping services..."
docker compose -f docker-compose.regtest.aws.yml down --remove-orphans

# Only clean Bitcoin data (LND volume is preserved for pre-warming / faster restarts)
echo "→ Removing bitcoin-data volume completely..."
docker volume rm agent-bitcoin_bitcoin-data -f 2>/dev/null || true

echo "→ Starting fresh bitcoind..."
docker compose -f docker-compose.regtest.aws.yml up -d --remove-orphans bitcoind

echo "→ Waiting for initial start Bitcoin container..."
sleep 40

echo "→ Aggressive clean of all bitcoin data..."
docker exec bitcoind rm -rf /home/bitcoin/.bitcoin/* 2>/dev/null || true

echo "→ Restarting bitcoind..."
docker compose -f docker-compose.regtest.aws.yml restart bitcoind

echo "→ Waiting for Bitcoin RPC to become ready..."
for i in {1..25}; do
    if docker exec bitcoind bitcoin-cli -regtest -rpcuser=btc -rpcpassword=btc getblockcount &>/dev/null; then
        echo "Bitcoin RPC is ready!"
        break
    fi
    echo "Waiting... ($i/25)"
    sleep 10
done

# Check Bitcoin height
echo "→ Check current Bitcoin height..."
docker exec bitcoind bitcoin-cli -regtest -rpcuser=btc -rpcpassword=btc getblockcount

# Create Bitcoin wallet if it doesn't exist
echo "→ Checking/creating Bitcoin Core wallet..."
docker exec bitcoind bitcoin-cli -regtest -rpcuser=btc -rpcpassword=btc createwallet "default" 2>/dev/null || true

# Load Bitcoin wallet
docker exec bitcoind bitcoin-cli -regtest -rpcuser=btc -rpcpassword=btc loadwallet "default" 2>/dev/null || true

# Mine Bitcoin
echo "→ Mining Bitcoin $BLOCKS blocks..."
ADDR=$(docker exec bitcoind bitcoin-cli -regtest -rpcuser=btc -rpcpassword=btc getnewaddress "")
docker exec bitcoind bitcoin-cli -regtest -rpcuser=btc -rpcpassword=btc generatetoaddress $BLOCKS $ADDR

# Check Bitcoin height
echo "→ Check final Bitcoin height..."
docker exec bitcoind bitcoin-cli -regtest -rpcuser=btc -rpcpassword=btc getblockcount

# === Start LND + Backend ===
echo "→ Starting agent-payment-decision-lnd + all services..."
docker compose -f docker-compose.regtest.aws.yml up -d

echo "→ Waiting for agent-payment-decision-lnd to start (RPC available)..."
for i in {1..40}; do
    sleep 5
    if docker logs --tail 10 agent-payment-decision-lnd 2>&1 | grep -q "Waiting for wallet encryption password\|wallet locked"; then
        break
    fi
    if docker exec agent-payment-decision-lnd lncli --lnddir=/home/lnd/.lnd --network=regtest getinfo &>/dev/null 2>&1; then
        echo "LND is already ready!"
        break
    fi
    echo "Waiting for agent-payment-decision-lnd to start... ($i/40)"
done

# Handle wallet: create or unlock
echo "→ Checking agent-payment-decision-lnd wallet status..."
if docker exec agent-payment-decision-lnd test -f /home/lnd/.lnd/data/chain/bitcoin/regtest/wallet.db 2>/dev/null; then
    echo "→ agent-payment-decision-lnd wallet exists. Unlocking interactively..."
    echo "   Run this in another terminal:"
    echo "   docker exec -it agent-payment-decision-lnd lncli --lnddir=/home/lnd/.lnd --network=regtest unlock"
    echo ""
    echo "After unlocking successfully, press Enter here..."
    read -r
else
    echo "→ No agent-payment-decision-lnd wallet found. Creating new wallet interactively..."
    echo "   Run this in another terminal:"
    echo "   docker exec -it agent-payment-decision-lnd lncli --lnddir=/home/lnd/.lnd --network=regtest create"
    echo ""
    echo "After you see 'lnd successfully initialized!', press Enter here..."
    read -r
fi

# Final readiness wait
echo "→ Waiting for agent-payment-decision-lnd to be fully ready..."
for i in {1..180}; do
    if docker exec agent-payment-decision-lnd lncli --lnddir=/home/lnd/.lnd --network=regtest getinfo &>/dev/null; then
        echo "agent-payment-decision-lnd is fully ready!"
        break
    fi
    echo "Waiting for agent-payment-decision-lnd ... ($i/180)"
    sleep 8
done

echo ""
echo "✅ Services started."
echo ""
echo "agent-payment-decision-lnd commands:"
echo "   Unlock agent-payment-decision-lnd wallet:"
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
