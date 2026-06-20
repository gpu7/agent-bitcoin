#!/bin/bash
echo "=== Agent-Bitcoin Full Infrastructure Start (Retry) ==="

docker compose down -v --remove-orphans 2>/dev/null || true
docker compose up -d

echo "Waiting for bitcoind..."
until docker compose ps --format "{{.Name}} {{.Status}}" bitcoind | grep -q "(healthy)"; do sleep 5; done
echo "✅ bitcoind ready"

# Fix wallet
docker compose exec -T bitcoind bitcoin-cli -regtest -rpcuser=rpcuser -rpcpassword=rpcpass createwallet "" 2>/dev/null || true
docker compose exec -T bitcoind bitcoin-cli -regtest -rpcuser=rpcuser -rpcpassword=rpcpass loadwallet "" 2>/dev/null || true

# Heavy mining
echo "Mining blocks..."
NEWADDR=$(docker compose exec -T bitcoind bitcoin-cli -regtest -rpcuser=rpcuser -rpcpassword=rpcpass getnewaddress)
docker compose exec -T bitcoind bitcoin-cli -regtest -rpcuser=rpcuser -rpcpassword=rpcpass generatetoaddress 250 "$NEWADDR"
sleep 20

echo "Creating wallets..."
docker compose exec -it agent-x-lnd lncli --network=regtest create
docker compose exec -it agent-b-lnd lncli --network=regtest create

echo "Unlocking..."
echo -e "\n" | docker compose exec -i agent-x-lnd lncli --network=regtest unlock
echo -e "\n" | docker compose exec -i agent-b-lnd lncli --network=regtest unlock

echo "Funding nodes..."
ADDR_X=$(docker compose exec -T agent-x-lnd lncli --network=regtest newaddress p2wkh | jq -r .address)
ADDR_B=$(docker compose exec -T agent-b-lnd lncli --network=regtest newaddress p2wkh | jq -r .address)
docker compose exec -T bitcoind bitcoin-cli -regtest -rpcuser=rpcuser -rpcpassword=rpcpass sendtoaddress "$ADDR_X" 30
docker compose exec -T bitcoind bitcoin-cli -regtest -rpcuser=rpcuser -rpcpassword=rpcpass sendtoaddress "$ADDR_B" 15
docker compose exec -T bitcoind bitcoin-cli -regtest -rpcuser=rpcuser -rpcpassword=rpcpass generatetoaddress 50 "$NEWADDR"
sleep 15

echo "Waiting for full sync..."
for i in {1..50}; do
  if docker compose exec -T agent-b-lnd lncli --network=regtest getinfo 2>/dev/null | grep -q '"synced_to_chain": true'; then
    echo "✅ Synced!"
    break
  fi
  sleep 10
done

echo "=== Opening channel (with retries) ==="
PUBKEY_B=$(docker compose exec -T agent-b-lnd lncli --network=regtest getinfo | jq -r '.identity_pubkey')

for i in {1..8}; do
  echo "Channel open attempt $i..."
  if docker compose exec -T agent-x-lnd lncli --network=regtest openchannel --node_key "$PUBKEY_B" --local_amt 8000000 --push_amt 3000000; then
    echo "✅ Channel opened successfully!"
    break
  fi
  sleep 12
done

echo "=== Baking macaroons ==="
for agent in agent-x-lnd agent-b-lnd; do
  docker compose exec -T $agent lncli --network=regtest bakemacaroon \
    --save_to /root/.lnd/data/chain/bitcoin/regtest/admin.macaroon \
    address:read address:write info:read info:write invoices:read invoices:write \
    macaroon:read macaroon:write message:read message:write offchain:read offchain:write \
    onchain:read onchain:write peers:read peers:write 2>/dev/null || true
done

echo "=== MACAROONS ==="
echo "Agent-X:"
docker compose exec -T agent-x-lnd cat /root/.lnd/data/chain/bitcoin/regtest/admin.macaroon | base64 | tr -d '\n'
echo -e "\n\nAgent-B:"
docker compose exec -T agent-b-lnd cat /root/.lnd/data/chain/bitcoin/regtest/admin.macaroon | base64 | tr -d '\n'

echo -e "\n✅ DONE!"
docker compose ps
docker compose exec agent-x-lnd lncli --network=regtest listchannels
