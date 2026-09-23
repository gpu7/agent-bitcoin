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
- Agent-to-Agent Lightning Network payments
- [Agent-to-Merchant Lightning Network payments](#agent-to-merchant-lightning-network-payments)
- Bitcoin final settlement layer
- Python SDK for autonomous AI agent swarms
- [Nostr for agents](#nostr-for-agents)
- [AI models for agents](#ai-models-for-agents)

---

## L402 tool suites

Paid JSON on Aperture `:8081`. Unpaid calls return **402**; finance/Nostr paths are typically **100 sats** (`l402_pay.py --price 100`). Not a public catalog (operator `/32`). Agent guide: **[docs/l402-tools.md](docs/l402-tools.md)**. Operators: [docs/l402-aperture.md](docs/l402-aperture.md).

**Bitcoin** (L1 fee / fullness / FX; skip if Lightning-only): `GET /paid/finance/mempool-feerate` — on-chain sat/vB fee bands; `mempool-backlog` — mempool tx count and fullness; `fee-for-vsize` — total fee for vbyte size; `confirm-target` — wait window to sat/vB; `btc-usd` — BTC/USD pass-through mark.

**Lightning** (decode → preflight → path-hint → pay): `POST /paid/finance/ln-invoice-decode` — inspect BOLT11 amount and dest; `ln-invoice-preflight` — allow/reject invoice policy reasons; `ln-path-fee-hint` — AWS LND QueryRoutes fee hint.

**Nostr** (local, no relay): `POST /paid/nostr/event-verify` — check NIP-01 id and sig; `npub-decode` — bech32 npub/note to hex (`nsec` rejected); `zap-receipt-inspect` — inspect kind-9735 zap receipt.

Demo files (`/paid/hello`, PDFs, PNG) are **1,000 sats**. Lab host: `http://3.90.159.146:8081` (allowlisted).

That section is the menu of paid HTTP tools, not the swarm.It says: Aperture on port 8081 sells small JSON. No payment → 402. Typical price is 100 sats. Only allowlisted IPs can reach the lab host. Details are in docs/l402-tools.md (agents) and docs/l402-aperture.md (you running the gateway).Then it lists three suites:Bitcoin — on-chain fee / mempool / USD mark (GET).  
Lightning — inspect an invoice, policy check, route-fee hint (POST) before someone pays.  
Nostr — verify a signature, decode an npub, inspect a zap receipt (no relay).

Hello/PDF/PNG demos cost 1,000 sats. This is “what sits behind the 402,” not “how Alice and Bob decide who pays.”

---

## Agent-to-Merchant Lightning Network payments

Several agents (two or eight) share one job: **buy one paid JSON** from our mechant. They do not all pay. They agree on a single payer, then that agent pays Lightning and reads the result.

- Each agent has its own Nostr ID (`npub`). They publish signed events so peers can negotiate who pays the merchant.
- **Who pays (pick one mode):**
  - **Hash (default):** highest score from `npub` + invoice id + round pays. Ties go to the larger `npub`.
  - **Puzzle (`fee-sats`):** first correct “vbytes × sat/vB” pays.
  - **LLM gate (two agents only):** each asks Grok YES/NO; only YES agents enter the hash. All NO → no payment. Needs `XAI_API_KEY`. Do not pass `--no-llm`. The vote reason stays on the Mac.
- **Who sends sats:** the Mac LND wallet, over the private channel to AWS. Do not pay from the AWS invoice node (self-pay fails).
- **What they buy:** one L402 URL (example: mempool-feerate `GET`, or path-hint `POST`) at about **100 sats**. Unpaid → `402`; paid → JSON.
- **Mock:** `--offline-bus` uses a local mock relay and fake payment (no mainnet).
- **Live:** start the first role and wait until it is listening; then start the others. Same env in every terminal (`NOSTR_PASSPHRASE`, LND exports, `ALLOW_MAINNET` / `ALLOW_AUTOPAY` on mainnet).

Examples:  
[examples/agent-swarm-merchant-2.md](examples/agent-swarm-merchant-2.md) (two agents)  
[examples/agent-swarm-merchant-8.md](examples/agent-swarm-merchant-8.md) (eight agents)

---

## Nostr for agents

Agents use [Nostr](https://nostr.org/) for identity, communication, censorship resistance, signatures, encryption and discovery.  

- **Agents get a unique ID.** Each agent is assigned a unique cryptographic secp256k1 keypair (npub & nsec), esentially, a unique ID.  Agents in an agent swarm can easily and uniquely identify one another via their public npub.  Agents never share or expose their private encrypted secret nsec.

- **Agents communicate with Nostr events.** Agents within agent swarms communicate with one-another via Nostr cryptographically signed events. Every accepted event must verify an agents ID, signature and pubkey. Events with sensitive payloads (i.e. invoices, etc.) are encrypted. 

- **Agents use Nostr relays.** Agents publish signed events once. If one relay dies or censors, events simply move to another relay. Thus, agents use redundant and reliable communication channels to exchange events.
 
- **Agents can use Nostr encryption.** Agents can choose encrypted events for sensitive information.  Encryption hides the inside of a message so a Nostr  relay can store and forward it without reading invoices, prompts or agent state. Signing still proves which agent sent a message.

- **Agents use Nostr for discovery.** Agents can find one-another by publishing a signed “I can do X” event. Nostr relays find matching agents for that event.  There is no need for a central directory.

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

## Documentation

| Doc | Why |
|-----|-----|
| [SDK.md](SDK.md) | Install + Python client |
| [docs/l402-tools.md](docs/l402-tools.md) | What the paid routes are |
| [docs/l402-client-pack.md](docs/l402-client-pack.md) | Known client: Ubuntu/Neutrino pack, `/32`, private channel |
| [docs/l402-client-pack-script.md](docs/l402-client-pack-script.md) | Same path via `client_pack.py` |
| [docs/l402-external-agent.md](docs/l402-external-agent.md) | How an external agent connects (operator admit) |
| [docs/l402-aperture.md](docs/l402-aperture.md) | Operator: Aperture on our box (self-host the cash register) |

More operator, lab, and swarm docs live under `docs/` and `examples/`.

---

## AI models for agents

Currently, you may choose default Grok or Ollama models for Agent-to-Agent payments or Agent-to-Merchant payments.

Agent-to-Agent Lightning Network payments: Grok or Ollama model  
Example: examples/agent-to-agent-pay.md

Agent-to-Merchant Lightning Network payments: Grok or Ollama model  
Example: examples/agent-to-merchant-pay.md

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
