#!/bin/bash
echo "=== Agent-Bitcoin Mac Counterparty Setup (for AWS Backend) ==="

NETWORK=${1:-regtest}
AWS_IP=${2:-localhost}
COMPOSE_FILE="docker-compose.regtest.mac.yml"

echo "=== Starting Mac Counterparty on $NETWORK (AWS IP: $AWS_IP) ==="

export AWS_BITCOIND_HOST=$AWS_IP

docker compose -f $COMPOSE_FILE down --remove-orphans 2>/dev/null || true
docker compose -f $COMPOSE_FILE up -d agent-bitcoin-lnd

sleep 10

# Check if wallet exists
if docker compose -f $COMPOSE_FILE exec -T agent-bitcoin-lnd test -f /home/lnd/.lnd/data/chain/bitcoin/regtest/wallet.db; then
    echo "=== Wallet already exists. Unlocking... ==="
    docker compose -f $COMPOSE_FILE exec -it agent-bitcoin-lnd lncli --lnddir=/home/lnd/.lnd --network=${NETWORK} unlock
else
    echo "=== Creating new Counterparty LND Wallet (Mac) ==="
    docker compose -f $COMPOSE_FILE exec -it agent-bitcoin-lnd lncli --lnddir=/home/lnd/.lnd --network=${NETWORK} create
    echo "=== Unlocking new wallet ==="
    docker compose -f $COMPOSE_FILE exec -it agent-bitcoin-lnd lncli --lnddir=/home/lnd/.lnd --network=${NETWORK} unlock
fi

echo ""
echo "=== Mac Counterparty Ready for AWS Backend ==="
echo "AWS IP: $AWS_IP"
echo ""
echo "Test with:"
echo "   uv run python tests/test_aws_integration.py --backend-url http://$AWS_IP:8000"
echo ""
echo "✅ Ready."
docker compose -f $COMPOSE_FILE ps