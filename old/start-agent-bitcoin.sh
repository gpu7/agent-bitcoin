#!/bin/bash
echo "=== Starting Agent-Bitcoin Infrastructure ==="

# Create network if it doesn't exist
echo "=== Creating agent-lightning-net ==="
docker network create agent-lightning-net 2>/dev/null || true

# Start Bitcoin Core
echo "=== Starting bitcoind ==="
docker rm -f bitcoind 2>/dev/null || true

docker run -d \
  --name bitcoind \
  --network agent-lightning-net \
  -p 18443:18443 \
  -p 28332:28332 \
  -p 28333:28333 \
  -v bitcoind-regtest-data:/root/.bitcoin \
  ruimarinho/bitcoin-core \
  bitcoind \
    -regtest \
    -rpcuser=rpcuser \
    -rpcpassword=rpcpass \
    -rpcallowip=0.0.0.0/0 \
    -rpcbind=0.0.0.0 \
    -zmqpubrawblock=tcp://0.0.0.0:28332 \
    -zmqpubrawtx=tcp://0.0.0.0:28333 \
    -fallbackfee=0.00001000

echo "Waiting for bitcoind to start..."
sleep 10
docker logs bitcoind --tail 10

# Create a new wallet in bitcoind
docker exec bitcoind bitcoin-cli -regtest -rpcuser=rpcuser -rpcpassword=rpcpass createwallet ""

# Start Agent-X LND
echo "Starting agent-x-lnd..."
docker rm -f agent-x-lnd 2>/dev/null || true

docker run -d \
  --name agent-x-lnd \
  --network agent-lightning-net \
  -p 8082:8080 \
  -p 9737:9735 \
  -p 10009:10009 \
  -v agent-x-lnd-data:/root/.lnd \
  lightninglabs/lnd:v0.20.1-beta \
  lnd \
    --bitcoin.regtest \
    --bitcoin.node=bitcoind \
    --bitcoind.rpcuser=rpcuser \
    --bitcoind.rpcpass=rpcpass \
    --bitcoind.rpchost=bitcoind \
    --bitcoind.zmqpubrawblock=tcp://bitcoind:28332 \
    --bitcoind.zmqpubrawtx=tcp://bitcoind:28333 \
    --listen=0.0.0.0:9735 \
    --rpclisten=0.0.0.0:10009 \
    --restlisten=0.0.0.0:8080 \
    --debuglevel=info

# Start Agent-B LND
echo "Starting agent-b-lnd..."
docker rm -f agent-b-lnd 2>/dev/null || true

docker run -d \
  --name agent-b-lnd \
  --network agent-lightning-net \
  -p 8083:8080 \
  -p 9738:9735 \
  -p 10010:10009 \
  -v agent-b-lnd-data:/root/.lnd \
  lightninglabs/lnd:v0.20.1-beta \
  lnd \
    --bitcoin.regtest \
    --bitcoin.node=bitcoind \
    --bitcoind.rpcuser=rpcuser \
    --bitcoind.rpcpass=rpcpass \
    --bitcoind.rpchost=bitcoind \
    --bitcoind.zmqpubrawblock=tcp://bitcoind:28332 \
    --bitcoind.zmqpubrawtx=tcp://bitcoind:28333 \
    --listen=0.0.0.0:9735 \
    --rpclisten=0.0.0.0:10009 \
    --restlisten=0.0.0.0:8080 \
    --debuglevel=info

echo "Waiting for LND nodes to start..."
sleep 12

docker ps --format "table {{.Names}}\t{{.Status}}"

# Delete existing wallets (clean reset)
echo "Removing existing wallets..."
docker exec agent-x-lnd rm -rf /root/.lnd/data/chain/bitcoin/regtest/wallet.db 2>/dev/null || true
docker exec agent-b-lnd rm -rf /root/.lnd/data/chain/bitcoin/regtest/wallet.db 2>/dev/null || true

echo "Wallets deleted. Now creating fresh ones..."

# === Wallet Creation ===
echo "Creating wallets for both agents (interactive method)..."

# Use interactive mode for wallet creation (most reliable)
echo "=== Create Wallet for Agent-X ==="
docker exec -it agent-x-lnd lncli --network=regtest create

echo "=== Create Wallet for Agent-B ==="
docker exec -it agent-b-lnd lncli --network=regtest create

echo "Unlocking wallets..."
docker exec -it agent-x-lnd lncli --network=regtest unlock
docker exec -it agent-b-lnd lncli --network=regtest unlock

