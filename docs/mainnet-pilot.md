# Mainnet pilot scope (Phases 0–8)

**Status:** **Phase 8 ops pilot COMPLETE** (2026-08-09/10) — dual-node private channel, **N = 5** human-attended mainnet pays via `lncli`, then **cooperative close** (funds back on-chain).
**Post-pilot topology A′ (2026-08-11):** public channels + first mainnet **Loop Out SUCCESS** — see [public-routing-loop.md](./public-routing-loop.md). **Capital intent: HOLD as-is.** Autoloop still **off**. Autonomous autopay still **off**.
**Date:** 2026-08-01 (infra 2026-08-03; BIP-110 freeze 2026-08-07; pilot complete 2026-08-10; A′ Loop Out 2026-08-11)
**Audience:** Operator and implementers of readiness Phases 1–8.

This document freezes what a **minimal, defensible mainnet pilot** means for agent-bitcoin and records the Phase 8 outcome. Engineering readiness (gRPC client, limits, backups, security) targeted this scope.

**Related:** [mainnet-infra.md](./mainnet-infra.md) · [liquidity-topology-b.md](./liquidity-topology-b.md) · [public-routing-loop.md](./public-routing-loop.md) (post-pilot topology A′) · [loop-multi-network.md](./loop-multi-network.md) · [SECURITY.md](../SECURITY.md) · [signet.md](./signet.md)

---

## Pilot goal

Prove that **human-supervised** Lightning payments work on mainnet with the same dual-node mental model as signet:

- One small channel between **your** two nodes
- Bounded loss if something goes wrong
- Clear kill switches and backups
- Create/pay path available (ops: `lncli`; product: SDK later)

### Success metrics

| Metric | Target | Phase 8 result (2026-08-10) |
|--------|--------|------------------------------|
| Human-attended mainnet pays | **N ≥ 5** | **PASS — 5/5 @ 2,000 sats** via `lncli` |
| Critical incidents | Zero (or written postmortem) | **None** |
| Loss budget respected | ≤ **50,000** sats total intentional exposure | **PASS** — funded 50k; channel 43k |
| Autoloop | Off | **Off** |
| Go/no-go expand limits/automation | Explicit later decision | **Not expanded** — still pilot ceilings |

**Note:** Original draft said “via SDK.” Ops pilot proved dual-node Lightning with **`lncli`**. SDK/`AgentBitcoinClient` mainnet pay under kill switches remains an **optional post-pilot** item, not a re-open of Phase 8 ops.

---

## Phase 8 pilot log (executed)

| Item | Value |
|------|--------|
| Topology | **B** — AWS agent LND ↔ Mac counterparty LND |
| Chain | Bitcoin Core **main**; both hosts matched public tip before open |
| BIP-110 | Freeze observed past block **961,632**; Mac + AWS tip/hash matched explorers; residual headers-only tip ignored |
| AWS LND identity | `0290ec8b1733192e5dcbc5d32f8fec5ae345ff777fc48dafed757c2d14781d4967` |
| Mac LND identity | `02abf846d9f1479b709dc9a542e6f98bc0a0091c88ec93caab0672e12da9fa153b` |
| AWS P2P | EIP **3.90.159.146:9735** (SG: Mac IP /32) |
| Fund deposit address | `bc1q0ycjstr6a66xy9cp8cq99mjkpmglun9xuuuc04` |
| Fund amount | **50,000 sats** (0.0005 BTC) |
| Fund txid | `900f7aebebaff9213ad4087c0c15d1930696bbed6f3834e2debf62aef29944a5` |
| Channel funding txid | `c8d24876298bb243e03757f8b5c8a603f51f3f2ab847ead077bc570169fd423b` |
| Channel point | `c8d248…423b:1` |
| Capacity | **43,000** sats, **private**, ANCHORS |
| Connect | Mac → AWS before open |
| Pays | 5 × **2,000** sats AWS → Mac; routing fee **0** |
| Balances after pays | AWS local **32,037** / remote **10,000**; Mac mirrored |
| Cooperative close | Yes — `COOPERATIVE_CLOSE`; closing tx `4d103ba0…cdd5`; settled AWS **32,624** / Mac **10,000** |
| Post-close wallets (approx) | AWS on-chain **~38,801** · Mac **~10,000** · Lightning **0** |
| Loop | `loopd` install allowed; **Autoloop off** during pilot |

Containers:

| Role | Host | Container |
|------|------|-----------|
| Agent LND | AWS | `agent-payment-decision-lnd-mainnet` |
| Agent bitcoind | AWS | `agent-payment-decision-bitcoind-mainnet` |
| Peer LND | Mac | `agent-bitcoin-lnd-mainnet` |
| Peer bitcoind | Mac | `agent-bitcoin-bitcoind-mainnet` |

