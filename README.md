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

## Backend API

The backend serves as the enforcement and payment routing layer for all Lightning operations.

### Current State (June 2026)

- Architecture: FastAPI backend + Docker-based LND nodes (regtest).
  
- Containers:agent-payment-decision-lnd (port 10009) — used by the backend agent-bitcoin-lnd (port 10010) — counterparty node for testing.

- Key Endpoints:POST /invoices — Create Lightning invoices (used by AI agents). Built-in Lightning client using docker exec (reliable connection to LND).

- Security & Control:All LND interactions go through the backend (no direct LND access for agents). Wallet and channel management handled by Docker infrastructure. Channel opened between the two nodes for instant routing.

- Fee Handling: Automatic Lightning routing fees + planned 1,000 sat fixed fee logic.

- Status: Fully functional for invoice creation and payment on regtest.

AI agents interact only with the HTTP API — they do not need LND credentials or direct SDK calls to Lightning. 

- Future enhancements planned: balance checks, outgoing payments, payment status, fee collection endpoint, and rate limiting.


---

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

## Testing
```bash
uv run pytest tests/ -v
```

- **Pull request process**:
  1. Fork the repository
  2. Create a feature branch (git checkout -b feature/amazing-feature)
  3. Make your changes
  4. Ensure tests pass
  5. Submit a Pull Request

### Areas We Welcome Help
- Testnet support
- More LangChain / Ollama examples
- Documentation improvements
- Bug reports and feature requests

---

## Support

Richard Casey
richardcaseyhpc@protonmail.com
+1 970-980-5975
---



