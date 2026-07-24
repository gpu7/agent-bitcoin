# Backend Management

---

## Workflow

The current workflow is shown here.  This is the test workflow on regtest.

Note: the "current-aws-instance-IPv4-address" changes each time a new AWS agent-bitcoin instance is launched.

- 1) On AWS: ./startup-aws.sh regtest <current-aws-instance-IPv4-address>
- 2) On AWS: Fund LND node. See below.
- 3) On Mac: ./startup-mac.sh regtest <current-aws-instance-IPv4-address>
- 4) On Mac: ./wait-mac-lnd.sh regtest
- 5) On Mac: ./connect-mac-to-aws.sh <current-aws-instance-IPv4-address> <pubkey-from-aws-getinfo> See below.
- 6) On Mac: Verify peer connection Mac <-> AWS. See below.
- 7) On Mac: Open Lightning channel Mac <-> AWS. See below.
- 8) On Mac: uv run python tests/test_aws_integration.py --backend-url http://<current-aws-instance-IPv4-address>:8000
- 9) On AWS: ./shutdown-aws.sh
- 10) On Mac: ./shutdown-mac.sh

### Optional diagnostics
Run these commands after each workflow step to determine if everything launched correctly.

- STEP #1. On AWS:

```bash
echo "=== Post-Startup Diagnostics (AWS) ==="

echo "Containers:"
docker ps

echo -e "Bitcoind Height:"
docker exec bitcoind bitcoin-cli -regtest -rpcuser=lightning -rpcpassword=lightning getblockcount

echo -e "LND Sync Status:"
docker exec agent-payment-decision-lnd lncli --lnddir=/home/lnd/.lnd --network=regtest getinfo | grep -E "block_height|synced_to_chain|synced_to_graph|identity_pubkey"

echo -e "Backend API Balance:"
curl -s http://localhost:8000/balance | jq . 2>/dev/null || curl -s http://localhost:8000/balance || echo "API not responding yet"

echo -e "Recent LND Logs:"
docker logs --tail 20 agent-payment-decision-lnd | tail -15

echo -e "Command to start agent-payment-decision-lnd"
docker compose -f docker-compose.regtest.aws.yml up -d agent-payment-decision-lnd
```

- STEP #2. On AWS:

```bash
# Get new LND address
ADDR=$(docker exec agent-payment-decision-lnd lncli --lnddir=/home/lnd/.lnd --network=regtest newaddress p2wkh | jq -r '.address')
echo "Funding address: $ADDR"

# Send 5 BTC from miner wallet
docker exec bitcoind bitcoin-cli -regtest -rpcwallet=miner sendtoaddress $ADDR 5

# Mine blocks to confirm
docker exec bitcoind bitcoin-cli -regtest -rpcwallet=miner generatetoaddress 6 $(docker exec bitcoind bitcoin-cli -regtest -rpcwallet=miner getnewaddress "")

# Check balance
curl -s http://localhost:8000/balance | jq .
```

- STEP #3. On Mac:

