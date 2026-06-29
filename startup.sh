#!/bin/bash
echo "=== Agent-Bitcoin Startup Script ==="

cd ~/agent-bitcoin

echo "Starting Docker services..."
docker compose -f docker-compose.regtest.yml up -d

echo "Waiting for services to be ready..."
sleep 25

echo "✅ Docker services started."
echo "Now unlock LND manually:"
echo "   docker exec -it agent-payment-decision-lnd lncli --lnddir=/home/lnd/.lnd unlock"
echo ""
echo "After unlocking, run:"
echo "   sleep 15 && curl http://localhost:8000/balance"
echo ""
echo "Backend starting in tmux..."
tmux kill-session -t backend 2>/dev/null || true
tmux new-session -d -s backend "cd ~/agent-bitcoin && PYTHONPATH=. uv run python backend/main.py"

echo "✅ Startup complete!"
echo "   Public URL: http://$(curl -s ifconfig.me):8000"
echo "   tmux attach -t backend"
