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

<!-- Step 4: move/expand from README (PyPI, source, uv, optional LangChain deps). -->

## Configuration

<!-- Step 4: env vars, backend URL if applicable, API keys (XAI_API_KEY), what SDK users must set vs operator-only. -->

## Quick start

<!-- Step 4: expand README mini example (create invoice, pay, check result). -->

## Python client API

<!-- Step 4: create_client, AgentBitcoinClient methods, models (Invoice, PaymentResult, balances), public exports from agent_bitcoin. -->

## Transaction fees and limits

<!-- Step 4: full rules — 1000 sat fee, 2000 sat minimum, net to recipient; implementer-focused. README keeps short summary. -->

## Errors and exceptions

<!-- Step 4: AgentBitcoinError hierarchy, when they surface, how to handle. -->

## LLM agents

<!-- Step 4: from README — PaymentDecisionAgent, BitcoinLNDAgent, prompts.py, Grok defaults, Ollama. -->

## HTTP Backend API

<!-- Step 4: from README Backend API + docs/api.md — base URL, endpoints table, example requests for agents. -->

## Examples

<!-- Step 4: from README Examples — basic_usage, ollama, grok, full agents, payment_decision, agent_api. -->

## Troubleshooting (client-side)

<!-- Step 4: common SDK issues (min amount, missing key, backend unreachable). Point node/channel issues to docs/backend.md. -->

---

## Related docs

| Doc | Audience |
|-----|----------|
| [README.md](README.md) | Product overview, fees summary, links |
| [docs/backend.md](docs/backend.md) | Operators: regtest, AWS/Mac, LND, channels |
| [examples/](examples/) | Runnable scripts |

---

*Scaffold only (step 2). Content fills in step 4 after README is slimmed to a hub (step 3).*
