# Liquidity automation (simple overview)

**Audience:** Operators and anyone reading the roadmap for channel health and rebalancing.
**Agents / SDK:** do **not** call Loop, open/close channels, or rebalance. Payment agents stay on invoice / pay / decide only.

This page is the **simple story** in one place. Deep runbooks live in the linked docs.

| Topic | Detail |
|-------|--------|
| Phase 1 — monitoring | [backend.md](./backend.md) (`check-aws-health.sh`, channel floors) |
| Phase 2 — Autoloop | [loop-autoloop.md](./loop-autoloop.md) (`wire-agent-loopd.sh`, `configure-autoloop-regtest.sh`) |
| Multi-network Loop install | [loop-multi-network.md](./loop-multi-network.md) (`wire-loopd.sh` regtest/signet/mainnet) |
| Security / keys | [SECURITY.md](../SECURITY.md) |

---

## Three questions (Phases 1–3)

| Phase | Question it answers | In one line |
|-------|---------------------|-------------|
| **1** | Are my channels healthy right now? | **Monitoring and floors** — know when inbound/outbound is too low. |
| **2** | Can the system automatically fix liquidity with Loop when outbound gets too high? | **Autoloop on the agent node** — Loop Out to restore inbound (regtest, operator-run). |
| **3** | How do we run this smarter and for real money? | **Better decisions, more tools, production safety** — not just “turn Loop on.” |

---

## Why this exists

The AWS node (`agent-payment-decision-lnd`) is **receive-heavy**: it needs **inbound** capacity (`remote_balance`) so agents and the backend can keep receiving Lightning payments.

- Closing good channels to “fix” imbalance is the wrong default.
- Prefer **keep channels open**, **watch floors**, and when local (outbound) grows too large, **Loop Out** to restore inbound.
- That automation is **infrastructure**, not something the payment SDK or agents should own.

---

## Phase 1 — Monitoring (complete on regtest)

**Question:** Are my channels healthy right now?

**What it does:**

- `./check-aws-health.sh` checks disk, Docker, bitcoind/LND sync, and **per-channel** local/remote balances against floors.
- Warns (or fails, if strict) when outbound or inbound is too low, or when no active channels exist.

**What it does not do:**

- Does not rebalance, open, or close channels.
- Does not call Loop.

**Detail:** [backend.md — channel capacity floors](./backend.md) · script `check-aws-health.sh`

---

## Phase 2 — Autoloop on the agent node (complete on regtest)

**Question:** Can the system automatically fix liquidity with Loop when outbound gets too high?

**What it does:**

- Runs Lightning Labs **Loop Autoloop** (Easy Autoloop / Loop Out) against **`agent-payment-decision-lnd`**, not only the Loop demo `lndclient`.
- Operator wires a dedicated **`agent-loopd`** sidecar, sets fee budget and local-balance target, then can **enable** automation on regtest.
- When **total local** channel balance exceeds the Easy target, Autoloop can dispatch **Loop Out** (subject to Loop min amounts, budget, and active channels).

**What it does not do:**

- Does not run on mainnet from this project’s default guides.
- Does not give agents Loop/channel APIs.
- Idle Autoloop with low local balance is **expected** (nothing to Loop Out).

**Detail:** [loop-autoloop.md](./loop-autoloop.md) · `./wire-agent-loopd.sh` · `./configure-autoloop-regtest.sh`

**Typical regtest flow (high level):**

1. Stack healthy: `./check-aws-health.sh`
2. Loop server path works (`terms` via agent-loopd)
3. `./wire-agent-loopd.sh`
4. `export LOOP_CLI='docker exec -i agent-loopd loop'`
5. `./configure-autoloop-regtest.sh --apply` then, when ready, `--apply --enable`
6. Peers/channels **active** (e.g. Mac → AWS connect)
7. Monitor `listswaps` and health; disable with `--apply --disable` if needed

---

## Phase 3 — Smarter automation and production (later)

**Question:** How do we run this smarter and for real money?

**Direction only (not implemented as a finished package):**

- Richer signals (e.g. Faraday channel productivity), not only raw local/remote balances
- Optional extra liquidity tools (e.g. Lightning Pool)
- Fee accounting / budgets suited to production
- Mainnet design: separate hosts, keys, and hard limits
- Multi-objective “controller” policy beyond Easy Autoloop alone

**Detail (sketch):** end of [loop-autoloop.md](./loop-autoloop.md)

---

## Status (regtest lab)

| Phase | Status |
|-------|--------|
| 1 — Monitoring / floors | **Complete** |
| 2 — Agent Autoloop (wire + configure + enable path) | **Complete** on regtest |
| 3 — Smarter + production | **Future** |

**Dual-node manual liquidity (signet / mainnet pilot topology B):** see [liquidity-topology-b.md](./liquidity-topology-b.md) (mainnet readiness Phase 5). Autoloop remains regtest-lab only for this project’s default guides.

Exact AMI / release tags change over time; treat this table as the **capability** status, not a version number.

---

## What operators run vs what agents run

| Role | Does |
|------|------|
| **Operator** | Health checks, LND unlock, peer connect, `wire-agent-loopd`, Autoloop configure/enable, Loop stack recovery |
| **Payment agent / SDK** | Invoices, pay, decide — **no** Loop, openchannel, closechannel, or rebalance |

---

## Related scripts (cheat sheet)

| Script | Phase | Role |
|--------|-------|------|
| `check-aws-health.sh` | 1 | Health + channel floors |
| `wire-agent-loopd.sh` | 2 | loopd → agent LND |
| `configure-autoloop-regtest.sh` | 2 | Autoloop params / enable / status |
| `startup-aws.sh` / `shutdown-aws.sh` | ops | Stack lifecycle (preserve volumes) |
| `connect-mac-to-aws.sh` | ops | Peer connectivity for live channels |