```bash
echo "=== Post-Startup Diagnostics (Mac) ==="

echo "1. Container Status:"
docker compose -f docker-compose.regtest.mac.yml ps

echo -e "Bitcoind Height (Mac):"
docker compose -f docker-compose.regtest.mac.yml exec bitcoind bitcoin-cli -regtest -rpcuser=rpcuser -rpcpassword=rpcpass getblockcount

echo -e "agent-bitcoin-lnd Status:"
docker compose -f docker-compose.regtest.mac.yml exec -T agent-bitcoin-lnd \
  lncli --lnddir=/home/lnd/.lnd --network=regtest getinfo | grep -E "identity_pubkey|block_height|synced_to_chain|synced_to_graph|uris"

echo -e "agent-bitcoin-1-lnd Status:"
docker compose -f docker-compose.regtest.mac.yml exec -T agent-bitcoin-1-lnd \
  lncli --lnddir=/home/lnd/.lnd --network=regtest getinfo | grep -E "identity_pubkey|block_height|synced_to_chain|synced_to_graph|uris"

echo -e "Test Connectivity to AWS bitcoind (from both agents):"
docker compose -f docker-compose.regtest.mac.yml exec agent-bitcoin-lnd \
  curl -s -X POST http://98.93.77.245:18443 -H "Content-Type: application/json" --data '{"jsonrpc":"1.0","id":"test","method":"getblockcount"}' || echo "Failed from agent-bitcoin-lnd"

docker compose -f docker-compose.regtest.mac.yml exec agent-bitcoin-1-lnd \
  curl -s -X POST http://98.93.77.245:18443 -H "Content-Type: application/json" --data '{"jsonrpc":"1.0","id":"test","method":"getblockcount"}' || echo "Failed from agent-bitcoin-1-lnd"

echo -e "Recent Logs (agent-bitcoin-lnd):"
docker compose -f docker-compose.regtest.mac.yml logs --tail 20 agent-bitcoin-lnd | tail -10

echo -e "Show a live tail of the logs, updating in real time as Mac LND receives and processes blocks from AWS."
docker compose -f docker-compose.regtest.mac.yml logs -f agent-bitcoin-lnd | grep -E "ZMQ|block|sync|new block|Filtering"
```

- STEP #4. On Mac:
-
```bash
echo "=== Mac Post-Startup Diagnostics ==="

echo "1. Containers:"
docker compose -f docker-compose.regtest.mac.yml ps

echo -e "Bitcoind Height (Mac):"
docker compose -f docker-compose.regtest.mac.yml exec -T bitcoind bitcoin-cli -regtest -rpcuser=rpcuser -rpcpassword=rpcpass getblockcount

echo -e "Mac LND Status:"
docker compose -f docker-compose.regtest.mac.yml exec -T agent-bitcoin-lnd \
  lncli --lnddir=/home/lnd/.lnd --network=regtest getinfo | grep -E "identity_pubkey|block_height|synced_to_chain|synced_to_graph"

echo -e "Connection to AWS LND:"
docker compose -f docker-compose.regtest.mac.yml exec -T agent-bitcoin-lnd \
  lncli --lnddir=/home/lnd/.lnd --network=regtest listpeers | grep -E "pub_key|address"

echo -e "Recent Mac LND Logs:"
docker compose -f docker-compose.regtest.mac.yml logs --tail 15 agent-bitcoin-lnd | tail -10
```

- STEP #5. It can take a fairly long time to sync the Lightning node with the Bitcoin blockchain. If you see "synced_to_chain: false", run these commands to advance the chain and force LND to catch up. This is not guaranteed to work. You may have to simply wait some time for the nodes to sync.

- Explanation for why mining more blocks on AWS helps the Mac LND sync faster:

- Your setup is:

  - AWS: Runs bitcoind (the Bitcoin blockchain) + agent-payment-decision-lnd
  - Mac: Runs only agent-bitcoin-lnd (connects to AWS bitcoind via RPC + ZMQ)

- When you mine blocks on AWS:

1) The AWS bitcoind adds new blocks to the blockchain.
2) The Mac LND is configured to listen to AWS bitcoind for new blocks (via ZMQ notifications on ports 28332/28333) and to query it via RPC.
3) When new blocks appear, the Mac LND gets notified and starts downloading and validating them.
4) This advances the Mac LND’s block_height and eventually flips synced_to_chain from false to true.

```bash
# On AWS:

# Mine more blocks
docker exec bitcoind bitcoin-cli -regtest -rpcuser=btc -rpcpassword=btc generatetoaddress 200 $(docker exec bitcoind bitcoin-cli -regtest -rpcuser=btc -rpcpassword=btc getnewaddress "")

# On Mac:

# Restart Mac LND
docker compose -f docker-compose.regtest.mac.yml restart agent-bitcoin-lnd

sleep 15

# Unlock if needed
docker compose -f docker-compose.regtest.mac.yml exec -it agent-bitcoin-lnd \
  lncli --lnddir=/home/lnd/.lnd --network=regtest unlock

# Monitor
./wait-mac-lnd.sh regtest
```

- STEP #6. On Mac:

Use AWS agent-payment-decision-lnd pubkey.

