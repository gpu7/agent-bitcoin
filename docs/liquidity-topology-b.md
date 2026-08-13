# Liquidity SOP — topology B (Mac ↔ AWS)

**Phase 5 of mainnet readiness.** Manual liquidity only.
**Audience:** Operator.
**Related:** [mainnet-pilot.md](./mainnet-pilot.md) · [signet.md](./signet.md) · [daily-ops-signet.md](./daily-ops-signet.md) · [liquidity-automation.md](./liquidity-automation.md)

---

## Goal

Keep **one small dual-node channel** usable for agent invoice/pay practice (signet now; mainnet pilot later) without Autoloop, Pool, or public routing.

---

## Roles and capital flow

```text
AWS agent LND  ──channel──  Mac peer LND
 (usually funds open)         (connects outbound)
 local_balance high           receives via invoices
```

| Role | Host (signet names) | Typical balance after open + small receives |
|------|---------------------|-----------------------------------------------|
| **Funder / opener** | AWS `agent-payment-decision-lnd-signet` | High **local** (can pay Mac invoices) |
| **Counterparty** | Mac `agent-bitcoin-lnd-signet` | High **remote**; small **local** after AWS→Mac pays |

**Product-path default:** Mac **creates** invoice → AWS **pays** (uses AWS outbound).

**Reverse path:** AWS creates → Mac pays only if Mac has enough **local** (≥ `MIN_PAYMENT_SATS`, default 1000).

---

## Hard rules (pilot)

From [mainnet-pilot.md](./mainnet-pilot.md) (accepted):

| Rule | Value |
|------|--------|
| Max channel capacity | **500,000 sats** |
| Max single payment | **50,000 sats** |
| Max daily payment sum | **100,000 sats** (mainnet defaults; lab daily cap optional) |
| Autoloop / Loop | **Disabled** on mainnet pilot; regtest lab only for Autoloop learning |
| Public routing / large inbound from strangers | **Out of scope** |
| Channel open/close | **Human operator only** |

Do **not** enable Easy Autoloop or Loop Out against mainnet agent channels until a later explicit decision (Phase 8 ops complete; Autoloop still off — see [mainnet-pilot.md](./mainnet-pilot.md)). For **public** routing + Loop (not dual-node Mac), see [public-routing-loop.md](./public-routing-loop.md).

---

## Signet practice (already proven)

You have already done this loop successfully:

1. Fund AWS signet wallet (faucet)
2. Mac bitcoind + LND sync; peer connect Mac→AWS
3. AWS `openchannel` to Mac (~50k lab channel)
4. Wait for confirmations → `active: true`
5. Rebalance / move sats via Lightning payments (SDK product path)
6. Health: `./check-signet-health.sh` both roles

That **is** the Phase 5 practice exit for topology B on signet.

---

## Open a channel (checklist)

Use when you need a new channel (new wallets, closed channel, mainnet pilot).

### Prerequisites

- [ ] Both nodes unlocked, `synced_to_chain: true`
- [ ] `./check-signet-health.sh` or equivalent (peers may be empty until connect)
- [ ] Mac: `./update-aws-sg-my-ip.sh`; SG allows **19735** from Mac
- [ ] Mac → AWS `connect` succeeds; `listpeers` non-empty both sides
- [ ] Funder has on-chain balance ≫ channel size + fees

### Connect (Mac)

```bash
export LND_CONTAINER=agent-bitcoin-lnd-signet
export AWS_EIP=<eip>
export AWS_PUB=<aws-identity-pubkey>
docker exec "$LND_CONTAINER" lncli --lnddir=/home/lnd/.lnd --network=signet \
  connect ${AWS_PUB}@${AWS_EIP}:19735
```

### Open (AWS — typical)

