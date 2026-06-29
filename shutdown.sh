#!/bin/bash
echo "=== Agent-Bitcoin Graceful Shutdown ==="

echo "Stopping backend API..."
pkill -f "uv run python backend/main.py" || true
pkill -f "python backend/main.py" || true

echo "Stopping Docker containers..."
docker compose down --timeout 30 || true
docker compose -f docker-compose.regtest.yml down --timeout 30 || true

echo "Waiting for services to stop..."
sleep 5

echo "✅ Shutdown complete. Instance is safe to terminate."
echo "You can now create an AMI or terminate the instance."