```bash
docker compose -f docker-compose.regtest.mac.yml exec -T agent-bitcoin-lnd \
  lncli --lnddir=/home/lnd/.lnd --network=regtest connect \
  0258b1aefcaa9c03423647a1c17094f04616a4849696d1db7ec67943eae73ab0ec@<current-aws-instance-IPv4-address>:9735
```

- STEP #7. On Mac:

```bash
docker compose -f docker-compose.regtest.mac.yml exec agent-bitcoin-lnd \
  lncli --lnddir=/home/lnd/.lnd --network=regtest listpeers
```

- STEP #8. On Mac:

Use AWS agent-payment-decision-lnd pubkey.

```bash
docker compose -f docker-compose.regtest.mac.yml exec agent-bitcoin-lnd \
  lncli --lnddir=/home/lnd/.lnd --network=regtest openchannel \
  --node_key 0258b1aefcaa9c03423647a1c17094f04616a4849696d1db7ec67943eae73ab0ec \
  --local_amt 1000000 \
  --push_amt 500000
```

- STEP #9. On AWS:

```bash
echo "=== Agent-Bitcoin Shutdown Diagnostics ==="

echo "→ Running containers:"
docker ps

echo "→ Agent networks:"
docker network ls | grep -E "agent|agent-net"

echo "→ Backend processes:"
ps aux | grep -E "uv run|backend/main.py" | grep -v grep

echo "→ Volumes (LND volume should remain):"
docker volume ls | grep agent-bitcoin

echo ""
echo "✅ If no containers or agent networks appear above, shutdown is clean."
echo "   (LND volume is intentionally kept for faster restarts)"
```

- STEP #10. On Mac:

```bash
echo "=== Mac Shutdown Diagnostics ==="

echo "→ Running containers:"
docker ps

echo "→ Agent networks:"
docker network ls | grep -E "agent|agent-lightning-net"

echo "→ Backend processes:"
ps aux | grep -E "uv run|backend/main.py" | grep -v grep

echo "→ Volumes (should keep LND and bitcoind data):"
docker volume ls | grep -E "agent-bitcoin|bitcoind"

echo ""
echo "✅ If no containers or agent networks appear above, shutdown is clean."
echo "   (Volumes are intentionally kept for faster restarts)"
```

---

## Publish to TestPyPi

- Update pyproject.toml as appropriate.

```bash
# Build and upload to TestPyPI
cd ~/agent-bitcoin
rm -rf dist/ build/ *.egg-info/
uv tool install twine
uv build
twine upload --repository testpypi dist/*
```

---

## AWS

### Instance type

- Currently using the AWS instance types:
t3.medium
i4i.xlarge

### SSH
Here is the command to ssh into a running AWS instance.

Note: the URL will change each time a new instance is started.

```bash
ssh -i ~/.ssh/aws/agent-bitcoin-key.pem ubuntu@100.58.101.173
```

### Start backend in tmux
```bash
tmux new-session -d -s backend "cd ~/agent-bitcoin && PYTHONPATH=. uv run python backend/main.py"
```

### Check if it's running
```bash
tmux ls
curl http://localhost:8000/balance
```

### docker-compose.regtest.yml

If you modify the file docker-compose.regtest.yml, immediately instantiate the changes by running these commands:

```bash
docker compose -f docker-compose.regtest.aws.yml down
docker compose -f docker-compose.regtest.aws.yml up -d
```

### AWS monitoring data

```bash
# 1. Current instance type and specs
echo "Instance type:"; curl -s http://169.254.169.254/latest/meta-data/instance-type

# 2. CPU usage
echo -e "\nCPU Usage:"; top -bn1 | head -n 20

# 3. Memory usage
echo -e "\nMemory Usage:"; free -h

# 4. Disk I/O (important for bitcoind + LND)
echo -e "\nDisk I/O:"; iostat -x 1 3 | tail -n 20

# 5. Current running processes
echo -e "\nTop processes:"; ps aux --sort=-%cpu | head -n 15
```

---

