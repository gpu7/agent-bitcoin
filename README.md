# Agent-Bitcoin

[![Test PyPI](https://img.shields.io/badge/Test%20PyPI-0.2.0-blue)](https://test.pypi.org/project/agent-bitcoin/)
[![Python](https://img.shields.io/badge/Python-3.10%20|%203.11%20|%203.12-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![GitHub Release](https://img.shields.io/github/v/release/gpu7/agent-bitcoin)](https://github.com/gpu7/agent-bitcoin/releases/latest)
[![GitHub Repo](https://img.shields.io/badge/GitHub-gpu7/agent--bitcoin-black)](https://github.com/gpu7/agent-bitcoin)
[![Code Coverage](https://codecov.io/gh/gpu7/agent-bitcoin/branch/main/graph/badge.svg)](https://codecov.io/gh/gpu7/agent-bitcoin)

<br><br>
**Lightning Bitcoin payments for autonomous AI Agents.**

A lightweight Python SDK that enables AI agents to send and receive Lightning/Bitcoin payments.

---

## Features

- Simple, agent-friendly API
- Create Lightning invoices
- Pay Lightning invoices
- Built-in 1000 sat transaction fee model
- Support for regtest, testnet, and mainnet
- Built-in error handling and Pydantic models
- Easy integration with LangChain, CrewAI, AutoGen, etc.
- Check Lightning and Bitcoin balances
- Autononomously decide to create invoices
- Trigger payments from counterparty agents
- Complete full transactions

---

## Transaction Fee Model

Agent-Bitcoin uses a **transparent fixed transaction fee** to support the intermediary infrastructure:

### Fee Details
- **Fixed Fee**: 1,000 sats per payment
- **Minimum Payment Amount**: 2,000 sats
- **How it works**:
  1. When a payment of `X` sats is approved, **1,000 sats** is deducted as the transaction fee.
  2. The remaining `X - 1000` sats are sent via Lightning to the recipient (Agent-Bitcoin).
  3. The **1,000 sat fee** is then sent **on-chain** (via Bitcoin) to Agent-Bitcoin’s on-chain wallet.

This model ensures sustainable operation of the payment routing infrastructure while remaining very low-cost for users.

### Example (2,000 sats payment)
- Original Amount: 2,000 sats
- Transaction Fee: 1,000 sats (sent on-chain)
- Net to Recipient: 1,000 sats (Lightning)

You can monitor fee deposits using:
```bash
docker exec agent-bitcoin-lnd lncli --network=regtest walletbalance
```

---

## Installation

### From PyPi
```bash
pip install agent-bitcoin
```

### From Source
```bash
git clone https://github.com/yourusername/agent-bitcoin.git
cd agent-bitcoin
uv sync
```

## Quick Start
```python
from agent_bitcoin import create_client

client = create_client()

# Create an invoice
invoice = client.create_invoice(memo="Test payment", amount_sats=5000)

# Pay an invoice
result = client.pay_invoice(invoice.payment_request)

if result.success:
    print(f"✅ Paid {result.amount} sats")
    print(f"Preimage: {result.preimage}")
```

---

## AI agent prompts

- The Agent-Bitcoin SDK includes intelligent agents powered by Large Language Models (LLMs). These agents help make autonomous decisions around payments and Lightning operations.

### Available agents

| Agent                | Purpose                                                 | Default Moel | File                |
|:---------------------|:--------------------------------------------------------|:-------------|:--------------------|
| PaymentDecisionAgent | Decides whether to approve or reject Lightning payments | Grok         | payment_decision.py |
| BitcoinLNDAgent      | Handles invoice creation and counterparty operations.   | Grok         | payment_decision.py |

### How to Change the Prompts

- The recommended way to customize prompts is through the centralized prompt file:

```python
# Edit this file to change prompts for all agents
agent_bitcoin/prompts.py
```

### Example – Customizing the Payment Decision prompt:

```python
# In agent_bitcoin/prompts.py
PAYMENT_DECISION_SYSTEM_PROMPT = """You are a cautious financial agent for autonomous AI systems.
You should only approve payments that are:
- Under 10,000 sats by default
- Related to previously agreed work
- From trusted agents

Be conservative and explain your reasoning clearly."""
```

### Supported AI Models

- 1) Grok (xAI) – RecommendedGrok models are used by default for intelligent decision-making.

```python
from agent_bitcoin.agents import create_grok_payment_decision_agent

# Default (recommended)
agent = create_grok_payment_decision_agent()

# Or specify a different Grok model
agent = create_grok_payment_decision_agent(model="grok-3")
```

- Available Grok models (as of now):
  - grok-4-1-fast-reasoning (default in the SDK)
  - grok-3
  - grok-beta


- 2) Ollama (Local Models)

You can also use local models via Ollama for privacy or offline use:

```python
from langchain_ollama import ChatOllama
from agent_bitcoin.agents import create_payment_decision_agent

llm = ChatOllama(model="llama3.2", temperature=0.2)
agent = create_payment_decision_agent(llm=llm)
```

- Popular Ollama models that work well:

  - llama3.2
  - llama3
  - mistral
  - phi3
  - qwen2.5

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

## Examples

### Basic Usage

```bash
uv run python examples/basic_usage.py
```

### LangChain + Ollama Example (Local, No API Key Required)

This is the recommended example for most users who want to integrate Agent-Bitcoin into AI agents without paying for API credits.

File: examples/ollama_example.py

```bash
# 1. Install dependencies
uv add langchain-core langchain-ollama

# 2. Make sure Ollama is running and has a model
ollama run llama3.2

# 3. Run the example
uv run python examples/ollama_example.py
```

---

### Grok example

File: examples/grok_example.py

```bash
# Make sure you have langchain-xai installed
uv add langchain-xai

# Set your API key (one time)
export XAI_API_KEY="xai-your-key-here"

# Run the example
uv run python examples/grok_example.py
```

---

### Full intelligent agent, Ollama version

File: examples/full_intelligent_agent_ollama.py

```bash
uv run python examples/full_intelligent_agent_ollama.py
```

#### Example transaction between autonomous agents
- Agent checked balance
- LLM decided to create an invoice for 8000 sats
- Invoice was created via the backend API
- The other node (agent-bitcoin-lnd) automatically paid it
- Payment SUCCEEDED

---

### Full intelligent agent, Grok version

File: examples/full_intelligent_agent_grok.py

```bash
# Install Grok support if not already done
uv add langchain-xai

# Set your xAI API key
export XAI_API_KEY="xai-your-api-key-here"

# Run the example
uv run python examples/full_intelligent_agent_grok.py
```

#### Example transaction between autonomous agents
- 🤖 Grok Autonomous Agent started with goal: Create an invoice for 12000 sats and get it paid by the other agent
- Current balance: 3497010412 sats
- Grok decided: CREATE_INVOICE:12000:Payment request for 12000 sats
- ✅ Invoice created for 12000 sats
- Payment Request: lnbcrt120u1p4yqqn4pp5wvxgwllgr2qpvmwatft0hqqpusc2mfprun3crfgv0wsk7h8fayysdps2psh...
- Payment Hash: 730c877fe81a80166ddd5a56fb8001e430ada423e4e381a50c7ba16f5ce9e909
- ⏳ Simulating payment from counterparty agent...
- Payment result: SUCCEEDED
- Invoice status: unknown

---

### Payment Decision Agent

File: examples/payment_decision_agent.py

```bash
# Make sure Ollama is running with a model
ollama run llama3.2

# Run the example
uv run python examples/payment_decision_agent.py
```

---

### AI Agent calls Backend API

File: examples/agent_api_example.py

```bash
uv run python examples/agent_api_example.py
```

---

## Backend API

The backend serves as the enforcement and payment routing layer for all Lightning operations. The backend/ provides a simple, secure HTTP API layer on top of your Lightning node. It is the recommended way for AI agents to interact with Bitcoin/Lightning.

### Key Features

- Automatic Fee Collection: Every payment made through /payments sends 1,000 sats on-chain to your configured fee address.
- Simple JSON API: Easy for autonomous agents (LangChain, Grok, Ollama, etc.) to use.
- Safety & Control: All Lightning operations go through a single controlled layer.
- Regtest Ready: Works seamlessly in your local regtest environment.

### Why Use the Backend?

- Keeps agents simple and focused on intelligence instead of LND complexity.
- Enforces monetization (fees) consistently.
- Makes it easy to add logging, rate limiting, or business rules later.

- Base URL: http://localhost:8000

### Available endpoints

| Method | Endpoint                   | Description                                   | Notes                             |
|:-------|:---------------------------|:----------------------------------------------|:----------------------------------|
| GET    | `/balance`                 | Get combined Lightning + on-chain balance     | Returns both balances in sats     |
| POST   | `/invoices`                | Create a new Lightning invoice                | Requires `memo` and `amount_sats` |
| POST   | `/payments`                | Pay a Lightning invoice                       | Expects `payment_request` in body |
| POST   | `/send-fee`                | Send collected fee on-chain to Bitcoin wallet | Requires `amount_sat` in body     |
| GET    | `/invoices/{payment_hash}` | Check status of an invoice or payment         | Useful for polling                |
| GET    | `/docs`                    | Swagger UI documentation                      | Interactive API explorer          |
| GET    | `/openapi.json`            | OpenAPI schema                                | For code generation               |

---

## Repository

GitHub: https://github.com/gpu7/agent-bitcoin
TestPyPi: https://test.pypi.org/project/agent-bitcoin/0.2.0/
PyPI: Coming soon

---

## License

MIT License — see LICENSE file.

---

## Support

Richard Casey
richardcaseyhpc@protonmail.com
+1 970-980-5975

---
