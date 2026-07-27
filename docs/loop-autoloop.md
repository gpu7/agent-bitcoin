# Loop Autoloop (Phase 2) — operator guide

**Audience:** Operators of the AWS regtest stack.
**Agents / SDK:** do **not** call Loop or open/close channels. Payment agents stay on invoice/pay/decide only.

**Related:** [backend.md](./backend.md) (health checks, channel floors), [SECURITY.md](../SECURITY.md).

---

## Goals (receive-heavy `agent-payment-decision-lnd`)

| Prefer | Avoid |
|--------|--------|
| Keep good channels open | Close/reopen to “fix” liquidity |
| Restore **inbound** (`remote_balance`) when depleted | Agents owning rebalance/close |
| Explicit fee budget + swap size caps | Unlimited Autoloop |

**Loop Out** pushes sats off-chain to the Loop service and returns them on-chain → typically **reduces local / increases inbound**. That matches a **receive-heavy** node after many incoming payments.

Autoloop defaults to **Loop Out** (`--type=out`). It can automate **either** Loop Out **or** Loop In, **not both at once**.

---

## What Phase 2 is (and is not)

| In scope | Out of scope (Phase 3 / later) |
|----------|--------------------------------|
| Document Autoloop on AWS | Faraday productivity reports |
| `suggestswaps` dry-run | Lightning Pool |
| Safe default params (budget, sizes) | Mainnet Autoloop |
| Optional enable with explicit flag | SDK APIs for Loop |
| Health: loopd container optional check | Full multi-objective controller |

**Regtest caveat:** Your host runs Lightning Labs’ **local** Loop regtest stack (`~/loop/regtest`). Stock **`loopclient`** is wired to demo **`lndclient`**, not to **`agent-payment-decision-lnd`**. For Autoloop on agent channels, run the **agent-loopd sidecar** (Phase 2C below).

| Container | LND target | Use for |
|-----------|------------|---------|
| `loopclient` | `lndclient` (demo) | Loop stack smoke tests only |
| **`agent-loopd`** | **`agent-payment-decision-lnd`** | **Real Phase 2 Autoloop** |

Confirm you are on the agent path before enabling automation:

```bash
./wire-agent-loopd.sh --status
export LOOP_CLI='docker exec -i agent-loopd loop'
# agent LND pubkey (must be the node you manage):
docker exec agent-payment-decision-lnd \
  lncli --lnddir=/home/lnd/.lnd --network=regtest getinfo | grep identity_pubkey
```

**Parameters are not always persisted** across `loopd` restart. Re-apply with `./configure-autoloop-regtest.sh` after Loop restarts (or after `startup-aws.sh` / `wire-agent-loopd.sh --recreate`).

---

## Prerequisites

1. AWS stack up; LND unlocked; channels active (`./check-aws-health.sh`).
2. Loop regtest stack healthy: **`loopserver` Up**, **`aperture` Up**, `loop terms` works (not 502).
3. Phase 1 floors understood (`CHANNEL_MIN_*` in health script).
4. Operator understands Autoloop will spend **budget** on fees (not principal swap amount).

### Loop server recovery notes (regtest)

If `loopserver` crash-loops:

- **Timezone migration:** use `~/loop/regtest/docker-compose.override.yml` with `TZ` / `PGTZ` / `PGOPTIONS` set so Postgres session timezone is exactly **`Etc/UTC`** (not bare `UTC`). Recreate `loopserver` (and its anonymous Postgres volume if needed).
- **Missing LND TLS/macaroons:** after recreate, copy from `lndserver` into `loopserver:/home/loopserver/` (see Lightning Labs `regtest.sh` `copy_loopserver_files`), then restart `loopserver`.
- **`synced_to_chain: false` at tip:** mine a few blocks (`generatetoaddress`); both demo and agent LND often flip together.

---

## Phase 2C: wire loopd to `agent-payment-decision-lnd`

Stock `loopclient` must **not** be repointed for day-to-day agent ops (it is the Loop demo client). Use a **sidecar**:

```bash
cd ~/agent-bitcoin
git pull   # need wire-agent-loopd.sh

# Requires: agent LND up; aperture + loopserver Up; volume agent-bitcoin_lnd-data
./wire-agent-loopd.sh
# or: ./wire-agent-loopd.sh --recreate

export LOOP_CLI='docker exec -i agent-loopd loop'
$LOOP_CLI --network=regtest getinfo
$LOOP_CLI --network=regtest terms

# Autoloop params still OFF
./configure-autoloop-regtest.sh --apply
./configure-autoloop-regtest.sh --status

# Only when balances / policy look right:
# ./configure-autoloop-regtest.sh --apply --enable
```

What `wire-agent-loopd.sh` does:

- Runs container **`agent-loopd`** on Docker network **`regtest_regtest`** (same as agent LND and Loop).
- Mounts **`agent-bitcoin_lnd-data`** read-only at `/lnd` (admin macaroon + TLS).
- Points `--lnd.host=agent-payment-decision-lnd:10009`.
- Points `--server.host=aperture:11018` and seeds aperture TLS from `loopclient`.
- Leaves **`loopclient`** unchanged (demo `lndclient`).

### TLS SAN for Docker DNS (`tlsextradomain`)

loopd dials **`agent-payment-decision-lnd:10009`**. LND’s TLS cert must include that name.
`docker-compose.regtest.aws.yml` sets `--tlsextradomain=agent-payment-decision-lnd`.

If you see:

```text
tls: failed to verify certificate: x509: certificate is valid for ..., not agent-payment-decision-lnd
```

