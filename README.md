<br>

<p align="center">
  <img src="./images/dark-factory-image.jpg" alt="Dark Factory Agent Bitcoin" width="700"/>
</p>

<br>

[![PyPI](https://img.shields.io/pypi/v/agent-bitcoin)](https://pypi.org/project/agent-bitcoin/)
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
| **[docs/mainnet-pilot.md](docs/mainnet-pilot.md)** | Mainnet pilot **Phases 0–8** (ops complete; ≤50k dual-node) |
| **[docs/public-routing-loop.md](docs/public-routing-loop.md)** | Topology A′: public channels + first Loop Out done; capital HOLD; Autoloop off |

---

## Features

- Simple, agent-friendly API (`create_client`)
- Create and pay Lightning invoices (**payee** creates, **payer** pays)
- **Explicit invoice quotes** for independent agents (`create_invoice_quote` / `pay_invoice_quote`) — one BOLT11 for the requested amount
- LND transports: **docker** `lncli` (lab default) or **gRPC** + macaroon ([docs/lnd-client.md](docs/lnd-client.md))
- Networks: **regtest** (default), **signet**, testnet; **mainnet** only with explicit latch
- Pydantic models and structured errors
- Optional LLM **payment decision** agent (PAY / REJECT / CONFIRM — never executes pays)
- Balance checks (Lightning and on-chain)
- Operator tooling: dual-node health, SCB backup, daily ops ([docs/index.md](docs/index.md))
- Optional **Aperture L402** paid JSON tool suites (Bitcoin / Lightning / Nostr, typically **100 sats**) — [docs/l402-tools.md](docs/l402-tools.md) (operators: [docs/l402-aperture.md](docs/l402-aperture.md))
- Optional **Nostr** agent identity and **NWC** wallets (not required for Lightning pays) — [Nostr (agent identity)](#nostr-agent-identity)

---

## Roles: payee and payer

| Role | Does |
|------|------|
| **Payee** | Creates the invoice (and quote); receives **X sats** over Lightning |
| **Payer** | Validates quote / budget; pays the BOLT11 amount (plus optional Lightning routing fee limit) |

Either physical node (AWS agent LND or Mac counterparty LND) can act as payee or payer depending on who creates the invoice.

---

## Payment amounts

There is **no platform / transaction fee**. A requested payment of **X** sats creates and pays a BOLT11 for **exactly X**. Lightning **routing** fees (the `fee_limit_sats` / `routing_fee_limit_sats` cap) are separate and still apply when paying.

| Rule | Default |
|------|--------|
| Platform / transaction fee | **None** |
| Minimum Lightning invoice amount | **100 sats** (`MIN_PAYMENT_SATS`) |

For independent agents, prefer **`create_invoice_quote`** so the payer sees `amount_sats` / `total_cost_sats` without shared env. Details: **[SDK.md](SDK.md#transaction-fees-and-limits)**.

There is no `collect_transaction_fee` / `POST /send-fee`. Mainnet **pays** stay latch-gated — see [docs/mainnet-pilot.md](docs/mainnet-pilot.md).

---

## L402 tool suites

Paid JSON on Aperture `:8081`. Unpaid calls return **402**; finance/Nostr paths are typically **100 sats** (`l402_pay.py --price 100`). Not a public catalog (operator `/32`). Agent guide: **[docs/l402-tools.md](docs/l402-tools.md)**. Operators: [docs/l402-aperture.md](docs/l402-aperture.md).

**Bitcoin** (L1 fee / fullness / FX; skip if Lightning-only): `GET /paid/finance/mempool-feerate` — on-chain sat/vB fee bands; `mempool-backlog` — mempool tx count and fullness; `fee-for-vsize` — total fee for vbyte size; `confirm-target` — wait window to sat/vB; `btc-usd` — BTC/USD pass-through mark.

**Lightning** (decode → preflight → path-hint → pay): `POST /paid/finance/ln-invoice-decode` — inspect BOLT11 amount and dest; `ln-invoice-preflight` — allow/reject invoice policy reasons; `ln-path-fee-hint` — AWS LND QueryRoutes fee hint.

**Nostr** (local, no relay): `POST /paid/nostr/event-verify` — check NIP-01 id and sig; `npub-decode` — bech32 npub/note to hex (`nsec` rejected); `zap-receipt-inspect` — inspect kind-9735 zap receipt.

---

## Nostr (agent identity)

Lightning invoice/pay does **not** require Nostr. L402 **finance** tools do not use it. Paid local checks (event-verify, npub-decode, zap-receipt-inspect) are in the [L402 Nostr suite](docs/l402-tools.md#nostr-suite) at 100 sats. Nostr is an optional layer so agents can have a public identity and, if you opt in, a limited wallet connection.

**Identity.** An agent can hold a Nostr keypair as a stable public ID (a username that is a cryptographic key). Two agents can recognize each other without a central account server.

**Phase A.** Proof-of-concept: two agents talk over Nostr only. No Lightning node required. See [`examples/nostr_agent_poc.py`](examples/nostr_agent_poc.py) and [docs/nostr-agent-identity.md](docs/nostr-agent-identity.md).

**Phase B.** Agents can send signed payment requests and offers on that same bus, then use Lightning invoices/pay when LND is in the picture. See [`examples/nostr_phase_b_payment.py`](examples/nostr_phase_b_payment.py).

**Phase C.** Signing policy lives in a separate local signer process. The agent itself is not supposed to hold the secret key (`nsec`). See [`examples/nostr_phase_c_signer.py`](examples/nostr_phase_c_signer.py).

**NWC (NIP-47).** For automatic wallets, the agent holds a Nostr Wallet Connect URI rather than an LND admin macaroon. The payment-decision agent still only says PAY / REJECT; settlement goes through NWC after PAY. See [docs/nwc-automatic-wallets.md](docs/nwc-automatic-wallets.md).

**NIP-46.** Optional bunker demo for remote signing: [`examples/nip46_bunker_demo.py`](examples/nip46_bunker_demo.py).

**Install.** Optional extra (`pynostr`): `uv sync --extra nostr` or `pip install 'agent-bitcoin[nostr]'`. Prefer **Python 3.12** for wheels ([SDK.md](SDK.md#nostr-agent-identity-phase-a-poc)).

More: [SDK.md](SDK.md#examples) (Nostr examples list), [docs/nostr-agent-identity.md](docs/nostr-agent-identity.md), [docs/nwc-automatic-wallets.md](docs/nwc-automatic-wallets.md).

---

## Installation

### From PyPI

```bash
pip install agent-bitcoin
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
# quote.payment_request, amount_sats, total_cost_sats (equals amount)

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
- **Regtest / signet first** for lab work; mainnet is never the implicit default (pilot ops complete under ≤50k dual-node — [docs/mainnet-pilot.md](docs/mainnet-pilot.md))

Report vulnerabilities privately — see **[SECURITY.md](SECURITY.md)**. Do not open public issues for security reports.

---

## Documentation

| Link | Description |
|------|-------------|
| [SDK.md](SDK.md) | Python SDK, quotes, fees, LLM agents, Backend HTTP API |
| [docs/index.md](docs/index.md) | Full docs index (signet, mainnet readiness, backup, health, liquidity) |
| [docs/backend.md](docs/backend.md) | Regtest dual-node workflow |
| [docs/signet.md](docs/signet.md) | Signet dual-node lab |
| [docs/mainnet-pilot.md](docs/mainnet-pilot.md) | Mainnet pilot Phases 0–8 (ops complete; ≤50k dual-node) |
| [docs/public-routing-loop.md](docs/public-routing-loop.md) | Public routing + Loop on AWS (topology A′; HOLD) |
| [docs/l402-tools.md](docs/l402-tools.md) | L402 paid JSON tools for agents (Bitcoin / Lightning / Nostr) |
| [docs/l402-aperture.md](docs/l402-aperture.md) | Aperture L402 operator runbook |
| [docs/nostr-agent-identity.md](docs/nostr-agent-identity.md) | Nostr identity (Phases A–C) |
| [docs/nwc-automatic-wallets.md](docs/nwc-automatic-wallets.md) | NWC / NIP-47 automatic wallets |
| [examples/](examples/) | Runnable sample scripts (incl. signet product path) |
| [CHANGELOG.md](CHANGELOG.md) | Release history |
| [SECURITY.md](SECURITY.md) | Security policy and vulnerability reporting |

---

## Repository

- GitHub: https://github.com/gpu7/agent-bitcoin
- PyPI: https://pypi.org/project/agent-bitcoin/

---

## License

MIT License — see [LICENSE](LICENSE).

---

## Support

Richard Casey<br>
richardcaseyhpc@protonmail.com<br>
+1 970-980-5975
