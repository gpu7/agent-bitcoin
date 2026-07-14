# This file is a catchall for miscellaneous items. 

- The contents of this file may or may not work their way into some proper location later.<br><br>

On AWS

# Start the full backend (bitcoind + LND + API)
./startup-aws.sh

# Check LND status
docker exec -it agent-payment-decision-lnd lncli --lnddir=/home/lnd/.lnd --network=regtest getinfo

# List peers
docker exec -it agent-payment-decision-lnd lncli --lnddir=/home/lnd/.lnd --network=regtest listpeers

# get current bitcoin blockchain blockcount
docker exec bitcoind bitcoin-cli -regtest -rpcuser=btc -rpcpassword=btc getblockcount

On Mac

# Start Mac counterparty node
./startup-mac.sh regtest <current-aws-instance-IPv4-address>

# Check LND status
docker compose -f docker-compose.regtest.mac.yml exec -it agent-bitcoin-lnd lncli --lnddir=/home/lnd/.lnd --network=regtest getinfo

# check if Mac age
# Connect to AWS node (using current IP)
./connect-mac-to-aws.sh 54.87.36.22

OR

On AWS:
# get pubkey
docker exec -it agent-payment-decision-lnd lncli --lnddir=/home/lnd/.lnd --network=regtest getinfo | grep identity_pubkey

On Mac:
# USE THIS ONE
# Connect to AWS node (directly)
# use pubkey from previous command
docker compose -f docker-compose.regtest.mac.yml exec -it agent-bitcoin-lnd \
  lncli --lnddir=/home/lnd/.lnd --network=regtest connect \
  039f2162629469491bf27e39d5f679d601662953b2db437db24e08c91b5d71b6de@13.220.186.146:9735

# List peers (to verify connection)
docker compose -f docker-compose.regtest.mac.yml exec -it agent-bitcoin-lnd lncli --lnddir=/home/lnd/.lnd --network=regtest listpeers

Diagnostics

# Basic connectivity test
nc -zv <AWS_IP> 9735

# Restart LND on Mac
docker compose -f docker-compose.regtest.mac.yml restart agent-bitcoin-lnd

# Restart LND on AWS
docker restart agent-payment-decision-lnd

You reached this stage by:Starting both sides
Ensuring wallets were unlocked
Connecting via public IP:9735
Verifying with listpeers

Open channel from Mac to AWS
Run this on your Mac:

docker compose -f docker-compose.regtest.mac.yml exec -it agent-bitcoin-lnd \
  lncli --lnddir=/home/lnd/.lnd --network=regtest openchannel \
    --node_key 039f2162629469491bf27e39d5f679d601662953b2db437db24e08c91b5d71b6de \
    --local_amt 5000000 \
    --push_amt 2000000

# Fund LND on Mac node

Run on mac:

# 1. Get a fresh address from LND
LND_ADDR=$(docker compose -f docker-compose.regtest.mac.yml exec -T agent-bitcoin-lnd \
  lncli --lnddir=/home/lnd/.lnd --network=regtest newaddress p2wkh | jq -r '.address')
echo "LND address: $LND_ADDR"

# Set fallback fee
docker compose -f docker-compose.regtest.mac.yml exec bitcoind \
  bitcoin-cli -regtest -rpcuser=rpcuser -rpcpassword=rpcpass settxfee 0.00001

# 2. Send coins from Mac's bitcoind to LND's address
docker compose -f docker-compose.regtest.mac.yml exec bitcoind \
  bitcoin-cli -regtest -rpcuser=rpcuser -rpcpassword=rpcpass \
  sendtoaddress "$LND_ADDR" 0.5

# 3. Mine blocks to confirm the transaction
ADDR=$(docker compose -f docker-compose.regtest.mac.yml exec bitcoind \
  bitcoin-cli -regtest -rpcuser=rpcuser -rpcpassword=rpcpass getnewaddress "")

docker compose -f docker-compose.regtest.mac.yml exec bitcoind \
  bitcoin-cli -regtest -rpcuser=rpcuser -rpcpassword=rpcpass generatetoaddress 6 "$ADDR"

# Now check balance on Mac
docker compose -f docker-compose.regtest.mac.yml exec agent-bitcoin-lnd \
  lncli --lnddir=/home/lnd/.lnd --network=regtest walletbalance

# Open channel from Mac to AWS
Run this on your Mac:

