#!/bin/bash
echo "=== Agent-Bitcoin Shutdown AWS ==="

echo "Stopping backend API..."
pkill -f "uv run python backend/main.py" || true
pkill -f "python backend/main.py" || true

echo "Stopping Docker containers..."
docker compose -f docker-compose.regtest.aws.yml down --timeout 30 || true

# Stop Loop regtest environment
echo "Stopping Loop regtest environment..."
cd ~/loop/regtest
./regtest.sh stop || true
cd ~/agent-bitcoin

# Clean up default network if it exists
echo "Remove network..."
docker network rm agent-bitcoin_default 2>/dev/null || true

echo "Waiting for services to stop..."
sleep 5

echo "✅ Shutdown complete."
echo "You can now create an AMI and then stop or terminate the instance."
