#!/bin/bash

echo "=== Agent-Bitcoin Full Infrastructure Start ==="

# Clean start
docker compose down -v --remove-orphans 2>/dev/null || true

# Start everything
docker compose up -d

echo "Waiting for bitcoind..."
until docker compose exec -T bitcoind bitcoin-cli -regtest -rpcuser=rpcuser -rpcpassword=rpcpass getblockchaininfo >/dev/null 2>&1; do 
  sleep 2
done

echo "Waiting for LND nodes to be fully ready (healthcheck)..."
docker compose wait agent-x-lnd agent-b-lnd

echo "Creating Bitcoin wallet..."
docker compose exec -T bitcoind bitcoin-cli -regtest -rpcuser=rpcuser -rpcpassword=rpcpass createwallet "" 2>/dev/null || true

echo "=== Creating LND Wallets (Interactive) ==="
docker compose exec -it agent-x-lnd lncli --network=regtest create
docker compose exec -it agent-b-lnd lncli --network=regtest create

echo "=== Unlocking wallets ==="
docker compose exec -it agent-x-lnd lncli --network=regtest unlock
docker compose exec -it agent-b-lnd lncli --network=regtest unlock

echo "=== Preparing macaroons ==="
docker compose exec -T agent-x-lnd mkdir -p /macaroons
docker compose exec -T agent-b-lnd mkdir -p /macaroons

echo "=== Mining + Funding ==="
NEWADDR=$(docker compose exec -T bitcoind bitcoin-cli -regtest -rpcuser=rpcuser -rpcpassword=rpcpass getnewaddress "")

docker compose exec -T bitcoind bitcoin-cli -regtest -rpcuser=rpcuser -rpcpassword=rpcpass generatetoaddress 110 "$NEWADDR"

echo "Funding nodes..."
ADDR_X=$(docker compose exec -T agent-x-lnd lncli --network=regtest newaddress p2wkh | jq -r .address)
ADDR_B=$(docker compose exec -T agent-b-lnd lncli --network=regtest newaddress p2wkh | jq -r .address)

docker compose exec -T bitcoind bitcoin-cli -regtest -rpcuser=rpcuser -rpcpassword=rpcpass sendtoaddress "$ADDR_X" 15
docker compose exec -T bitcoind bitcoin-cli -regtest -rpcuser=rpcuser -rpcpassword=rpcpass sendtoaddress "$ADDR_B" 10

docker compose exec -T bitcoind bitcoin-cli -regtest -rpcuser=rpcuser -rpcpassword=rpcpass generatetoaddress 10 "$NEWADDR"

echo "=== Connecting nodes & Opening channel ==="
PUBKEY_X=$(docker compose exec -T agent-x-lnd lncli --network=regtest getinfo | jq -r '.identity_pubkey')
PUBKEY_B=$(docker compose exec -T agent-b-lnd lncli --network=regtest getinfo | jq -r '.identity_pubkey')

echo "Agent-X PubKey: $PUBKEY_X"
echo "Agent-B PubKey: $PUBKEY_B"

docker compose exec -T agent-x-lnd lncli --network=regtest connect "$PUBKEY_B@agent-b-lnd:9735" || true
sleep 5

docker compose exec -T agent-x-lnd lncli --network=regtest openchannel \
  --node_key "$PUBKEY_B" \
  --local_amt 5000000 \
  --push_amt 2000000

echo "=== Mining 6 blocks to confirm channel ==="
docker compose exec -T bitcoind bitcoin-cli -regtest -rpcuser=rpcuser -rpcpassword=rpcpass generatetoaddress 6 "$NEWADDR"
sleep 8

echo "=== Baking macaroons ==="
docker compose exec -T agent-x-lnd lncli --network=regtest bakemacaroon \
  --save_to /root/.lnd/data/chain/bitcoin/regtest/admin.macaroon \
  address:read address:write info:read info:write invoices:read invoices:write \
  macaroon:read macaroon:write message:read message:write offchain:read offchain:write \
  onchain:read onchain:write peers:read peers:write

docker compose exec -T agent-b-lnd lncli --network=regtest bakemacaroon \
  --save_to /root/.lnd/data/chain/bitcoin/regtest/admin.macaroon \
  address:read address:write info:read info:write invoices:read invoices:write \
  macaroon:read macaroon:write message:read message:write offchain:read offchain:write \
  onchain:read onchain:write peers:read peers:write

docker compose exec -T agent-x-lnd cp /root/.lnd/data/chain/bitcoin/regtest/admin.macaroon /macaroons/admin.macaroon
docker compose exec -T agent-b-lnd cp /root/.lnd/data/chain/bitcoin/regtest/admin.macaroon /macaroons/admin.macaroon

echo "=== MACAROONS (Copy for n8n) ==="
echo "Agent-X (Payer):"
docker compose exec -T agent-x-lnd cat /macaroons/admin.macaroon | base64 | tr -d '\n'
echo -e "\n\nAgent-B (Payee):"
docker compose exec -T agent-b-lnd cat /macaroons/admin.macaroon | base64 | tr -d '\n'

echo "=== Starting n8n ==="
docker compose up -d n8n

echo -e "\n✅ FULL INFRASTRUCTURE READY!"
echo "n8n UI: http://localhost:5678"
docker compose ps