docker compose -f docker-compose.regtest.mac.yml exec -it agent-bitcoin-lnd \
  lncli --lnddir=/home/lnd/.lnd --network=regtest openchannel \
    --node_key 039f2162629469491bf27e39d5f679d601662953b2db437db24e08c91b5d71b6de \
    --local_amt 5000000 \
    --push_amt 2000000

# Confirm the channel
# Mine blocks to confirm the funding transaction
ADDR=$(docker compose -f docker-compose.regtest.mac.yml exec bitcoind \
  bitcoin-cli -regtest -rpcuser=rpcuser -rpcpassword=rpcpass getnewaddress "")

docker compose -f docker-compose.regtest.mac.yml exec bitcoind \
  bitcoin-cli -regtest -rpcuser=rpcuser -rpcpassword=rpcpass generatetoaddress 6 "$ADDR"

# Then check the channel status on Mac and AWS:

Run on Mac:
docker compose -f docker-compose.regtest.mac.yml exec agent-bitcoin-lnd \
  lncli --lnddir=/home/lnd/.lnd --network=regtest listchannels

Run on AWS:
docker exec -it agent-payment-decision-lnd \
  lncli --lnddir=/home/lnd/.lnd --network=regtest listchannels

# Test connectivity from Mac

Run on mac:

# 1. Test RPC connection to AWS bitcoind
docker compose -f docker-compose.regtest.mac.yml exec agent-bitcoin-lnd \
  lncli --lnddir=/home/lnd/.lnd --network=regtest getblockcount

# 2. Full LND info
docker compose -f docker-compose.regtest.mac.yml exec agent-bitcoin-lnd \
  lncli --lnddir=/home/lnd/.lnd --network=regtest getinfo


# We had difficulty getting mac and aws to connect and open a channel.
# Here are the commands that got it to work.

Why it was failing for so long
Both LND nodes had stale chain/wallet state ("Block height out of range" errors).
Peer connections were unstable (dropped immediately).
Graph sync stayed false because no channels existed.
Wallet unlock and chain sync issues on AWS after resets.

On aws:

1. Reset LND completely:
  
```bash
docker compose -f docker-compose.regtest.aws.yml down
docker volume rm agent-bitcoin_lnd-data -f
docker compose -f docker-compose.regtest.aws.yml up -d lnd
```

2. Create fresh wallet + unlock:

```bash
docker exec -it agent-payment-decision-lnd lncli --lnddir=/home/lnd/.lnd --network=regtest create
# (enter password, create new seed)
docker exec -it agent-payment-decision-lnd lncli --lnddir=/home/lnd/.lnd --network=regtest unlock
```

3. Mine a solid chain:
```bash
docker exec bitcoind bitcoin-cli -regtest -rpcuser=btc -rpcpassword=btc generatetoaddress 100 "$(docker exec bitcoind bitcoin-cli -regtest -rpcuser=btc -rpcpassword=btc getnewaddress)"
```

On Mac:
 
4. Get funding address and receive funds from AWS (you did this with the address ending in r4mc).

5. Finally open the channel (using the new AWS pubkey after reset):
```bash
# Connect
docker compose -f docker-compose.regtest.mac.yml exec -it agent-bitcoin-lnd \
  lncli --lnddir=/home/lnd/.lnd --network=regtest connect \
  <AWS_PUBKEY>@3.84.7.71:9735

sleep 2

# Open channel
docker compose -f docker-compose.regtest.mac.yml exec -it agent-bitcoin-lnd \
  lncli --lnddir=/home/lnd/.lnd --network=regtest openchannel \
  --node_key <AWS_PUBKEY> \
  --local_amt 500000 \
  --push_amt 100000 \
  --min_confs 0
```

6. Mine 6+ blocks on AWS to confirm the funding transaction.

This cleared all stale state, gave both nodes fresh wallets and confirmed funds, and allowed the channel to open successfully.The key was full resets on both sides + fresh wallets + sufficient mining.You now have a working bidirectional Lightning channel between Mac (SDK) and AWS (backend). 


# Restart backend on AWS

# 1. Kill the old session (if any)
tmux kill-session -t backend 2>/dev/null || true

# 2. Start fresh backend session
tmux new-session -d -s backend 'cd ~/agent-bitcoin && PYTHONPATH=. uv run python backend/main.py'

# 3. (Optional) Check it's running
tmux ls

# 4. View live logs (optional)
tmux attach -t backend
# (Press Ctrl+B then D to detach)

# Project Outline for autonomous AI agent swarm

