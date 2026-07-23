#!/bin/bash
echo "=== Agent-Bitcoin Shutdown AWS ==="

echo "Stopping backend API..."
pkill -f "uv run python backend/main.py" || true
pkill -f "python backend/main.py" || true

echo "Stopping agent-payment-decision-lnd (agent-bitcoin compose)..."
docker compose -f docker-compose.regtest.aws.yml down --timeout 30 || true

# Stop Loop regtest (bitcoind + Loop nodes) WITHOUT deleting volumes.
# Do NOT use ./regtest.sh stop — it runs `docker compose down --volumes` and
# wipes regtest_bitcoind, which breaks LND wallet sync (Block height out of range).
echo "Stopping Loop regtest environment (preserving volumes / chain data)..."
cd ~/loop/regtest
docker compose -p regtest down || true
cd ~/agent-bitcoin

# Clean up default network if it exists
echo "Remove network..."
docker network rm agent-bitcoin_default 2>/dev/null || true

echo "Waiting for services to stop..."
sleep 5

echo "✅ Shutdown complete."
echo "   Volumes preserved: agent-bitcoin_lnd-data, regtest_bitcoind, etc."
echo "   You can create an AMI and then stop the instance."
echo "   For a FULL wipe (destroy chain + Loop data), run manually:"
echo "     cd ~/loop/regtest && docker compose -p regtest down --volumes"
