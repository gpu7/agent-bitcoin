# Public routing channel + Loop liquidity (topology A′)

**Status:** **First public channels + first mainnet Loop Out COMPLETE** (2026-08-11). **Capital intent: HOLD as-is** — no further opens, deposits, or swaps without a new written go. **Autoloop remains OFF.**
**Date:** 2026-08-10 (design); execution log 2026-08-11
**Audience:** Operator (post–Phase 8 pilot).
**Related:** [mainnet-pilot.md](./mainnet-pilot.md) · [mainnet-infra.md](./mainnet-infra.md) · [loop-multi-network.md](./loop-multi-network.md) · [loop-autoloop.md](./loop-autoloop.md) · [liquidity-automation.md](./liquidity-automation.md) · [security-hardening.md](./security-hardening.md) · [docker/loop-timeout-fix/](../docker/loop-timeout-fix/)

---

## Goal

Run a **permanent, public** Lightning channel on AWS that the wider network can use for **routing**, and use **Lightning Labs Loop** (manual first, then optional Autoloop) to manage **inbound/outbound liquidity**.

This is a **new phase after** the ≤50k dual-node pilot (topology B). It required an explicit **capital and policy go** before mainnet open or swap. That go was taken for topology A′; see **Execution log** below.

---

## Correct infrastructure (short)

| Question | Answer |
|----------|--------|
| Open from which node? | **`agent-payment-decision-lnd-mainnet`** on AWS |
| Second AWS “agent” LND as partner? | **No** — not required for public routing |
| Mac as permanent partner? | **No** — unreliable for always-on public routes |
| Who is the channel partner? | A **public LN peer** (or LSP), not another of *your* agents |
| Where does Loop run? | **`agent-loopd-mainnet`** sidecar on the **same** AWS host, same LND |

```text
Lightning Network (public peers A, B, C, …)
                    │
           public channel(s)
                    │
     agent-payment-decision-lnd-mainnet   (AWS, EIP, always on)
                    │
              agent-loopd-mainnet
                    │
         Lightning Labs Loop (public servers)
```

Mac may remain a **test client** (pay/invoice experiments). It is **not** the permanent routing counterparty.

---

## Why not a second AWS agent as partner?

A channel between **two LND nodes you control** (even both on AWS) is still essentially a **private dual-node** topology unless:

- both are public **and**
- third parties actually path through that link in useful ways.

For “be a routing hop on the public graph,” the other side of the channel should be a **well-connected external node** (or an LSP that provides inbound). Adding a second AWS agent mainly **doubles** wallets, seeds, SCB, disk, and ops without giving the network a better path.

**Optional later:** split **routing LND** vs **agent LND** for risk isolation — a separate design, not required for this goal.

---

## Topology map (project language)

| Topology | Partner | Channel | Use |
|----------|---------|---------|-----|
| **B** (Phase 8 pilot) | Mac (or your 2nd private node) | Usually **private** | Agent practice, tight budget |
| **A′** (this doc) | **External public peer(s)** | **Public** (announced) | Routing + Loop liquidity |
| **C-ish** | LSP dual-fund / inbound purchase | Varies | Alternative to Loop for inbound |

Pilot docs called topology **A** “AWS-only + public peer” and deferred it for the pilot. **A′** is that path, plus Loop as the liquidity tool this repo already wires.

---

## Policy gates (must pass before funds)

Record decisions in writing (ticket, PR, or checklist below). Defaults until changed remain **no**.

| Gate | Required decision |
|------|-------------------|
| Loss budget | New ceiling **above** pilot 50k (public Loop mins are often **~250k sats** class — confirm live `loop terms`) |
| Public channels | Explicit allow public announce / routing traffic |
| Loop | Explicit allow mainnet **manual** Loop Out/In |
| Autoloop | Separate explicit allow (stricter); fee budget + kill switch |
| SG 9735 | Document how open (world / selected ASNs / peer IPs) |
| Agents | Still **never** call `openchannel` / `loop` / `closechannel` |

### Operator go checklist (P0)

- [x] New loss budget amount (sats) and rationale — operator go for ~2× **500k** public channels + Loop Out min class (**~250k**); Phase 8 ≤50k ceiling no longer bounds this phase
- [x] Accept routing risks (probes, force-close, fee loss, HTLC timeouts)
- [x] Accept public P2P exposure plan for **9735** (AWS EIP published)
- [x] Autoloop: **off** (manual Loop Out only for first swap)
- [x] SCB after material channel/Loop changes (operator hygiene — re-export after Loop Out)
- [x] Signed off by operator: **2026-08-11** (topology A′ execution)

