# Loop install on regtest, signet, and mainnet

**Audience:** Operators.
**Agents / SDK:** never call Loop or open/close channels.

**Related:** [loop-autoloop.md](./loop-autoloop.md) (regtest Autoloop deep dive) · [liquidity-automation.md](./liquidity-automation.md) · [mainnet-pilot.md](./mainnet-pilot.md)

---

## Policy (2026-08)

| Network | Install `loopd` | Enable Autoloop | Open channels / swaps |
|---------|-----------------|-----------------|------------------------|
| **regtest** | Yes (local Loop server) | Optional, operator flag | Lab only |
| **signet** | Yes if LND up; public Loop may be limited | Prefer off | Lab only |
| **mainnet** | Yes (public Loop servers) | **OFF** until explicit post-pilot go | Dual-node pilot **done** ([mainnet-pilot.md](./mainnet-pilot.md)). **Public routing + Loop** design: [public-routing-loop.md](./public-routing-loop.md). No swaps/Autoloop without P0 checklist. |

Installing Loop **does not** open channels or move funds. Autoloop is separate and must stay **disabled** on mainnet until a written post-pilot decision ([public-routing-loop.md](./public-routing-loop.md)).

---

## Architecture

```text
regtest (AWS):
  agent-payment-decision-lnd  <---loopd--->  local aperture/loopserver

signet / mainnet:
  agent-*-lnd-*  <---loopd--->  Lightning Labs public Loop (default)
```

Script: [`wire-loopd.sh`](../wire-loopd.sh)
Legacy regtest-only helper: [`wire-agent-loopd.sh`](../wire-agent-loopd.sh) (still valid; regtest defaults)

---

## Prerequisites

### All networks

- LND container **running** and **unlocked**
- Matching Docker **network** and **volume** names (script defaults; override with env if compose project names differ)
- LND TLS cert SAN includes the container hostname (`--tlsextradomain` in compose)

### Regtest only

- Lightning Labs Loop regtest stack: **`aperture`** + **`loopserver`** Up
- See [loop-autoloop.md](./loop-autoloop.md)

### Mainnet / signet

- Outbound network from the host (Loop client talks to LL servers)
- **No** requirement for a local `loopserver`

---

## Install commands

### Regtest (AWS — primary lab path)

```bash
cd ~/agent-bitcoin
# regtest LND + Loop stack already up
./wire-loopd.sh regtest
# or: ./wire-agent-loopd.sh

export LOOP_CLI='docker exec -i agent-loopd-regtest loop'
# if using legacy name agent-loopd:
# export LOOP_CLI='docker exec -i agent-loopd loop'

$LOOP_CLI --network=regtest getinfo
$LOOP_CLI --network=regtest terms

# Autoloop params (still OFF until --enable):
./configure-autoloop-regtest.sh --apply
./configure-autoloop-regtest.sh --status
```

### Signet (AWS or Mac)

```bash
# Stack must be up: startup-signet-*.sh, wallets unlocked
./wire-loopd.sh signet              # AWS agent LND
./wire-loopd.sh signet --host mac   # Mac peer LND

export LOOP_CLI='docker exec -i agent-loopd-signet loop'
$LOOP_CLI --network=signet getinfo
$LOOP_CLI --network=signet terms   # may fail if LL has no signet Loop service
```

If `terms` fails on signet, keep the install documented as “client ready” and use **regtest** for full Loop server tests.

### Mainnet (AWS and/or Mac) — install only

Docker Hub image is **`lightninglabs/loop:<version>`** (there is **no** `:latest` tag). Default in `wire-loopd.sh` is **`v0.34.0-beta`**. Override with `LOOPD_IMAGE=...` if needed.

```bash
# Mainnet LND up, unlocked, synced_to_chain preferred
./wire-loopd.sh mainnet              # AWS
./wire-loopd.sh mainnet --host mac   # Mac

# Or pin explicitly:
# LOOPD_IMAGE=lightninglabs/loop:v0.34.0-beta ./wire-loopd.sh mainnet

export LOOP_CLI='docker exec -i agent-loopd-mainnet loop'
$LOOP_CLI --network=mainnet getinfo
$LOOP_CLI --network=mainnet terms
```

**Do not:**

```bash
# DO NOT enable Autoloop on mainnet without explicit post-pilot go
loop ... setparams --autoloop=true
```

Status / recreate / stop:

```bash
./wire-loopd.sh mainnet --status
./wire-loopd.sh mainnet --recreate
./wire-loopd.sh mainnet --stop
```

---

## Volume / network defaults (override if needed)

| Target | LND container | Typical volume | Docker network |
|--------|---------------|----------------|----------------|
| regtest AWS | `agent-payment-decision-lnd` | `agent-bitcoin_lnd-data` | `regtest_regtest` |
| signet AWS | `agent-payment-decision-lnd-signet` | `agent-bitcoin_lnd-signet-data` | `agent-bitcoin-signet` |
| signet Mac | `agent-bitcoin-lnd-signet` | `…lnd-signet-data` | `agent-bitcoin_agent-signet-net` |
| mainnet AWS | `agent-payment-decision-lnd-mainnet` | `agent-bitcoin_lnd-mainnet-data` | `agent-bitcoin-mainnet` |
| mainnet Mac | `agent-bitcoin-lnd-mainnet` | `…lnd-mainnet-data` | `agent-bitcoin_agent-mainnet-net` |

Discover:

```bash
docker ps --format '{{.Names}}'
docker volume ls
docker network ls
```

---

## Success criteria (install phase)

- [x] `loop getinfo` works against the intended LND pubkey (AWS mainnet install)
- [ ] `loop terms` works (regtest/mainnet; signet best-effort)
- [x] Autoloop **disabled** on mainnet (policy)
- [x] BIP-110 observation complete; dual-node channel pilot done — see [mainnet-pilot.md](./mainnet-pilot.md)

---

## BIP-110 note (historical)

Channel open was deferred until after block **961,632** mandatory signaling and split review. That freeze is **lifted for the dual-node pilot** (complete 2026-08-10). **Autoloop / Loop swaps on mainnet remain off** until a separate post-pilot decision. See [mainnet-pilot.md](./mainnet-pilot.md), [public-routing-loop.md](./public-routing-loop.md), and [start9.com/bip110](https://start9.com/bip110/).
