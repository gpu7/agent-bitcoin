#!/bin/bash
echo "=== Agent-Bitcoin Startup Script ==="

cd ~/agent-bitcoin

echo "Starting Docker services (regtest)..."
docker compose -f docker-compose.regtest.yml up -d

echo "Waiting for services to be ready..."
sleep 10

echo "Starting Backend API in tmux session..."
tmux new-session -d -s backend "cd ~/agent-bitcoin && PYTHONPATH=. uv run python backend/main.py"

echo ""
echo "✅ Startup complete!"
echo "   - Backend API: http://$(curl -s ifconfig.me):8000"
echo "   - tmux session: 'tmux attach -t backend'"
echo "   - Stop everything: ./shutdown.sh"
