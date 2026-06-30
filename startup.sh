#!/bin/bash
set -e

echo "=== Agent-Bitcoin Startup (m5d) ==="

# Start services
echo "Starting services..."
docker compose -f docker-compose.regtest.yml up -d

sleep 5

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

sleep 8

echo "✅ Full startup complete!"
echo "   → Backend running at http://localhost:8000"
echo ""
echo "Useful commands:"
echo "   curl http://localhost:8000/balance"
echo "   tmux attach -t backend     # to see logs"
echo "   ./shutdown.sh              # clean stop"
echo "   ./reset-and-mine.sh        # clean regtest chain + mine blocks"