Step-by-Step Implementation PlanPhase 1: Infrastructure Preparation (1–2 days)Duplicate the Mac counterparty setupCreate a second LND node on the Mac (or a second container).
Recommended: Add agent-bitcoin-1-lnd service in docker-compose.regtest.mac.yml.
Give it its own volume (agent-bitcoin-1-lnd-data) and different ports (e.g., 9737, 10011).

Update startup/shutdown scriptsModify startup-mac.sh to start both agent-bitcoin-lnd and agent-bitcoin-1-lnd.
Create shutdown-mac.sh that stops both cleanly.

Connect the new nodeConnect agent-bitcoin-1-lnd to the AWS agent-payment-decision-lnd.
Open a channel from AWS → agent-bitcoin-1-lnd with sufficient push amount (similar to what we did for the first node).

Phase 2: Agent Abstraction Layer (2–3 days)Create a base Agent classIn a new folder agents/, create a clean Python class structure.
BaseAgent class that handles:Connection to its own LND node
Creating invoices on the AWS backend
Paying invoices (from its own LND)
Checking balances

Implement two concrete agentsAgentBitcoin (existing logic)
AgentBitcoin1 (new, almost identical but points to the second LND container)

Centralize configurationUse environment variables or a config file so each agent knows:Its own LND container name / lnddir
Backend URL
Fee settings

Phase 3: Swarm Coordination Logic (1–2 days)Create a simple Swarm OrchestratorNew script: swarm/sequential_swarm.py
It should:Initialize both agents
Run payments sequentially:python

for agent in [agent_bitcoin, agent_bitcoin_1]:
    invoice = agent.create_invoice(amount=5000)
    success = agent.pay_invoice(invoice.payment_request)
    fee_success = agent.send_fee()   # or call backend /send-fee

Add verification stepAfter both payments:Check Lightning balances on AWS
Check on-chain fee transactions on AWS bitcoind / LND
Print a clean summary report

Phase 4: Testing & Validation (1–2 days)Create a dedicated swarm testtests/test_two_agent_swarm.py
Run the sequential payment flow multiple times
Assert that:Both invoices were created
Both payments succeeded
Fees were sent to the Bitcoin wallet

Add logging and observabilityLog every step with clear agent names ([agent-bitcoin] / [agent-bitcoin-1])
Record TXIDs and payment hashes for traceability

Phase 5: Documentation & Future-Proofing (Ongoing)Document the swarm architectureCreate a simple docs/swarm_architecture.md
Explain roles, communication flow, and how to add new agents

Prepare for scalingDesign the BaseAgent class so adding agent-bitcoin-2, agent-bitcoin-3, etc. is trivial
Consider moving toward a message queue (Redis / RabbitMQ) or simple event bus later for true autonomy

Recommended Order of WorkPriority
Task
Estimated Time
Dependencies
1
Add agent-bitcoin-1-lnd container
1 day
None
2
Fund + connect new node
½ day
Task 1
3
Create BaseAgent + two agents
2–3 days
Task 2
4
Build sequential swarm script
1–2 days
Task 3
5
Add verification + test script
1 day
Task 4
6
Documentation
½ day
Task 5

Refined Step-by-Step PlanPhase 1: Add the Second Agent Container on Mac (1 day)Update docker-compose.regtest.mac.yml  Add a new service agent-bitcoin-1-lnd (copy of agent-bitcoin-lnd but with different ports and volume)

Update startup-mac.sh  Start both LND containers

Update shutdown-mac.sh  Stop both cleanly

Fund and connect the new node  Get pubkey of new agent  
Open channel from AWS → new agent with push amount (5M sats)  
Mine blocks to confirm

Phase 2: Create Agent Abstraction (2 days)Create agents/base_agent.py  Common class with methods: create_invoice(), pay_invoice(), get_balance()

Create agents/agent_bitcoin.py and agents/agent_bitcoin_1.py  Inherit from base, point to their respective LND containers

Update .env or config to map agent names to container names

Phase 3: Swarm Orchestrator (1–2 days)Create swarm/sequential_two_agent_swarm.py  Initialize both agents
Run sequential payments
Call backend /send-fee after each payment

Create tests/test_two_agent_swarm.py  Run the swarm and verify:Both payments succeeded
Fees were sent to Bitcoin wallet
Final balances updated correctly

Phase 4: Verification & Polish (1 day)Test the full swarm multiple times
Add clear logging with agent names
Document the current swarm setup

