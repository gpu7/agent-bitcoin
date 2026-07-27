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

**Regtest caveat:** Your host runs Lightning Labs’ **local** Loop regtest stack (`~/loop/regtest`). Autoloop talks to **whatever LND `loopd` is configured against**. For Autoloop to manage **agent-payment-decision-lnd** channels, `loopd` must use that node’s RPC/macaroon—not only the demo `lndserver` / `lndclient` nodes, unless those are the nodes you care about.

Confirm connectivity before enabling automation:

```bash
# On AWS — adjust if your loop CLI target differs
loop --network=regtest getinfo
# or: docker exec loopclient loop --network=regtest getinfo
```

If `getinfo` does not reflect `agent-payment-decision-lnd` identity, wire loopd to that LND first (macaroon + RPC), then continue.

**Parameters are not persisted** across `loopd` restart. Re-apply with `./configure-autoloop-regtest.sh` after Loop restarts (or after `startup-aws.sh`).

---

## Prerequisites

1. AWS stack up; LND unlocked; channels active (`./check-aws-health.sh`).
2. Loop regtest stack running (`loopclient` / loopd as in `startup-aws.sh`).
3. Phase 1 floors understood (`CHANNEL_MIN_*` in health script).
4. Operator understands Autoloop will spend **budget** on fees (not principal swap amount).

---

## Recommended receive-heavy defaults (regtest lab)

These are **starting points**, not mainnet advice. Tune with `suggestswaps` before enabling.

| Parameter | Suggested lab value | Purpose |
|-----------|---------------------|---------|
| Autoloop | **off** until dry-run looks right | Safety |
| Type | `out` (default) | Restore inbound |
| Easy Autoloop | optional | Loop Out when **total local** &gt; `localbalancesat` |
| `localbalancesat` (Easy) | e.g. `500000` | Cap aggregate outbound before Loop Out |
| Incoming threshold (rules) | e.g. `40` (% capacity) | Min inbound share |
| Outgoing threshold | e.g. `10` or `0` | Reserve some outbound |
| `autobudget` | e.g. `50000` sats | Max **fees** per budget period |
| `autobudgetrefreshperiod` | e.g. `86400s` (1 day) | Budget refresh |
| `autoinflight` | `1` | One automated swap at a time |
| `sweepconf` | high (e.g. `100`–`250`) | Cheap sweeps when possible |
| `minamt` / `maxamt` | within `loop terms` | Swap size bounds |

Easy Autoloop (simple): when **total local channel balance** exceeds `localbalancesat`, dispatch **Loop Out**. Good first experiment for receive-heavy.

Rule-based (more control):

```bash
loop setrule <chan_id_or_peer> --incoming_threshold=40 --outgoing_threshold=10
```

---

## Script: `configure-autoloop-regtest.sh`

From `~/agent-bitcoin` on AWS (after `git pull`):

```bash
# Dry-run: print commands + suggestswaps (does not enable Autoloop)
./configure-autoloop-regtest.sh

# Apply budget/type/easy params but keep Autoloop DISABLED
./configure-autoloop-regtest.sh --apply

# Apply and enable Autoloop (explicit)
./configure-autoloop-regtest.sh --apply --enable

# Show status only
./configure-autoloop-regtest.sh --status
```

Environment overrides (examples):

```bash
LOOP_CLI="docker exec -i loopclient loop"
AUTOLOOP_LOCAL_BALANCE_SAT=500000
AUTOLOOP_BUDGET_SATS=50000
AUTOLOOP_BUDGET_REFRESH=86400s
./configure-autoloop-regtest.sh --apply
```

Always review:

```bash
loop --network=regtest getparams    # if available
loop --network=regtest suggestswaps
loop --network=regtest listswaps
```

Disable quickly:

```bash
loop --network=regtest setparams --autoloop=false
# or: ./configure-autoloop-regtest.sh --apply --disable
```

---

## Operational workflow

1. **Monitor** with `./check-aws-health.sh` (Phase 1 floors).
2. **Dry-run** Autoloop: `./configure-autoloop-regtest.sh` + `suggestswaps`.
3. If suggestions look sane on regtest, `--apply` (still disabled).
4. Re-check `suggestswaps`.
5. Only then `--apply --enable` on regtest.
6. After every Loop/LND restart, re-run `--apply` (and `--enable` if desired).
7. Watch `listswaps` and fee spend vs budget.

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
