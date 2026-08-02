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
| **[SDK.md](SDK.md)** | App & agent developers (install, API, fees, quotes, LLM agents, HTTP API) |
| **[docs/backend.md](docs/backend.md)** | Operators: AWS/Mac **regtest** dual-node lab |
| **[docs/signet.md](docs/signet.md)** | Operators: dual-node **signet** (current pre-mainnet lab) |
| **[docs/mainnet-pilot.md](docs/mainnet-pilot.md)** | Mainnet **readiness** scope only — not go-live |

---

## Features

- Simple, agent-friendly API (`create_client`)
- Create and pay Lightning invoices (**payee** creates, **payer** pays)
- **Explicit invoice quotes** for independent agents (`create_invoice_quote` / `pay_invoice_quote`) — BOLT11 amount plus disclosed platform/transaction fee
- Fixed **platform fee** (transaction fee) model — separate from Lightning **routing** fees
- LND transports: **docker** `lncli` (lab default) or **gRPC** + macaroon ([docs/lnd-client.md](docs/lnd-client.md))
- Networks: **regtest** (default), **signet**, testnet; **mainnet** only with explicit latch
- Pydantic models and structured errors
- Optional LLM **payment decision** agent (PAY / REJECT / CONFIRM — never executes pays)
- Balance checks (Lightning and on-chain)
- Operator tooling: dual-node health, SCB backup, daily ops ([docs/index.md](docs/index.md))

---

## Roles: payee and payer

| Role | Does |
|------|------|
| **Payee** | Creates the invoice (and quote); receives the **invoice amount** over Lightning |
| **Payer** | Validates quote / budget; pays the BOLT11 amount (plus optional routing fee limit) |

Either physical node (AWS agent LND or Mac counterparty LND) can act as payee or payer depending on who creates the invoice.

---

## Transaction fee (platform fee)

Agent-Bitcoin’s **transaction fee** is a fixed **platform fee** (default **1,000 sats**), **not** a Lightning routing fee.

| Rule | Default |
|------|--------|
| Platform / transaction fee | **1,000 sats** (`FEE_AMOUNT_SATS`) |
| Minimum Lightning invoice amount | **2,000 sats** (`MIN_PAYMENT_SATS`) |

**How it works (when fee collection is used)**

1. Payee issues an **invoice quote**: Lightning amount `X` plus disclosed `platform_fee_sats` / `total_cost_sats`.
2. Payer pays **`X` over Lightning** to the payee (full BOLT11 amount).
3. Platform fee is collected **separately on-chain** to `FEE_WALLET_ADDRESS` when you call fee collection (not automatic inside every `pay_invoice`).

For independent agents, prefer **`create_invoice_quote`** so the payer learns the fee without shared env. Details: **[SDK.md](SDK.md#transaction-fees-and-limits)** and the explicit-quote section.

Mainnet pilot: fee collection stays **off** unless explicitly allowed — see [docs/mainnet-pilot.md](docs/mainnet-pilot.md).

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

# Payee: invoice + explicit quote for independent payers
quote = client.create_invoice_quote(memo="Test payment", amount_sats=2000)
# quote.payment_request, amount_sats, platform_fee_sats, total_cost_sats

# Payer: validate / decision inputs, then pay Lightning amount
inputs = client.build_payer_decision_inputs(quote, routing_fee_limit_sats=200)
if inputs.quote_valid:
    result = client.pay_invoice_quote(quote, routing_fee_limit_sats=200)
    if result.success:
        print(f"Paid {result.amount} sats (LN); total_cost was {quote.total_cost_sats}")
```

Bare `create_invoice` / `pay_invoice` remain available for simple lab flows.

Configure LND via env (`LND_NETWORK`, `LND_TRANSPORT=docker|grpc`, container or gRPC cert/macaroon).
Full API → **[SDK.md](SDK.md)**.
Regtest operators → **[docs/backend.md](docs/backend.md)**.
Signet operators → **[docs/signet.md](docs/signet.md)**.

---

## Security

Agent-Bitcoin is developed with security in mind:

- **Secrets stay out of the repository** — API keys, wallet material, and host credentials are configured via environment and local ops practice, not committed source
- **Least privilege** for network and node access (admin/API/RPC not left open to the whole internet in operator deployments)
- **Conservative defaults** for payment amounts and fees (see [SDK.md](SDK.md))
- **Authenticated payment APIs** — backend balance/invoice/pay routes require an API key when deployed
- **Bounded autonomous payment decisions** — hard amount limits in code before any LLM approval
- **Mainnet kill switches** — e.g. `AGENT_BITCOIN_ALLOW_MAINNET`, `AGENT_BITCOIN_ALLOW_AUTOPAY`, daily spend caps
- **Operator health checks** — dual-node signet health, backups ([docs/daily-ops-signet.md](docs/daily-ops-signet.md), [docs/security-hardening.md](docs/security-hardening.md))
- **Regtest / signet first**; mainnet is never the implicit default and is not a completed go-live path

Report vulnerabilities privately — see **[SECURITY.md](SECURITY.md)**. Do not open public issues for security reports.

---

## Documentation

| Link | Description |
|------|-------------|
| [SDK.md](SDK.md) | Python SDK, quotes, fees, LLM agents, Backend HTTP API |
| [docs/index.md](docs/index.md) | Full docs index (signet, mainnet readiness, backup, health, liquidity) |
| [docs/backend.md](docs/backend.md) | Regtest dual-node workflow |
| [docs/signet.md](docs/signet.md) | Signet dual-node lab |
| [docs/mainnet-pilot.md](docs/mainnet-pilot.md) | Mainnet pilot scope (readiness; not go-live) |
| [examples/](examples/) | Runnable sample scripts (incl. signet product path) |
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