## Bitcoin wallet management
```bash
echo "→ Deleting ALL Bitcoin wallets (clean slate)..."

# Unload all wallets
docker exec bitcoind bitcoin-cli -regtest listwallets | \
  docker exec -i bitcoind xargs -I {} bitcoin-cli -regtest unloadwallet "{}" 2>/dev/null || true

# Delete the entire wallets directory (nuclear but safe on regtest)
docker exec bitcoind rm -rf /home/bitcoin/.bitcoin/regtest/wallets

# Recreate the empty wallets directory
docker exec bitcoind mkdir -p /home/bitcoin/.bitcoin/regtest/wallets

echo "✅ All wallets deleted. Fresh start ready."
```

---

## Lightning Labs Loop service

- We use Lightning Labs Loop for lightning channel management and funding.

- The Loop github repo is: https://github.com/lightninglabs/loop

- Install, configure and run Loop in regtest.

```bash
#!/bin/bash
set -e

echo "=== Setting up Loop on regtest (official environment) ==="

# 1. Install docker-compose if needed
echo "Installing docker-compose..."
sudo apt update
sudo apt install -y docker-compose

# 2. Clone Loop repo
echo "Cloning Loop repo..."
cd ~
git clone https://github.com/lightninglabs/loop.git || true
cd loop/regtest

# 3. Update docker-compose.yml to use working etcd image
echo "Updating etcd image..."
sed -i 's|bitnami/etcd:.*|quay.io/coreos/etcd:v3.5.18|' docker-compose.yml

# 4. Clean up old conflicting containers
echo "Cleaning up old containers..."
cd ~/agent-bitcoin || true
docker compose -f docker-compose.regtest.aws.yml down 2>/dev/null || true
docker rm -f $(docker ps -aq) 2>/dev/null || true
docker volume rm $(docker volume ls -q) 2>/dev/null || true

# 5. Start the official regtest environment
echo "Starting regtest environment..."
cd ~/loop/regtest
./regtest.sh start

echo "✅ Loop regtest setup complete!"
echo "Test with: loop --network=regtest getinfo"
```

---

## Lightning channels

Here are instructions for managing Lightning channels.

### Step 1: Fund the AWS node

- Run these commands on the AWS instance:

It may be necessary to run this first if using regtest:

```bash
# Set a fallback fee
docker exec bitcoind bitcoin-cli -regtest -rpcuser=btc -rpcpassword=btc settxfee 0.00001
```

```bash
# 1. Get a new address on the AWS payment-decision node
ADDR=$(docker exec -it agent-payment-decision-lnd lncli --lnddir=/home/lnd/.lnd --network=regtest newaddress p2wkh | jq -r .address)
echo "AWS Address: $ADDR"

# 2. Send coins from bitcoind to the AWSpayment-decision node
docker exec bitcoind bitcoin-cli -regtest -rpcuser=btc -rpcpassword=btc sendtoaddress "$ADDR" 20

# 3. Mine blocks to confirm the funds
docker exec bitcoind bitcoin-cli -regtest -rpcuser=btc -rpcpassword=btc generatetoaddress 6 $(docker exec bitcoind bitcoin-cli -regtest -rpcuser=btc -rpcpassword=btc getnewaddress)

# 4. Check balance on AWS
docker exec -it agent-payment-decision-lnd lncli --lnddir=/home/lnd/.lnd --network=regtest walletbalance
```

Summary
- AWS payment-decision-lnd now has 2,000,000,000 sats (20 BTC) confirmed.

### Step 2: Connect Mac to AWS

- Run this command on the Mac:

- Note: You will have to update the AWS instance IP address every time you launch a new instance

```bash
docker compose -f docker-compose.regtest.mac.yml exec -T agent-bitcoin-lnd lncli --lnddir=/home/lnd/.lnd --network=regtest connect 022c3c33f5974b37861859de0417bf8f95fba55dae3677053c2aa6f9aaa2032b67@54.227.203.21:9735
```

### Open Lightning channel from Mac to AWS
```bash
# Open a 5M sat channel (you can adjust the amount)
docker compose -f docker-compose.regtest.mac.yml exec -it agent-bitcoin-lnd \
  lncli --lnddir=/home/lnd/.lnd --network=regtest openchannel \
    --node_key 039f2162629469491bf27e39d5f679d601662953b2db437db24e08c91b5d71b6de \
    --local_amt 5000000 \
    --push_amt 2000000
```

