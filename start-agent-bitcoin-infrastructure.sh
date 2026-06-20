#!/bin/bash
echo "=== Agent-Bitcoin Full Infrastructure Start ==="

# Clean start
docker compose down -v --remove-orphans 2>/dev/null || true
docker compose up -d

echo "Waiting for bitcoind to be healthy..."
until docker compose ps --format "{{.Name}} {{.Status}}" bitcoind | grep -q "(healthy)"; do
  echo "  bitcoind not healthy yet..."
  sleep 5
done
echo "✅ bitcoind is healthy"

# Fix bitcoind wallet
echo "Fixing bitcoind wallet..."
docker compose exec -T bitcoind bitcoin-cli -regtest -rpcuser=rpcuser -rpcpassword=rpcpass createwallet "" 2>/dev/null || true
docker compose exec -T bitcoind bitcoin-cli -regtest -rpcuser=rpcuser -rpcpassword=rpcpass loadwallet "" 2>/dev/null || true

echo "Mining blocks to help LND sync..."
NEWADDR=$(docker compose exec -T bitcoind bitcoin-cli -regtest -rpcuser=rpcuser -rpcpassword=rpcpass getnewaddress)
docker compose exec -T bitcoind bitcoin-cli -regtest -rpcuser=rpcuser -rpcpassword=rpcpass generatetoaddress 150 "$NEWADDR"
sleep 15

echo "=== Creating LND Wallets (Interactive) ==="
echo "→ Follow the prompts for both agents (empty password + 'n' for new seed)"
docker compose exec -it agent-x-lnd lncli --network=regtest create
docker compose exec -it agent-b-lnd lncli --network=regtest create

echo "=== Unlocking wallets (non-interactive) ==="
echo -e "\n" | docker compose exec -i agent-x-lnd lncli --network=regtest unlock
echo -e "\n" | docker compose exec -i agent-b-lnd lncli --network=regtest unlock

echo "=== Mining more blocks and funding nodes ==="
NEWADDR=$(docker compose exec -T bitcoind bitcoin-cli -regtest -rpcuser=rpcuser -rpcpassword=rpcpass getnewaddress)
docker compose exec -T bitcoind bitcoin-cli -regtest -rpcuser=rpcuser -rpcpassword=rpcpass generatetoaddress 100 "$NEWADDR"

ADDR_X=$(docker compose exec -T agent-x-lnd lncli --network=regtest newaddress p2wkh | jq -r .address)
ADDR_B=$(docker compose exec -T agent-b-lnd lncli --network=regtest newaddress p2wkh | jq -r .address)

docker compose exec -T bitcoind bitcoin-cli -regtest -rpcuser=rpcuser -rpcpassword=rpcpass sendtoaddress "$ADDR_X" 25
docker compose exec -T bitcoind bitcoin-cli -regtest -rpcuser=rpcuser -rpcpassword=rpcpass sendtoaddress "$ADDR_B" 15
docker compose exec -T bitcoind bitcoin-cli -regtest -rpcuser=rpcuser -rpcpassword=rpcpass generatetoaddress 20 "$NEWADDR"

echo "Waiting for LND nodes to sync..."
sleep 15

echo "=== Opening channel ==="
PUBKEY_B=$(docker compose exec -T agent-b-lnd lncli --network=regtest getinfo | jq -r '.identity_pubkey')
docker compose exec -T agent-x-lnd lncli --network=regtest openchannel --node_key "$PUBKEY_B" --local_amt 5000000 --push_amt 2000000
sleep 10

echo "=== Baking macaroons ==="
for agent in agent-x-lnd agent-b-lnd; do
  echo "→ Baking macaroon for $agent"
  docker compose exec -T $agent lncli --network=regtest bakemacaroon \
    --save_to /root/.lnd/data/chain/bitcoin/regtest/admin.macaroon \
    address:read address:write info:read info:write invoices:read invoices:write \
    macaroon:read macaroon:write message:read message:write offchain:read offchain:write \
    onchain:read onchain:write peers:read peers:write 2>/dev/null || true
done

echo "=== MACAROONS (Copy these for n8n!) ==="
echo "Agent-X (Payer):"
docker compose exec -T agent-x-lnd cat /root/.lnd/data/chain/bitcoin/regtest/admin.macaroon | base64 | tr -d '\n'
echo -e "\n\nAgent-B (Payee):"
docker compose exec -T agent-b-lnd cat /root/.lnd/data/chain/bitcoin/regtest/admin.macaroon | base64 | tr -d '\n'

echo -e "\n✅ FULL INFRASTRUCTURE READY!"
docker compose ps

# Final sync check
echo "Final LND sync status:"
docker compose exec agent-b-lnd lncli --network=regtest getinfo | grep -E "block_height|synced_to_chain"
