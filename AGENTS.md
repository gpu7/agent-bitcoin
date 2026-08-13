# AGENTS.md — Agent-Bitcoin

Project rules for AI coding agents (Grok, Claude, Cursor, etc.) working in this repository.
Keep this file actionable. Prefer links to `README.md`, `docs/`, and `SECURITY.md` over duplicating long docs.

---

## 1. Project overview and goals

**Agent-Bitcoin** is a Python SDK and regtest infrastructure that lets **autonomous AI agents send and receive Lightning Network payments**.

### Goals

- Provide a simple, agent-friendly API for invoices, payments, balances, and fee collection.
- Support intelligent payment decisions via LLMs (Grok by default; Ollama optional).
- Run a split **AWS payment-decision node + Mac counterparty node** architecture on **Bitcoin regtest**.
- Keep fees transparent and low (fixed **21 sat** fee; minimum payment **2,000 sats**).
- Stay secure by default: no real funds in automated flows unless the user explicitly opts into testnet/mainnet.

### Non-goals (unless explicitly requested)

- Custodial production wallets or multi-tenant custody.
- Silent mainnet deployments or automated mainnet payments.
- Replacing full LND ops tooling (use `lncli` / Lightning Labs docs for deep node ops).

### Key paths

| Path | Role |
|------|------|
| `agent_bitcoin/` | Public SDK (client, models, LND wrapper, agents, prompts) |
| `agent_bitcoin/client.py` | High-level `AgentBitcoinClient` + `create_client()` |
| `agent_bitcoin/lightning.py` | LND access via `docker exec` + `lncli` (regtest) |
| `agent_bitcoin/agents/` | LLM agents (`PaymentDecisionAgent`, `BitcoinLNDAgent`) |
| `agent_bitcoin/prompts.py` | **Only** place to edit agent system prompts by default |
| `backend/main.py` | FastAPI backend (invoices, pay, balance, fee) |
| `examples/` | Runnable demos (Grok, Ollama, full flows) |
| `tests/` | Unit/integration tests + `test-suite.md` workflow cases |
| `docker-compose.regtest.aws.yml` / `docker-compose.regtest.mac.yml` | Node stacks |
| `startup-*.sh` / `shutdown-*.sh` / `watch-lnd-sync.sh` | Ops scripts |
| `docs/` | Operator docs (`backend.md`); see also root `SDK.md` / `README.md` |
| Current AWS EIP | Canonical value in `docs/backend.md` → **Current environment** (do not hardcode elsewhere) |

### Runtime agents (product, inside the SDK)

| Agent | Code | Default model | Purpose |
|-------|------|---------------|---------|
| **Payment Decision Agent** | `agent_bitcoin/agents/payment_decision.py` | `grok-4-1-fast-reasoning` | Conservative gatekeeper: PAY / REJECT |
| **Bitcoin LND Agent** | same file (`BitcoinLNDAgent`) | `grok-4-1-fast-reasoning` | Counterparty: invoices, cooperative LND ops |

Prompts live in `agent_bitcoin/prompts.py`. Prefer editing prompts there over scattering prompt strings.

---

## 2. Development sub-agents (personas for this repo)

When work is multi-step or spans concerns, **delegate** using Grok subagents / parallel agents.
Pick the persona that matches the work. Use `general-purpose` for implementation, `explore` for read-only investigation, `plan` for design.

### 2.1 Orchestrator (main session)

- Owns the user goal, PR scope, and final merge readiness.
- Delegates exploration, LND ops, prompt work, tests, and review.
- Does not run real mainnet payments without explicit user approval.
- Keeps secrets out of commits, logs, and chat when possible.

### 2.2 LND Integration Agent

**Responsibilities**

- `agent_bitcoin/lightning.py`, Docker `lncli` wrappers, container names, network flags.
- Regtest sync, wallet unlock, funding, peer connect, channel open.
- AWS/Mac compose files and startup/shutdown scripts.
- Backend FastAPI ↔ LND wiring (`backend/main.py`).

**Capabilities**

- Read/edit LND client code and shell scripts.
- Run diagnostic `docker exec … lncli` / `bitcoin-cli` commands on **regtest only** unless told otherwise.
- Propose safer gRPC paths without breaking the current docker-exec model unless that is the task.

**Do not**

- Hardcode mainnet flags, real seed phrases, or production macaroons into the repo.
- Force-close channels or reset AWS volumes without user confirmation.

### 2.3 Payment Decision Agent (SDK + policy)

**Responsibilities**