### Open Channel Mac <--> AWS
```bash
# Get the identity pubkey of the AWS node
# Run this command on AWS node
docker exec -it agent-payment-decision-lnd lncli --lnddir=/home/lnd/.lnd --network=regtest getinfo
```

```bash
# 1. Connect Mac node to AWS node
#    Run these commands on Mac
#    Note: change the pubkey based on the previous command
docker compose exec -T agent-bitcoin-lnd lncli --network=regtest connect 022c3c33f5974b37861859de0417bf8f95fba55dae3677053c2aa6f9aaa2032b67@100.58.101.173:9735

# 2. Open channel from Mac to AWS
docker compose exec -T agent-bitcoin-lnd lncli --network=regtest openchannel \
  --node_key 022c3c33f5974b37861859de0417bf8f95fba55dae3677053c2aa6f9aaa2032b67 \
  --local_amt 5000000 \
  --push_amt 1000000
```

---

## Tests

### Test integration of frontend SDK with backend AWS API

File: tests/test_aws_integration.py

Run on mac:

```bash
# Basic usage (localhost)
uv run python tests/test_aws_integration.py

# With your AWS backend IP
uv run python tests/test_aws_integration.py --backend-url http://34.204.169.174:8000

# Custom amount
uv run python tests/test_aws_integration.py --backend-url http://34.204.169.174:8000 --amount 10000
```

---

## Logs

### Docker commands to follow log files
```bash
# On AWS:
docker compose -f docker-compose.regtest.aws.yml logs -f agent-payment-decision-lnd

# On Mac:
docker compose -f docker-compose.regtest.mac.yml logs -f agent-bitcoin-lnd
```

---

## ZMQ (ZeroMQ) connands

- ZeroMQ is a high-performance, lightweight messaging library that allows different programs (in this case, bitcoind and LND) to communicate efficiently.

- In current setup, AWS bitcoind uses ZMQ to publish (send out) real-time notifications whenever
  - 1) a new block is mined (rawblock)
  - 2) a new transaction is seen (rawtx)

- ZMQ is the fast notification system that lets LND know immediately when new blocks arrive on the AWS node.

- Mac agent-bitcoin-lnd subscribes to those ZMQ feeds (on ports 28332 and 28333) so it can stay in sync with the Bitcoin blockchain without constantly polling.

Here are commands related to ZMQ.

```bash
# Check from Mac terminal whether agent-bitcoin-lnd is receiving ZMQ messages from AWS bitcoind. Look for lines like:
  # Started listening for bitcoind block notifications via ZMQ
  # New block epoch subscription
  # Received block or similar
docker compose -f docker-compose.regtest.mac.yml logs --tail 50 agent-bitcoin-lnd | grep -E "ZMQ|block|sync|new block"
```

- More detailed ZMQ status

```bash
# Check if LND is connected to ZMQ
docker compose -f docker-compose.regtest.mac.yml exec agent-bitcoin-lnd \
  lncli --lnddir=/home/lnd/.lnd --network=regtest getinfo | grep -E "block_height|synced_to_chain"

# Watch live ZMQ activity
docker compose -f docker-compose.regtest.mac.yml logs -f agent-bitcoin-lnd | grep -E "ZMQ|block|height"
```

- Verify ZMQ ports are open
  - If ports 28332 and 28333 are listening, ZMQ is configured.

```bash
docker compose -f docker-compose.regtest.mac.yml exec agent-bitcoin-lnd \
  ss -tlnp | grep -E "28332|28333"
```

---

## Terminal screen management

- Sometimes, the terminal is left in an unstable state.  These commands usually fix it.

| Command   | What it does                    | When to use                 |
|:----------|:--------------------------------|:----------------------------|
| stty echo | Turns typing visibility back on | When text is invisible      |
| stty sane | Best all around fix             | When output looks broken    |
| reset     | Full terminal reset             | When stty sane isn't enough |

---