### Capital intent (current)

| Decision | Value |
|----------|--------|
| **Intent** | **HOLD pilot as-is** |
| Further public opens | **No** without new go |
| Further Loop Out/In | **No** without new go |
| Autoloop | **Off** |
| Further mainnet deposits | **No** without new budget decision |
| Steady state | Keep LND + loopd up; monitor; SCB; optional external receive smoke |

---

## Execution log (2026-08-11)

Operator-executed topology A′ on AWS mainnet. Values are approximate ops notes, not a live API.

### Infrastructure

| Item | Value |
|------|--------|
| Agent LND | `agent-payment-decision-lnd-mainnet` |
| Agent bitcoind | `agent-payment-decision-bitcoind-mainnet` |
| loopd | `agent-loopd-mainnet` |
| AWS identity | `0290ec8b1733192e5dcbc5d32f8fec5ae345ff777fc48dafed757c2d14781d4967` |
| AWS P2P | EIP **3.90.159.146:9735** |
| LOOPD image (L402 fix) | `agent-bitcoin/loop:v0.34.0-beta-timeoutfix` (see troubleshooting) |

### Public channels (both active, not private)

| Peer | Capacity | Channel point (short) | Notes |
|------|----------|----------------------|--------|
| **ACINQ** | 500,000 sats | `a33df4c3…3684:1` | Opened first; fee policy 1 sat / 1 ppm |
| **LNBiG [Hub-1]** | 500,000 sats | `de466bd4…0cbc:1` | Second peer for path diversity after first Loop Out NO_ROUTE |

### First mainnet Loop Out

| Field | Value |
|-------|--------|
| Swap id | `0c14e5c8eff58982b4899313efbbeb8d575493ed197f951847082c61ce605a94` |
| Type | `LOOP_OUT` |
| Amount | **250,000** sats (server min class) |
| Final state | **`SUCCESS`** (`FAILURE_REASON_NONE`) |
| cost_server | 332 sats |
| cost_onchain | 113 sats |
| cost_offchain | 396 sats |
| **Total cost** | **~841 sats** (~0.34% of 250k) |
| HTLC address | `bc1pryk235qsw2ur5wzsc2ftgvfgkzv9035kg0fexurr63qmnyzpxt9sknvysw` |
| Path notes | L402 needed timeout patch; single-peer path failed OFFCHAIN/NO_ROUTE; LNBiG channel restored route diversity |

### Liquidity after success (approx)

| Peer | Local | Remote (inbound) |
|------|-------|------------------|
| LNBiG | ~278k | **~221k** |
| ACINQ | ~469k | **~30k** |
| **Total** | ~747k | **~251k** |
| On-chain wallet | — | **~316k** confirmed |

**Outcome:** Real **receive capacity** (~250k inbound). Most Loop Out flow went LNBiG; ACINQ remains outbound-heavy. Acceptable under **hold**.

### Fee policy (routing)

Both public channels: `base_fee_msat=1000` (1 sat), `fee_per_mil=1` (1 ppm). Competitive / cheap; `feereport` day/week/month sums still **0** (no third-party routing volume yet — expected).

---

## Capital (order of magnitude)

Phase 8 residual alone was **below** typical public Loop minimums. Topology A′ required additional mainnet capital (operator go) sized for two **500k** public channels plus Loop Out ≥ **250k** class.

Before any **future** open or swap (not under current HOLD):

1. On AWS: `loop terms` (via `agent-loopd-mainnet`) — note min swap sizes.
2. Size **on-chain fund** ≥ channel + open fee + at least one Loop Out + buffer.
3. Prefer solid public peers; re-check connectivity after opens.

Do **not** hardcode sizes in automation; re-check `terms` at go-time.

---

## Security (non-negotiable)

| Surface | Rule |
|---------|------|
| LND gRPC / REST | **127.0.0.1 only** — never open 10009 to the internet |
| bitcoind RPC | Not published |
| LND P2P **9735** | Required for public peers; document SG |
| Wallet unlock | Human only |
| Seed / SCB | Offline / encrypted; never git |
| Loop | Operator CLI only; fee budget |

See [security-hardening.md](./security-hardening.md).

---

## Phase P1 — Harden AWS node (before open)