```bash
export LND_CONTAINER=agent-payment-decision-lnd-signet
export MAC_PUB=<mac-identity-pubkey>
# amount ≤ pilot max channel (signet lab often 50000)
docker exec "$LND_CONTAINER" lncli --lnddir=/home/lnd/.lnd --network=signet \
  openchannel --node_key="$MAC_PUB" --local_amt=50000
```

### Wait for active

```bash
# either host
docker exec "$LND_CONTAINER" lncli --lnddir=/home/lnd/.lnd --network=signet pendingchannels
docker exec "$LND_CONTAINER" lncli --lnddir=/home/lnd/.lnd --network=signet listchannels | grep active
```

Signet/mainnet: wait for chain confirmations (no regtest mine shortcut).

### After open

- [ ] `./export-lnd-backup.sh` on **both** hosts
- [ ] `./check-signet-health.sh` both roles HEALTHY
- [ ] Record channel_point offline if useful

---

## Rebalance (move local/remote without closing)

Lightning payments move **local** balance toward the recipient.

| Goal | Action |
|------|--------|
| More AWS **outbound** (local) | Mac pays AWS invoices (Mac needs local first) |
| More Mac **outbound** | AWS pays Mac invoices (usual product path) |
| “Stuck” with all local on one side | Pay invoices the other way until floors feel right |

Lab tooling:

```bash
# Mac create → scp bolt11 → AWS pay (see signet product path)
# or examples/signet_product_path.py create/pay
```

Health floors (optional): set `CHANNEL_MIN_LOCAL_SATS` / `CHANNEL_MIN_REMOTE_SATS` when running `check-signet-health.sh` if you want WARN below a floor (defaults are 0 for signet health).

---

## Close channel (rare — know the risks)

Prefer **cooperative close** when both peers are online:

```bash
# on either node that can initiate
docker exec "$LND_CONTAINER" lncli --lnddir=/home/lnd/.lnd --network=signet \
  closechannel --chan_point <funding_txid:index>
```

| Close type | When | Risk |
|------------|------|------|
| Cooperative | Both online, planned | Lowest; wait for confs |
| Force close | Peer gone / emergency | Delay (CSV), higher fees, worse UX |

**Force close** can lock funds for a time window and costs more on-chain. Do not force-close for “cleanup” on mainnet without a plan.

After any close: export SCB again; update health expectations (zero channels until re-open).

**Splice** (resize channel): not required for pilot; treat as out of scope unless you deliberately learn it on signet later.

---

## Mainnet pilot differences (Phase 8 ops complete — limits still apply)

| Topic | Pilot rule |
|-------|------------|
| Channel size | ≤ **50,000** sats (first channel **43,000** private) |
| Funding | New mainnet wallet/volumes; never reuse signet seed; budget ≤ **50,000** sats total |
| Autoloop | **Off** |
| Public peers | Not required; dual-node only (private channel) |
| Rebalance | Same payment technique; human-attended; respect Phase 2 limits + autopay flag |
| Liquidity “enough” | Enough outbound on the **payer** (AWS funded first pilot) |
| Result | N=5 pays @ 2k sats — [mainnet-pilot.md](./mainnet-pilot.md) |

---

## Deferred (not Phase 5)

- Autoloop / Loop Out on signet or mainnet
- Lightning Pool, Faraday “productivity” controller
- Multi-channel routing node
- LSP-managed inbound (topology C)

See [liquidity-automation.md](./liquidity-automation.md) Phase 3 for future direction only.

---

## Phase 5 exit checklist

- [x] Topology B capital flow documented
- [x] Open / rebalance / close SOP written
- [x] Pilot channel max + no Autoloop rule restated
- [x] Signet practice already completed (50k channel, payments, health green)
- [ ] Operator re-reads this before any mainnet channel open

---

## Quick reference — current lab state (example)

When healthy after product-path pays:

| Host | local | remote |
|------|-------|--------|
| AWS | ~42.5k | ~4k |
| Mac | ~4k | ~42.5k |

AWS remains the natural **payer** for Mac invoices until you reverse-pay enough to flip liquidity.
