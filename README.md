<br>

<p align="center">
  <img src="./images/dark-factory-image.jpg" alt="Dark Factory Agent Bitcoin" width="700"/>
</p>

<br>

[![GitHub Repo](https://img.shields.io/badge/GitHub-gpu7/agent--bitcoin-black)](https://github.com/gpu7/agent-bitcoin)
[![GitHub Release](https://img.shields.io/github/v/release/gpu7/agent-bitcoin)](https://github.com/gpu7/agent-bitcoin/releases/latest)
[![Python](https://img.shields.io/badge/Python-3.10%20|%203.11%20|%203.12-blue)](https://www.python.org/)
[![PyPI](https://img.shields.io/pypi/v/agent-bitcoin)](https://pypi.org/project/agent-bitcoin/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

<br>

## Lightning Bitcoin payments for autonomous AI Agents

A Python SDK and Merchant endpoint that enables autonomous AI agents to transact via Lightning Network payments with Bitcoin final settlement.

---

## Features

- [Agentic Finance](#agentic-finance)
- [Autonomous AI Agent Swarms](#autonomous-ai-agent-swarms)
- [Agent-to-Agent Lightning Network Payments](#agent-to-agent-lightning-network-payments)
- [Agent-to-Merchant Lightning Network Payments](#agent-to-merchant-lightning-network-payments)
- [Merchant Endpoints](#merchant-endpoints)
- [Bitcoin Final Settlement Layer](#bitcoin-final-settlement-layer)
- [Python SDK](#python-sdk)
- [Nostr for Agents](#nostr-for-agents)
- [AI Models for Agents](#ai-models-for-agents)

---

## Agentic Finance

Agentic finance is financial transactions and market activity carried out by autonomous goal-directed AI agents.  Human mediation is minimal or non-existent. Agents perceive data, make decisions under policy, and execute transactions (pay, invoice, reconcile, route a trade) with minimal or no human prompting.  

**The term is used in two overlapping ways:**

- Enterprise finance ops — specialized agents own jobs such as invoicing, matching trades, controls, and close, across existing systems. Humans set limits and handle exceptions. 
  
- Markets and payments — autonomous or semi-autonomous agents take part in information management, monitoring, and execution, so their actions can move money or prices. 

Currently, in practice, many agentic systems are semi-autonomous where some policies, spend caps, and an operator intervene in some financial activites.  But agentic swarms are increasingly taking over these functions. 

**Key benefits**

- Throughput — routine payments and ops run continuously, 24/7  
- Smaller tickets — agents can settle amounts that are too small or too frequent for human approval, i.e. micropayments  
- Division of labor — one agent retrieves, one checks policy, one pays (a swarm), instead of a single program performing all steps  
- Audit trail — if each transaction is an invoice, a signed message, or a logged decision, audit review is more transparent  
- Working-capital velocity — the same locked balance can support many completed transfers per day (Lightning is one example payment rail)

---

## Autonomous AI Agent Swarms

An agent swarm is a set of cooperating software agents that jointly execute a workflow. Each agent has a distinct cryptographic identity. They coordinate with one another via signed messages, allocate tasks, and can authorize payments without a human approving each transfer. In this design the nodes and wallets remain under an operator; autonomy refers to the execution loop after the agent infrastructure is funded and started.

**Agent-to-Agent settlement on Lightning**

Payment is a Lightning invoice issued by one agent and discharged by another. Value moves by updating balances inside a pre-funded channel, typically in seconds. The Bitcoin base chain is not used for each micropayment. Instead, Bitcoin Layer 1 is used when a Lightning channel is opened, closed, or a dispute is enforced.  This represents final settlement of the net position between agents.

**Why pair agent swarms with Lightning**  

- Low-latency payment and settlement between agents  
- Micropayments between agents  
- Bilateral, auditable funds transfer — query, invoice, and payment — without a pooled omnibus account  
- Separation of roles among agents (retrieve, decide, pay)  
- One payment rail for peer invoices and Merchant endpoints

Currently, to protect funds, some human constraints remain in place (but may be relaxed or transferred to agents in the future). A human operator must capitalize Lightning nodes, maintain inbound and outbound channel liquidity and impose spend limits. Public multipath routing of very small amounts is unreliable unless counterparties have provisioned an appropriate channel.  

**Velocity of money**

Velocity of money is the turnover rate of sats between paying agents. In an agent swarm with Lightning payments, the same channel inventory can settle a Merchant call, then a peer invoice, then another call, many times per day, without a new block per payment. An agent swarm uses Lightning payments as a high-turnover working-capital layer.  Thus, agent swarms dramatically increase the velocity of money.

---

## Agent-to-Agent Lightning Network Payments

In an autonomous AI agent swarm, agents can make direct Lightning Network payments to one-another.  A payee agent **invoices** a payer agent; the payer agent **pays that invoice** over the Lightning Network.

- Each agent has its own Nostr ID (`npub`). The payee sends an invoice as an encrypted Nostr event to the payer’s ID (`npub`).
- **Who is who:**
  - **Payee:** AWS invoice LND (`agent-payment-decision-lnd-mainnet`). It creates a ~100 sat invoice. It does not autopay.
  - **Payer:** Client LND (`agent-bitcoin-lnd-mainnet`). It pays over a direct private channel.
- **Whether the payer sends sats:**
  - **No AI model (`--no-llm`):** Pay as soon as the invoice arrives.
  - **Grok or Ollama AI model:** The **payer** asks the model “Should I pay this invoice?” YES → pay; NO → no payment. Needs `XAI_API_KEY` for Grok, or a running Ollama model.

Example:  

- [examples/agent-to-agent-pay.md](examples/agent-to-agent-pay.md) (Nostr invoice + optional Grok/Ollama model)

---

## Agent-to-Merchant Lightning Network Payments

Agents in two-agent or eight-agent swarms negotiate with one-another to determine who pays the Merchant endpoint.  They agree on a single payer. Then, that agent makes a Lightning payment to the Merchant and reads the results.

- Each agent has its own Nostr ID (`npub`). They publish Nostr signed events so peers can negotiate who pays the Merchant.
- There are several negotiating styles to choose from to demonstrate how agents work together.
- **Who pays:**
  - **Hash score (default):** The highest score from the combination "`npub` + invoice id + round" pays. Ties go to the larger `npub`.
  - **Solve a simple puzzle (`fee-sats`):** The first correct “vbytes × sat/vB” pays.
  - **Grok vote (two agents only):** Agents (Alice and Bob) each ask Grok one question: “Should I spend ~100 sats on this Merchant service?” Grok answers YES or NO and gives a short reason.
    - If **both say NO**, nobody pays and there is no payment to Merchant.
    - If **one says YES**, that agent pays the Merchant.
    - If **both say YES**, they use a hash score to pick one payer.
    - Needs a Grok account and `XAI_API_KEY`.
- **What they buy:** See [Merchant Endpoints](#merchant-endpoints).

Examples:
- [examples/agent-swarm-merchant-2.md](examples/agent-swarm-merchant-2.md) (two agents)
- [examples/agent-swarm-merchant-8.md](examples/agent-swarm-merchant-8.md) (eight agents)

---

## Merchant Endpoints

The Merchant endpoints serve up a variety of services that might be of interest to autonomous AI agent swarms. Agents make Lightning Network payments directly to Merchant endpoints. After a valid payment, the Merchant returns a small JSON file, in agent machine-readable format.

Currently, the fee rate for Merchant services is 100 sats, but can be set to any value. The Merchant host URL (`http://3.90.159.146:8081`) is open to allowed IP's but not the entire Internet.  The URL is hosted on AWS but could be hosted on other platforms as well.  (There are demo services that return "hello world", PDF files and PNG files for 1,000 sats, but these are mostly for testing purposes).

Currently, the Merchant provides a short list of Bitcoin, Lightning and Nostr services, but almost any kind of service could be added as a paid endpoiont.

**Bitcoin services**:

- `GET /paid/finance/mempool-feerate` — check current transaction fees (high / medium / low priority, sat per vbyte)
- `GET /paid/finance/mempool-backlog` — check how full the mempool is
- `GET /paid/finance/fee-for-vsize` — total fee in sats for a transaction of that many virtual bytes
- `GET /paid/finance/confirm-target` — “I can wait this long” (`minutes` or `target=fast|medium|slow`) → recommended sat per vbyte
- `GET /paid/finance/btc-usd` — current BTC price in USD

**Lightning services**:

- `POST /paid/finance/ln-invoice-decode` — parse a Lightning BOLT11 invoice: get amount in sats, expiry, and payee pubkey
- `POST /paid/finance/ln-invoice-preflight` — should we pay this invoice? (expired, too small, too large, wrong network)
- `POST /paid/finance/ln-path-fee-hint` — estimate the Lightning routing fee for an invoice (AWS looks up a route; it does not pay)

**Nostr services**:

- `POST /paid/nostr/event-verify` — check that a Nostr events ID and signature match its pubkey (`npub`)
- `POST /paid/nostr/npub-decode` — turn an `npub` (or `note`) into hex; refuse `nsec` private keys. Agents compare hex, verify events, or call other tools that expect hex. This service does that conversion.

Documents:
- Agent menu: [docs/l402-tools.md](docs/l402-tools.md)
- How to run Aperture: [docs/l402-aperture.md](docs/l402-aperture.md)
- Known client connecting in: [docs/l402-client-pack.md](docs/l402-client-pack.md)

---

## Bitcoin Final Settlement layer

The Bitcoin blockchain network is used as the final settlement layer for Lightning payments between agents.  Bitcoin is treated as a Layer-1 protocol and Lightning is treated as a Layer-2 protocol.  

For autonomous AI agent swarms, the payment and settlement protocol is:

- **Open a Lightning channel.** Operator (human-in-the-loop) opens a Lightning channel on behalf of agents.  Currently, this is for safety reasons to protect funds. Creates 2-of-2 multisig UTXO in the Bitcoin blockchain.  Funds Lightning channel for agents.
- **Make Lightning payments.** Agents pay one another via the Lightning channel.
- **Close the Lightning channel.** Operator (human-in-the-loop) closes the Lightning channel on behalf of agents.  Again, this is for safety reasons to protect funds.  
- **Update Bitcoin ledger.** Spend 2-of-2 multisig UTXO.  Payout fund balances to each party's Bitcoin address. Final settlement of Lightning payment balances in the Bitcoin blockchain network. 

---

## Nostr for Agents

Agents use [Nostr](https://nostr.org/) for identity, communication, censorship resistance, signatures, encryption and discovery.

- **Agents get a unique ID.** Each agent is assigned a unique cryptographic secp256k1 keypair (npub & nsec), esentially, a unique ID.  Agents in an agent swarm can easily and uniquely identify one another via their public npub.  Agents never share or expose their private encrypted secret nsec.

- **Agents communicate with Nostr events.** Agents within agent swarms communicate with one-another via Nostr cryptographically signed events. Every accepted event must verify an agents ID, signature and pubkey. Events with sensitive payloads (i.e. invoices, etc.) are encrypted.

- **Agents use Nostr relays.** Agents publish signed events once. If one relay dies or censors, events simply move to another relay. Thus, agents use redundant and reliable communication channels to exchange events.

- **Agents can use Nostr encryption.** Agents can choose encrypted events for sensitive information.  Encryption hides the inside of a message so a Nostr  relay can store and forward it without reading invoices, prompts or agent state. Signing still proves which agent sent a message.

- **Agents use Nostr for discovery.** Agents can find one-another by publishing a signed “I can do X” event. Nostr relays find matching agents for that event.  There is no need for a central directory.

---

## AI Models for Agents

Currently, you may choose default Grok or Ollama models for Agent-to-Agent payments or Agent-to-Merchant payments.  

Agent-to-Agent Lightning Network payments: Grok or Ollama model  
Example: examples/agent-to-agent-pay.md  

Agent-to-Merchant Lightning Network payments: Grok or Ollama model  
Example: examples/agent-to-merchant-pay.md  

---

## Python SDK

Agent-Bitcoin services are available via a Python SDK.

Install from [PyPI](https://pypi.org/) or from this repo.

**PyPI (library only):**

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install agent-bitcoin
# optional: pip install 'agent-bitcoin[nostr]'
python -c "import agent_bitcoin; print(agent_bitcoin.__version__)"
```

This does not download examples/ or docs/. If you need those files use the repo clone below.

**GitHub repo (SDK + examples + docs):**

```bash
git clone https://github.com/gpu7/agent-bitcoin.git
cd agent-bitcoin
git pull origin main
uv sync --python 3.12
uv run python -c "import agent_bitcoin; print(agent_bitcoin.__version__)"
```

**Nostr / swarm scripts:**

```bash
uv venv -p 3.12 .venv-nostr
uv pip install --python .venv-nostr/bin/python -e '.[nostr]'
```

The import package is `agent_bitcoin`.

- `create_client()` / `AgentBitcoinClient` — create invoices, pay BOLT11, read on-chain and channel balances (talks to your LND).
- `L402Client` — call a Merchant URL: handle HTTP 402, pay the invoice, retry, return JSON.
- `L402Challenge` / `parse_www_authenticate` — read the Lightning invoice out of a 402 response.
- `Invoice`, `InvoiceQuote`, `PayerDecisionInputs` — invoice and “should I pay?” data.
- `LightningConfig` — how the client finds LND (network, container, transport).
- `DEFAULT_MIN_PAYMENT_SATS`, `DEFAULT_MAX_PAYMENT_SATS`, `DEFAULT_L402_PRICE_SATS` — floor (100), caps, typical Merchant price.
- `PaymentDecisionAgent` / `create_grok_payment_decision_agent()` — Grok or Ollama YES/NO gate before a pay.
- `PaymentDecision` — PAY / REJECT / CONFIRM_REQUIRED.
- Exceptions (`PaymentError`, `InsufficientBalanceError`, `NoRouteError`, …) — typed failures instead of raw lncli text.

**Documentation and source code:**   

Full developer reference for SDK: [SDK.md](SDK.md)  
Python package source: `agent_bitcoin/`    

---

## Installation

### From github repo source

```bash
git clone https://github.com/gpu7/agent-bitcoin.git
cd agent-bitcoin
uv sync
```

### From PyPI

```bash
pip install agent-bitcoin==27.1.0
```

---

## Documentation and Examples

To review documents and examples for this repo, see the **`docs/`** folder or **`examples/`** folder.

---

## Security

Agent-Bitcoin is developed with security in mind:

- **Secrets stay out of the repository.** API keys, wallet material, and host credentials are configured via environment and local ops practice, not committed source
- **Least privilege.** For network and node access (admin/API/RPC not left open to the whole internet in operator deployments)
- **Conservative defaults.** For payment amounts and fees (see [SDK.md](SDK.md))
- **Authenticated payment APIs.** Backend balance/invoice/pay routes require an API key when deployed
- **Bounded autonomous payment decisions.** Hard amount limits in code before any LLM approval
- **Mainnet kill switches.** For example `AGENT_BITCOIN_ALLOW_MAINNET`, `AGENT_BITCOIN_ALLOW_AUTOPAY`, daily spend caps
- **Operator health checks.** Dual-node signet health, backups ([docs/daily-ops-signet.md](docs/daily-ops-signet.md), [docs/security-hardening.md](docs/security-hardening.md))
- **Regtest / signet first.** For lab work; mainnet is never the implicit default (pilot ops complete under ≤50k dual-node — [docs/mainnet-pilot.md](docs/mainnet-pilot.md))

Report vulnerabilities privately — see **[SECURITY.md](SECURITY.md)**. Do not open public issues for security reports.

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