---

## Phase 8 pilot-complete checklist

Use this as the operator close-out for Phase 8 ops. Check off what you have done; items under **Post-pilot optional** are not required for “ops complete.”

### Pre-open (done)

- [x] Phases 0–7 complete (scope, gRPC, limits, backup runbooks, health, liquidity SOP, security, signet dress rehearsal)
- [x] Mainnet infra up (compose, new volumes, both bitcoind + LND synced)
- [x] BIP-110: tip ≥ 961,632; Mac + AWS `bestblockhash` match each other and public explorers
- [x] LND both sides: unlocked, `synced_to_chain=true` (Mac also `synced_to_graph=true`)
- [x] SCB baseline export (empty-channel OK)

### Fund + channel (done)

- [x] Fund AWS only ≤ **50,000** sats once
- [x] Confirmed balance before open
- [x] Mac `connect` to AWS `@EIP:9735`
- [x] Open private channel ~**40–45k** (executed **43k**)
- [x] Channel **active** both sides (`listchannels`)

### Payments (done)

- [x] **N ≥ 5** human-attended pays (2k each, AWS → Mac)
- [x] Balances consistent (sent/received mirror)
- [x] Zero critical incidents

### Housekeeping (operator — confirm)

- [ ] Post-open **and** post-pay SCB on **both** hosts
- [ ] AWS SCB copied **off-instance** (Mac or offline storage)
- [ ] Wallet passwords / seed still offline only (never in git)
- [ ] Autoloop remains **disabled** on mainnet
- [ ] No additional mainnet deposits without a new budget decision

### Post-pilot optional (not Phase 8 ops)

- [ ] One reverse pay Mac → AWS (both directions)
- [ ] One SDK/backend pay with `AGENT_BITCOIN_ALLOW_MAINNET=1` and explicit autopay latch
- [ ] Formal restore drill date logged
- [ ] Explicit go/no-go: keep ≤50k dual-node only vs raise limits / automation
- [ ] AMI refresh after pilot

---

## BIP-110 (RDTS) — freeze (historical) and residual risk

