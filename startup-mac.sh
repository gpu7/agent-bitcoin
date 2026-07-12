#!/bin/bash
echo "=== Agent-Bitcoin Mac Counterparty Setup (for AWS Backend) ==="

# Get arguments
NETWORK=${1}
AWS_IP=${2}
export AWS_IP

echo "=== Agent-Bitcoin Startup Mac (Network: $NETWORK, AWS IP: $AWS_IP) ==="

COMPOSE_FILE="docker-compose.regtest.mac.yml"

docker compose -f $COMPOSE_FILE down --remove-orphans 2>/dev/null || true
docker compose -f $COMPOSE_FILE up -d agent-bitcoin-lnd

echo "=== Creating/Unlocking counterparty agent-bitcoin-lnd wallet (Mac) ==="
sleep 10

if docker compose -f $COMPOSE_FILE exec -T agent-bitcoin-lnd test -f /home/lnd/.lnd/data/chain/bitcoin/regtest/wallet.db; then
    echo "agent-bitcoin-lnd wallet exists. Unlocking..."
    docker compose -f $COMPOSE_FILE exec -it agent-bitcoin-lnd lncli --lnddir=/home/lnd/.lnd --network=${NETWORK} unlock
else
    echo "Creating new agent-bitcoin-lnd wallet..."
    docker compose -f $COMPOSE_FILE exec -it agent-bitcoin-lnd lncli --lnddir=/home/lnd/.lnd --network=${NETWORK} create
fi

echo ""
echo "=== Mac Counterparty Ready for AWS Backend ==="
echo ""
echo "Test with:"
echo "   uv run python tests/test_aws_integration.py --backend-url http://$AWS_IP:8000"
echo ""
echo "✅ Ready."
docker compose -f $COMPOSE_FILE ps