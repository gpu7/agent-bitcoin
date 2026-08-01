# Mainnet pilot scope (Phase 0)

**Status:** Phase 0 — scope only. **No mainnet go-live.**
**Date:** 2026-08-01
**Audience:** Operator (you) and implementers of readiness Phases 1–8.

This document freezes what a **minimal, defensible mainnet pilot** means for agent-bitcoin. Engineering readiness work (gRPC client, limits, backups, security) targets this scope. It does **not** authorize funding a mainnet wallet or autonomous payments.

**Related:** [signet.md](./signet.md) (current lab) · [SECURITY.md](../SECURITY.md) · [liquidity-automation.md](./liquidity-automation.md) · mainnet readiness plan (session)

---

## Pilot goal

Prove that **human-supervised** Lightning payments work on mainnet with the same dual-node mental model as signet:

- Create/pay via product stack (SDK, later gRPC transport)
- One small channel between **your** two nodes
- Bounded loss if something goes wrong
- Clear kill switches and backups

**Success metric (when Phase 8 is approved later):**

- At least **N = 5** successful human-attended mainnet payments via SDK
- Zero critical incidents (or a written postmortem)
- Explicit go/no-go on expanding limits or automation

Until Phase 8, all practice stays on **signet** (or regtest).

---

## Topology B — dual-node Mac ↔ AWS (chosen)

```text
AWS:  agent LND (payment decision / primary funded side)
        │
   Lightning channel (mainnet pilot — small)
        │
Mac:  counterparty LND (bitcoind or other production-grade chain backend)
```

| Role | Host | Lab analogue (signet today) |
|------|------|------------------------------|
| Agent / primary | AWS | `agent-payment-decision-lnd-signet` |
| Counterparty | Mac | `agent-bitcoin-lnd-signet` + local bitcoind |
| Connect direction | Mac → AWS (outbound from home) | Same as signet |
| Channel open | Prefer AWS funds open (or as operator decides) | Same as signet |

**Why B:** Matches skills and docs you already have (SG IP, unlock, connect, dual-node pay). Higher ops burden than AWS-only + LSP, but no third-party custody of the channel counterparty.

**Rejected for this pilot (unless scope is revised):**

- **A** — AWS-only + public LN peer (less dual-node practice reuse)
- **C** — LSP-managed liquidity (faster liquidity, more external dependency)

---

## Numeric limits (draft — adjust before Phase 8)

These are **pilot ceilings**, not product marketing defaults. Code in Phase 2 should be able to enforce them via env.

| Limit | Draft value | Rationale |
|-------|-------------|-----------|
| Max single payment | **50,000 sats** (~0.0005 BTC) | Tight blast radius |
| Max daily payments (sum) | **100,000 sats** | Caps runaway loops |
| Max channel capacity | **500,000 sats** | Small channel; not a routing node |
| Min payment (product default) | **2,000 sats** (unchanged) | Existing SDK policy |
| First mainnet on-chain fund | **≤ 1,000,000 sats** total to node | Enough for channel + fees + margin |
| Autoloop / Loop on mainnet | **Disabled** | Not in pilot |
| Autonomous agent `pay_invoice` | **Disabled** by default | Human attends every pay |

Revise this table in a follow-up commit if you want different numbers; treat Phase 8 as blocked until you explicitly accept these (or an update).

---

## Who may do what

| Action | Pilot rule |
|--------|------------|
| Unlock LND wallet | **Human operator only** (no auto-unlock) |
| Open / close channel | **Human operator only** |
| `pay_invoice` / `POST /pay` | **Human operator only**; no autopay flag on mainnet until post-pilot |
| `create_invoice` | Operator or agent process OK if receive-only credentials later |
| PaymentDecisionAgent | May **recommend** only; must not execute |
| AMI / host admin | Operator; AMI stays **private** |

---

## Fee model on mainnet (decision)

**Lab today:** fixed **1,000 sat on-chain** fee per payment design (`FEE_*` / `/send-fee`).

**Mainnet pilot decision:**

- **Disable** automatic on-chain fee collection (`collect_transaction_fee` / `/send-fee`) on mainnet for the pilot.
- Rationale: mainnet on-chain fees and UX make a fixed 1k-sat side payment a separate product decision; do not couple it to the first Lightning pilot.
- Lightning payment amount is the full invoice amount (no “X − 1000 to recipient” split in pilot).
- Redesign fee model **after** pilot (Phase 8 review), not as a go-live blocker.

Regtest/signet lab fee demos may continue unchanged.

---

## Chain backend (mainnet, when Phase 8 is approved)

| Host | Expectation |
|------|-------------|
| AWS LND | Prefer **bitcoind** (or equivalent full/neutrino policy you accept); lab Neutrino on signet is not a free pass for mainnet without review |
| Mac LND | Prefer **local bitcoind** (same lesson as signet Neutrino failure on Docker Desktop) |

Exact compose files are Phase 1–6 engineering; Phase 0 only requires: **do not reuse signet/regtest wallets or volumes on mainnet.**

---

## Non-goals (frozen for this pilot)

Do **not** block mainnet readiness on:

- Nostr production identity / NWC
- Liquidity Phase 3 (Faraday, Pool, multi-objective controller)
- Mainnet Autoloop / Loop
- Multi-agent swarm orchestrator
- Public routing node / large inbound from strangers
- Signet HTTP API (optional; SDK path is enough for pilot)

---

## Readiness phases (execute in order)

| Phase | Name | Status |
|-------|------|--------|
| **0** | This document — scope | **In progress / complete when operator accepts** |
| 1 | gRPC + macaroon LND client (lab docker-exec kept) | Not started |
| 2 | Limits + kill switches in code | Not started |
| 3 | Backup / restore drill (signet) | Not started |
| 4 | Health / daily ops automation | Not started |
| 5 | Liquidity SOP for topology B | Not started (lab practice exists) |
| 6 | Security hardening | Not started |
| 7 | Signet dress rehearsal “as if mainnet” | Not started |
| 8 | Mainnet pilot go-live | **Explicit separate decision** |

---

## Operator acceptance (Phase 0 exit)

Check when you agree this scope is correct:

- [x] Topology **B** (Mac ↔ AWS dual-node)
- [ ] Draft numeric limits accepted or revised in this file
- [x] Fee path **disabled** on mainnet for pilot
- [x] Non-goals list accepted
- [ ] Ready to start **Phase 1** (gRPC client)

Edit this section when limits are finalized.

---

## Immediate lab practice (no mainnet)

Continue using [signet.md](./signet.md) dual-node + SDK product path. Daily ops:

1. Mac: `./update-aws-sg-my-ip.sh`
2. Unlock LND on both hosts as needed
3. Mac connect → AWS; `listchannels` active
4. SDK create/pay; tests per [test-suite.md](./test-suite.md)

No `LND_NETWORK=mainnet` and no real funds under this document alone.
