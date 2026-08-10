# Public routing channel + Loop liquidity (topology A′)

**Status:** Design + operator runbook. **Does not** fund, open channels, or enable Autoloop by itself.
**Date:** 2026-08-10
**Audience:** Operator (post–Phase 8 pilot).
**Related:** [mainnet-pilot.md](./mainnet-pilot.md) · [mainnet-infra.md](./mainnet-infra.md) · [loop-multi-network.md](./loop-multi-network.md) · [loop-autoloop.md](./loop-autoloop.md) · [liquidity-automation.md](./liquidity-automation.md) · [security-hardening.md](./security-hardening.md)

---

## Goal

Run a **permanent, public** Lightning channel on AWS that the wider network can use for **routing**, and use **Lightning Labs Loop** (manual first, then optional Autoloop) to manage **inbound/outbound liquidity**.

This is a **new phase after** the ≤50k dual-node pilot (topology B). It requires an explicit **capital and policy go** before any mainnet open or swap.

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

- [ ] New loss budget amount (sats) and rationale
- [ ] Accept routing risks (probes, force-close, fee loss, HTLC timeouts)
- [ ] Accept public P2P exposure plan for **9735**
- [ ] Autoloop: off | manual-only | enabled with fee cap _______
- [ ] SCB + AMI schedule while public channels exist
- [ ] Signed off by operator (date): ________

---

## Capital (order of magnitude)

Phase 8 residual (~39k AWS + ~10k Mac on-chain) is **below** typical public Loop minimums and thin for meaningful public routing.

Before open:

1. On AWS: `loop terms` (via `agent-loopd-mainnet`) — note min swap sizes.
2. Size **on-chain fund** ≥ first channel + open fee + at least one Loop Out + buffer.
3. Prefer **one solid public channel** first; add peers later.

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

- [ ] EIP stable; instance suitable for always-on LND (CPU/disk/RAM)
- [ ] Mainnet bitcoind + LND synced; wallet unlock procedure known
- [ ] `./wire-loopd.sh mainnet` (or existing `agent-loopd-mainnet`) healthy
- [ ] `loop getinfo` / `loop terms` succeed against agent LND
- [ ] Autoloop **disabled** until P3
- [ ] Monitoring: disk, container health, optional `check-aws-health.sh` adaptation
- [ ] Baseline SCB export + off-instance copy
- [ ] SG: plan for **9735** documented and applied
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

- [ ] Channel `active: true`, **not** private
- [ ] Node appears in public explorers (may lag)
- [ ] Fresh **SCB** exported and copied offline

**Initial liquidity shape:** after a normal funded open, **local ≈ capacity**, **remote ≈ 0**. You can send outbound; **inbound/routing toward you** needs rebalancing (Loop Out or reverse flow).

---

## Phase P3 — Loop liquidity management

### Mental model

| Action | Effect |
|--------|--------|
| **Loop Out** | Spend local LN → receive on-chain → **more remote (inbound)** |
| **Loop In** | Spend on-chain → LN → **more local (outbound)** |
| **Easy Autoloop** | Automates Loop Out when local exceeds a target (fee-capped) |

Agents / SDK: **invoice / pay / decide only** — never Loop.

### Manual Loop Out first (prove path)

1. Confirm active public channel and `loop terms` mins.
2. Choose amount ≥ min, ≤ local balance minus reserve.
3. Run Loop Out via `loop` CLI (exact flags per current Loop version — see Lightning Labs docs).
4. Watch `listswaps` until success; re-check `listchannels` local/remote.
5. Export SCB after material change.

```bash
export LOOP_CLI='docker exec -i agent-loopd-mainnet loop'
$LOOP_CLI --network=mainnet listswaps
# Manual out: see https://docs.lightning.engineering/lightning-network-tools/loop
# Example shape (verify flags on your loop version before use):
# $LOOP_CLI --network=mainnet out --amt=<sats> ...
```

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

## Steady-state ops

1. Keep instance and LND up; unlock after reboots.
2. SCB after open/close/rebalance/Loop material changes.
3. Watch disk, chain sync, channel active state, Loop swaps.
4. Review fee policies and peer quality periodically.
5. Prefer cooperative close if exiting a peer; avoid force-close for cleanup.
6. Lab (regtest/signet) stays separate volumes/wallets.

---

## Explicit non-goals (this phase)

- Multi-agent swarm routing policy
- Faraday / Pool as required dependencies (may come later — liquidity-automation Phase 3)
- Public gRPC
- Mac as permanent public peer
- Second AWS LND “only to be channel partner”

---

## Relation to Phase 8 pilot

| Pilot (done) | This phase |
|--------------|------------|
| Topology B private Mac↔AWS | Topology A′ public external peers |
| ≤50k budget | New higher budget required |
| Autoloop off | Manual Loop then optional Autoloop |
| Channel may be closed | New **public** channel(s) after go |
| N=5 human pays proved LN path | Routing + liquidity automation |

---

## References

- [Loop](https://lightning.engineering/loop/)
- [Autoloop](https://docs.lightning.engineering/lightning-network-tools/loop/autoloop)
- [Channel liquidity](https://docs.lightning.engineering/lightning-network-tools/lightning-terminal/channel-liquidity)
- In-repo: [loop-multi-network.md](./loop-multi-network.md), [loop-autoloop.md](./loop-autoloop.md)