- `PaymentDecisionAgent` behavior, decision parsing (`PAY` / `REJECT`), risk policy.
- Fee model consistency (21 sat fee, 2,000 sat minimum) across client, backend, docs, and examples.
- Ensure agents never auto-pay without a clear decision path.

**Capabilities**

- Edit agent classes, factories, and tests around payment approval.
- Align policy text with actual enforcement in code (min amount, fee collection).

### 2.4 Prompt Engineer Agent

**Responsibilities**

- All prompt templates in `agent_bitcoin/prompts.py`.
- Clear system/user message structure for Grok and Ollama.
- Conservative financial tone for payment decisions; cooperative clarity for LND agent.

**Capabilities**

- Tighten prompts for reliability (explicit `PAY` / `REJECT`, amount limits, context fields).
- Avoid dumping secrets, full payment requests, or macaroons into prompts when truncated context is enough.

### 2.5 Backend API Agent

**Responsibilities**

- `backend/main.py` routes: `/`, `/balance`, `/invoices`, `/pay`, `/send-fee`.
- Request/response shapes, retries (e.g. payment retries), env-based fee config.
- Keep API agent-friendly and documented in `SDK.md` (HTTP Backend API) when endpoints change.

### 2.6 Testing Agent

**Responsibilities**

- `tests/test_client.py`, `tests/test_sdk.py`, `tests/test_aws_integration.py`.
- Workflow cases in `tests/test-suite.md` (ABT-001, ABT-002, …).
- Regtest integration smoke paths described in `docs/backend.md`.

**Capabilities**

- Add pytest cases that mock LND where possible; mark live Docker tests clearly.
- Run `uv run pytest` for offline tests; only run AWS/Mac integration when the environment is up.

**Do not**

- Require live mainnet or real money for CI unit tests.
- Skip asserting min-payment / fee invariants when touching payment paths.

### 2.7 DevOps / Regtest Ops Agent

**Responsibilities**

- `startup-aws.sh`, `startup-aws-reset.sh`, `startup-mac.sh`, `shutdown-*.sh`.
- `watch-lnd-sync.sh`, `wait-mac-lnd.sh`, `connect-mac-to-aws.sh`.
- Compose health, bitcoind mining for confirms, wallet↔chain sync issues.

**Rules**

- Prefer **non-destructive** `startup-aws.sh` over `startup-aws-reset.sh`.
- Confirm with the user before full volume resets or long-running remote restarts.
- Document any new required ports (e.g. 8000, 9735, 18443).

### 2.8 Security Agent

**Responsibilities**

- Macaroons, TLS certs, `.env`, API keys (`XAI_API_KEY`, webhook keys), fee wallet addresses.
- Ensure examples never commit real credentials.
- Review payment and on-chain fee send paths for accidental fund movement.

**Rules**

- Never commit `.env`, macaroons, seed phrases, or private keys.
- Prefer env vars and gitignored paths (see `.env.example`).
- Follow `SECURITY.md` for vulnerability handling; no public issue dump of secrets.

### 2.9 Docs Agent

**Responsibilities**

- `README.md`, `docs/*`, `CHANGELOG.md` when behavior changes.
- Keep fee model, workflow steps, and agent tables accurate.
- Prefer short, correct updates over large rewrites.

### 2.10 Code Review Agent

**Responsibilities**

- Review diffs for Lightning safety, fee correctness, Docker network assumptions, and API breaks.
- Flag mainnet risk, missing tests, prompt regressions, and version string drift.

---

## 3. How to invoke sub-agents

### In Grok Build (this environment)

| Intent | How |
|--------|-----|
| Default multi-step work | Main agent may `spawn_subagent` with `subagent_type`: `general-purpose`, `explore`, or `plan` |
| Read-only codebase map | `explore` |
| Implementation plan only | `plan` |
| Implement + edit | `general-purpose` (or main session) |
| Parallel independent tasks | Multiple subagents / workflow fan-out |

**Prompt pattern when delegating**

```text
You are the <Persona Name> for agent-bitcoin.
Repo root: agent-bitcoin (gpu7/agent-bitcoin).
Constraints from AGENTS.md apply (regtest default, no secrets, fee model).
Task: <specific outcome>
Done when: <tests / files / commands>
```

### Product agents (SDK runtime)

