#!/bin/bash
echo "=== Agent-Bitcoin Mac Counterparty Shutdown ==="

echo "Stopping Docker containers..."
docker compose -f docker-compose.regtest.mac.yml down --timeout 30 || true

echo "Waiting for services to stop..."
sleep 5

echo "✅ Mac shutdown complete."
