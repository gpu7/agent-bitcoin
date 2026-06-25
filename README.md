# Agent-Bitcoin

**Bitcoin Lightning network payments for autonomous AI Agents.**

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

```bash
# 1. Install dependencies
uv add langchain-core langchain-ollama

# 2. Make sure Ollama is running and has a model
ollama run llama3.2

# 3. Run the example
uv run python examples/ollama_example.py
```

File: examples/ollama_example.py

This example demonstrates:

Creating Lightning invoices
Paying Lightning invoices  
Checking wallet balance
Full LangChain tool integration with a local LLM

### Payment Decision Agent

File: examples/payment_decision_agent.py

```bash
# Make sure Ollama is running with a model
ollama run llama3.2

# Run the example
uv run python examples/payment_decision_agent.py
```
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

### Testing
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

---