sleep 5

# Unlock wallets
echo "Unlocking wallets..."
docker exec -it agent-x-lnd lncli --network=regtest unlock
docker exec -it agent-b-lnd lncli --network=regtest unlock

sleep 8

# load bitcoin wallet
docker exec bitcoind bitcoin-cli -regtest -rpcuser=rpcuser -rpcpassword=rpcpass loadwallet ""

# Mine more blocks to build fee estimates
echo "Mining extra blocks for fee estimation..."
NEWADDR=$(docker exec bitcoind bitcoin-cli -regtest -rpcuser=rpcuser -rpcpassword=rpcpass getnewaddress)
docker exec bitcoind bitcoin-cli -regtest -rpcuser=rpcuser -rpcpassword=rpcpass generatetoaddress 20 "$NEWADDR"

sleep 5

# Check current on-chain balances for LND nodes
echo "=== LND On-Chain Balances ==="
docker exec agent-x-lnd lncli --network=regtest getbalance
docker exec agent-b-lnd lncli --network=regtest getbalance

# Check bitcoind balance
echo "=== Bitcoin Core Balance ==="
docker exec bitcoind bitcoin-cli -regtest -rpcuser=rpcuser -rpcpassword=rpcpass getbalance

# Mine even more blocks to a known address
NEWADDR=$(docker exec bitcoind bitcoin-cli -regtest -rpcuser=rpcuser -rpcpassword=rpcpass getnewaddress)
docker exec bitcoind bitcoin-cli -regtest -rpcuser=rpcuser -rpcpassword=rpcpass generatetoaddress 30 "$NEWADDR"

sleep 5

# Fund LND nodes
echo "Funding wallets..."
ADDR_X=$(docker exec agent-x-lnd lncli --network=regtest newaddress p2wkh | jq -r .address)
ADDR_B=$(docker exec agent-b-lnd lncli --network=regtest newaddress p2wkh | jq -r .address)

docker exec bitcoind bitcoin-cli -regtest -rpcuser=rpcuser -rpcpassword=rpcpass sendtoaddress "$ADDR_X" 25
docker exec bitcoind bitcoin-cli -regtest -rpcuser=rpcuser -rpcpassword=rpcpass sendtoaddress "$ADDR_B" 10

NEWADDR=$(docker exec bitcoind bitcoin-cli -regtest -rpcuser=rpcuser -rpcpassword=rpcpass getnewaddress)
docker exec bitcoind bitcoin-cli -regtest -rpcuser=rpcuser -rpcpassword=rpcpass generatetoaddress 6 "$NEWADDR"

# sync nodes
echo "Agent-X sync status:"
docker exec agent-x-lnd lncli --network=regtest getinfo | grep -E "synced_to_chain|block_height"

echo "Agent-B sync status:"
docker exec agent-b-lnd lncli --network=regtest getinfo | grep -E "synced_to_chain|block_height"

# Open channel
echo "Opening Lightning channel..."
PUBKEY_B=$(docker exec agent-b-lnd lncli --network=regtest getinfo | jq -r '.identity_pubkey')
docker exec agent-x-lnd lncli --network=regtest openchannel --node_key "$PUBKEY_B" --local_amt 5000000 --push_amt 2000000

sleep 8

# Bake fresh macaroons
echo "Baking fresh macaroons..."
docker exec agent-x-lnd lncli --network=regtest bakemacaroon --save_to /macaroons/admin.macaroon address:read address:write info:read info:write invoices:read invoices:write macaroon:read macaroon:write message:read message:write offchain:read offchain:write onchain:read onchain:write peers:read peers:write

docker exec agent-b-lnd lncli --network=regtest bakemacaroon --save_to /macaroons/admin.macaroon address:read address:write info:read info:write invoices:read invoices:write macaroon:read macaroon:write message:read message:write offchain:read offchain:write onchain:read onchain:write peers:read peers:write

# Show final status and macaroons
echo "=== SETUP COMPLETE ==="
echo "Containers running:"
docker ps --format "table {{.Names}}\t{{.Status}}"

echo -e "\n=== NEW MACAROONS (Copy these for n8n!) ==="
echo "Agent-X (Payer):"
docker exec agent-x-lnd cat /macaroons/admin.macaroon | base64 | tr -d '\n'
echo -e "\n\nAgent-B (Payee):"
docker exec agent-b-lnd cat /macaroons/admin.macaroon | base64 | tr -d '\n'

echo -e "\n✅ Full infrastructure ready!"