**Why freeze existed:** User-activated soft fork **BIP-110 / RDTS** entered **mandatory signaling at block 961,632** (~8–9 Aug 2026). Enforcing clients can reject non-signaling blocks; a split raises revoked-state risk for open Lightning channels. See [Start9 BIP-110 guide](https://start9.com/bip110/).

**What we did:** Held channel open until after signaling height; confirmed **Bitcoin Core** tips on Mac and AWS matched **public main** (e.g. height ~961,741+ with matching `bestblockhash`); observed only a **headers-only** non-active tip near 961,633 — not a competing full chain on our nodes.

**Status now:** Freeze **lifted for this pilot** after observation + operator **proceed**. Residual multi-client soft-fork risk is non-zero in theory; pilot accepted it under the **≤50k** loss budget.

| Still frozen without new decision | Allowed |
|-----------------------------------|---------|
| **Autoloop** on mainnet | Human `lncli` / optional SDK under kill switches |
| Further capital / new channels / more Loop (A′ is on **HOLD**) | SCB, health, AMI, docs; monitor existing public channels |
| Autonomous agent execution of pays | Human unlock / open / pay only |

**Note:** Manual mainnet Loop Out and public channels were approved under topology A′ (not Phase 8 ≤50k). See [public-routing-loop.md](./public-routing-loop.md) execution log.

---

## Topology B — dual-node Mac ↔ AWS (chosen)

```text
AWS:  agent LND (payment decision / primary funded side)
        │
   Lightning channel (mainnet pilot — small, private)
        │
Mac:  counterparty LND + local bitcoind
```

| Role | Host | Lab analogue (signet) |
|------|------|------------------------|
| Agent / primary | AWS | `agent-payment-decision-lnd-signet` |
| Counterparty | Mac | `agent-bitcoin-lnd-signet` + local bitcoind |
| Connect direction | Mac → AWS (outbound from home) | Same as signet |
| Channel open | AWS funds open | Same as signet |

**Why B:** Matches existing dual-node ops (SG IP, unlock, connect, pay). No third-party custody of the counterparty.

**Rejected for this pilot:** topology A (AWS-only + public peer), C (LSP-managed liquidity).

---

## Numeric limits (first mainnet pilot — still in force)

These remain **pilot ceilings** until an explicit expand decision. Enforced in code via env where noted (Phase 2).

| Limit | Pilot value | Rationale |
|-------|-------------|-----------|
| **Max loss budget (all funds on pilot nodes)** | **≤ 50,000 sats** | Worst-case if wallet/host/channel lost |
| Max single payment | **≤ 50,000 sats** (`MAX_PAYMENT_SATS`) | Prefer smaller pays (2k–10k) |
| Max daily payments (sum) | Prefer **≤ 50,000** pilot discipline | Code default may be higher; do not treat as budget raise |
| Max channel capacity | **≤ 50,000 sats** | First channel was **43,000** |
| Min payment (product default) | **2,000 sats** | Pilot pays used 2k |
| First mainnet on-chain fund | **≤ 50,000 sats** total | Executed at 50k on AWS only |
| Autoloop on mainnet | **Disabled** | Manual Loop Out done under A′; Autoloop still off |
| Autonomous agent `pay_invoice` | **Disabled** by default | Human attends every pay |

### What “max loss ≈ 50k” means

- **In scope:** sats sent on-chain to pilot LND wallets + sats in the pilot channel.
- **Also real:** open/close/anchor on-chain fees (size channel under 50k when funding exactly 50k).
- **Not in scope:** future deposits, other wallets, or raising limits without a new go decision.

Earlier draft (500k channel / 1M fund) remains **retired** for this pilot.

---

## Who may do what

| Action | Pilot rule (still in force) |
|--------|------------------------------|
| Unlock LND wallet | **Human operator only** |
| Open / close channel | **Human operator only** |
| `payinvoice` / SDK pay / `POST /pay` | **Human operator only**; no autopay on mainnet until post-pilot go |
| `create_invoice` / `addinvoice` | Operator OK |
| PaymentDecisionAgent | May **recommend** only; must not execute |
| AMI / host admin | Operator; AMI stays **private** |

---

## Fee model on mainnet (decision)

**Lab (regtest/signet):** fixed **1,000 sat on-chain** fee path may still apply (`FEE_*` / `/send-fee`).

**Mainnet pilot:**

- **Disable** automatic on-chain fee collection on mainnet for the pilot.
- Lightning amount is the full invoice amount (no “X − 1000” split).
- Redesign product fee model is a **post-pilot** product decision.

---

## Chain backend (mainnet)

| Host | Expectation | Pilot reality |
|------|-------------|----------------|
| AWS LND | **bitcoind** (pruned OK) | In use |
| Mac LND | **local bitcoind** | In use |

Compose: `docker-compose.mainnet.{aws,mac}.yml` + `startup-mainnet-*.sh`.
**Do not** reuse signet/regtest wallets or volumes on mainnet.

---

## Non-goals (still frozen unless a new go)

Do **not** treat Phase 8 complete or A′ first Loop as approval for:

- Nostr production identity / NWC on mainnet (lab A/B only on regtest+signet; mainnet process documented, **not executed** — [nostr-agent-identity.md](./nostr-agent-identity.md#mainnet-process-not-yet-executed))
- Liquidity Phase 3 (Faraday, Pool, multi-objective controller)
- **Mainnet Autoloop** (manual Loop Out is done; automation is not)
- Multi-agent swarm orchestrator
- Further public channel growth or deposits while A′ capital intent is **HOLD**
- Autonomous agent `pay_invoice` on mainnet

---

## Readiness phases

| Phase | Name | Status |
|-------|------|--------|
| **0** | Scope (this document) | **Complete** |
| **1** | gRPC + macaroon LND client | **Complete** — [lnd-client.md](./lnd-client.md) |
| **2** | Limits + kill switches | **Complete** — see below |
| **3** | Backup / restore | **Complete** — [lnd-backup-restore.md](./lnd-backup-restore.md) |
| **4** | Health / daily ops | **Complete** — [daily-ops-signet.md](./daily-ops-signet.md) |
| **5** | Liquidity SOP topology B | **Complete** — [liquidity-topology-b.md](./liquidity-topology-b.md) |
| **6** | Security hardening | **Complete** — [security-hardening.md](./security-hardening.md) |
| **7** | Signet dress rehearsal | **Complete** (PASS 2026-08-03) — [signet-dress-rehearsal.md](./signet-dress-rehearsal.md) |
| **8** | Mainnet pilot go-live | **Ops COMPLETE** (2026-08-10) — lncli dual-node; see pilot log |

**Path taken:** dress rehearsal → infra ([mainnet-infra.md](./mainnet-infra.md)) → BIP-110 observation → fund/open/pay under ≤50k.

---

## Operator acceptance (Phase 0 exit)

- [x] Topology **B** (Mac ↔ AWS dual-node)
- [x] Numeric limits accepted (≤50k)
- [x] Fee path **disabled** on mainnet for pilot
- [x] Non-goals list accepted
- [x] Phase 1+ engineering complete
- [x] Phase 8 ops success metrics met (N=5 pays, no critical incidents)

---

## Phase 2 — limits and kill switches (implemented)

Enforced in `agent_bitcoin.constants`, `AgentBitcoinClient`, and the FastAPI backend.

| Control | Env | Lab default | Mainnet default |
|---------|-----|-------------|-----------------|
| Single pay max | `MAX_PAYMENT_SATS` | 1_000_000 | **50_000** |
| Daily pay sum (UTC) | `MAX_DAILY_PAYMENT_SATS` | 0 (off) | **100_000** (code); pilot discipline ≤50k |
| Allow Lightning pay | `AGENT_BITCOIN_ALLOW_AUTOPAY` | on (set `0` to kill) | **off** (need `=1`) |
| Allow on-chain fee send | `AGENT_BITCOIN_ALLOW_MAINNET_FEE` | on | **off** (need `=1`) |
| Mainnet network | `AGENT_BITCOIN_ALLOW_MAINNET` | n/a | **must be `1`** |
| Spend ledger file | `AGENT_BITCOIN_SPEND_LEDGER` | `~/.config/agent-bitcoin/spend-ledger.json` | same |

**Custody:** wallet password/seed offline only; macaroons/certs restricted paths; never commit secrets.

Signet/regtest product path does **not** need `ALLOW_AUTOPAY` (lab default allows pay).

---

## Phase 3 — backup / restore

| Piece | Location |
|-------|----------|
| Export SCB (+ optional volume tarball) | `./export-lnd-backup.sh` |
| Verify backup dir | `./verify-lnd-backup.sh <dir>` |
| Full runbook + drill checklist | [lnd-backup-restore.md](./lnd-backup-restore.md) |
| Pilot RPO / RTO | ≤ 24h / ≤ 4h (see runbook) |

**After pilot payments (required hygiene):**

```bash
# AWS
docker exec agent-payment-decision-lnd-mainnet \
  lncli --lnddir=/home/lnd/.lnd --network=mainnet exportchanbackup --all \
  > ~/lnd-backups/mainnet/scb-aws-post-pays.backup

# Mac
docker exec agent-bitcoin-lnd-mainnet \
  lncli --lnddir=/home/lnd/.lnd --network=mainnet exportchanbackup --all \
  > ~/lnd-backups/mainnet/scb-mac-post-pays.backup
```

Copy AWS backup off the instance. Schedule further exports after close/rebalance.

---

## Ongoing ops (mainnet pilot steady state)

1. Mac: keep AWS SG updated for your IP (`update-aws-sg-my-ip.sh` or equivalent) so **9735** stays reachable.
2. Unlock LND on both hosts when operating (no auto-unlock).
3. Confirm `listchannels` active and peer connected before pays.
4. Prefer small human-attended pays; respect ≤50k budget.
5. Export SCB after material channel state changes.
6. Lab work continues on **regtest/signet**; do not conflate volumes with mainnet.

**Steady state is valid:** no open pilot channel, residual on-chain on both hosts, Autoloop off, human control only.

---

## Post-pilot decisions

| Decision | Status (2026-08-11) | Notes |
|----------|---------------------|--------|
| Topology A′ public channels | **Done** | ACINQ + LNBiG, 500k each |
| Manual mainnet Loop Out | **Done — SUCCESS** | 250k; ~841 sats cost; ~251k inbound |
| Capital intent | **HOLD as-is** | No further opens/swaps/deposits without new go |
| Mainnet Autoloop | **Off** | Manual path proven only |
| Enable `AGENT_BITCOIN_ALLOW_AUTOPAY` on mainnet | **No** | Product go still required |
| Second AWS LND as “routing partner” | **No** | Not needed for public routing |
| SDK mainnet integration test | Optional | Kill switches |
| Nostr mainnet (M1 identity / M2 2k Phase B smoke) | **Not started** | Explicit go required; process in [nostr-agent-identity.md](./nostr-agent-identity.md#mainnet-process-not-yet-executed) |
| Nostr NWC / production swarm (M3) | **Frozen** | After M2 + separate design |
| Sweep residual to cold storage | Operator choice | On-chain fees apply |

**Public routing + Loop** is documented in [public-routing-loop.md](./public-routing-loop.md) (design + execution log). Further expansion requires a **new written go**, not an implicit extension of HOLD.

---

*Phase 0–8 readiness and ops pilot recorded. Topology A′ first Loop Out recorded under HOLD. Further product/capital expansion requires a new written go decision.*
