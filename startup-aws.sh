#!/bin/bash
set -e

# =============================================
# Agent-Bitcoin AWS Startup Script (Regtest)
# This version does NOT perform aggressive blockchain reset
# =============================================

# Load .env if it exists
echo "→ Load .env if it exists..."
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
fi

# Get arguments
echo "→ Get arguments..."
NETWORK=${1:-regtest}
AWS_IP=${2}
export NETWORK
export AWS_IP

echo "→ Set number of bitcoin blocks to mine..."
BLOCKS=50
export BLOCKS

echo "=== Agent-Bitcoin Startup AWS (Network: $NETWORK, AWS IP: $AWS_IP) ==="

cd ~/agent-bitcoin

# === Stop existing services ===
echo "→ Stopping existing services..."
docker compose -f docker-compose.regtest.aws.yml down --remove-orphans

# === Start Loop regtest environment ===
echo "→ Starting Loop regtest environment (logs saved to /tmp/regtest.log)..."
cd ~/loop/regtest
./regtest.sh start > /tmp/regtest.log 2>&1
cd ~/agent-bitcoin

# === Bitcoin Core Wallet Management (FIXED ORDER + STRONGER CLEANUP) ===
echo "→ Setting up Bitcoin Core wallet 'miner'..."

# Strong cleanup
docker exec bitcoind bitcoin-cli -regtest unloadwallet "miner" 2>/dev/null || true
docker exec bitcoind rm -rf /home/bitcoin/.bitcoin/regtest/wallets/miner
docker exec bitcoind mkdir -p /home/bitcoin/.bitcoin/regtest/wallets

# Create fresh wallet
docker exec bitcoind bitcoin-cli -regtest createwallet "miner"

# Mine extra blocks for maturity (now safe because wallet exists)
echo "→ Mining extra blocks for maturity..."
docker exec bitcoind bitcoin-cli -regtest -rpcwallet=miner generatetoaddress 120 \
  $(docker exec bitcoind bitcoin-cli -regtest -rpcwallet=miner getnewaddress "")

echo "→ Current block height:"
docker exec bitcoind bitcoin-cli -regtest getblockcount

# Wait for Bitcoin RPC
echo "→ Waiting for Bitcoin RPC to become ready..."
for i in {1..25}; do
    if docker exec bitcoind bitcoin-cli -regtest getblockcount &>/dev/null; then
        echo "Bitcoin RPC is ready!"
        break
    fi
    echo "Waiting... ($i/25)"
    sleep 10
done

# Mine the main $BLOCKS blocks
echo "→ Mining Bitcoin $BLOCKS blocks..."
ADDR=$(docker exec bitcoind bitcoin-cli -regtest -rpcwallet=miner getnewaddress "")
docker exec bitcoind bitcoin-cli -regtest -rpcwallet=miner generatetoaddress $BLOCKS $ADDR

echo "→ Current Bitcoin height:"
docker exec bitcoind bitcoin-cli -regtest getblockcount

# === Start agent services ===
echo "→ Starting agent-payment-decision-lnd + all services..."
docker compose -f docker-compose.regtest.aws.yml up -d

# Wait for LND to start
echo "→ Waiting for agent-payment-decision-lnd to start..."
for i in {1..40}; do
    sleep 5
    if docker exec agent-payment-decision-lnd lncli --lnddir=/home/lnd/.lnd --network=regtest getinfo &>/dev/null 2>&1; then
        echo "LND is ready!"
        break
    fi
    echo "Waiting for agent-payment-decision-lnd... ($i/40)"
done

# === LND Wallet Handling (Improved) ===
echo "→ Checking agent-payment-decision-lnd wallet status..."

if docker exec agent-payment-decision-lnd test -f /home/lnd/.lnd/data/chain/bitcoin/regtest/wallet.db 2>/dev/null; then
    echo "→ Wallet exists. Please unlock it in another terminal:"
    echo "   docker exec -it agent-payment-decision-lnd lncli --lnddir=/home/lnd/.lnd --network=regtest unlock"
    echo ""
    echo "After unlocking successfully, press Enter here to continue..."
    read -r dummy          # <-- Changed from -s (silent) to normal read
else
    echo "→ No wallet found. Please create one in another terminal:"
    echo "   docker exec -it agent-payment-decision-lnd lncli --lnddir=/home/lnd/.lnd --network=regtest create"
    echo ""
    echo "After you see 'lnd successfully initialized!', press Enter here..."
    read -r dummy          # <-- Changed from -s (silent) to normal read
fi

# Final readiness check
echo "→ Waiting for agent-payment-decision-lnd to be fully ready..."
for i in {1..50}; do
    if docker exec agent-payment-decision-lnd lncli --lnddir=/home/lnd/.lnd --network=regtest getinfo &>/dev/null; then
        echo "✅ agent-payment-decision-lnd is fully ready!"
        break
    fi
    echo "Waiting... ($i/50)"
    sleep 5
done

# === Start Backend API in tmux ===
echo "→ Starting backend API in tmux..."
tmux kill-session -t backend 2>/dev/null || true
tmux new-session -d -s backend 'cd ~/agent-bitcoin && PYTHONPATH=. uv run python backend/main.py'

sleep 10

echo ""
echo "✅ Full startup complete!"
echo "   → Backend running at http://localhost:8000"
echo ""
echo "Useful commands:"
echo "   curl http://localhost:8000/balance"
echo "   tmux attach -t backend          # view logs"
echo "   docker exec -it bitcoind bitcoin-cli -regtest getblockcount"
echo "   ./shutdown-aws.sh               # stop everything"
echo ""
