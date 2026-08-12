# ADR: Automatic wallets via Nostr Wallet Connect (NIP-47)

**Status:** N0–N5 **done**. **N6 mainnet invoice smoke PASS** (2026-08-12, AWS) — tight budget max **2k**; latches unset after session. **Closed:** no further mainnet NWC pays unless a new go. Autoloop still off.
**Date:** 2026-08-12
**Audience:** Operators and implementers.
**Related:** [nostr-agent-identity.md](./nostr-agent-identity.md) · [mainnet-pilot.md](./mainnet-pilot.md) · [lnd-client.md](./lnd-client.md) · [SECURITY.md](../SECURITY.md) · [NIP-47](https://nips.nostr.com/47)

---

## Summary

**Nostr Wallet Connect (NWC / NIP-47)** lets agents control a **limited** Lightning wallet over Nostr relays using a connection URI, without holding LND admin macaroons.

This document is the design for agent-bitcoin **automatic wallets**. Phases **N2–N5** are implemented; **N6** allows **session-scoped mainnet** under explicit latches and a tight pay ceiling.

---

## Problem

Today agents either:

1. Call `LNDClient` / `lncli` with broad node access, or
2. Coordinate payments via Phase B file bus while a host process still has full LND.

Neither is ideal for multi-agent swarms:

- Admin macaroons in agent processes are high blast-radius.
- Phase B proves coordination + settlement on dual LND, but settlement is still “whoever runs lncli.”

**Goal:** agents hold only an **NWC connection secret** with **method + amount budgets**. A separate **wallet service** next to LND enforces policy and executes Lightning ops.

---

## Goals / non-goals

### Goals (v1)

- NIP-47-compatible **client** and **service** in-repo (minimal method set).
- Agents never need LND admin macaroons for invoice/pay/balance.
- Reuse project kill switches: min/max payment, optional daily ledger, network latches.
- `PaymentDecisionAgent` remains **recommend-only**; NWC client executes only after an explicit product path allows it.
- Regtest end-to-end: `make_invoice` + `pay_invoice` ≥ `MIN_PAYMENT_SATS` (2,000).

### Non-goals (v1 / N6)

- Mainnet NWC **without** multi-latch env + operator acknowledgement.
- Autoloop / channel open-close / on-chain send via NWC.
- Unlimited or high mainnet NWC budgets (default max remains **2k sats**).
- Replacing FastAPI `AGENT_BITCOIN_API_KEY` backend auth.
- Full Alby Hub feature parity or every NIP-47 extension.
- Full NIP-46 bunker (orthogonal; Phase C Unix signer remains the local identity path).
- Merging payment **execution** into `PaymentDecisionAgent`.

---

## Theory of operation (NIP-47)

1. Operator runs an **NWC wallet service** that can talk to LND and holds a **wallet Nostr keypair**.
2. Operator issues a **connection URI** to an agent:
   ```text
   nostr+walletconnect://<wallet-pubkey>?relay=<url>&secret=<client-secret>&lud16=...
   ```
3. Agent (client) encrypts **requests** to the wallet pubkey and publishes them on configured relays (NIP-47 event kinds).
4. Wallet service decrypts, **authorizes** (allowlist + budgets), calls LND, encrypts **response** back to the client.
5. Client never sees macaroons; compromise of the URI is still serious but **scope-limited** by service policy.

Exact event kinds, encryption, and method JSON follow [NIP-47](https://nips.nostr.com/47). Implementations must track the live NIP; this ADR freezes **product policy**, not a fork of the wire format.

---

## Architecture (agent-bitcoin)

```text
  PaymentDecisionAgent          Agent runtime (NWC URI only)
           |                              |
           | PAY / REJECT                 | NWC client
           v                              v
                    Nostr relays (or lab local mock bus)
                                      |
                                      v
                    NWC wallet service (operator)
                         |  budgets + allowlist
                         v
                    LNDClient (docker default / grpc optional)
                         |
              agent-payment-decision-lnd  (regtest → later mainnet)
```

| Component | Host (typical) | Secrets |
|-----------|----------------|---------|
| NWC service | Same host as agent LND (AWS in prod topology) | Wallet nsec, LND access, connection secrets |
| NWC client | Agent process (Mac or AWS app) | Connection URI secret only |
| LND | Existing compose containers | Macaroons/certs **not** in agent |

**Phase B file bus** remains valid for **coordination** experiments. **Settlement** for automatic agents should migrate to NWC so agents do not need docker/lncli.

---

## Method allowlist (v1)

| Method | In v1? | Notes |
|--------|--------|-------|
| `get_info` | Yes | Node alias / network sanity |
| `get_balance` | Yes | Map from LND channel/wallet balance as appropriate |
| `make_invoice` | Yes | Enforce min/max amount |
| `pay_invoice` | Yes | Enforce min/max + daily ledger; fee limits |
| `lookup_invoice` | Optional later | |
| `list_transactions` | Optional later | |
| `multi_pay_invoice` / keysend | **No** | Deny |
| On-chain send / openchannel / close | **No** | Operator-only outside NWC |

Unknown methods → structured error (NIP-47 error codes where applicable).

---

## Budgets and kill switches

Map NWC service enforcement to existing project controls:

| Control | Env / mechanism | NWC use |
|---------|-----------------|--------|
| Enable service | `AGENT_BITCOIN_NWC_ENABLE=1` | Default **off** |
| Mainnet NWC go | `AGENT_BITCOIN_NWC_ALLOW_MAINNET=1` | Default **off** (N6) |
| LND mainnet | `AGENT_BITCOIN_ALLOW_MAINNET=1` | Required for `LNDClient` on mainnet |
| Network | `LND_NETWORK` | `mainnet` only for N6 smoke |
| Min amount | `MIN_PAYMENT_SATS` / `NWC_MIN_PAYMENT_SATS` | default 2,000 |
| Max single pay | `NWC_MAX_PAYMENT_SATS` or mainnet default **2,000** | Lab uses `MAX_PAYMENT_SATS` |
| Transport | `LND_TRANSPORT=docker` default | Avoid stale gRPC port misconfig (see M2 lesson) |

**Mainnet (N6):** all three of `NWC_ENABLE`, `NWC_ALLOW_MAINNET`, and `ALLOW_MAINNET` must be `1`. Budget defaults to **max 2,000 sats**.

---

## Threat model (short)

| Threat | Mitigation |
|--------|------------|
| Stolen NWC URI | Short-lived connections, low max pay, rotate secret, method allowlist |
| Prompt injection → “please pay” | Decision agent does not execute; service ignores free-form LLM text |
| Relay eavesdrop / MITM | NIP-47 encryption; prefer trusted/private relays for high value |
| Service compromise | Same as LND host compromise — protect host, SCB, minimal OS surface |
| Overspend loops | Daily ledger, rate limits, enable kill switch |

---

## Implementation phases

| Phase | Deliverable | Network |
|-------|-------------|---------|
| **N0** | Policy go: design + regtest only | — |
| **N1** | This design doc + cross-links | — |
| **N2** | `agent_bitcoin/nwc/` skeleton: URI parse, allowlist, types; unit tests | Offline |
| **N3** | NWC **client** (request/response; mock relay tests) | Offline / mock |
| **N4** | NWC **service** → `LNDClient`; regtest e2e invoice+pay | **regtest** |
| **N5** | Example + docs: decision → NWC pay path; SDK.md note | **Done** (mock/regtest) |
| **N6** | Mainnet tight-budget go + latches | **Go 2026-08-12** (max 2k; multi-latch) |

### Suggested module layout

```text
agent_bitcoin/nwc/
  __init__.py      # public parse helpers (stable, small)
  uri.py           # nostr+walletconnect:// parse/serialize
  policy.py        # method allowlist + budget checks
  client.py        # N3
  service.py       # N4
  errors.py
examples/nwc_regtest_smoke.py
tests/test_nwc_uri.py
tests/test_nwc_policy.py
```

Do **not** export NWC pay as the default `AgentBitcoinClient` path until N5 is deliberate and documented.

---

## Relation to prior Nostr work

| Prior work | Role after NWC |
|------------|----------------|
| Phase A keys | Agent identity still useful for discovery/reputation |
| Phase B bus pay | Lab dual-LND coordination; not the long-term agent settlement API |
| Phase C policy signer | Identity signing (nsec); **orthogonal** to Lightning NWC |
| Mainnet M2 Dual | Proved human-attended Nostr+LND; does **not** authorize mainnet NWC |

---

## Operator checklist (regtest — N4)

1. Regtest LND unlocked; channel active if using `--pay` live.
2. ```bash
   export AGENT_BITCOIN_NWC_ENABLE=1
   export LND_NETWORK=regtest
   export LND_TRANSPORT=docker
   export LND_CONTAINER=agent-payment-decision-lnd
   uv run --python 3.12 python examples/nwc_regtest_smoke.py --amount 2000
   # or offline:
   uv run --python 3.12 python examples/nwc_regtest_smoke.py --mock --pay
   ```
3. Never commit issued NWC URIs or secrets.
4. Disable when done: `AGENT_BITCOIN_NWC_ENABLE=0`.

---

## Success criteria (v1)

- [x] Design ADR accepted (this document)
- [x] URI parse + policy unit tests (`tests/test_nwc_uri.py`, `tests/test_nwc_policy.py`)
- [x] NWC client + mock wallet offline tests (`tests/test_nwc_client.py`)
- [x] NWC service + FakeLND offline tests (`tests/test_nwc_service.py`)
- [ ] Live regtest Docker: client+service invoice+pay (operator smoke)
- [x] Agent path holds no LND admin macaroon (client only has NWC URI)
- [x] PaymentDecisionAgent still non-executing
- [x] Mainnet NWC off by default (`AGENT_BITCOIN_NWC_ENABLE`)
- [x] SDK.md + `examples/nwc_decision_pay.py` + `nwc_pay_if_approved` (N5)
- [x] N6 mainnet multi-latch + tight 2k default budget + `nwc_mainnet_smoke.py`
- [x] N6 live invoice smoke on AWS (2026-08-12) — session closed; no `--pay`

### N2 scaffold (landed)

```text
agent_bitcoin/nwc/
  __init__.py
  uri.py       # parse_nwc_uri / build_nwc_uri
  policy.py    # V1 allowlist, budgets, AGENT_BITCOIN_NWC_ENABLE
  errors.py
```

```bash
uv run pytest tests/test_nwc_uri.py tests/test_nwc_policy.py -q
```

### N3 client (landed)

```text
agent_bitcoin/nwc/
  crypto.py    # NIP-04 encrypt/decrypt (pynostr)
  bus.py       # InMemoryNWCBus (lab mock relay)
  client.py    # NWCClient + attach_mock_wallet
```

```bash
uv run pytest tests/test_nwc_uri.py tests/test_nwc_policy.py tests/test_nwc_client.py -q
```

Encryption note: v1 uses **NIP-04** via pynostr (NIP-47 allows legacy; NIP-44 preferred long-term).

### N4 service (landed)

```text
agent_bitcoin/nwc/service.py   # NWCService + create_nwc_service
examples/nwc_regtest_smoke.py  # --mock offline; live LND optional
```

```bash
export AGENT_BITCOIN_NWC_ENABLE=1
uv run --python 3.12 pytest tests/test_nwc_service.py -q
uv run --python 3.12 python examples/nwc_regtest_smoke.py --mock --pay
# Live LND (regtest, wallet unlocked):
# export LND_NETWORK=regtest LND_TRANSPORT=docker LND_CONTAINER=agent-payment-decision-lnd
# uv run --python 3.12 python examples/nwc_regtest_smoke.py --amount 2000
```

Service enforces: method allowlist, min/max sats, authorized client pubkeys from
`issue_connection()`, `AGENT_BITCOIN_NWC_ENABLE`, and on mainnet
`assert_nwc_network_allowed()` (NWC_ALLOW_MAINNET + ALLOW_MAINNET).

### N5 product path (landed)

```text
agent_bitcoin/nwc/flow.py          # decision_is_pay, nwc_pay_if_approved, rule_based_decision
examples/nwc_decision_pay.py       # decide → invoice → NWC pay (agent has no macaroon)
tests/test_nwc_flow.py
```

```bash
export AGENT_BITCOIN_NWC_ENABLE=1
uv run --python 3.12 python examples/nwc_decision_pay.py --mock
uv run --python 3.12 pytest tests/test_nwc_flow.py -q
```

Flow: **PaymentDecisionAgent / rule_based_decision** returns PAY|REJECT → only on PAY does
`nwc_pay_if_approved` call `NWCClient.pay_invoice`.

### N6 mainnet tight budget (landed)

**Policy go (2026-08-12):** mainnet NWC allowed for **human-attended smoke** only.

| Limit | Value |
|-------|--------|
| Max single pay | **2,000 sats** (`DEFAULT_NWC_MAINNET_MAX_SATS`; override `NWC_MAX_PAYMENT_SATS`) |
| Min pay | **2,000 sats** (project min) |
| Recommended N | **1** successful path per session |
| Autoloop | **Off** |
| Transport | in-memory bus + docker LND (same process smoke) |

```bash
export LND_NETWORK=mainnet
export AGENT_BITCOIN_ALLOW_MAINNET=1
export AGENT_BITCOIN_NWC_ENABLE=1
export AGENT_BITCOIN_NWC_ALLOW_MAINNET=1
export LND_TRANSPORT=docker
export LND_CONTAINER=agent-payment-decision-lnd-mainnet   # or Mac payer container
# optional: export NWC_MAX_PAYMENT_SATS=2000

uv run --python 3.12 python examples/nwc_mainnet_smoke.py --yes-mainnet --amount 2000
# settle only when ready:
# uv run --python 3.12 python examples/nwc_mainnet_smoke.py --yes-mainnet --amount 2000 --pay

# Hard stop
unset AGENT_BITCOIN_NWC_ALLOW_MAINNET AGENT_BITCOIN_NWC_ENABLE AGENT_BITCOIN_ALLOW_MAINNET
```

**Prereqs:** unlocked mainnet LND; for `--pay`, sufficient **local** channel balance (e.g. Mac dual private channel after M2). Invoice-only exercises receive path on the service node.

### N6 exercise log (operator)

| Field | Value |
|-------|--------|
| Date | **2026-08-12** |
| Host | **AWS** (`agent-payment-decision-lnd-mainnet`) |
| Path | Invoice-only (`nwc_mainnet_smoke.py --yes-mainnet --amount 2000`) |
| Result | **PASS** — get_info / get_balance / make_invoice |
| Amount | **2000** sats |
| Payment hash | `7afc7a2b0c0098a61aaa64ed4b7d433424faa3996ccca70db4bafdb7f47c28e6` |
| `--pay` | **Not run** (session closed at invoice smoke) |
| Hard stop | Latches **unset** after run |
| Next | **Hold** — new go required for NWC `--pay` or higher budget |

---

## Decision record

| Decision | Choice |
|----------|--------|
| Protocol | NIP-47 NWC |
| v1 scope | Design + regtest code path |
| Mainnet | Frozen until post-regtest go |
| In-repo vs only external Hub | **In-repo** minimal service for policy control; interop with external wallets optional later |
| Decision agent | Recommend only |
| Default enable | **Off** (`AGENT_BITCOIN_NWC_ENABLE`) |

---

*N0/N1 complete when this file is on `main`. Proceed to N2 scaffold without mainnet funds movement.*
