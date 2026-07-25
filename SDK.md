# Agent-Bitcoin SDK

**Audience:** Application and AI-agent developers who want to send and receive Lightning payments using the Python package.

**Not covered here:** AWS/Mac regtest operations, Docker, LND admin, AMIs, security groups. See [docs/backend.md](docs/backend.md).

**Product overview:** See [README.md](README.md).

---

## Table of contents

1. [Installation](#installation)
2. [Configuration](#configuration)
3. [Quick start](#quick-start)
4. [Python client API](#python-client-api)
5. [Transaction fees and limits](#transaction-fees-and-limits)
6. [Errors and exceptions](#errors-and-exceptions)
7. [LLM agents](#llm-agents)
8. [HTTP Backend API](#http-backend-api)
9. [Examples](#examples)
10. [Troubleshooting (client-side)](#troubleshooting-client-side)

---

## Installation

### Requirements

- Python **3.10+**
- A reachable Lightning setup for your environment (typically LND via the project’s Docker-based regtest stack, or your own node wiring)
- Optional: [Ollama](https://ollama.com/) or an [xAI](https://x.ai/) API key for LLM agents

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

### Optional dependencies for LLM agents

Core package already pulls in LangChain xAI/Ollama-related deps in `pyproject.toml`. If you install minimally or hit import errors:

```bash
uv add langchain-core langchain-xai langchain-ollama
# or: pip install langchain-core langchain-xai langchain-ollama
```

---

## Configuration

The Python client loads environment variables via `python-dotenv` (typically a `.env` in the working directory).

### Client fee / limit settings

| Variable | Default | Purpose |
|----------|---------|---------|
| `FEE_WALLET_ADDRESS` | (none) | On-chain address for `collect_transaction_fee()` |
| `FEE_AMOUNT_SATS` | `1000` | Fee amount for `collect_transaction_fee()` |
| `MIN_PAYMENT_SATS` | `2000` | Minimum `amount_sats` for `create_invoice()` |
| `MAX_PAYMENT_SATS` | `1000000` | Shared max for invoices and agent pays |
| `MAX_INVOICE_SATS` | same as max | Optional override for backend only |
| `PAYMENT_DECISION_MAX_SATS` | same as max | Optional override for agent only |

### LND connection (models / env helpers)

`LightningConfig.from_env()` reads:

| Variable | Default | Purpose |
|----------|---------|---------|
| `LND_GRPC_HOST` | `localhost` | Host |
| `LND_GRPC_PORT` | `10009` | Port |
| `LND_TLS_CERT_PATH` | (none) | TLS cert path |
| `LND_MACAROON_PATH` | (none) | Macaroon path |

See also [.env.example](.env.example) for container/macaroon names used in regtest.

**Note:** The current default `LNDClient` talks to LND primarily via `docker exec` + `lncli` on the payment-decision container (`agent-payment-decision-lnd`), for the project’s regtest layout. Operator setup for that stack is in [docs/backend.md](docs/backend.md).

| Variable | Default | Purpose |
|----------|---------|---------|
| `LND_NETWORK` | `regtest` | Network passed to `lncli` |
| `AGENT_BITCOIN_ALLOW_MAINNET` | unset | Must be `1` to allow `LND_NETWORK=mainnet` (safety latch) |

### LLM agents

| Variable | Purpose |
|----------|---------|
| `XAI_API_KEY` | API key for Grok (`ChatXAI`) payment-decision agents |

You can also pass `api_key=` into the agent constructors.

### HTTP backend (separate process)

When using `backend/main.py` (FastAPI), fee collection uses:

| Variable | Default | Purpose |
|----------|---------|---------|
| `FEE_SATS` | `1000` | On-chain fee amount |
| `FEE_ADDRESS` | (none) | Destination for `/send-fee` |

Base URL is typically `http://localhost:8000` or `http://<aws-public-ip>:8000`.

---

## Quick start

```python
from agent_bitcoin import create_client

client = create_client()

# Amount must be >= MIN_PAYMENT_SATS (default 2000)
invoice = client.create_invoice(memo="Test payment", amount_sats=5000)

result = client.pay_invoice(invoice.payment_request)

if result.success:
    print(f"Paid successfully")
    print(f"Hash: {result.payment_hash}")
    print(f"Status: {result.status}")
else:
    print(f"Payment failed: {result.status}")
```

Requires a working LND path (see [docs/backend.md](docs/backend.md) for the AWS + Mac regtest workflow).

---

## Python client API

### Factory

```python
from agent_bitcoin import create_client, AgentBitcoinClient

client = create_client()  # -> AgentBitcoinClient
```

### `AgentBitcoinClient` methods

| Method | Returns | Description |
|--------|---------|-------------|
| `create_invoice(memo, amount_sats, expiry_seconds=3600)` | `Invoice` | Creates a Lightning invoice. Raises `ValueError` if `amount_sats < min_payment_sats`. |
| `pay_invoice(payment_request)` | `PaymentResult` | Pays a BOLT11 invoice. Raises `ValueError` if request is empty. |
| `send_onchain(address, amount_sats)` | `OnChainSendResult` | On-chain send. |
| `collect_transaction_fee()` | `OnChainSendResult` | Sends `FEE_AMOUNT_SATS` to `FEE_WALLET_ADDRESS`. Raises `RuntimeError` if address unset. |
| `get_balance()` | `LightningBalance` | On-chain wallet balances (string fields from LND). |
| `get_channel_balance()` | `ChannelBalance` | Local/remote channel balances (ints). |

### Models (`agent_bitcoin.models`)

```python
Invoice:
  payment_request: str
  r_hash: str
  payment_hash: str

PaymentResult:
  success: bool
  payment_hash: Optional[str]
  amount: int = 0
  status: str = "UNKNOWN"

OnChainSendResult:
  txid: str
  success: bool = True

LightningBalance:
  total_balance: str
  confirmed_balance: str
  unconfirmed_balance: str

ChannelBalance:
  local_balance: int
  remote_balance: int

LightningConfig:
  host, port, tls_cert_path, macaroon_path, ...
  LightningConfig.from_env(env_file=".env")
```

### Public exports (`agent_bitcoin`)

```python
from agent_bitcoin import (
    create_client,
    AgentBitcoinClient,
    LightningConfig,
    AgentBitcoinError,
    InvoiceCreationError,
    PaymentError,
    MacaroonError,
    InsufficientBalanceError,
    NoRouteError,
    PaymentDecisionAgent,
    create_payment_decision_agent,
    create_grok_payment_decision_agent,
    PaymentDecision,
)
```

Also useful:

```python
from agent_bitcoin.models import Invoice, PaymentResult, LightningBalance, ChannelBalance
from agent_bitcoin.agents.payment_decision import (
    BitcoinLNDAgent,
    create_grok_bitcoin_lnd_agent,
)
```

---

## Transaction fees and limits

| Rule | Default | Configurable via |
|------|---------|------------------|
| Fixed fee | **1,000 sats** | `FEE_AMOUNT_SATS` / backend `FEE_SATS` |
| Minimum invoice/payment amount | **2,000 sats** | `MIN_PAYMENT_SATS` |
| Maximum invoice/payment amount | **1,000,000 sats** | `MAX_PAYMENT_SATS` (shared) |

### Semantics

1. When a payment of **X** sats is approved, **1,000 sats** is the platform fee.
2. **X − 1000** sats are intended for the recipient over Lightning.
3. The **1,000 sat fee** is collected **on-chain** to the configured fee address (`collect_transaction_fee()` or backend `/send-fee`).

### Example (2,000 sats)

| | Sats |
|--|------|
| Original amount | 2,000 |
| Fee (on-chain) | 1,000 |
| Net to recipient (Lightning) | 1,000 |

### Implementer notes

- `create_invoice` enforces the minimum at the client.
- Fee collection is **not** always automatic inside `pay_invoice`; use `collect_transaction_fee()` or the backend `/send-fee` path (and your own orchestration) depending on architecture.
- HTTP agents often call the **Backend API** so fee policy is enforced in one place.

---

## Errors and exceptions

Base type: `AgentBitcoinError`.

| Exception | Typical meaning |
|-----------|-----------------|
| `LNDException` | LND / `lncli` failure |
| `InvoiceCreationError` | Invoice creation failed |
| `PaymentError` | Payment failed |
| `MacaroonError` | Macaroon load/use problem |
| `InsufficientBalanceError` | Not enough balance |
| `NoRouteError` | No Lightning route |
| `ConfigurationError` | Bad or missing config |
| `ValueError` | Client validation (min amount, empty pay req, etc.) |
| `RuntimeError` | e.g. missing `FEE_WALLET_ADDRESS` on fee collect |

```python
from agent_bitcoin import create_client, PaymentError, AgentBitcoinError

client = create_client()
try:
    client.pay_invoice(payment_request)
except ValueError as e:
    print("Bad request:", e)
except AgentBitcoinError as e:
    print("Lightning error:", e)
```

---

## LLM agents

Intelligent helpers live under `agent_bitcoin/agents/` and use prompts from `agent_bitcoin/prompts.py`.

### Available agents

| Agent | Purpose | Default model | Module |
|-------|---------|---------------|--------|
| `PaymentDecisionAgent` | Conservative gatekeeper: approve/reject paying an invoice | `grok-4-1-fast-reasoning` | `payment_decision.py` |
| `BitcoinLNDAgent` | Counterparty-oriented prompts (invoices / cooperative LND ops) | `grok-4-1-fast-reasoning` | `payment_decision.py` |

### Payment decision (Grok)

The agent **never executes payments**. It only returns a decision. Callers must run `pay_invoice` (or not) after checking the result.

**Coded policy runs first** (no LLM if blocked):

| Env / constructor | Default | Effect |
|-------------------|---------|--------|
| `MIN_PAYMENT_SATS` / `min_sats` | 2000 | Reject below minimum |
| `PAYMENT_DECISION_MAX_SATS` / `max_sats` | **1000000** (shared default) | Hard reject above max |
| `PAYMENT_DECISION_CONFIRM_ABOVE_SATS` / `confirm_above_sats` | unset | If set, amounts above return `CONFIRM_REQUIRED` (human must approve) |

`decision` values: `PAY`, `REJECT`, `CONFIRM_REQUIRED`.

```python
from agent_bitcoin import create_grok_payment_decision_agent

agent = create_grok_payment_decision_agent()  # uses XAI_API_KEY or api_key=
# or with explicit policy:
# agent = create_grok_payment_decision_agent(max_sats=50_000, confirm_above_sats=20_000)

result = agent.decide_payment(
    {
        "amount_sats": 5000,
        "memo": "Service payment",
        "payment_request": invoice.payment_request,
    },
    context="Agreed work item #42",
)
# result["decision"] -> "PAY" | "REJECT" | "CONFIRM_REQUIRED"
# result["blocked_by_policy"] -> True if hard policy applied
# result["reasoning"] -> policy or model text
```

Only auto-pay when `result["decision"] == "PAY"`. Treat `CONFIRM_REQUIRED` as a human gate.

`create_payment_decision_agent` is an alias of `create_grok_payment_decision_agent`.

Custom model:

```python
from agent_bitcoin.agents.payment_decision import PaymentDecisionAgent

agent = PaymentDecisionAgent(model="grok-3", api_key=None, max_sats=50_000)
```

### Bitcoin LND agent (Grok)

```python
from agent_bitcoin.agents.payment_decision import create_grok_bitcoin_lnd_agent

lnd_agent = create_grok_bitcoin_lnd_agent()
prompt = lnd_agent.create_invoice_prompt(amount_sats=5000, memo="Demo")
```

### Customizing prompts

Edit the centralized templates:

```text
agent_bitcoin/prompts.py
```

- `PAYMENT_DECISION_SYSTEM_PROMPT`
- `PAYMENT_DECISION_DEFAULT_INSTRUCTIONS`
- `BITCOIN_LND_SYSTEM_PROMPT`

Example system prompt direction:

```python
PAYMENT_DECISION_SYSTEM_PROMPT = """You are a cautious financial agent for autonomous AI systems.
You should only approve payments that are:
- Under 10,000 sats by default
- Related to previously agreed work
- From trusted agents

Be conservative and explain your reasoning clearly."""
```

### Ollama (local models)

Use LangChain’s `ChatOllama` in your app and/or the provided examples. The shipped `PaymentDecisionAgent` class is wired to `ChatXAI` (Grok). For Ollama, prefer:

- [examples/ollama_example.py](examples/ollama_example.py) — tools + local model
- [examples/full_intelligent_agent_ollama.py](examples/full_intelligent_agent_ollama.py)

```bash
ollama run llama3.2
uv run python examples/ollama_example.py
```

Popular local models: `llama3.2`, `llama3`, `mistral`, `phi3`, `qwen2.5`.

### Grok models (as used in the project)

- `grok-4-1-fast-reasoning` (default in agents)
- `grok-3`
- Others available via xAI as the platform evolves

---

## HTTP Backend API

The FastAPI app in `backend/main.py` is an HTTP layer over LND for agents that prefer JSON over the Python client.

- **Default base URL:** `http://localhost:8000`
- **Remote:** `http://<host>:8000`
- **Interactive docs:** `GET /docs`
- **OpenAPI:** `GET /openapi.json`

### Authentication (required)

Protected routes require `AGENT_BITCOIN_API_KEY` on the server and one of:

```http
X-API-Key: <your-key>
```

```http
Authorization: Bearer <your-key>
```

| Status | Meaning |
|--------|---------|
| `401` | Missing or wrong key |
| `503` | Server has no `AGENT_BITCOIN_API_KEY` configured |

Generate (example): `openssl rand -hex 32` — store in a password manager and host `.env`, never in git.

### Amount limits (server-side)

| Env | Default | Applies to |
|-----|---------|------------|
| `MIN_PAYMENT_SATS` | 2000 | `POST /invoices` |
| `MAX_INVOICE_SATS` / `MAX_PAYMENT_SATS` | 1000000 | `POST /invoices` |
| `MAX_FEE_SEND_SATS` | 100000 | `POST /send-fee` |

### Why use it

- Single control point for Lightning ops
- Fee collection hooks (`FEE_SATS`, `FEE_ADDRESS`)
- API key gate on balances and payments
- Easy for any language / HTTP agent

### Endpoints (as implemented)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/` | No | Liveness only |
| `GET` | `/balance` | Yes | Lightning + on-chain balances |
| `POST` | `/invoices` | Yes | Create invoice (`memo`, `amount_sats`) |
| `POST` | `/pay` | Yes | Pay invoice (`payment_request`, optional `fee_limit_sats`) |
| `POST` | `/send-fee` | Yes | On-chain fee send (`amount_sats` optional override) |

> **Note:** Use **`POST /pay`** (not `/payments`).

### Create invoice

`POST /invoices`

```json
{
  "memo": "Payment for service",
  "amount_sats": 5000
}
```

Example response fields:

```json
{
  "payment_request": "lnbcrt...",
  "r_hash": "...",
  "amount_sats": 5000,
  "memo": "Payment for service"
}
```

### Pay invoice

`POST /pay`

```json
{
  "payment_request": "lnbcrt...",
  "fee_limit_sats": 500
}
```

### Balance

`GET /balance` — returns Lightning and on-chain payloads plus `total_sat` when successful.

### Send fee

`POST /send-fee`

```json
{
  "amount_sats": 1000
}
```

Requires `FEE_ADDRESS` (and positive amount).

### Minimal HTTP example

```python
import os
import requests

base = "http://localhost:8000"
headers = {"X-API-Key": os.environ["AGENT_BITCOIN_API_KEY"]}

r = requests.post(
    f"{base}/invoices",
    json={"memo": "agent job", "amount_sats": 5000},
    headers=headers,
    timeout=60,
)
r.raise_for_status()
invoice = r.json()

pay = requests.post(
    f"{base}/pay",
    json={"payment_request": invoice["payment_request"]},
    headers=headers,
    timeout=120,
)
pay.raise_for_status()
print(pay.json())
```

See also [examples/agent_api_example.py](examples/agent_api_example.py).

---

## Examples

Runnable scripts under [examples/](examples/):

| Script | Description |
|--------|-------------|
| `basic_usage.py` | Create client |
| `ollama_example.py` | LangChain tools + Ollama + SDK client |
| `grok_example.py` | Grok-oriented example |
| `full_intelligent_agent_ollama.py` | Fuller autonomous flow (Ollama) |
| `full_intelligent_agent_grok.py` | Fuller autonomous flow (Grok) |
| `payment_decision_agent.py` | Payment decision agent demo |
| `agent_api_example.py` | HTTP wrapper around the backend API |

### Basic

```bash
uv run python examples/basic_usage.py
```

### Ollama (local, no xAI key)

```bash
uv add langchain-core langchain-ollama   # if needed
ollama run llama3.2
uv run python examples/ollama_example.py
```

### Grok

```bash
uv add langchain-xai   # if needed
export XAI_API_KEY="xai-your-key-here"
uv run python examples/grok_example.py
```

### Full intelligent agents

```bash
uv run python examples/full_intelligent_agent_ollama.py

export XAI_API_KEY="xai-your-api-key-here"
uv run python examples/full_intelligent_agent_grok.py
```

### Payment decision agent

```bash
ollama run llama3.2   # if the example uses Ollama
uv run python examples/payment_decision_agent.py
```

### Backend HTTP from an agent

```bash
# Backend must be running (see docs/backend.md)
uv run python examples/agent_api_example.py
```

---

## Troubleshooting (client-side)

| Symptom | Likely cause | What to do |
|---------|--------------|------------|
| `Minimum payment is 2000 sats` | Amount below `MIN_PAYMENT_SATS` | Use ≥ 2000 or lower env (not recommended for production policy) |
| `FEE_WALLET_ADDRESS not configured` | Fee collect without env | Set `FEE_WALLET_ADDRESS` in `.env` |
| `Payment request is required` | Empty BOLT11 | Pass full `payment_request` |
| Import errors for `langchain_xai` / `langchain_ollama` | Optional stack missing | `uv add` / `pip install` those packages |
| Grok agent fails auth | Missing API key | `export XAI_API_KEY=...` or pass `api_key=` |
| `lncli` / Docker errors from client | LND container not running or wrong name | Start stack per [docs/backend.md](docs/backend.md) |
| HTTP 400 from `/pay` | No route, locked wallet, insufficient channel balance | Check peers, channels, unlock; see backend.md |
| Example uses `/payments` but server 404 | Path drift | Use **`POST /pay`** |

Node, channel, sync, and AWS/Mac issues → **[docs/backend.md](docs/backend.md)**.

---

## Related docs

| Doc | Audience |
|-----|----------|
| [README.md](README.md) | Product overview, fee summary, links |
| [docs/backend.md](docs/backend.md) | Operators: regtest, AWS/Mac, LND, channels |
| [examples/](examples/) | Runnable scripts |
| [CHANGELOG.md](CHANGELOG.md) | Releases |

---

*SDK guide for library end users. Operator runbooks stay in docs/backend.md.*
