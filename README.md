# Agent-Bitcoin

[![Test PyPI](https://img.shields.io/badge/Test%20PyPI-0.2.0-blue)](https://test.pypi.org/project/agent-bitcoin/)
[![Python](https://img.shields.io/badge/Python-3.10%20|%203.11%20|%203.12-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![GitHub Release](https://img.shields.io/github/v/release/gpu7/agent-bitcoin)](https://github.com/gpu7/agent-bitcoin/releases/latest)
[![GitHub Repo](https://img.shields.io/badge/GitHub-gpu7/agent--bitcoin-black)](https://github.com/gpu7/agent-bitcoin)

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

- GitHub: https://github.com/gpu7/agent-bitcoin

- TestPyPi: https://test.pypi.org/project/agent-bitcoin/0.2.0/

- PyPI: Coming soon

---

## License

MIT License — see LICENSE file.

---

## Support

- Richard Casey
- richardcaseyhpc@protonmail.com
- +1 970-980-5975

---