- [x] EIP stable; instance suitable for always-on LND (CPU/disk/RAM)
- [x] Mainnet bitcoind + LND synced; wallet unlock procedure known
- [x] `./wire-loopd.sh mainnet` (or existing `agent-loopd-mainnet`) healthy
- [x] `loop getinfo` / `loop terms` succeed against agent LND
- [x] Autoloop **disabled** (remains off under HOLD)
- [x] Monitoring: operator `docker ps` / LND / loopd checks
- [x] Baseline SCB export + off-instance copy (re-export after Loop Out)
- [x] SG: **9735** for public peers / EIP
- [ ] Optional: node alias/color via `lncli setalias` / conf (operator taste)

### Verify loopd (AWS)

```bash
export LOOP_CLI='docker exec -i agent-loopd-mainnet loop'
$LOOP_CLI --network=mainnet getinfo
$LOOP_CLI --network=mainnet terms
$LOOP_CLI --network=mainnet getparams   # autoloop should be off
```

### Verify LND (AWS)

```bash
docker exec agent-payment-decision-lnd-mainnet \
  lncli --lnddir=/home/lnd/.lnd --network=mainnet getinfo \
  | grep -E 'identity_pubkey|synced_to_chain|num_peers|uris'
```

Public peers need a usable **URI** (pubkey@host:9735). EIP + advertised address must match what you intend to publish.

---

## Phase P2 — Open first public channel

### Peer selection (operator research)

Prefer peers with:

- High uptime / long history
- Substantial capacity and sensible fee policies
- Clear identity (known operators help)

Sources at open time: graph explorers (e.g. 1ML, Amboss), your own `describegraph` after sync, community recommendations. **Re-evaluate** — do not freeze peer pubkeys in this doc forever.

### Connect + open (public)

Replace placeholders. **Do not** use `--private`.

```bash
PEER_PUB='<public-peer-pubkey>'
PEER_HOST='<host-or-ip>:9735'    # if required for first connect
LOCAL_AMT='<sats>'               # sized from budget + loop terms
SAT_PER_VBYTE='<fee>'            # check mempool

# Connect (if not already peered)
docker exec agent-payment-decision-lnd-mainnet \
  lncli --lnddir=/home/lnd/.lnd --network=mainnet \
  connect ${PEER_PUB}@${PEER_HOST}

# Public channel (omit --private)
docker exec agent-payment-decision-lnd-mainnet \
  lncli --lnddir=/home/lnd/.lnd --network=mainnet \
  openchannel --node_key=${PEER_PUB} --local_amt=${LOCAL_AMT} --sat_per_vbyte=${SAT_PER_VBYTE}
```

### After confirmations

```bash
docker exec agent-payment-decision-lnd-mainnet \
  lncli --lnddir=/home/lnd/.lnd --network=mainnet listchannels

docker exec agent-payment-decision-lnd-mainnet \
  lncli --lnddir=/home/lnd/.lnd --network=mainnet getnodeinfo ${PEER_PUB}
```

- [x] Channel `active: true`, **not** private — **ACINQ** then **LNBiG**, 500k each
- [x] Node reachable on public graph (EIP URI)
- [x] Fresh **SCB** after opens (and again after Loop Out)

**Initial liquidity shape:** after a normal funded open, **local ≈ capacity**, **remote ≈ 0**. You can send outbound; **inbound/routing toward you** needs rebalancing (Loop Out or reverse flow). First Loop Out (below) created ~**251k** total remote.

---

## Phase P3 — Loop liquidity management

### Mental model

| Action | Effect |
|--------|--------|
| **Loop Out** | Spend local LN → receive on-chain → **more remote (inbound)** |
| **Loop In** | Spend on-chain → LN → **more local (outbound)** |
| **Easy Autoloop** | Automates Loop Out when local exceeds a target (fee-capped) |

Agents / SDK: **invoice / pay / decide only** — never Loop.

### Manual Loop Out first (prove path) — **DONE 2026-08-11**

1. [x] Confirm active public channel(s) and `loop terms` mins.
2. [x] Choose amount ≥ min (**250k**), ≤ local balance minus reserve.
3. [x] Run Loop Out via `loop` CLI (`--payment_timeout=1h` after L402 patch).
4. [x] Watch `listswaps` until **SUCCESS**; re-check `listchannels` local/remote.
5. [x] Export SCB after material change (operator — confirm off-instance copy).

```bash
export LOOP_CLI='docker exec -i agent-loopd-mainnet loop'
$LOOP_CLI --network=mainnet listswaps
# Manual out: see https://docs.lightning.engineering/lightning-network-tools/loop
# Example shape (verify flags on your loop version before use):
# $LOOP_CLI --network=mainnet out --amt=250000 --payment_timeout=1h
```

