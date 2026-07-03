#!/bin/bash
echo "=== Agent-Bitcoin Mac Counterparty Setup (for AWS Backend) ==="

NETWORK=${1:-regtest}
echo "=== Starting Mac Counterparty on $NETWORK ==="

# Clean local containers
docker compose down -v --remove-orphans 2>/dev/null || true

# Start only bitcoind + counterparty LND on Mac
docker compose up -d bitcoind agent-bitcoin-lnd

echo "Waiting for bitcoind to be healthy..."
until docker compose ps --format "{{.Name}} {{.Status}}" bitcoind | grep -q "(healthy)"; do
  echo "  bitcoind not healthy yet..."
  sleep 5
done
echo "✅ bitcoind is healthy"

# Fix bitcoind wallet
echo "Fixing bitcoind wallet..."
docker compose exec -T bitcoind bitcoin-cli -${NETWORK} -rpcuser=rpcuser -rpcpassword=rpcpass createwallet "" 2>/dev/null || true
docker compose exec -T bitcoind bitcoin-cli -${NETWORK} -rpcuser=rpcuser -rpcpassword=rpcpass loadwallet "" 2>/dev/null || true

# Mine initial blocks
echo "Mining blocks for counterparty funding..."
NEWADDR=$(docker compose exec -T bitcoind bitcoin-cli -${NETWORK} -rpcuser=rpcuser -rpcpassword=rpcpass getnewaddress)
docker compose exec -T bitcoind bitcoin-cli -${NETWORK} -rpcuser=rpcuser -rpcpassword=rpcpass generatetoaddress 300 "$NEWADDR"
sleep 10

echo "=== Creating Counterparty LND Wallet (Mac) ==="
docker compose exec -it agent-bitcoin-lnd lncli --network=${NETWORK} create

echo "=== Unlocking counterparty wallet ==="
echo -e "\n" | docker compose exec -i agent-bitcoin-lnd lncli --network=${NETWORK} unlock

echo "=== Funding counterparty node ==="
ADDR_B=$(docker compose exec -T agent-bitcoin-lnd lncli --network=${NETWORK} newaddress p2wkh | jq -r .address)
docker compose exec -T bitcoind bitcoin-cli -${NETWORK} -rpcuser=rpcuser -rpcpassword=rpcpass sendtoaddress "$ADDR_B" 25
docker compose exec -T bitcoind bitcoin-cli -${NETWORK} -rpcuser=rpcuser -rpcpassword=rpcpass generatetoaddress 20 "$NEWADDR"
sleep 15

echo "Waiting for counterparty LND to sync..."
for i in {1..60}; do
  SYNCED=$(docker compose exec -T agent-bitcoin-lnd lncli --network=${NETWORK} getinfo 2>/dev/null | grep -o '"synced_to_chain": true' || echo "false")
  if [ "$SYNCED" = '"synced_to_chain": true' ]; then
    echo "✅ Counterparty LND is synced!"
    break
  fi
  echo "  Still syncing... ($i/60)"
  sleep 10
done

echo ""
echo "=== Mac Counterparty Ready for AWS Backend Testing ==="
echo "AWS Backend should be running on http://YOUR_AWS_IP:8000"
echo ""
echo "Test the full integration with:"
echo "   uv run python tests/test_aws_integration.py --backend-url http://YOUR_AWS_IP:8000"
echo ""
echo "✅ Setup complete. You can now test payments between Mac counterparty and AWS backend."
docker compose ps