```python
from agent_bitcoin import create_client, create_grok_payment_decision_agent
from agent_bitcoin.agents.payment_decision import create_grok_bitcoin_lnd_agent

client = create_client()
decision_agent = create_grok_payment_decision_agent()  # needs XAI_API_KEY
lnd_agent = create_grok_bitcoin_lnd_agent()

invoice = client.create_invoice(memo="demo", amount_sats=2000)
result = decision_agent.decide_payment(
    {
        "amount_sats": 2000,
        "memo": "demo",
        "payment_request": invoice.payment_request,
    },
    context="Unit test payment between agents",
)
```

Examples: `examples/payment_decision_agent.py`, `examples/full_intelligent_agent_grok.py`, `examples/full_intelligent_agent_ollama.py`.

### User phrases that should select a persona

| User says | Prefer |
|-----------|--------|
| "fix LND sync / channel / lncli" | LND Integration + DevOps |
| "change payment policy / approve logic" | Payment Decision + Prompt Engineer |
| "rewrite system prompts" | Prompt Engineer |
| "add API endpoint" | Backend API |
| "add tests / ABT case" | Testing |
| "security review before release" | Security + Code Review |
| "update docs for workflow" | Docs |

---

## 4. Preferred model settings

### Coding sessions (Grok Build)

| Setting | Preference |
|---------|------------|
| Model | `grok-4.5` (session default) |
| Reasoning effort | **high** for LND/payment/security changes; **medium** for docs/examples; **low** for renames/typos |
| Context | Prefer targeted file reads over dumping entire compose logs; summarize long `docker logs` |
| Subagents | Use `explore` to save parent context on large tree walks |

Switch effort: `/effort high|medium|low` or `/model grok-4.5 high`.

### SDK LLM agents (in application code)

| Agent | Default model | Temperature | Notes |
|-------|---------------|-------------|-------|
| PaymentDecisionAgent | `grok-4-1-fast-reasoning` | `0.1` | Deterministic, conservative |
| BitcoinLNDAgent | `grok-4-1-fast-reasoning` | `0.3` | Slightly freer phrasing |
| Ollama alternative | e.g. `llama3.2` | low (≈0.2) | Offline/privacy |

- Do not bump payment-decision temperature without a reason.
- Keep decision output parseable: final **PAY** or **REJECT** must remain detectable.
- API keys via env (`XAI_API_KEY` / LangChain conventions); never hardcode.

---

## 5. Coding conventions

### Language and tooling

- Python **3.10+** (see `requires-python` in `pyproject.toml`).
- Package manager: **`uv`** preferred (`uv sync`, `uv run …`).
- Formatter/linter intent: **Black** + **Ruff** (dev group in `pyproject.toml`).
- Public models: **Pydantic v2**.
- HTTP API: **FastAPI** + **Uvicorn**.
- LLM: **langchain-xai** / **langchain-ollama** as already used.

### Style

- Prefer small, focused modules over large “god” files.
- Keep the public surface stable: export changes go through `agent_bitcoin/__init__.py` and `__all__`.
- Use existing exception types in `agent_bitcoin/exceptions.py` (`PaymentError`, `LNDException`, etc.) instead of bare `Exception` at API boundaries.
- Match surrounding naming: `amount_sats`, `payment_request`, `fee_*`.
- Avoid drive-by refactors unrelated to the task.
- Do not add unsolicited markdown docs; update existing docs when behavior changes.

### LND / Docker patterns

- Default container for payment decision: `agent-payment-decision-lnd`.
- Default network for scripts and client: **`regtest`**.
- Prefer existing `_run(*args)` / `lncli` patterns unless migrating deliberately to gRPC.
- Any change to container names must update compose files, scripts, `.env.example`, and docs together.

### Version strings

Keep these in sync on every tagged release (`RELEASE_CHECKLIST.md`):

- `pyproject.toml` `version`
- `agent_bitcoin/__init__.__version__`
- Git tag (`v.26.0.0` style) and CHANGELOG heading

Do not change version numbers casually mid-feature.

---

## 6. Testing conventions

### Offline / unit

```bash
uv sync
uv run pytest tests/test_client.py tests/test_sdk.py -q
```

- Prefer pure unit tests that do not need Docker.
- Mock `LNDClient` / subprocess where possible.

### Live regtest integration (optional, environment-dependent)

```bash
# After AWS + Mac workflow is up (see docs/backend.md)
uv run python tests/test_aws_integration.py --backend-url http://<aws-ip>:8000
```

- Document required services in the test docstring or CLI help.
- Workflow narrative tests: `tests/test-suite.md` (ABT-001 nominal, ABT-002 underpayment, etc.).

### When you change payments

Always consider:

1. Amount &lt; minimum (2,000 sats) → reject / error.
2. Nominal payment ≥ 2,000 sats → success path.
3. Fee path: 21 sats fee configuration still makes sense.
4. Decision agent PAY/REJECT parsing still works with prompt changes.

### Definition of done (code changes)

- Relevant tests pass (or new tests added).
- No secrets in the diff.
- README / SDK.md / docs/backend.md updated if user-facing workflow or API changed.
- Examples still import public APIs that exist.

---

## 7. Project-specific rules (Lightning, security, networks)

### Networks

| Network | Default for development? | Automation allowed? |
|---------|--------------------------|---------------------|
| **regtest** | **Yes** | Yes (Docker scripts, mining, open channels) |
| testnet | Only if user asks | Careful; real test coins, rate limits |
| **mainnet** | **No** | **Never** without explicit user confirmation every time |

- Do not change default `--network=regtest` to mainnet in code or scripts.
- Treat any mainnet `sendpayment` / `sendcoins` as a **high-risk** action requiring confirmation.

### Fee model (do not silently change)

- Fixed fee: **21 sats** per payment (env overrides may exist: `FEE_AMOUNT_SATS`, `FEE_SATS`).
- Minimum payment: **2,000 sats** (`MIN_PAYMENT_SATS`).
- Typical path: Lightning pay net amount; fee may be collected on-chain to `FEE_WALLET_ADDRESS` / `FEE_ADDRESS`.
- Update client, backend, README, and examples together if the model changes.

### Security

- Never commit: macaroons, TLS keys, wallet seeds, `.env`, cloud API keys, webhook secrets.
- Do not print full macaroon paths with secrets in CI logs if avoidable.
- Payment Decision agent must remain **conservative**; do not “optimize” by auto-approving large amounts.
- On-chain fee sends and Lightning pays are irreversible on real networks—gate them.
- Report vulnerabilities per `SECURITY.md` (private email), not public issues with exploit detail.
- Routine shutdown: volume-preserving scripts only; never default to `down --volumes` or Loop `regtest.sh stop`.
- Incident: contain → rotate keys → revoke macaroons → recover from trusted AMI; details in `docs/backend.md` ops section.

### Infrastructure safety

- Prefer `startup-aws.sh` (persistent) over `startup-aws-reset.sh` (destructive).
- Confirm before: `docker volume` wipes, force channel close, security group / firewall changes on AWS, killing remote bitcoind with unconfirmed work you care about.
- AWS public IPs change across instances—do not hardcode stale IPs into permanent docs or code; use placeholders.

### Dependencies and AI providers

- Prefer existing stack: Pydantic, FastAPI, docker+lncli, LangChain xAI/Ollama.
- When adding AI features, follow project direction (Grok/xAI first; Ollama for local).
- Do not add heavy new frameworks without a clear need.

---

## 8. Common commands cheat sheet

```bash
# Install
uv sync

# Unit tests
uv run pytest -q

# Package import check
uv run python -c "from agent_bitcoin import create_client; print('ok')"

# AWS regtest (on AWS host)
./startup-aws.sh regtest <public-ipv4>
# destructive full reset only when needed:
# ./startup-aws-reset.sh ...

# Mac counterparty
./startup-mac.sh regtest <aws-public-ipv4>
./wait-mac-lnd.sh
# (auto-detects regtest vs signet from the running Mac LND container)

# Backend (typical)
# uvicorn / docker per compose — see docs/backend.md

# Shutdown
./shutdown-aws.sh
./shutdown-mac.sh
```

---

## 9. Git and PR hygiene

- Create a feature branch from current `main` (this worktree may start detached—branch before committing).
- Prefer focused commits; do not commit `.env` or generated macaroons.
- PR description: what / why, regtest steps run, risk notes for payment paths.
- Do not force-push shared `main`; do not amend published commits unless asked.

---

## 10. Quick decision guide

| Situation | Action |
|-----------|--------|
| Unsure if regtest or mainnet | Assume **regtest**; ask before mainnet |
| Touching prompts | Edit `agent_bitcoin/prompts.py` only (unless redesigning agent API) |
| Touching fees/min amount | Update code + env example + README together |
| Failing LND sync | DevOps/LND agent: logs, mining, `watch-lnd-sync.sh` — not random SDK refactors |
| “Make payments smarter” | Payment Decision + Prompt Engineer; keep conservative defaults |
| Broad unknown codebase question | `explore` subagent first |

---

*This file is the source of truth for agent behavior in-repo. Product docs for humans remain in `README.md` and `docs/`.*
