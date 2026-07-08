# Agent-Bitcoin

[![Test PyPI](https://img.shields.io/badge/Test%20PyPI-0.1.0-blue)](https://test.pypi.org/project/agent-bitcoin/)
[![Python](https://img.shields.io/badge/Python-3.10%20|%203.11%20|%203.12-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![GitHub Release](https://img.shields.io/github/v/release/gpu7/agent-bitcoin)](https://github.com/gpu7/agent-bitcoin/releases/latest)
[![GitHub Repo](https://img.shields.io/badge/GitHub-gpu7/agent--bitcoin-black)](https://github.com/gpu7/agent-bitcoin)

**Lightning Bitcoin payments for autonomous AI Agents.**

A lightweight Python SDK that enables AI agents to send and receive Bitcoin/Lightning payments trustlessly and programmatically.

---

## Features

- Simple, agent-friendly API
- Create Lightning invoices
- Pay Lightning invoices
- Built-in 1000 sat transaction fee model
- Support for regtest, testnet, and mainnet
- Built-in error handling and Pydantic models
- Easy integration with LangChain, CrewAI, AutoGen, etc.

### Autonomous AI-agent to AI-agent Lightning and Bitcoin transactions

- Check Lightning and Bitcoin balances
- Autononomously decide to create invoices
- Trigger payments from counterparty agents
- Complete full transactions

---
## Project Status

- Network: Currently optimized for regtest
- Next: Moving to testnet after public feedback
- Not yet: Mainnet (security review required)

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
uv sync          # or pip install -e .
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

## Workflow

The current workflow is shown here.  This is the test workflow on regtest.  It is changing frequently during testing.

Note: the AWS backend url changes each time a new AWS agent-bitcoin instance is launched.  Must modify #2 and #3 accordingly.

- 1) On AWS instance: ./startup-aws.sh
- 2) On Mac: ./start-agent-bitcoin-infrastructure-mac.sh regtest 13.218.193.158
- 3) On Mac: uv run python tests/test_aws_integration.py --backend-url http://13.218.193.158:8000

---

## Backend API

The backend serves as the enforcement and payment routing layer for all Lightning operations. The backend/ provides a simple, secure HTTP API layer on top of your Lightning node. It is the recommended way for AI agents to interact with Bitcoin/Lightning.

### Current State (June 2026)

- Architecture: FastAPI backend + Docker-based LND nodes (regtest).
  
- Containers:agent-payment-decision-lnd (port 10009) — used by the backend agent-bitcoin-lnd (port 10010) — counterparty node for testing.

- Key Endpoints:POST /invoices — Create Lightning invoices (used by AI agents). Built-in Lightning client using docker exec (reliable connection to LND).

- Security & Control:All LND interactions go through the backend (no direct LND access for agents). Wallet and channel management handled by Docker infrastructure. Channel opened between the two nodes for instant routing.

- Fee Handling: Automatic Lightning routing fees + planned 1,000 sat fixed fee logic.

- Status: Fully functional for invoice creation and payment on regtest.

AI agents interact only with the HTTP API — they do not need LND credentials or direct SDK calls to Lightning. 

- Future enhancements planned: balance checks, outgoing payments, payment status, fee collection endpoint, and rate limiting.

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

| Method | Endpoint                 | Description                               | Notes                                 |
|:-------|:-------------------------|:------------------------------------------|:--------------------------------------|
| POST   | /invoices                | Create a Lightning invoice                | Requires memo and amount_sats         |
| POST   | /payments                | Pay a Lightning invoice                   | Automatically collects 1,000 sats fee |
| GET    | /balance                 | Get combined Lightning + on-chain balance |                                       |
| GET    | /invoices/{payment_hash} | Check status of an invoice/payment        |                                       |

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

### Recommended Architecture for Agent Swarm

- AWS payment-decision-lnd → Central hub / routing node (manages channels, enforces fees, etc.)
- Mac / other counterparty nodes → Leaf nodes that open channels to the AWS node
- This is a classic hub-and-spoke model, which is ideal for your use case.

## Repository

GitHub: https://github.com/gpu7/agent-bitcoin
PyPI: Coming soon

---

## License

MIT License — see LICENSE file.

---

## Contributing

Thank you for considering contributing to Agent-Bitcoin!

### Development Setup

```bash
git clone https://github.com/gpu7/agent-bitcoin.git
cd agent-bitcoin
uv sync
```

### Code Style

-Formatting: Black
-Linting: Ruff
-Type Checking: Optional (we use Pydantic)

Run checks before submitting:

```bash
uv run ruff check .
uv run black --check .
```

### Project build

File: pyproject.toml

```bash
uv build
```

### Project rebuild

File: pyproject.toml

```bash
# 1. Clean and rebuild
rm -rf dist/ build/ *.egg-info
uv build

# 2. Check distribution
ls -l dist/

# 3. Validate the package (important before PyPI)
uv run twine check dist/*
```

---

## PyPi

### Publish to Test PyPi

https://test.pypi.org/project/agent-bitcoin/

```bash
# Install twine (if not already installed)
uv tool install twine

# Upload to Test PyPI
uv tool run twine upload --repository testpypi dist/*
```

### Test Installing from Test PyPI

```bash
uv pip install --index-url https://test.pypi.org/simple/ agent-bitcoin==0.1.0

uv run python -c "
from agent_bitcoin import create_client
client = create_client()
print('✅ Successfully installed from Test PyPI!')
print('Balance check:', client.get_balance())
"
```

---

## AWS

### Instance type

- Currently using the AWS instance types:
m5d.large
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

---

## Tests

### Test integration of frontend SDK with backend AWS API

File: tests/test_aws_integration.py

```bash
# Basic usage (localhost)
uv run python tests/test_aws_integration.py

# With your AWS backend IP
uv run python tests/test_aws_integration.py --backend-url http://34.204.169.174:8000

# Custom amount
uv run python tests/test_aws_integration.py --backend-url http://34.204.169.174:8000 --amount 10000
```

---

## Misc

### Docker commands to follow log files
```bash
docker compose -f docker-compose.regtest.mac.yml logs -f agent-bitcoin-lnd
docker compose -f docker-compose.regtest.aws.yml logs -f agent-payment-decision-lnd
```

## Support

Richard Casey
richardcaseyhpc@protonmail.com
+1 970-980-5975
---



## Temporary save of commands

Work these into proper sections later.  Just saving these for now.

On AWS

# Start the full backend (bitcoind + LND + API)
./startup-aws.sh

# Check LND status
docker exec -it agent-payment-decision-lnd lncli --lnddir=/home/lnd/.lnd --network=regtest getinfo

# List peers
docker exec -it agent-payment-decision-lnd lncli --lnddir=/home/lnd/.lnd --network=regtest listpeers

On Mac

# Start Mac counterparty node
./startup-mac.sh

# Check LND status
docker compose -f docker-compose.regtest.mac.yml exec -it agent-bitcoin-lnd lncli --lnddir=/home/lnd/.lnd --network=regtest getinfo

# Connect to AWS node (using current IP)
./connect-mac-to-aws.sh 54.87.36.22

OR

# USE THIS ONE
# Connect to AWS node (directly)
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
