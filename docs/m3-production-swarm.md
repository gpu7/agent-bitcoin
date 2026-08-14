# M3 — Production swarm (relays, NIP-46, NIP-17, NWC, multi-agent)

**Status:** **v1 implemented** (2026-08-12) — primitives + offline tests; mainnet NWC `--pay` and always-on autopay remain **operator-gated**.
**Date:** 2026-08-12
**Related:** [nostr-agent-identity.md](./nostr-agent-identity.md) · [nwc-automatic-wallets.md](./nwc-automatic-wallets.md) · [mainnet-pilot.md](./mainnet-pilot.md)

---

## What M3 is

From the Nostr mainnet target table:

| Ingredient | v1 in this repo |
|------------|-----------------|
| NIP-47 NWC client + service + decision→pay | Already N1–N5 |
| Mainnet NWC invoice smoke | N6 PASS, then closed |
| Mainnet NWC `--pay` | **Not auto-run**; Dual/manual path documented; 2k cap |
| Public Nostr relays for wallet / swarm traffic | `WebsocketNWCRelay`; dual-host `get_info`/`get_balance` PASS |
| NIP-46 remote signer (bunker-style) | `agent_bitcoin.nostr.nip46` (kind 24133 JSON-RPC; NIP-04 lab crypto) |
| NIP-17 private DMs | `agent_bitcoin.nostr.nip17` gift-wrap structure (lab crypto) |
| Multi-agent discovery / registry | `agent_bitcoin.nostr.swarm` |
| Autonomous mainnet autopay always-on | **Still off** (latches; no auto enable) |

M3 v1 is **production-shaped primitives**, not “flip Autoloop / unattended mainnet pays.”

---

## Step-by-step (how we implement M3)

### Step 1 — Freeze the table (this doc)

Scope: remaining M3 rows. Non-goals: Autoloop, unbounded mainnet, replacing FastAPI auth.

### Step 2 — Relay transport

NWC (and later NIP-46) can leave the in-memory bus:

```text
NWCClient / Nip46Client  →  WebsocketNWCRelay (pynostr RelayManager)
                                      ↓
                              wss://… public or private relay
                                      ↓
                         NWCService / Nip46Bunker
```

Lab default remains `InMemoryNWCBus`. Relays are optional and network-dependent.

### Step 3 — NIP-46 bunker

| Method | v1 |
|--------|-----|
| `connect` / `ping` / `describe` | Yes |
| `get_public_key` | Yes |
| `sign_event` | Yes (policy: allowed kinds) |
| `nip04_encrypt` / `decrypt` | Optional later |
| Full remote bunker over public relays | Same event kinds; encryption is NIP-04 until NIP-44 lands in-tree |

Phase C Unix socket remains valid for localhost; NIP-46 is the interoperable RPC shape.

### Step 4 — NIP-17 DMs

Gift-wrap **structure** (rumor → seal kind 13 → wrap kind 1059).
v1 uses NIP-04 for payload crypto (documented lab limitation). Prefer NIP-44 before high-value mainnet DMs.

### Step 5 — Swarm registry

Local registry of agents (name, npub, role, relays). Kind-0 profile payload helper + kind-1 coordination note. No global directory service.

### Step 6 — Dual-host NWC pay (small sats)

- **Do not** enable always-on autopay.
- Invoice on AWS via NWC (already proven).
- Pay from **Mac** with `lncli sendpayment` (2k) **or** same-process `--pay` only with a new go.
- Operator interjects for unlock / confirm amount.

### Step 7 — Close-out

Document what shipped vs still gated. Latches stay off after any mainnet session.

---

## Commands

```bash
uv sync --python 3.12 --extra nostr --group dev
uv run --python 3.12 pytest tests/test_nwc_*.py tests/test_nostr_*.py -q

# NIP-46 bunker + client (in-memory)
uv run --python 3.12 python examples/nip46_bunker_demo.py

# Swarm registry (local)
uv run --python 3.12 python examples/swarm_registry_demo.py

# Optional: NWC over a real relay (network-dependent)
# uv run --python 3.12 python examples/nwc_relay_loopback.py --relay wss://relay.damus.io

# Mainnet Dual pay of an AWS invoice (Mac, 2000 sats) — operator only:
# docker exec agent-bitcoin-lnd-mainnet lncli --lnddir=/home/lnd/.lnd --network=mainnet \
#   sendpayment --pay_req='lnbc…' --fee_limit 50 --json --force
```

---

## Success criteria (M3 v1)

- [x] This design accepted
- [x] WebSocket relay adapter for NWC (optional network)
- [x] NIP-46 bunker methods + offline tests
- [x] NIP-17 wrap/unwrap helpers + offline tests
- [x] Swarm registry + demos
- [x] Mainnet `--pay` **not** auto-executed; Dual pay runbook only
- [x] Autopay / Autoloop remain off

---

*M3 v1 closes the “have we implemented M3?” table with primitives. Full production swarm (NIP-44, public-relay reliability, unattended pays) is a later go.*
