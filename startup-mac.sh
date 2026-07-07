#!/bin/bash
echo "=== Agent-Bitcoin Mac Counterparty Setup (for AWS Backend) ==="

NETWORK=${1:-regtest}
COMPOSE_FILE="docker-compose.regtest.mac.yml"

echo "=== Starting Mac Counterparty on $NETWORK ==="

docker compose -f $COMPOSE_FILE down --remove-orphans 2>/dev/null || true
docker compose -f $COMPOSE_FILE up -d

echo "→ Waiting for bitcoind..."
sleep 30

echo "→ Mining blocks to pre-warm LND..."
ADDR=$(docker exec bitcoind bitcoin-cli -regtest -rpcuser=rpcuser -rpcpassword=rpcpass getnewaddress)
docker exec bitcoind bitcoin-cli -regtest -rpcuser=rpcuser -rpcpassword=rpcpass generatetoaddress 300 $ADDR

echo "=== Creating/Unlocking Counterparty LND Wallet (Mac) ==="
sleep 10

if docker compose -f $COMPOSE_FILE exec -T agent-bitcoin-lnd test -f /home/lnd/.lnd/data/chain/bitcoin/regtest/wallet.db; then
    echo "Wallet exists. Unlocking..."
    docker compose -f $COMPOSE_FILE exec -it agent-bitcoin-lnd lncli --lnddir=/home/lnd/.lnd --network=${NETWORK} unlock
else
    echo "Creating new wallet..."
    docker compose -f $COMPOSE_FILE exec -it agent-bitcoin-lnd lncli --lnddir=/home/lnd/.lnd --network=${NETWORK} create
fi

echo ""
echo "=== Mac Counterparty Ready for AWS Backend ==="
echo ""
echo "Test with:"
echo "   uv run python tests/test_aws_integration.py --backend-url http://YOUR_AWS_IP:8000"
echo ""
echo "✅ Ready."
docker compose -f $COMPOSE_FILE ps