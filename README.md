# Agent-Bitcoin

[![Test PyPI](https://img.shields.io/badge/Test%20PyPI-0.2.0-blue)](https://test.pypi.org/project/agent-bitcoin/)
[![Python](https://img.shields.io/badge/Python-3.10%20|%203.11%20|%203.12-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![GitHub Release](https://img.shields.io/github/v/release/gpu7/agent-bitcoin)](https://github.com/gpu7/agent-bitcoin/releases/latest)
[![GitHub Repo](https://img.shields.io/badge/GitHub-gpu7/agent--bitcoin-black)](https://github.com/gpu7/agent-bitcoin)

<br>

## Lightning Bitcoin payments for autonomous AI Agents

A lightweight Python SDK that enables AI agents to send and receive Lightning/Bitcoin payments.

| Doc | Who it's for |
|-----|----------------|
| **[SDK.md](SDK.md)** | App & agent developers (install, API, fees, LLM agents, HTTP API, examples) |
| **[docs/backend.md](docs/backend.md)** | Operators (AWS/Mac regtest, LND, channels, diagnostics) |

---

## Features

- Simple, agent-friendly API
- Create and pay Lightning invoices
- Built-in 1,000 sat transaction fee model
- Support for regtest, testnet, and mainnet
- Pydantic models and structured errors
- Easy integration with LangChain, CrewAI, AutoGen, and similar frameworks
- Balance checks (Lightning and on-chain)
- Optional LLM agents for payment decisions and counterparty flows

---

## Transaction fee model

Agent-Bitcoin uses a **transparent fixed fee** to support intermediary infrastructure:

| Rule | Value |
|------|--------|
| Fixed fee | **1,000 sats** per payment |
| Minimum payment | **2,000 sats** |

**How it works**

1. For an approved payment of `X` sats, **1,000 sats** is the transaction fee.
2. **`X − 1000` sats** go to the recipient over Lightning.
3. The **1,000 sat fee** is sent **on-chain** to the configured fee wallet.

**Example (2,000 sats)**

| | Sats |
|--|------|
| Original amount | 2,000 |
| Fee (on-chain) | 1,000 |
| Net to recipient (Lightning) | 1,000 |

Full implementer rules, client usage, and edge cases: **[SDK.md](SDK.md#transaction-fees-and-limits)**.

---

## Installation

### From TestPyPI

```bash
pip install -i https://test.pypi.org/simple/ agent-bitcoin==0.2.0
```

### From source

```bash
git clone https://github.com/gpu7/agent-bitcoin.git
cd agent-bitcoin
uv sync
```

More detail (optional LangChain / Grok / Ollama deps): **[SDK.md](SDK.md#installation)**.

---

## Quick start

```python
from agent_bitcoin import create_client

client = create_client()

invoice = client.create_invoice(memo="Test payment", amount_sats=5000)
result = client.pay_invoice(invoice.payment_request)

if result.success:
    print(f"Paid {result.amount} sats")
```

This assumes a configured Lightning backend (local or remote).
For the full client API, agents, HTTP API, and examples → **[SDK.md](SDK.md)**.
For running the AWS + Mac regtest stack → **[docs/backend.md](docs/backend.md)**.

---

## Security

Agent-Bitcoin is developed with security in mind:

- **Secrets stay out of the repository** — API keys, wallet material, and host credentials are configured via environment and local ops practice, not committed source
- **Least privilege** for network and node access (admin/API/RPC not left open to the whole internet in operator deployments)
- **Conservative defaults** for payment amounts and fees (see [SDK.md](SDK.md))
- **Authenticated payment APIs** — backend balance/invoice/pay routes require an API key when deployed
- **Bounded autonomous payment decisions** — hard amount limits in code before any LLM approval
- **Regtest-first** development; mainnet is never the implicit default

Report vulnerabilities privately — see **[SECURITY.md](SECURITY.md)** (scope, practices, disclosure). Do not open public issues for security reports.

---

## Documentation

| Link | Description |
|------|-------------|
| [SDK.md](SDK.md) | Python SDK, LLM agents, Backend HTTP API, examples |
| [docs/backend.md](docs/backend.md) | Regtest workflow, startup/shutdown, LND, channels |
| [examples/](examples/) | Runnable sample scripts |
| [CHANGELOG.md](CHANGELOG.md) | Release history |
| [SECURITY.md](SECURITY.md) | Security policy and vulnerability reporting |

---

## Repository

- GitHub: https://github.com/gpu7/agent-bitcoin
- TestPyPI: https://test.pypi.org/project/agent-bitcoin/
- PyPI: Coming soon

---

## License

MIT License — see [LICENSE](LICENSE).

---

## Support

Richard Casey
richardcaseyhpc@protonmail.com
+1 970-980-5975
