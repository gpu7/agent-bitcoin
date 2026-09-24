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

- Autonomous AI agent swarms
- [Agent-to-Agent Lightning Network payments](#agent-to-agent-lightning-network-payments)
- [Agent-to-Merchant Lightning Network payments](#agent-to-merchant-lightning-network-payments)
- [Bitcoin final settlement layer](#bitcoin-final-settlement-layer)
- Python SDK for autonomous AI agent swarms
- [Nostr for agents](#nostr-for-agents)
- [AI models for agents](#ai-models-for-agents)

---

## Agent-to-Agent Lightning Network payments

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

## Agent-to-Merchant Lightning Network payments

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

## Bitcoin Final Settlement layer

---

## Nostr for agents

Agents use [Nostr](https://nostr.org/) for identity, communication, censorship resistance, signatures, encryption and discovery.

- **Agents get a unique ID.** Each agent is assigned a unique cryptographic secp256k1 keypair (npub & nsec), esentially, a unique ID.  Agents in an agent swarm can easily and uniquely identify one another via their public npub.  Agents never share or expose their private encrypted secret nsec.

- **Agents communicate with Nostr events.** Agents within agent swarms communicate with one-another via Nostr cryptographically signed events. Every accepted event must verify an agents ID, signature and pubkey. Events with sensitive payloads (i.e. invoices, etc.) are encrypted.

- **Agents use Nostr relays.** Agents publish signed events once. If one relay dies or censors, events simply move to another relay. Thus, agents use redundant and reliable communication channels to exchange events.

- **Agents can use Nostr encryption.** Agents can choose encrypted events for sensitive information.  Encryption hides the inside of a message so a Nostr  relay can store and forward it without reading invoices, prompts or agent state. Signing still proves which agent sent a message.

- **Agents use Nostr for discovery.** Agents can find one-another by publishing a signed “I can do X” event. Nostr relays find matching agents for that event.  There is no need for a central directory.

---

## AI models for agents

Currently, you may choose default Grok or Ollama models for Agent-to-Agent payments or Agent-to-Merchant payments.

Agent-to-Agent Lightning Network payments: Grok or Ollama model
Example: examples/agent-to-agent-pay.md

Agent-to-Merchant Lightning Network payments: Grok or Ollama model
Example: examples/agent-to-merchant-pay.md

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
