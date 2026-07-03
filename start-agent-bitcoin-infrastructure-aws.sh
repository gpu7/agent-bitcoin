#!/bin/bash
echo "=== Agent-Bitcoin Full Infrastructure Start (Updated with Manual Channel Flow) ==="

NETWORK=${1:-regtest}   # Default is regtest. You can pass testnet or mainnet
echo "=== Starting Agent-Bitcoin on $NETWORK ==="
export NETWORK=$NETWORK

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
docker compose exec -T bitcoind bitcoin-cli -${NETWORK} -rpcuser=rpcuser -rpcpassword=rpcpass createwallet "" 2>/dev/null || true
docker compose exec -T bitcoind bitcoin-cli -${NETWORK} -rpcuser=rpcuser -rpcpassword=rpcpass loadwallet "" 2>/dev/null || true

# Heavy initial mining
echo "Mining blocks to help LND sync..."
NEWADDR=$(docker compose exec -T bitcoind bitcoin-cli -${NETWORK} -rpcuser=rpcuser -rpcpassword=rpcpass getnewaddress)
docker compose exec -T bitcoind bitcoin-cli -${NETWORK} -rpcuser=rpcuser -rpcpassword=rpcpass generatetoaddress 300 "$NEWADDR"
sleep 20

echo "=== Creating LND Wallets ==="
docker compose exec -it agent-payment-decision-lnd lncli --network=${NETWORK} create
docker compose exec -it agent-bitcoin-lnd lncli --network=${NETWORK} create

echo "=== Unlocking wallets ==="
echo -e "\n" | docker compose exec -i agent-payment-decision-lnd lncli --network=${NETWORK} unlock
echo -e "\n" | docker compose exec -i agent-bitcoin-lnd lncli --network=${NETWORK} unlock

echo "=== Funding nodes ==="
ADDR_X=$(docker compose exec -T agent-payment-decision-lnd lncli --network=${NETWORK} newaddress p2wkh | jq -r .address)
ADDR_B=$(docker compose exec -T agent-bitcoin-lnd lncli --network=${NETWORK} newaddress p2wkh | jq -r .address)

docker compose exec -T bitcoind bitcoin-cli -${NETWORK} -rpcuser=rpcuser -rpcpassword=rpcpass sendtoaddress "$ADDR_X" 35
docker compose exec -T bitcoind bitcoin-cli -${NETWORK} -rpcuser=rpcuser -rpcpassword=rpcpass sendtoaddress "$ADDR_B" 15
docker compose exec -T bitcoind bitcoin-cli -${NETWORK} -rpcuser=rpcuser -rpcpassword=rpcpass generatetoaddress 50 "$NEWADDR"
sleep 20

echo "Waiting for LND nodes to fully sync..."
for i in {1..60}; do
  SYNCED=$(docker compose exec -T agent-bitcoin-lnd lncli --network=${NETWORK} getinfo 2>/dev/null | grep -o '"synced_to_chain": true' || echo "false")
  if [ "$SYNCED" = '"synced_to_chain": true' ]; then
    echo "✅ LND nodes are synced!"
    break
  fi
  echo "  Still syncing... ($i/60)"
  sleep 10
done

echo "=== Opening channel from Agent-Payment-Decision to Agent-Bitcoin ==="
PUBKEY_B=$(docker compose exec -T agent-bitcoin-lnd lncli --network=${NETWORK} getinfo | jq -r '.identity_pubkey')

echo "Connecting Agent-Payment-Decision to Agent-Bitcoin..."
docker compose exec -T agent-payment-decision-lnd lncli --network=${NETWORK} connect "$PUBKEY_B@agent-bitcoin-lnd:9735"
sleep 8

for i in {1..10}; do
  echo "Channel open attempt $i of 10..."
  if docker compose exec -T agent-payment-decision-lnd lncli --network=${NETWORK} openchannel --node_key "$PUBKEY_B" --local_amt 8000000 --push_amt 3000000; then
    echo "✅ Channel opened successfully!"
    break
  fi
  echo "  Peer not ready yet, waiting..."
  sleep 12
done

echo "Mining 6 blocks to confirm the channel..."
NEWADDR=$(docker compose exec -T bitcoind bitcoin-cli -${NETWORK} -rpcuser=rpcuser -rpcpassword=rpcpass getnewaddress)
docker compose exec -T bitcoind bitcoin-cli -${NETWORK} -rpcuser=rpcuser -rpcpassword=rpcpass generatetoaddress 6 "$NEWADDR"
sleep 8

echo "=== Baking macaroons ==="
for agent in agent-payment-decision-lnd agent-bitcoin-lnd; do
  echo "→ Baking macaroon for $agent"
  docker compose exec -T $agent lncli --network=${NETWORK} bakemacaroon \
    --save_to /root/.lnd/data/chain/bitcoin/${NETWORK}/admin.macaroon \
    address:read address:write info:read info:write invoices:read invoices:write \
    macaroon:read macaroon:write message:read message:write offchain:read offchain:write \
    onchain:read onchain:write peers:read peers:write 2>/dev/null || true
done

echo "=== MACAROONS (Copy these for n8n!) ==="
echo "Agent-Payment-Decision (Payer):"
docker compose exec -T agent-payment-decision-lnd cat /root/.lnd/data/chain/bitcoin/${NETWORK}/admin.macaroon | base64 | tr -d '\n'
echo -e "\n\nAgent-Bitcoin (Payee):"
docker compose exec -T agent-bitcoin-lnd cat /root/.lnd/data/chain/bitcoin/${NETWORK}/admin.macaroon | base64 | tr -d '\n'

echo -e "\n✅ FULL INFRASTRUCTURE READY!"
docker compose ps
