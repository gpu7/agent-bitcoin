#!/bin/bash
echo "=== Starting Agent-Bitcoin Infrastructure ==="

docker compose down -v --remove-orphans 2>/dev/null || true
docker compose up -d

echo "Waiting for bitcoind to be ready..."
docker compose exec -T bitcoind bash -c '
  until bitcoin-cli -regtest -rpcuser=rpcuser -rpcpassword=rpcpass getblockchaininfo >/dev/null 2>&1; do
    sleep 2
  done
'

# Create Bitcoin wallet
docker compose exec bitcoind bitcoin-cli -regtest -rpcuser=rpcuser -rpcpassword=rpcpass createwallet "" 2>/dev/null || true

echo "=== Creating LND wallets (interactive) ==="
docker compose exec -it agent-x-lnd lncli --network=regtest create
docker compose exec -it agent-b-lnd lncli --network=regtest create

echo "=== Unlocking wallets ==="
docker compose exec -it agent-x-lnd lncli --network=regtest unlock
docker compose exec -it agent-b-lnd lncli --network=regtest unlock

# Rest of your setup (mining, funding, channel, macaroons)...
echo "Mining blocks and funding nodes..."
# ... (you can keep the rest of your logic here)

echo "✅ Infrastructure ready!"
docker compose ps