regenerate LND TLS only (wallet volume kept):

```bash
export AWS_IP=<your-eip>   # required; empty externalip crashes LND after unlock
docker compose -f docker-compose.regtest.aws.yml stop agent-payment-decision-lnd
docker run --rm -v agent-bitcoin_lnd-data:/data alpine:3.20 \
  rm -f /data/tls.cert /data/tls.key
docker compose -f docker-compose.regtest.aws.yml up -d agent-payment-decision-lnd
# unlock, then:
./wire-agent-loopd.sh --recreate
```

Status / stop:

```bash
./wire-agent-loopd.sh --status
./wire-agent-loopd.sh --stop     # removes container; keeps agent-loopd-data volume
```

Identity check: agent pubkey must be your receive-heavy node (historically `03f3f7…` on this lab), **not** demo `lndclient` (`02bdc3…`).

---

## Recommended receive-heavy defaults (regtest lab)

These are **starting points**, not mainnet advice. Tune with `suggestswaps` before enabling.

| Parameter | Suggested lab value | Purpose |
|-----------|---------------------|---------|
| Autoloop | **off** until dry-run looks right | Safety |
| Type | Loop **Out** (Easy Autoloop) | Restore inbound; rule-based type uses `setrule --type=out` (not `setparams`) |
| Easy Autoloop | recommended first | Loop Out when **total local** &gt; `localbalancesat` |
| `localbalancesat` (Easy) | e.g. `500000` | Cap aggregate outbound before Loop Out |
| Incoming threshold (rules) | e.g. `40` (% capacity) | Min inbound share |
| Outgoing threshold | e.g. `10` or `0` | Reserve some outbound |
| `autobudget` | e.g. `50000` sats | Max **fees** per budget period |
| `autobudgetrefreshperiod` | e.g. `86400s` (1 day) | Budget refresh |
| `autoinflight` | `1` | One automated swap at a time |
| `sweepconf` | high (e.g. `100`–`250`) | Cheap sweeps when possible |
| `minamt` / `maxamt` | within `loop terms` | Swap size bounds |

Easy Autoloop (simple): when **total local channel balance** exceeds `localbalancesat`, dispatch **Loop Out**. Good first experiment for receive-heavy.

Rule-based (more control; **type** goes on `setrule`, not `setparams`):

```bash
loop --network=regtest setrule <chan_id_or_peer> \
  --type=out \
  --incoming_threshold=40 \
  --outgoing_threshold=10
```

---

## Script: `configure-autoloop-regtest.sh`

From `~/agent-bitcoin` on AWS (after `git pull` and `./wire-agent-loopd.sh`):

```bash
export LOOP_CLI='docker exec -i agent-loopd loop'

# Dry-run: print commands + suggestswaps (does not enable Autoloop)
./configure-autoloop-regtest.sh

# Apply Easy Autoloop params but keep Autoloop DISABLED
./configure-autoloop-regtest.sh --apply

# Apply and enable Autoloop (explicit)
./configure-autoloop-regtest.sh --apply --enable

# Show status only
./configure-autoloop-regtest.sh --status
```

If `LOOP_CLI` is unset and `agent-loopd` is running, the script **defaults to agent-loopd**.
Set `REQUIRE_AGENT_LOOPD=1` to refuse a mistaken `loopclient` CLI.

Environment overrides (examples):

```bash
export LOOP_CLI='docker exec -i agent-loopd loop'
AUTOLOOP_LOCAL_BALANCE_SAT=500000
AUTOLOOP_BUDGET_SATS=50000
AUTOLOOP_BUDGET_REFRESH=86400s
./configure-autoloop-regtest.sh --apply
```

Always review:

```bash
$LOOP_CLI --network=regtest getparams
$LOOP_CLI --network=regtest suggestswaps
$LOOP_CLI --network=regtest listswaps
```

Disable quickly:

```bash
$LOOP_CLI --network=regtest setparams --autoloop=false
# or: ./configure-autoloop-regtest.sh --apply --disable
```

---

## Operational workflow

1. **Monitor** with `./check-aws-health.sh` (Phase 1 floors).
2. Ensure Loop **server** path is healthy (`terms` works).
3. **Wire agent loopd:** `./wire-agent-loopd.sh` (once per recreate).
4. **Dry-run / apply** Autoloop with `LOOP_CLI=...agent-loopd...` (still disabled).
5. Re-check `getparams` / channel balances vs `localbalancesat`.
6. Only then `--apply --enable` on regtest.
7. After every `agent-loopd` / Loop restart, re-run wire if needed + `--apply` (and `--enable` if desired).
8. Watch `listswaps` and fee spend vs budget.

---

## Safety rules

- Do **not** enable Autoloop on mainnet from this guide.
- Keep a **hard fee budget**; stop if swaps fail repeatedly (backoff).
- Autoloop will not use channels already in a **manual** swap.
- Prefer health-check WARN on low inbound before enabling automation.
- Agents never call `loop` / `openchannel` / `closechannel`.

---

## Phase 3 (later)

- Faraday channel productivity
- Optional Pool
- Fee payment batching to on-chain fee wallet
- Mainnet-only design (separate hosts, keys, budgets)

## References

- [Autoloop docs](https://docs.lightning.engineering/lightning-network-tools/loop/autoloop)
- [Loop](https://lightning.engineering/loop/)
- [Managing channel liquidity](https://docs.lightning.engineering/lightning-network-tools/lightning-terminal/channel-liquidity)