**Under HOLD:** do not start another `loop out` / `loop in` without a new capital decision.

### Autoloop (only after manual success + policy go)

Regtest path is documented in [loop-autoloop.md](./loop-autoloop.md). Mainnet:

- Start with **conservative** fee budget and local-balance target.
- Enable only after P0 Autoloop gate.
- Kill switch:

```bash
$LOOP_CLI --network=mainnet setparams --autoloop=false
```

- Monitor fee spend daily while enabled.
- Disable on repeated failures or budget breach.

**Do not** copy regtest Autoloop enable commands onto mainnet without re-reading params and budgets.

---

## Phase P4 — Product integration (optional)

- SDK / FastAPI against the **same** AWS LND under existing kill switches (`AGENT_BITCOIN_ALLOW_MAINNET`, `ALLOW_AUTOPAY`, max pay caps).
- PaymentDecisionAgent still **recommends only** unless you separately enable execution.
- Keep Loop and channel ops **operator-only**.

---

## Steady-state ops (current: HOLD)

1. Keep instance and LND up; unlock after reboots.
2. SCB after open/close/rebalance/Loop material changes (fresh export after first Loop Out).
3. Watch disk, chain sync, channel active state; `listswaps` only if starting new swaps.
4. Leave fee policy at defaults unless intentionally changing; expect low/zero earned fees at small capacity.
5. Prefer cooperative close if exiting a peer; avoid force-close for cleanup.
6. Lab (regtest/signet) stays separate volumes/wallets.
7. **Do not** deposit more funds, open channels, or enable Autoloop while capital intent is **HOLD**.
8. Optional: external smoke receive (`addinvoice` ~2k paid from outside) to prove inbound without spending more capital.

---

## Explicit non-goals (this phase)

- Multi-agent swarm routing policy
- Faraday / Pool as required dependencies (may come later — liquidity-automation Phase 3)
- Public gRPC
- Mac as permanent public peer
- Second AWS LND “only to be channel partner”

---

## Relation to Phase 8 pilot

| Pilot (done) | This phase (A′) |
|--------------|-----------------|
| Topology B private Mac↔AWS | Topology A′ public external peers (**ACINQ + LNBiG**) |
| ≤50k budget | Higher capital for 2×500k + Loop Out class |
| Autoloop off | **Manual Loop Out SUCCESS**; Autoloop still **off** |
| Channel cooperatively closed | New **public** channels live |
| N=5 human pays proved LN path | First **inbound liquidity** via Loop Out (~251k remote) |
| Post-pilot design only | **Execution complete**; capital **HOLD** |

---

## Troubleshooting: Loop Out + L402 `timeout_seconds`

**Symptoms**

```text
cannot initiate swap: timeout_seconds must be specified
# or
payment isn't initiated. consider removing pending token file...
```

`listauth` shows `l402.token.pending` with zero preimage; `listpayments` has no matching hash; logs say “paying invoice” but no `lnbc…`.

**Cause:** LND requires `timeout_seconds` on `SendPaymentV2`. Loop L402 pays via `lndclient.PayInvoice`, which omits that field.

**Fix:** rebuild Loop with the project patch, then recreate loopd (volume kept):

```bash
docker build -t agent-bitcoin/loop:v0.34.0-beta-timeoutfix \
  -f docker/loop-timeout-fix/Dockerfile \
  docker/loop-timeout-fix

docker exec agent-loopd-mainnet rm -f /root/.loop/mainnet/l402.token.pending 2>/dev/null || true
export LOOPD_IMAGE=agent-bitcoin/loop:v0.34.0-beta-timeoutfix
./wire-loopd.sh mainnet --recreate
```

Details: [docker/loop-timeout-fix/README.md](../docker/loop-timeout-fix/README.md).

Then retry `loop out` with `--payment_timeout=1h`. Keep Autoloop off until a manual out succeeds.

---

## References

- [Loop](https://lightning.engineering/loop/)
- [Autoloop](https://docs.lightning.engineering/lightning-network-tools/loop/autoloop)
- [Channel liquidity](https://docs.lightning.engineering/lightning-network-tools/lightning-terminal/channel-liquidity)
- In-repo: [loop-multi-network.md](./loop-multi-network.md), [loop-autoloop.md](./loop-autoloop.md), [docker/loop-timeout-fix/](../docker/loop-timeout-fix/)
